#!/usr/bin/env python3
"""
Business MCP Server - Cognitive Database Analyst for PostgreSQL

This MCP server provides read-only access to a PostgreSQL database,
allowing the AI assistant to analyze database schema and execute SELECT queries safely.

Requires:
  - PostgreSQL database connection
  - Environment variables: DATABASE_URL or DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

import asyncio
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

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
    column names, data types, and null constraints.
    
    Args:
        schema_name: The schema to inspect (default: 'public')
        
    Returns:
        Dict with tables and their column information:
            {
                "schema": str,
                "tables": {
                    "table_name": [
                        {"name": "col_name", "type": "type", "nullable": bool},
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
            
            # Organize results by table
            schema_data: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                table_name = row['table_name']
                if table_name not in schema_data:
                    schema_data[table_name] = []
                
                schema_data[table_name].append({
                    "name": row['column_name'],
                    "type": row['data_type'],
                    "nullable": row['is_nullable'] == 'YES'
                })
            
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
            start_time = datetime.utcnow()
            
            # Execute query with optional parameters
            if params:
                rows = await connection.fetch(query, *params)
            else:
                rows = await connection.fetch(query)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
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


async def cleanup():
    """Close database connection pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def main():
    """Start the Business MCP server."""
    try:
        await mcp.run(
            transport='stdio',
            debug=os.getenv("DEBUG", "false").lower() == "true"
        )
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
