"""
Quick Start Script - Local Development (No Docker)

This script starts the API server with:
- SQLite database (no PostgreSQL needed)
- FakeRedis (no Redis server needed)
- Mock AI mode (no API keys needed)
"""

import os
import subprocess
import sys

# Set environment for local development
os.environ['ENVIRONMENT'] = 'development'
os.environ['DEBUG'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./amm.db'
os.environ['REDIS_URL'] = 'memory://'
os.environ['MOCK_AI'] = 'true'
os.environ['MOCK_SCOUTS'] = 'true'
os.environ['JWT_SECRET'] = 'dev-secret-key'

print("="*60)
print("AI Money Machine - Local Development Mode")
print("="*60)
print("\nConfiguration:")
print(f"  Database: SQLite (amm.db)")
print(f"  Redis: In-memory (FakeRedis)")
print(f"  AI Mode: Mock (no API keys needed)")
print("="*60)
print("\nStarting API server on http://127.0.0.1:8080")
print("Press Ctrl+C to stop\n")

# Start the server
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "api.main:app",
    "--host", "127.0.0.1",
    "--port", "8080",
    "--reload"
])
