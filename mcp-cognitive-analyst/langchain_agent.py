#!/usr/bin/env python3
"""
Langchain Agent z Ollamą + MCP Tools
Profesjonalne rozwiązanie z Langchain framework

This agent integrates:
- Ollama LLM (local execution)
- PostgreSQL database access
- Persistent memory with SQLite
- React pattern for reasoning
"""
import os
import sys
import subprocess
import json
import re
from urllib.parse import urlsplit, urlunsplit
import asyncpg
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

# LangChain imports moved across packages in newer releases.
try:
    from langchain_ollama import ChatOllama
except ImportError:  # pragma: no cover - fallback for older installs
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError as exc:  # pragma: no cover - clearer startup error
        raise SystemExit(
            "Missing LangChain Ollama integration. Install dependencies with: pip install -r requirements.txt"
        ) from exc

from langchain.agents import create_agent
from langchain_core.tools import Tool

load_dotenv()


def _resolve_ollama_model() -> str:
    """Pick an installed Ollama model, or fall back to an env override/default."""
    configured_model = os.getenv("OLLAMA_MODEL", "").strip()
    if configured_model:
        return configured_model

    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) > 1:
            installed_models = [line.split()[0] for line in lines[1:] if line.split()]
            if installed_models:
                print(f"✅ Using installed Ollama model: {installed_models[0]}")
                return installed_models[0]
    except Exception:
        pass

    return "llama3.2"


def _extract_tool_call(text: str) -> dict[str, Any] | None:
    """Extract a JSON tool call from <tool_call>...</tool_call> text."""
    match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if not match:
        return None

    try:
        payload = json.loads(match.group(1))
        if isinstance(payload, dict) and payload.get("name"):
            return payload
    except json.JSONDecodeError:
        return None

    return None


def _rewrite_port(database_url: str, port: str) -> str:
    """Rewrite the port in a PostgreSQL URL while keeping everything else intact."""
    parts = urlsplit(database_url)
    if not parts.netloc:
        return database_url

    userinfo, _, hostinfo = parts.netloc.rpartition("@")
    if ":" in hostinfo:
        host, _, _ = hostinfo.partition(":")
    else:
        host = hostinfo

    rebuilt_netloc = f"{userinfo + '@' if userinfo else ''}{host}:{port}"
    return urlunsplit((parts.scheme, rebuilt_netloc, parts.path, parts.query, parts.fragment))


def _resolve_database_url() -> str:
    """Prefer DATABASE_URL, but fall back to DB_* vars and the Compose host port."""
    configured = os.getenv("DATABASE_URL", "").strip()
    fallback_port = os.getenv("DB_PORT", "5433").strip() or "5433"

    candidates: list[str] = []
    if configured:
        candidates.append(configured)

        if ("localhost:5432" in configured or "127.0.0.1:5432" in configured) and fallback_port != "5432":
            candidates.append(_rewrite_port(configured, fallback_port))

    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "business_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    candidates.append(f"postgresql://{db_user}:{db_password}@{db_host}:{fallback_port}/{db_name}")

    for candidate in candidates:
        if candidate:
            return candidate

    return "postgresql://postgres:postgres@localhost:5433/business_db"

# ============================================
# 1. TOOLS - Zdefiniuj dostępne narzędzia
# ============================================

