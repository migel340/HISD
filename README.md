# Implementation of LLM+MCP model with a database
This project connects two MCP to an open source agent OpenCode giving it access to a relational Postgre database and SQLite context memory.

Thanks to the business_mcp, which is responsible for access to the database OpenCode can:
<ul>
  <li>execute INSERT, SELECT, UPDATE, CREATE queries</li>
  <li>execute DROP, DELETE, ALTER, TRUNCATE queries after an appropriate confirmation</li>
</ul>
DROP, DELETE, ALTER and TRUNCATE queries where created as a proof of concept and wouldn't be added in a comercial version.

The memory_mcp remebers:
<ul>
  <li>users' preferences</li>
  <li>commonly asked queries</li>
</ul>

## Requirements
To use this program the user needs:
<ul>
  <li>Docker Desktop</li>
  <li>OpenCode</li>
</ul>

## Start up
To start the project open terminal in the projects folder and enter this commands:
```bash
docker compose up -d
opencode
```

## Testing
