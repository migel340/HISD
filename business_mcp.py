#!/usr/bin/env python3
"""
Business MCP Server - Cognitive Database Analyst for PostgreSQL

This MCP server provides read-only access to a PostgreSQL database,
allowing the AI assistant to analyze database schema and execute SELECT queries safely.

Requires:
  - PostgreSQL database connection
  - Environment variables: DATABASE_URL or DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import asyncpg
from dotenv import load_dotenv
from fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize MCP server
mcp = FastMCP("Business DB")

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    """
    Get or create the asyncpg connection pool.
    
    Returns:
        asyncpg.Pool: Connection pool to PostgreSQL database
        
    Raises:
        RuntimeError: If connection fails or DATABASE_URL is not configured
    """
    global _pool
    
    if _pool is not None:
        return _pool
    
    # Build connection string
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Build from individual components
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "business_db")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "")
        
        database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    try:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        return _pool
    except Exception as e:
        raise RuntimeError(f"Failed to connect to PostgreSQL: {str(e)}")


@mcp.tool()
async def get_schema(schema_name: str = "public") -> Dict[str, Any]:
    """
    Retrieve the database schema: tables and their columns.
    
    Provides a complete overview of the specified schema, including table names,
    column names, data types, null constraints and foreign key relationships.
    
    Args:
        schema_name: The schema to inspect (default: 'public')
        
    Returns:
        Dict with tables and their column information:
            {
                "schema": str,
                "tables": {
                    "table_name": [
                        {
                        "name": "col_name", 
                        "type": "type", 
                        "nullable": bool, 
                        "foreign_keys": {"table": "other_table", "column": "other_column"} or None
                        },
                        ...
                    ],
                    ...
                }
            }
            
    Raises:
        RuntimeError: If database connection fails
    """
    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            query = """
                SELECT 
                    t.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable
                FROM information_schema.tables t
                JOIN information_schema.columns c 
                    ON t.table_name = c.table_name 
                    AND t.table_schema = c.table_schema
                WHERE t.table_schema = $1
                ORDER BY t.table_name, c.ordinal_position
            """
            rows = await connection.fetch(query, schema_name)
            
            fk_query = """
            SELECT
                kcu.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.table_constraints tc 
                ON kcu.constraint_name = tc.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu 
                ON ccu.constraint_name = tc.constraint_name 
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' 
              AND tc.table_schema = $1
            """
            fk_rows = await connection.fetch(fk_query, schema_name)

            fks_map = {}
            for row in fk_rows:
                fks_map[(row['table_name'], row['column_name'])] = {
                    "table": row['foreign_table'],
                    "column": row['foreign_column']
                }

            # Organize results by table
            schema_data: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                table_name = row['table_name']
                column_name = row['column_name']
                if table_name not in schema_data:
                    schema_data[table_name] = []
                
                column_info = {
                    "name": column_name,
                    "type": row['data_type'],
                    "nullable": row['is_nullable'] == 'YES'}

                if (table_name, column_name) in fks_map:
                    column_info["foreign_keys"] = fks_map[(table_name, column_name)]

                schema_data[table_name].append(column_info)
            
            return {
                "schema": schema_name,
                "tables": schema_data,
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve schema: {str(e)}")

@mcp.tool()
async def execute_query(query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Execute a read-only SELECT query against the database.
    
    Enforces strict security constraints:
    - Only SELECT statements are allowed
    - Prevents DROP, UPDATE, DELETE, INSERT, ALTER operations
    
    Args:
        query: SQL SELECT query to execute
        params: Optional parameters for parameterized queries (passed as list)
        
    Returns:
        Dict containing query results:
            {
                "rows": [dict, ...],
                "row_count": int,
                "columns": [str, ...],
                "execution_time": float
            }
            
    Raises:
        ValueError: If query is not a safe SELECT statement
        RuntimeError: If database execution fails
    """
    # Validate query safety
    query_upper = query.strip().upper()
    
    if not query_upper.startswith('SELECT'):
        raise ValueError("Only SELECT queries are allowed")
    
    forbidden_keywords = ['DROP', 'UPDATE', 'DELETE', 'INSERT', 'ALTER', 'TRUNCATE', 'CREATE']
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            raise ValueError(f"Query cannot contain {keyword} operations")
    
    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            start_time = datetime.now(timezone.utc)
            
            # Execute query with optional parameters
            if params:
                rows = await connection.fetch(query, *params)
            else:
                rows = await connection.fetch(query)
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Convert records to dictionaries
            result_rows = [dict(row) for row in rows]
            
            # Get column names
            columns = list(rows[0].keys()) if rows else []
            
            return {
                "rows": result_rows,
                "row_count": len(result_rows),
                "columns": columns,
                "execution_time": execution_time
            }
    except Exception as e:
        raise RuntimeError(f"Query execution failed: {str(e)}")


