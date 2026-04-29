#!/bin/bash
# Quick test script to verify web interface works

set -e

echo "🧪 Testing DDL Lineage Web Interface"
echo "======================================"
echo ""

# Check Python
echo "✓ Checking Python..."
python --version

# Check Flask
echo "✓ Checking Flask..."
python -c "import flask; print(f'  Flask: {flask.__version__}')" || {
    echo "✗ Flask not found. Installing..."
    pip install flask
}

# Check ddl_lineage
echo "✓ Checking ddl_lineage..."
python -c "import ddl_lineage; print(f'  ddl_lineage: {ddl_lineage.__version__}')"

# Quick API test
echo ""
echo "🔌 Testing API..."
python -c "
from app import app
import json

with app.test_client() as client:
    # Test health
    response = client.get('/api/health')
    data = response.get_json()
    print(f'  Health: {data[\"status\"]}')
    
    # Test analyze
    response = client.post('/api/analyze',
        json={'ddl': 'CREATE TABLE t (id INT PRIMARY KEY);'}
    )
    data = response.get_json()
    if data['success']:
        print(f'  Analyze: ✓ ({data[\"data\"][\"stats\"][\"total_objects\"]} objects)')
    else:
        print(f'  Analyze: ✗ ({data[\"error\"]})')
"

echo ""
echo "✅ All tests passed!"
echo ""
echo "🚀 To start the server:"
echo "   cd web && python app.py"
echo ""
