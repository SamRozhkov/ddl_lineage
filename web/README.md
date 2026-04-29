# Web Interface for DDL Lineage Analyzer

This directory contains the Flask-based web application for visualizing SQL DDL lineage.

## 🚀 Quick Start

### Option 1: Using the shell script

```bash
cd web
bash run.sh
```

### Option 2: Manual setup

```bash
# Install dependencies
cd web
pip install -r requirements.txt

# Start the app
python app.py
```

The interface will be available at: **http://127.0.0.1:5000**

## 📂 Structure

```
web/
├── app.py                  # Flask application with REST API
├── templates/
│   └── index.html         # Main HTML interface
├── static/
│   ├── css/
│   │   └── style.css      # Styling and responsive design
│   └── js/
│       └── app.js         # Client-side JavaScript logic
├── requirements.txt       # Python dependencies
└── run.sh                 # Startup script
```

## 🎯 Features

### UI Components

- **SQL Input Panel** - Paste or write SQL DDL statements
- **Analysis Controls** - Analyze, Clear, Export buttons
- **Statistics View** - Summary of objects, edges, cycles
- **Objects Tab** - Detailed list of all database objects with columns
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
