#!/usr/bin/env python3
import asyncio
import os
import sqlite3
import asyncpg
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("Databes and Context MCP")

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

# Global database connection
_db_path = os.getenv("MEMORY_DB_PATH", "./memory.db")
_connection: Optional[sqlite3.Connection] = None


def _get_connection() -> sqlite3.Connection:
    """
    Get or create the SQLite connection.
    
    Returns:
        sqlite3.Connection: Database connection
        
    Raises:
        RuntimeError: If database initialization fails
    """
    global _connection
    
    if _connection is not None:
        return _connection
    
    try:
        _connection = sqlite3.connect(_db_path, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _initialize_database()
        return _connection
    except Exception as e:
        raise RuntimeError(f"Failed to initialize memory database: {str(e)}")


def _initialize_database() -> None:
    """
    Create the context memory table if it doesn't exist.
    
    Table schema:
    - id: Unique identifier (auto-incremented)
    - topic: Category or topic for the stored context
    - content: The actual content/fact to remember
    - created_at: Timestamp when the context was created
    - expires_at: Timestamp when the context expires (TTL)
    
    Raises:
        RuntimeError: If table creation fails
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                UNIQUE(topic, content)
            )
        """)
        
        # Create index on topic for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_topic ON context(topic)
        """)
        
        # Create index on expires_at for cleanup operations
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON context(expires_at)
        """)
        
        conn.commit()
    except Exception as e:
        raise RuntimeError(f"Failed to initialize database schema: {str(e)}")


@mcp.tool()
async def save_context(topic: str, content: str, ttl_hours: int = 24) -> Dict[str, Any]:
    """
    Save a fact or context to memory with TTL.
    
    Stores contextual information that the AI assistant can retrieve later.
    Automatically calculates expiration time based on TTL.
    
    Args:
        topic: Category or topic name (e.g., 'user_preferences', 'db_schema_notes')
        content: The actual content to remember (text or JSON string)
        ttl_hours: Time-to-live in hours (default: 24)
        
    Returns:
        Dict with save confirmation:
            {
                "success": bool,
                "id": int,
                "topic": str,
                "expires_at": str (ISO format),
                "ttl_hours": int
            }
            
    Raises:
        ValueError: If topic or content is empty
        RuntimeError: If database write fails
    """
    if not topic or not content:
        raise ValueError("Topic and content cannot be empty")
    
    if ttl_hours <= 0:
        raise ValueError("TTL must be positive")
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        # Calculate expiration time
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        
        # Insert or ignore (prevents duplicates)
        cursor.execute("""
            INSERT INTO context (topic, content, expires_at)
            VALUES (?, ?, ?)
        """, (topic, content, expires_at.isoformat()))
        
        conn.commit()
        
        return {
            "success": True,
            "id": cursor.lastrowid,
            "topic": topic,
            "expires_at": expires_at.isoformat(),
            "ttl_hours": ttl_hours
        }
    except sqlite3.IntegrityError:
        # Already exists, return the existing record
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, expires_at FROM context 
            WHERE topic = ? AND content = ?
        """, (topic, content))
        row = cursor.fetchone()
        if row:
            return {
                "success": True,
                "id": row['id'],
                "topic": topic,
                "expires_at": row['expires_at'],
                "message": "Context already exists"
            }
    except Exception as e:
        raise RuntimeError(f"Failed to save context: {str(e)}")


@mcp.tool()
async def retrieve_context(topic: str) -> Dict[str, Any]:
    """
    Retrieve all valid (non-expired) contexts for a given topic.
    
    Automatically filters out expired records. Use this to recall
    previous learnings, user preferences, or analysis notes.
    
    Args:
        topic: Topic name to retrieve contexts for
        
    Returns:
        Dict with retrieved contexts:
            {
                "topic": str,
                "count": int,
                "contexts": [
                    {
                        "id": int,
                        "content": str,
                        "created_at": str (ISO format),
                        "expires_at": str (ISO format)
                    },
                    ...
                ],
                "retrieved_at": str (ISO format)
            }
            
    Raises:
        ValueError: If topic is empty
        RuntimeError: If database read fails
    """
    if not topic:
        raise ValueError("Topic cannot be empty")
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        # Retrieve non-expired contexts
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            SELECT id, content, created_at, expires_at
            FROM context
            WHERE topic = ? AND expires_at > ?
            ORDER BY created_at DESC
        """, (topic, now))
        
        rows = cursor.fetchall()
        contexts = [dict(row) for row in rows]
        
        return {
            "topic": topic,
            "count": len(contexts),
            "contexts": contexts,
            "retrieved_at": now
        }
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve context: {str(e)}")


@mcp.tool()
async def cleanup_expired_contexts() -> Dict[str, Any]:
    """
    Remove all expired contexts from the memory database.
    
    Call this periodically to maintain database performance.
    
    Returns:
        Dict with cleanup statistics:
            {
                "success": bool,
                "deleted_count": int,
                "remaining_count": int
            }
            
    Raises:
        RuntimeError: If cleanup fails
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        
        # Delete expired records
        cursor.execute("DELETE FROM context WHERE expires_at <= ?", (now,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        
        # Get remaining count
        cursor.execute("SELECT COUNT(*) as count FROM context")
        remaining_count = cursor.fetchone()['count']
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "remaining_count": remaining_count
        }
    except Exception as e:
        raise RuntimeError(f"Failed to cleanup expired contexts: {str(e)}")


@mcp.tool()
async def list_topics() -> Dict[str, Any]:
    """
    List all topics that have non-expired contexts.
    
    Useful for discovering what the AI assistant has learned.
    
    Returns:
        Dict with topic list:
            {
                "count": int,
                "topics": [
                    {
                        "name": str,
                        "context_count": int
                    },
                    ...
                ]
            }
            
    Raises:
        RuntimeError: If database query fails
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            SELECT topic, COUNT(*) as context_count
            FROM context
            WHERE expires_at > ?
            GROUP BY topic
            ORDER BY context_count DESC
        """, (now,))
        
        rows = cursor.fetchall()
        topics = [dict(row) for row in rows]
        
        return {
            "count": len(topics),
            "topics": topics
        }
    except Exception as e:
        raise RuntimeError(f"Failed to list topics: {str(e)}")

def main():
    """Start the Unified MCP server."""
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