class DatabaseTools:
    """Tools dla bazy danych"""
    
    def __init__(self):
        self.db_url = _resolve_database_url()
    
    def get_database_schema(self, schema_name: str = "public") -> str:
        """
        Get schema information from PostgreSQL database.
        Shows tables and their columns.
        """
        async def _get_schema():
            try:
                conn = await asyncpg.connect(self.db_url)
                tables = await conn.fetch(f"""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = $1
                """, schema_name)
                
                schema_info = f"📊 Schema: {schema_name}\n"
                schema_info += "=" * 50 + "\n"
                
                for table in tables:
                    table_name = table['table_name']
                    columns = await conn.fetch(f"""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = $1 AND table_name = $2
                    """, schema_name, table_name)
                    
                    schema_info += f"\n📋 Table: {table_name}\n"
                    for col in columns:
                        nullable = "✓" if col['is_nullable'] else "✗"
                        schema_info += f"  - {col['column_name']}: {col['data_type']} [{nullable}]\n"
                
                await conn.close()
                return schema_info
                
            except Exception as e:
                return f"❌ Error: {str(e)}"
        
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_get_schema())
        loop.close()
        return result
    
    def execute_database_query(self, query: str) -> str:
        """
        Execute SELECT query on database.
        WARNING: Only SELECT queries are allowed.
        """
        async def _execute():
            try:
                # Security check
                query_upper = query.strip().upper()
                if not query_upper.startswith("SELECT"):
                    return "❌ Only SELECT queries allowed"
                
                if any(cmd in query_upper for cmd in ["DROP", "DELETE", "UPDATE", "INSERT"]):
                    return "❌ Dangerous operation detected"
                
                conn = await asyncpg.connect(self.db_url)
                result = await conn.fetch(query)
                await conn.close()
                
                if not result:
                    return "✓ Query returned 0 rows"
                
                # Format output
                output = f"✓ Query returned {len(result)} rows\n"
                for i, row in enumerate(result[:5]):  # Show first 5
                    output += f"\nRow {i+1}: {dict(row)}"
                
                if len(result) > 5:
                    output += f"\n... and {len(result) - 5} more rows"
                
                return output
                
            except Exception as e:
                return f"❌ Error: {str(e)}"
        
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_execute())
        loop.close()
        return result


class MemoryTools:
    """Tools dla memory database"""
    
    def __init__(self):
        self.db_path = os.getenv("MEMORY_DB_PATH", "./memory.db")
        self._init_db()
    
    def _init_db(self):
        """Inicjalizuj bazę"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contexts (
                id INTEGER PRIMARY KEY,
                topic TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def save_insight(self, topic: str, content: str, ttl_hours: int = 168) -> str:
        """
        Save insight or context to memory database.
        ttl_hours: Time to live in hours (default 7 days = 168 hours)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            expires = datetime.now() + timedelta(hours=ttl_hours)
            
            cur.execute("""
                INSERT INTO contexts (topic, content, expires_at)
                VALUES (?, ?, ?)
            """, (topic, content, expires))
            
            conn.commit()
            conn.close()
            
            return f"✓ Saved '{topic}' to memory (expires in {ttl_hours}h)"
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def recall_insight(self, topic: str) -> str:
        """
        Retrieve saved insights from memory for a specific topic.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            now = datetime.now()
            
            cur.execute("""
                SELECT content, created_at 
                FROM contexts 
                WHERE topic = ? AND expires_at > ?
                ORDER BY created_at DESC
            """, (topic, now))
            
            results = cur.fetchall()
            conn.close()
            
            if not results:
                return f"ℹ️ No active memories for topic: {topic}"
            
            output = f"📚 Memories for '{topic}':\n"
            for i, (content, created) in enumerate(results, 1):
                output += f"\n{i}. [{created}]\n   {content}\n"
            
            return output
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def list_topics(self) -> str:
        """List all active memory topics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            now = datetime.now()
            
            cur.execute("""
                SELECT DISTINCT topic, COUNT(*) as count
                FROM contexts 
                WHERE expires_at > ?
                GROUP BY topic
            """, (now,))
            
            results = cur.fetchall()
            conn.close()
            
            if not results:
                return "ℹ️ No active memory topics"
            
            output = "📖 Active Memory Topics:\n"
            for topic, count in results:
                output += f"  - {topic} ({count} entries)\n"
            
            return output
            
        except Exception as e:
            return f"❌ Error: {str(e)}"


# ============================================
# 2. LANGCHAIN AGENT
# ============================================

