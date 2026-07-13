#!/bin/bash
# Start the DDL Lineage Web Interface

cd "$(dirname "$0")"

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing backend dependencies..."
    python3 -m pip install -r backend/requirements.txt
fi

# Start the app
echo "Starting DDL Lineage API on http://127.0.0.1:5001"
python3 backend/app.py
