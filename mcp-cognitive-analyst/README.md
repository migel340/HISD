# MCP Cognitive Analyst - Dual Server System

A sophisticated system for **intelligent database analysis and contextual memory management**. This project integrates:

1. **MCP Servers** - Model Context Protocol implementation
2. **Langchain Agent** - Conversational AI with reasoning
3. **Ollama** - Local LLM execution
4. **PostgreSQL** - Business data storage
5. **SQLite** - Persistent memory for insights

### What Can You Do With It?

```
"What are our top customers?" 
→ Agent queries database + saves the insight

"Show me monthly trends"
→ Agent writes SQL query + plots results

"Remember we have 50k active users"
→ Agent stores fact with 7-day expiration

"What did you learn about users?"
→ Agent recalls previous findings
```

## Architecture

### Two Independent MCP Servers

**1. Business MCP Server** (`business_mcp.py`)
- **Purpose**: Safe, read-only access to PostgreSQL databases
- **Key Tools**:
  - `get_schema(schema_name)`: Retrieve table and column metadata
  - `execute_query(query, params)`: Execute SELECT queries with strict validation
- **Security**: Enforces read-only access, prevents DROP/UPDATE/DELETE operations

**2. Memory MCP Server** (`memory_mcp.py`)
- **Purpose**: Cognitive context memory with TTL management
- **Key Tools**:
  - `save_context(topic, content, ttl_hours)`: Store facts with automatic expiration
  - `retrieve_context(topic)`: Fetch non-expired contexts by topic
  - `cleanup_expired_contexts()`: Maintenance operation for old records
  - `list_topics()`: Discover available memory topics

## Setup with Docker (Recommended)

### Quick Start with Docker Compose

```bash
cd mcp-cognitive-analyst

# Copy environment configuration
cp .env.example .env

# Build and start all services (PostgreSQL + Business MCP + Memory MCP)
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f
```

**Services started:**
- PostgreSQL (port 5433 on the host, 5432 inside Docker)
- Business MCP Server (port 8001)
- Memory MCP Server (port 8002)
- (Ollama runs locally on port 11434)

### With Ollama + Langchain (Interactive)

```bash
# 1. Start Docker services
docker-compose up -d

# 2. Start Ollama (in separate terminal)
ollama serve

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Run the Langchain agent
python langchain_agent.py
```

Now you have an **interactive AI agent** with database access!

### Docker Access

```bash
# Access PostgreSQL directly
docker exec -it mcp-postgres psql -U postgres -d business_db

# View business-mcp logs
docker-compose logs -f business-mcp

# View memory-mcp logs
docker-compose logs -f memory-mcp

# Stop all services
docker-compose down

# Clean up (including volumes)
docker-compose down -v
```

## Local Setup (Without Docker)

### 1. Install Dependencies

```bash
cd mcp-cognitive-analyst
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

**Example .env:**
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/business_db
MEMORY_DB_PATH=./memory.db
DEBUG=false
```

If you already had a PostgreSQL volume from an older setup or changed the database password, reset the container state once:

```bash
docker-compose down -v
docker-compose up -d
```

### 3. Initialize PostgreSQL Database (if needed)

```bash
createdb business_db
# Apply your schema and sample data
```

## Integration with Claude Desktop / Cursor

### Option A: Configure in Claude Desktop

Edit `~/.claude/config.json` or create one:

```json
{
  "mcpServers": {
    "business-db": {
      "command": "python",
      "args": ["/path/to/business_mcp.py"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5433/business_db"
      }
    },
    "context-memory": {
      "command": "python",
      "args": ["/path/to/memory_mcp.py"],
      "env": {
        "MEMORY_DB_PATH": "/path/to/memory.db"
      }
    }
  }
}
```

### Option B: Use provided mcp.json

```json
{
  "mcpServers": {
    "business-db": {
      "command": "python",
      "args": ["business_mcp.py"],
      "env": {
        "DATABASE_URL": "${DATABASE_URL}"
      }
    },
    "context-memory": {
      "command": "python",
      "args": ["memory_mcp.py"],
      "env": {
        "MEMORY_DB_PATH": "${MEMORY_DB_PATH}"
      }
    }
  }
}
```