def create_ollama_agent():
    """Stwórz agenta z Ollamą i narzędziami"""
    
    # Inicjalizuj narzędzia
    db_tools = DatabaseTools()
    memory_tools = MemoryTools()
    
    # Konwertuj na Langchain Tools
    tools = [
        Tool(
            name="GetDatabaseSchema",
            func=db_tools.get_database_schema,
            description="Get schema of PostgreSQL database. Use only when the user asks about tables, columns, types, or database structure. Do not use this for table rows or record contents."
        ),
        Tool(
            name="ExecuteQuery",
            func=db_tools.execute_database_query,
            description="Execute a read-only SELECT query on PostgreSQL database. Use this when the user asks to show rows, records, data, contents, values, or examples from a table. Only SELECT queries allowed for security."
        ),
        Tool(
            name="SaveMemory",
            func=memory_tools.save_insight,
            description="Save insight or finding to memory database. Useful for remembering analysis results."
        ),
        Tool(
            name="RecallMemory",
            func=memory_tools.recall_insight,
            description="Retrieve previously saved insights from memory for a topic."
        ),
        Tool(
            name="ListMemoryTopics",
            func=memory_tools.list_topics,
            description="List all active memory topics with their entry counts."
        ),
    ]
    
    # Inicjalizuj Ollama LLM
    print("🔌 Connecting to Ollama at http://localhost:11434...")
    model_name = _resolve_ollama_model()
    print(f"🤖 Selected Ollama model: {model_name}")
    llm = ChatOllama(
        model=model_name,
        base_url="http://localhost:11434",
        temperature=0.7
    )

    system_prompt = """You are a helpful local assistant with access to database and memory tools.
Use tools when needed. Prefer concise answers and summarize database results clearly.
When you query the database, only use read-only SELECT statements.
Important routing rule: if the user asks for table rows, records, data, contents, or values from a table, use ExecuteQuery with a SELECT statement such as SELECT * FROM table_name LIMIT 10.
Use GetDatabaseSchema only for metadata like table names, column names, data types, or schema structure.
"""

    # Stwórz agenta w nowym API LangChain 1.x
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )

    return agent, db_tools, memory_tools


# ============================================
# 3. MAIN - Interactive Chat
# ============================================

def main():
    """Main interactive loop"""
    print("\n" + "=" * 70)
    print("🤖 Langchain + Ollama Cognitive Analyst")
    print("=" * 70)
    print("\n📚 Available Capabilities:")
    print("  📊 Query PostgreSQL database")
    print("  💾 Save and recall insights")
    print("  🧠 Intelligent multi-step reasoning")
    print("  🔄 React loop (Thought → Action → Observation)")
    print("\n💡 Example prompts:")
    print("  - 'What tables are in the database?'")
    print("  - 'Show me the top 5 rows from customers table'")
    print("  - 'Remember we have 100 active users'")
    print("  - 'What did you remember about our users?'")
    print("\nType 'quit' or 'exit' to stop\n")
    print("=" * 70 + "\n")
    
    try:
        agent, db_tools, memory_tools = create_ollama_agent()
    except Exception as e:
        print(f"❌ Error initializing agent: {e}")
        print("❌ Make sure Ollama is running: ollama serve")
        return
    
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit", "bye"]:
                print("\n👋 Goodbye! Agent shutting down...")
                break
            
            print("\n🤔 Agent thinking (React loop)...\n")
            print("-" * 70)
            
            response = agent.invoke({"messages": [{"role": "user", "content": user_input}]})

            print("-" * 70)
            messages = response.get("messages", []) if isinstance(response, dict) else []
            final_message = messages[-1].content if messages else str(response)

            tool_call = _extract_tool_call(final_message)
            if tool_call:
                tool_name = tool_call.get("name")
                arguments = tool_call.get("arguments", {}) or {}

                if tool_name == "GetDatabaseSchema":
                    schema_name = arguments.get("schema_name", "public")
                    if isinstance(schema_name, str) and schema_name.startswith("SELECT"):
                        schema_name = "public"
                    tool_result = db_tools.get_database_schema(schema_name)
                elif tool_name == "ExecuteQuery":
                    query = arguments.get("query") or arguments.get("__arg1") or ""
                    if not isinstance(query, str) or not query.strip().upper().startswith("SELECT"):
                        tool_result = "❌ Invalid query from model. Use a SELECT statement."
                    else:
                        tool_result = db_tools.execute_database_query(query)
                elif tool_name == "SaveMemory":
                    tool_result = memory_tools.save_insight(
                        topic=str(arguments.get("topic", "general")),
                        content=str(arguments.get("content", "")),
                        ttl_hours=int(arguments.get("ttl_hours", 168)),
                    )
                elif tool_name == "RecallMemory":
                    tool_result = memory_tools.recall_insight(str(arguments.get("topic", "general")))
                elif tool_name == "ListMemoryTopics":
                    tool_result = memory_tools.list_topics()
                else:
                    tool_result = f"❌ Unknown tool call: {tool_name}"

                print(f"\n🤖 Final Answer:\n{tool_result}")
            else:
                print(f"\n🤖 Final Answer:\n{final_message}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            print("💡 Tip: Make sure PostgreSQL and Ollama are running")


if __name__ == "__main__":
    main()
