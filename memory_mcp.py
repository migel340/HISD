#!/usr/bin/env python3
"""
Memory MCP Server - Cognitive Context Memory for SQLite

This MCP server manages contextual memory for the AI assistant,
storing facts, insights, and retrieved context with TTL (time-to-live) support.

Requires:
  - SQLite database (local file)
  - Environment variable: MEMORY_DB_PATH (defaults to ./memory.db)
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize MCP server
mcp = FastMCP("Context Memory")

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
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        
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
        raise RuntimeError("Context already exists but could not be retrieved")
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
        now = datetime.now(timezone.utc).isoformat()
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
        
        now = datetime.now(timezone.utc).isoformat()
        
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
        
        now = datetime.now(timezone.utc).isoformat()
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


def cleanup():
    """Close database connection on shutdown."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def main():
    """Start the Memory MCP server."""
    try:
        mcp.run(
            transport='stdio'
        )
    finally:
        cleanup()


if __name__ == "__main__":
    main()