## 🤖 Langchain + Ollama Integration (NEW!)

### What is the Langchain Agent?

The Langchain agent (`langchain_agent.py`) provides an **intelligent, conversational interface** to your database:

- 🧠 **Multi-step reasoning**: Uses React pattern (Thought → Action → Observation)
- 🔗 **Tool orchestration**: Automatically decides which tools to use
- 💾 **Memory management**: Persists insights across conversations
- 🚀 **Local execution**: Runs entirely on your machine with Ollama
- 🎯 **No API keys needed**: 100% local, no external dependencies

### Quick Start: Run the Langchain Agent

```bash
# 1. Start the project stack
cd mcp-cognitive-analyst
docker-compose up -d

# 2. Make sure Ollama is running
ollama serve  # In a separate terminal

# 3. Install Langchain dependencies (if not already done)
pip install -r requirements.txt

# 4. Run the agent
python langchain_agent.py
```

### Example Interaction

```
🤖 Langchain + Ollama Cognitive Analyst
=====================================

👤 You: What tables are in the database?

🤔 Agent thinking (React loop)...
---------------------------------------
Thought: I need to understand the database structure
Action: GetDatabaseSchema
Observation: 📊 Schema: public
  📋 Table: customers
  📋 Table: orders
  📋 Table: products

Thought: I have the schema, let me provide a summary
Final Answer: The database contains 3 main tables: customers, orders, and products.
Each is used for managing business data.
----------------------------------------

👤 You: Show me top 5 customers and remember this

🤔 Agent thinking...
---------------------------------------
Thought: I need to fetch customers and save them to memory
Action: ExecuteQuery
Observation: ✓ Query returned 5 rows
  Row 1: {'id': 1, 'name': 'Acme Corp', 'email': 'info@acme.com'}
  ...

Action: SaveMemory
Observation: ✓ Saved 'customers' to memory (expires in 168h)

Final Answer: I've fetched the top 5 customers and saved them to my memory.
Here are your key customers...
----------------------------------------

👤 You: What do you remember about customers?

🤔 Agent thinking...
---------------------------------------
Action: RecallMemory
Observation: 📚 Memories for 'customers':
  1. [2024-01-25 14:30:00]
     Top 5 customers: Acme Corp, Beta Inc, Gamma LLC...

Final Answer: I remember the top 5 customers from earlier...
```

### Agent Capabilities

| Capability | Tool | Use Case |
|-----------|------|----------|
| **Explore Schema** | `GetDatabaseSchema` | Understand database structure |
| **Query Data** | `ExecuteQuery` | Fetch specific business data |
| **Save Insights** | `SaveMemory` | Remember analysis results |
| **Recall Facts** | `RecallMemory` | Reference previous findings |
| **List Topics** | `ListMemoryTopics` | See what's been learned |

### Running with Different Models

The agent automatically picks the first installed Ollama model from `ollama list`.
If you want to force a specific model, set `OLLAMA_MODEL` before running:

```bash
export OLLAMA_MODEL="SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M"
python langchain_agent.py
```

You can also pull and try other models:

```bash
# Download a faster model
ollama pull mistral
ollama pull neural-chat

python langchain_agent.py
```

**Recommended models:**
- `SpeakLeash/bielik-11b-v3.0-instruct` - Local Polish/English instruct model
- `llama2` - Good balance (7B)
- `mistral` - Faster, lighter (7B)
- `neural-chat` - Good at conversation (7B)

## Usage Examples

### Example 1: Explore Database Schema

```
User: "What tables are available in the public schema?"

AI uses: get_schema("public") 
→ Returns all tables and columns with types
```

### Example 2: Analyze Data with Query

```
User: "Show me all customers from the customers table"

AI uses: execute_query("SELECT * FROM customers LIMIT 10")
→ Returns customer records safely
```

### Example 3: Store Analysis Results

```
AI: "I found 2,847 active customers. Let me save this insight."

AI uses: save_context(
  topic="customer_analysis",
  content="Active customer count: 2,847 (updated 2024-01-15)",
  ttl_hours=168  // 7 days
)
```

