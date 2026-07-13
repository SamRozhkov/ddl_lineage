# DDL Lineage Web Interface

A web application for interactive SQL DDL lineage analysis with database connectivity.

## Architecture

The application is split into separate frontend and backend components:

```
web/
├── backend/           # Flask API server
│   ├── app.py        # Main Flask application
│   ├── requirements.txt
│   └── db_connectors/ # Modular database connectors
│       ├── __init__.py
│       ├── factory.py
│       ├── postgresql.py
│       └── mysql.py
├── frontend/          # React frontend (Create React App + Gravity UI)
│   ├── package.json
│   ├── public/
│   └── src/
└── run.py           # Script to run both servers
```

## Features

- **DDL Analysis**: Parse and analyze SQL DDL statements
- **Interactive Graph**: Visualize table relationships with React Flow
- **Database Connectivity**: Extract DDL directly from PostgreSQL/MySQL databases
- **Modular Architecture**: Easy to extend with new database types

## Database Connectors

The application uses a modular connector system for database connectivity:

### Adding a New Database Connector

1. Create a new connector class inheriting from `DatabaseConnector`
2. Implement the required abstract methods:
   - `connect()`: Establish database connection
   - `extract_ddl()`: Extract DDL from database
   - `get_connection_url()`: Return connection URL
3. Register the connector in `DatabaseConnectorFactory`

Example:
```python
from . import DatabaseConnector

class NewDBConnector(DatabaseConnector):
    def connect(self):
        # Implementation
        pass

    def extract_ddl(self, objects=None):
        # Implementation
        pass

    def get_connection_url(self):
        # Implementation
        pass
```

## Installation

1. Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Install frontend dependencies:
```bash
cd frontend
npm install
```

## Running

Run both servers simultaneously:
```bash
python run.py
```

Or run separately:

Backend:
```bash
cd backend
python app.py
```

Frontend:
```bash
cd frontend
npm start
```

The backend listens on `http://127.0.0.1:5001`. The frontend dev server listens on
`http://localhost:3000` and proxies `/api/*` requests to the backend.

## API Endpoints

### POST /api/analyze
Analyze DDL and return lineage data.

**Request:**
```json
{
  "ddl": "CREATE TABLE users (...);"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "objects": [...],
    "edges": [...],
    "stats": {...}
  }
}
```

### POST /api/connect
Connect to database and extract DDL.

**Request:**
```json
{
  "type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "user",
  "password": "pass",
  "schema": "public",
  "objects": ["table1", "table2"]
}
```

**Response:**
```json
{
  "success": true,
  "ddl": "CREATE TABLE..."
}
```
- **Cycles Tab** - Detected circular dependencies (if any)
- **Topo Tab** - Topological sort order for safe DDL execution
- **Mermaid Diagram** - Interactive visualization of lineage
- **Table View** - Tabular representation of all edges/relationships

### Example SQL

Pre-loaded examples:
- **Basic**: Simple users → orders → order_items schema
- **Cycles**: Schema with circular dependencies
- **Complex**: E-commerce schema with procedures and multiple relationships

## 🔌 API Endpoints

### POST /api/analyze
Analyze SQL DDL and return lineage information.

**Request:**
```json
{
    "ddl": "CREATE TABLE users (id INT PRIMARY KEY, ...)"
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "objects": [...],
        "edges": [...],
        "cycles": [...],
        "stats": {...}
    },
    "mermaid": "graph LR ...",
    "error": null
}
```

### POST /api/impact/<object_name>
Get impact analysis for a specific object.

**Request:**
```json
{
    "ddl": "CREATE TABLE users (...)"
}
```

**Response:**
```json
{
    "success": true,
    "target": "orders",
    "upstream": ["users", "categories"],
    "downstream": ["order_items", "order_summary"],
    "summary": "..."
}
```

### POST /api/topo
Get topological sort order.

**Request:**
```json
{
    "ddl": "CREATE TABLE users (...)"
}
```

**Response:**
```json
{
    "success": true,
    "order": ["users", "categories", "products", "orders", ...]
}
```

## 🎨 UI Features

### Visualization

- **Mermaid Diagrams** - Auto-generated flow diagrams showing relationships
  - Different colors for edge types (FK, READ, WRITE, INHERITS)
  - Interactive zoom and pan
- **Table View** - Sortable, searchable edge list
  - Color-coded edge types
  - Details about relationships

### Data Export

- **Download as JSON** - Export complete analysis results
- **Copy to Clipboard** - Quick copy of SQL

### Responsive Design

- Works on desktop, tablet, and mobile
- Collapsible panels for small screens
- Touch-friendly buttons and controls

## 🛠️ Development

### Adding Custom Visualizations

Edit `web/static/js/app.js` to add new visualization types:

```javascript
function switchViz(vizName) {
    // Add new visualization type here
}
```

### Customizing Styles

Modify `web/static/css/style.css` to change the look and feel.

### API Extensions

Add new endpoints to `web/app.py`:

```python
@app.route('/api/custom', methods=['POST'])
def custom_endpoint():
    # Your logic here
    return jsonify(response)
```

## 🐛 Troubleshooting

### Port 5000 already in use

```bash
# Use different port
python -c "from app import app; app.run(port=5001)"
```

### Import errors

```bash
# Make sure parent directory is in Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/.."
python app.py
```

### SSL/Certificate errors

The web interface uses Bulma CDN. If behind a proxy, configure your environment:

```bash
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=https://proxy:port
```

## 📦 Dependencies

- **Flask** - Web framework
- **Mermaid.js** - Diagram rendering (CDN)
- **Bulma CSS** - UI framework (CDN)
- **Font Awesome** - Icons (CDN)

## 📋 Browser Support

- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 💡 Tips

1. **Load Examples** - Use pre-loaded SQL examples to understand the interface
2. **Monitor Cycles** - Always check the Cycles tab - circular dependencies need fixing
3. **Use Topo Order** - Execute DDL in topological order to avoid foreign key errors
4. **Export Results** - Download JSON for integration with other tools
5. **Copy HTML** - Save the Mermaid diagram as PNG using browser DevTools

## 🤝 Contributing

Found a bug or want to improve the UI? Create an issue or pull request!
