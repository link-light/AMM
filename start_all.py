"""
Quick Start Script - Start API and Dashboard

Usage:
    python start_all.py

This will start:
- API server on http://127.0.0.1:8080
- Dashboard on http://127.0.0.1:3000
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

print("="*70)
print(" AI Money Machine - Quick Start")
print("="*70)
print("\n📋 Configuration:")
print("   Database: SQLite (amm.db)")
print("   Redis: In-memory (FakeRedis)")
print("   AI Mode: Mock (no API keys needed)")
print("")
print("🔗 URLs:")
print("   API:       http://127.0.0.1:8080")
print("   API Docs:  http://127.0.0.1:8080/docs")
print("   Dashboard: http://127.0.0.1:3000")
print("")
print("👤 Default Login:")
print("   Username: admin")
print("   Password: admin123")
print("="*70)
print("\n⚠️  Press Ctrl+C to stop")
print("")

# Start API server
api_cmd = [
    sys.executable, "-m", "uvicorn",
    "api.main:app",
    "--host", "127.0.0.1",
    "--port", "8080",
    "--reload"
]

# Start Dashboard
dashboard_cmd = ["npm", "run", "dev"]

# Run both
try:
    import threading
    
    def run_api():
        subprocess.run(api_cmd)
    
    def run_dashboard():
        os.chdir("dashboard")
        subprocess.run(dashboard_cmd)
    
    api_thread = threading.Thread(target=run_api, daemon=True)
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    
    api_thread.start()
    print("🚀 API server starting on http://127.0.0.1:8080...")
    
    import time
    time.sleep(3)
    
    dashboard_thread.start()
    print("🚀 Dashboard starting on http://127.0.0.1:3000...")
    
    # Keep main thread alive
    while True:
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\n\n👋 Stopping servers...")
    sys.exit(0)