### Example 4: Recall Previous Insights

```
User: "What did you previously learn about our customers?"

AI uses: retrieve_context("customer_analysis")
→ Returns all non-expired customer-related insights
```

## Tool Documentation

### Business MCP Tools

#### `get_schema(schema_name: str = "public")`
Retrieves comprehensive schema information.

**Returns:**
```json
{
  "schema": "public",
  "tables": {
    "customers": [
      {"name": "id", "type": "integer", "nullable": false},
      {"name": "email", "type": "text", "nullable": false}
    ]
  }
}
```

#### `execute_query(query: str, params: Optional[List[Any]] = None)`
Executes read-only SELECT queries with parameter binding.

**Returns:**
```json
{
  "rows": [
    {"id": 1, "name": "John", "email": "john@example.com"},
    {"id": 2, "name": "Jane", "email": "jane@example.com"}
  ],
  "row_count": 2,
  "columns": ["id", "name", "email"],
  "execution_time": 0.123
}
```

### Memory MCP Tools

#### `save_context(topic: str, content: str, ttl_hours: int = 24)`
Stores a context fact with automatic expiration.

**Returns:**
```json
{
  "success": true,
  "id": 42,
  "topic": "database_insights",
  "expires_at": "2024-02-01T10:30:00",
  "ttl_hours": 24
}
```

#### `retrieve_context(topic: str)`
Fetches all valid contexts for a topic.

**Returns:**
```json
{
  "topic": "database_insights",
  "count": 3,
  "contexts": [
    {
      "id": 42,
      "content": "Found 2,847 active customers",
      "created_at": "2024-01-25T10:30:00",
      "expires_at": "2024-02-01T10:30:00"
    }
  ],
  "retrieved_at": "2024-01-25T14:00:00"
}
```

## Security Considerations

### Business MCP
- **Read-only by design**: Only SELECT queries are allowed
- **Query validation**: Blocks DROP, UPDATE, DELETE, INSERT, ALTER, TRUNCATE, CREATE
- **Connection pooling**: Reuses connections efficiently
- **Parameter binding**: Supports parameterized queries to prevent injection

### Memory MCP
- **Local SQLite storage**: No remote exposure
- **TTL enforcement**: Automatic cleanup of expired data
- **Topic isolation**: Contexts organized by topic for easy retrieval

## Troubleshooting

### Connection Issues
```bash
# Test PostgreSQL connection
python -c "import asyncpg; asyncio.run(asyncpg.connect('postgresql://...'))"
```

### Memory Database Not Found
```bash
# Check path
ls -la ./memory.db

# Reset database (will delete all contexts)
rm ./memory.db
```

### Query Execution Failed
- Verify table names and columns with `get_schema()`
- Check database permissions (SELECT access only)
- Ensure tables exist in the specified schema

## Development

### Running All Components Locally

```bash
# Terminal 1: Start PostgreSQL (if using Docker)
docker-compose up postgres

# Terminal 2: Start Ollama
ollama serve

# Terminal 3: Activate venv and run agent
source venv/bin/activate
python langchain_agent.py

# Terminal 4 (optional): Start MCP servers individually
python business_mcp.py
python memory_mcp.py
```

### Running Servers Individually (for testing)

```bash
# Terminal 1: Start Business MCP
python business_mcp.py

# Terminal 2: Start Memory MCP  
python memory_mcp.py
```

### Testing Tools

```python
import asyncio
from business_mcp import get_schema, execute_query

# Test schema retrieval
result = asyncio.run(get_schema())
print(result)

# Test safe query
result = asyncio.run(execute_query("SELECT * FROM customers LIMIT 5"))
print(result)
```

## Performance Optimization

- **Connection pooling**: business_mcp maintains 2-10 connections
- **Indexing**: memory_mcp uses indexes on topic and expires_at
- **Query timeout**: 30-second timeout on database queries
- **Cleanup**: Run `cleanup_expired_contexts()` periodically (e.g., daily)

## License

This MCP implementation is provided as-is for local use with Claude Desktop and Cursor AI editors.
