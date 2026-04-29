#!/bin/bash
# Start the DDL Lineage Web Interface

cd "$(dirname "$0")"

# Check if Flask is installed
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    pip install -r requirements.txt
fi

# Start the app
echo "Starting DDL Lineage Web Interface on http://127.0.0.1:5000"
python app.py
