# Implementation of LLM+MCP model with a database

This project integrates the open-source agent **OpenCode** (LLM) with two relational databases using the **MCP (Model Context Protocol)**. This allows the language model to interact with business data (PostgreSQL) and maintain persistent contextual memory (SQLite) for personalization and remembering user preferences.

The project consists of two main MCP servers:

1. **Business MCP** – responsible for accessing, analyzing, and modifying the PostgreSQL database.
2. **Memory MCP** – a cognitive contextual memory that allows the model to save and retrieve facts (e.g., user preferences) in a local SQLite database.

---

## WARNING: Destructive Operations

The **Business MCP** server includes functions that allow modifying and deleting the database structure (`DROP`, `DELETE`, `ALTER`, `TRUNCATE` queries).
These were implemented **strictly as a Proof of Concept (PoC)** for testing and developmental purposes. They should NOT be deployed in production environments without additional security layers.

The LLM is **strictly forbidden** from executing these operations without first informing the user of the exact SQL query to be run and obtaining explicit confirmation (e.g., the user typing "yes" or "confirm" in the chat).

---

## Available Tools for the LLM

The model gains access to a set of tools that automatically execute the corresponding Python functions.

### Business MCP (PostgreSQL)

Allows the model to read, write, and safely interact with business data.

* `get_schema(schema_name)` – Retrieves the full database structure, including table names, columns, data types, NULL constraints, and foreign key relationships.
* `execute_query(query, params)` – A safe tool for executing **SELECT** queries. It strictly prevents any data modification.
* `execute_write(query, params)` – Tool for write operations (strictly limited to **INSERT** and **UPDATE**, optionally with a `RETURNING` clause).
* `add_table(table_name, columns)` – Allows the model to dynamically create new tables (`CREATE TABLE`).

**Tools requiring explicit user authorization (Destructive):**

* `alter_table(query)` – Allows modification of existing tables (`ALTER TABLE`).
* `truncate_table(table_name)` – Quickly clears all rows from a table while keeping its structure (`TRUNCATE`).
* `execute_destructive(query, params)` – Tool for deleting data or dropping structures (strictly limited to **DELETE** and **DROP**).

### Memory MCP (SQLite)

Allows the model to maintain context between sessions using a TTL (Time-to-Live) mechanism.

* `save_context(topic, content, ttl_hours)` – Saves a fact, insight, or preference assigned to a specific topic (e.g., `user_preferences`). The default TTL is 24 hours.
* `retrieve_context(topic)` – Retrieves all valid (non-expired) facts saved under a given topic.
* `list_topics()` – Displays a list of all remembered categories that currently have active, non-expired entries.
* `cleanup_expired_contexts()` – A maintenance tool used to delete expired facts from the SQLite database.

---

## Capabilities and Use Cases

Here are examples of what you can ask the **OpenCode** agent to do using the implemented MCP servers:

### 1. Business Database Integration (Business MCP)

**Understanding the structure and querying data (Read-Only):**
* *"Describe the database structure to me. What tables are there and how are they related?"* (Triggers `get_schema`)
* *"What columns does the `products` table contain, and can the `description` field accept NULL values?"* (Triggers `get_schema`)
* *"Fetch the 5 most recent orders from the orders table that have a 'pending' status."* (Triggers `execute_query`)
* *"Calculate the average order value (`total_price` column) from all orders completed last month."* (Triggers `execute_query` with an aggregate function)
* *"Show me the first and last names of all customers from the `users` table who bought the product named 'Laptop X Pro' (join with the `orders` table)."* (Triggers `execute_query` using a `JOIN`)

**Inserting and updating data (Write):**
* *"Add a new user to the users table with the name John and email john@example.com."* (Triggers `execute_write` - `INSERT`)
* *"Update the status of all orders from 'processing' to 'shipped' for orders handled by DHL courier."* (Triggers `execute_write` - `UPDATE`)
* *"Increase the price of all products in the 'Accessories' category (`products` table) by 10%."* (Triggers `execute_write` - `UPDATE`)

**Managing database structure (DDL):**
* *"Create a new table named `product_reviews`. Add the following columns: `id` (integer), `product_id` (integer), `rating` (integer), and `comment` (text)."* (Triggers `add_table`)
* *"Add a new `discount_code` column of type VARCHAR to the existing `orders` table."* (The model will prepare an `alter_table` query and **ask for your confirmation** before executing).

**Destructive operations (Always require your explicit consent!):**
* *"Delete all entries from the logs table that are older than 30 days."* (The model will prepare an `execute_destructive` query using `DELETE`, show you the SQL code, and ask for confirmation).
* *"Delete the user account from the `users` table that has the email address 'spam@example.com'."* (Triggers `execute_destructive` using `DELETE` after your approval).
* *"Completely clear the temporary_data table."* (Triggers `truncate_table` after your approval - a very fast row deletion without dropping the table).
* *"Completely drop the `old_analytics_2023` table from the database."* (Triggers `execute_destructive` using `DROP TABLE` after your strict approval).

### 2. Contextual Memory (Memory MCP)

The agent can decide on its own when to remember something, but you can also give it direct instructions:

* *"Remember that I always prefer SQL results as formatted Markdown tables. Save this for 48 hours."* (Triggers `save_context`)
* *"What formatting preferences have you saved in the context?"* (Triggers `retrieve_context`)
* *"Clean up the memory and remove all expired entries."* (Triggers `cleanup_expired_contexts`)
* *"Check our contextual memory. What topics are you currently tracking?"* (Triggers `list_topics`)

---

## Requirements

To use this program, ensure you have the following installed:

* Docker Desktop
* OpenCode
* Python 3.12 or higher
* A Postgres database dump file (`.sql`) for initialization
* *(Optional)* Ollama with the `granite3.1:8b` model (or `granite 4.1:8b` depending on availability)

---

## Start up

To start the project, open your terminal in the project's root folder and enter these commands:

```bash
# 1. Prepare the virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Prepare environment variables
cp .env.example .env

```

**Optional Step:** Edit the `docker-compose.yml` file and modify the `.sql` mount path if necessary:

```yaml
- ./init-db.sql:/docker-entrypoint-initdb.d/init.sql

```

Adjust the `.env` file (e.g., database passwords, hostnames), then spin up the containers and the agent:

```bash
# 4. Start the database in the background
docker compose up -d

# 5. Start the OpenCode agent
opencode

```