@mcp.tool()
async def execute_write(query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Execute a safe write operation (INSERT or UPDATE).

    Security rules:
    - Only INSERT and UPDATE statements are allowed (optionally with RETURNING)
    - Forbids DROP, DELETE, ALTER, TRUNCATE, CREATE
    - Encourages parameterized queries via `params`

    Returns a dict with command results and timing. If the query uses
    `RETURNING`, returned rows are included.
    """
    # Basic safety checks
    query_upper = query.strip().upper()

    if not (query_upper.startswith('INSERT') or query_upper.startswith('UPDATE')):
        raise ValueError("Only INSERT and UPDATE statements are allowed for write operations")

    forbidden_keywords = ['DROP', 'DELETE', 'ALTER', 'TRUNCATE', 'CREATE']
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            raise ValueError(f"Query cannot contain {keyword} operations")

    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            start_time = datetime.now(timezone.utc)

            # If RETURNING is present, fetch returned rows; otherwise execute
            if 'RETURNING' in query_upper:
                if params:
                    rows = await connection.fetch(query, *params)
                else:
                    rows = await connection.fetch(query)

                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                result_rows = [dict(r) for r in rows]

                return {
                    "rows": result_rows,
                    "row_count": len(result_rows),
                    "columns": list(rows[0].keys()) if rows else [],
                    "execution_time": execution_time,
                }
            else:
                # execute returns a command tag like 'INSERT 0 1' or 'UPDATE 3'
                if params:
                    command_tag = await connection.execute(query, *params)
                else:
                    command_tag = await connection.execute(query)

                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                # Try to parse affected row count from command tag
                parts = command_tag.split()
                affected: Optional[int] = None
                if parts and parts[-1].isdigit():
                    affected = int(parts[-1])

                return {
                    "command_tag": command_tag,
                    "row_count": affected if affected is not None else 0,
                    "execution_time": execution_time,
                }
    except Exception as e:
        raise RuntimeError(f"Write query execution failed: {str(e)}")

@mcp.tool()
async def alter_table(query: str) -> Dict[str, Any]:
    """
    Execute a safe ALTER TABLE operation.
    NEVER USE THIS TOOL WITHOUT USER CONFIRMATION.
    Before using this tool the assistant must tell the user exactly what SQL query will be executed
    and explicitly ask the user "Are you sure you want to execute this destructive operation?".
    Only execute if the user replies with a clear "yes" or "confirm". 
    If the user replies with anything else, do not execute and respond with "Operation cancelled by user."
    
    Security rules:
    - Only ALTER TABLE statements are allowed
    - Forbids DROP, DELETE, UPDATE, INSERT, TRUNCATE, CREATE
    - Encourages parameterized queries via `params`

    Returns a dict with command results and timing.
    """
    # Basic safety checks
    query_upper = query.strip().upper()

    if not query_upper.startswith('ALTER TABLE'):
        raise ValueError("Only ALTER TABLE statements are allowed for this operation")

    forbidden_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'CREATE']
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            raise ValueError(f"Query cannot contain {keyword} operations")

    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            start_time = datetime.now(timezone.utc)

            command_tag = await connection.execute(query)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "command_tag": command_tag,
                "execution_time": execution_time,
            }
            
    except Exception as e:
        raise RuntimeError(f"ALTER TABLE execution failed: {str(e)}")

@mcp.tool()
async def add_table(table_name: str, columns: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Create a new table with specified columns.

    Args:
        table_name: Name of the new table
        columns: List of column definitions, each as dict with 'name' and 'type'

    Returns a dict with command results and timing.
    """
    # Basic safety checks
    if not table_name.isidentifier():
        raise ValueError("Invalid table name")

    for col in columns:
        if 'name' not in col or 'type' not in col:
            raise ValueError("Each column definition must have 'name' and 'type'")
        if not col['name'].isidentifier():
            raise ValueError(f"Invalid column name: {col['name']}")

    # Build CREATE TABLE query
    column_defs = ", ".join(f"{col['name']} {col['type']}" for col in columns)
    query = f"CREATE TABLE {table_name} ({column_defs})"

    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            start_time = datetime.now(timezone.utc)

            command_tag = await connection.execute(query)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "command_tag": command_tag,
                "execution_time": execution_time,
            }
            
    except Exception as e:
        raise RuntimeError(f"Table creation failed: {str(e)}")

