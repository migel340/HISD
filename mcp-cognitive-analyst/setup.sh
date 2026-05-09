#!/bin/bash
# Quick setup script for MCP Cognitive Analyst

set -e

echo "🚀 Setting up MCP Cognitive Analyst..."

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "✓ Python $PYTHON_VERSION found"

# Create virtual environment (optional but recommended)
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Copy .env.example to .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your PostgreSQL credentials"
fi

# Test imports
echo "🔍 Testing imports..."
python3 -c "import fastmcp; import asyncpg; import sqlite3; print('✓ All dependencies imported successfully')"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your PostgreSQL credentials"
echo "  2. Run: source venv/bin/activate"
echo "  3. Test: python business_mcp.py"
echo "  4. Configure in Claude Desktop or Cursor"
