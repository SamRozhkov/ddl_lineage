#!/usr/bin/env python3
"""
Script to run both backend and frontend servers.
"""

import subprocess
import sys
import os
import time

def run_backend():
    """Run the Flask backend server."""
    return subprocess.Popen([
        sys.executable, 'backend/app.py'
    ], cwd=os.path.dirname(__file__))

def run_frontend():
    """Run the React frontend dev server."""
    return subprocess.Popen([
        'npm', 'start'
    ], cwd=os.path.join(os.path.dirname(__file__), 'frontend'))

if __name__ == '__main__':
    print("Starting DDL Lineage servers...")
    print("Backend (Flask): http://127.0.0.1:5001")
    print("Frontend (React): http://localhost:3000")
    print("Press Ctrl+C to stop both servers")

    # Start servers
    backend_process = run_backend()
    time.sleep(2)  # Wait for backend to start
    frontend_process = run_frontend()

    try:
        # Wait for both processes
        backend_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print("\nStopping servers...")
        backend_process.terminate()
        frontend_process.terminate()
        backend_process.wait()
        frontend_process.wait()
        print("Servers stopped.")