@mcp.tool()
async def truncate_table(table_name: str) -> Dict[str, Any]:
    """
    Truncate a table, removing all rows but keeping the structure.
    NEVER USE THIS TOOL WITHOUT USER CONFIRMATION.
    Before using this tool the assistant must tell the user exactly what SQL query will be executed
    and explicitly ask the user "Are you sure you want to execute this destructive operation?".
    Only execute if the user replies with a clear "yes" or "confirm". 
    If the user replies with anything else, do not execute and respond with "Operation cancelled by user."
    
    Args:
        table_name: Name of the table to truncate
    Returns a dict with command results and timing.
    """
    # Basic safety checks
    if not table_name.isidentifier():
        raise ValueError("Invalid table name")

    query = f"TRUNCATE TABLE {table_name}"

    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            start_time = datetime.now(timezone.utc)

            command_tag = await connection.execute(query)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "command_tag": command_tag,
                "execution_time": execution_time,
            }
            
    except Exception as e:
        raise RuntimeError(f"Table truncation failed: {str(e)}")

@mcp.tool()
async def execute_destructive(query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Execute a destructive database operation (DELETE or DROP).

    NEVER USE THIS TOOL WITHOUT USER CONFIRMATION.
    Before using this tool the assistant must tell the user exactly what SQL query will be executed
    and explicitly ask the user "Are you sure you want to execute this destructive operation?".
    Only execute if the user replies with a clear "yes" or "confirm". 
    If the user replies with anything else, do not execute and respond with "Operation cancelled by user."
    
    Security rules:
    - Only DELETE and DROP statements are allowed.
    - Prevents CREATE, ALTER, INSERT, UPDATE, TRUNCATE operations.

    Returns a dict with command results and timing. If the query uses
    `RETURNING`, returned rows are included.
    """
    query_upper = query.strip().upper()

    if not (query_upper.startswith('DELETE') or query_upper.startswith('DROP')):
        raise ValueError("Only DELETE and DROP statements are allowed for destructive operations")

    forbidden_keywords = ['INSERT', 'UPDATE', 'ALTER', 'CREATE', 'TRUNCATE']
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            raise ValueError(f"Query cannot contain {keyword} operations")

    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            start_time = datetime.now(timezone.utc)

            # If RETURNING is present, fetch returned rows; otherwise execute
            if 'RETURNING' in query_upper and query_upper.startswith('DELETE'):
                if params:
                    rows = await connection.fetch(query, *params)
                else:
                    rows = await connection.fetch(query)

                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                result_rows = [dict(r) for r in rows]

                return {
                    "warning": "Destructive operation executed",
                    "rows": result_rows,
                    "row_count": len(result_rows),
                    "columns": list(rows[0].keys()) if rows else [],
                    "execution_time": execution_time,
                }
            else:
                # DROP or DELETE without RETURNING
                if params:
                    command_tag = await connection.execute(query, *params)
                else:
                    command_tag = await connection.execute(query)

                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                # Try to parse affected row count from command tag
                parts = command_tag.split()
                affected: Optional[int] = None
                if parts and parts[-1].isdigit():
                    affected = int(parts[-1])

                return {
                    "warning": "Destructive operation executed",
                    "command_tag": command_tag,
                    "row_count": affected if affected is not None else 0,
                    "execution_time": execution_time,
                }
    except Exception as e:
        raise RuntimeError(f"Destructive query execution failed: {str(e)}")

@mcp.tool()
async def get_current_user_privilages() -> Dict[str, Any]:
    """
    Retrieve the database privileges for the current logged-in user.
    The assistant must use this tool at the begining of the session to check what permissions it has.
    """
    try:
        pool = await _get_pool()
        async with pool.acquire() as connection:
            query = """
                SELECT current_user as username, 
                       rolsuper as is_superuser,
                       rolcreatedb as can_create_db
                FROM pg_roles 
                WHERE rolname = current_user
            """
            user_info = await connection.fetchrow(query)
            
            priv_query = """
                SELECT table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = current_user AND table_schema = 'public'
            """
            grants = await connection.fetch(priv_query)

            table_privileges = {}
            for grant in grants:
                t_name = grant['table_name']
                p_type = grant['privilege_type']
                if t_name not in table_privileges:
                    table_privileges[t_name] = []
                table_privileges[t_name].append(p_type)

            return {
                "user_info": dict(user_info) if user_info else {"username": "unknown"},
                "table_privileges": table_privileges,
                "message": "Please present these privileges clearly to the user."
            }
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve user privileges: {str(e)}")

async def cleanup():
    """Close database connection pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def main():
    """Start the Business MCP server."""
    try:
        mcp.run(
            transport='stdio'
        )
    finally:
        import asyncio

        asyncio.run(cleanup())


if __name__ == "__main__":
    main()
