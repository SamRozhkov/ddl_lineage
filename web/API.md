# 📖 API Documentation

Complete API reference for DDL Lineage Web Interface.

## Base URL

```
http://127.0.0.1:5000
```

## Authentication

Currently, no authentication is required. In production, add authentication tokens as needed.

---

## Endpoints

### 1. Analyze DDL

**Endpoint:** `POST /api/analyze`

Analyze SQL DDL and return complete lineage information.

**Request:**
```json
{
  "ddl": "CREATE TABLE users (id INT PRIMARY KEY, ...)",
  "save_result": false,
  "project_name": "my_project"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ddl` | string | ✓ | SQL DDL statements to analyze |
| `save_result` | boolean | ✗ | Save result to file (default: false) |
| `project_name` | string | ✗ | Project name for saved file |

**Response (Success):**
```json
{
  "success": true,
  "data": {
    "objects": [
      {
        "name": "users",
        "type": "TABLE",
        "schema": "public",
        "columns": [
          {
            "name": "id",
            "type": "INT",
            "pk": true,
            "fk": ""
          }
        ]
      }
    ],
    "edges": [
      {
        "source": "users",
        "target": "orders",
        "type": "FK",
        "via": "",
        "details": ""
      }
    ],
    "cycles": [],
    "stats": {
      "total_objects": 2,
      "total_edges": 1,
      "has_cycles": false
    }
  },
  "mermaid": "graph LR\n  users[\"TABLE<br/>users\"]\n  orders[\"TABLE<br/>orders\"]\n  users -->|FK| orders",
  "text_report": "...",
  "error": null
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "DDL content is empty"
}
```

**Status Codes:**
| Code | Meaning |
|------|---------|
| 200 | Analysis successful |
| 400 | Bad request (missing/invalid DDL) |
| 500 | Server error |

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "ddl": "CREATE TABLE users (id INT PRIMARY KEY);"
  }'
```

---

### 2. Impact Analysis

**Endpoint:** `POST /api/impact/<object_name>`

Perform impact analysis for a specific database object (upstream and downstream dependencies).

**Request:**
```json
{
  "ddl": "CREATE TABLE users (...)"
}
```

**Parameters:**
| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `object_name` | string | URL path | ✓ | Name of object to analyze |
| `ddl` | string | body | ✓ | SQL DDL statements |

**Response:**
```json
{
  "success": true,
  "target": "orders",
  "upstream": ["users", "categories"],
  "downstream": ["order_items", "order_summary"],
  "summary": "Impact analysis: orders\n============================================\n  Upstream   (depends on): users, categories\n  Downstream (used by):    order_items, order_summary"
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/impact/orders \
  -H "Content-Type: application/json" \
  -d '{
    "ddl": "CREATE TABLE users (...); CREATE TABLE orders (...);"
  }'
```

---

### 3. Topological Sort

**Endpoint:** `POST /api/topo`

Get safe execution order for DDL objects (topological sort).

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
  "order": ["users", "categories", "products", "orders", "order_items"]
}
```

**Description:** Returns object names in dependency order (create tables first, then views, then procedures, etc.)

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/topo \
  -H "Content-Type: application/json" \
  -d '{"ddl": "CREATE TABLE orders (...)"}'
```

---

### 4. File Upload

**Endpoint:** `POST /api/upload`

Upload SQL file for analysis.

**Request:**
```
Content-Type: multipart/form-data

file: <binary SQL file>
```

**Allowed Files:**
- `.sql` files
- `.txt` files
- Max size: 16MB (configurable)

**Response:**
```json
{
  "success": true,
  "filename": "schema.sql",
  "content": "CREATE TABLE users (...)",
  "size": 1234
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/upload \
  -F "file=@schema.sql"
```

---

### 5. Export Results

**Endpoint:** `POST /api/export`

Export analysis results in various formats.

**Request:**
```json
{
  "data": { ... },
  "format": "json|mermaid|text",
  "filename": "my_lineage"
}
```

**Parameters:**
| Parameter | Type | Required | Values | Description |
|-----------|------|----------|--------|-------------|
| `data` | object | ✓ | - | Analysis result from `/api/analyze` |
| `format` | string | ✗ | json, mermaid, text | Output format (default: json) |
| `filename` | string | ✗ | any string | Filename without extension |

**Formats:**
- `json` - Machine-readable JSON format
- `mermaid` - Mermaid diagram syntax
- `text` - Human-readable text report

**Response:**
```json
{
  "success": true,
  "download_url": "/download/my_lineage.json"
}
```

**Example:**
```bash
# Export as JSON
curl -X POST http://127.0.0.1:5000/api/export \
  -H "Content-Type: application/json" \
  -d '{
    "data": {...},
    "format": "json",
    "filename": "lineage_report"
  }'

# Export as Mermaid
curl -X POST http://127.0.0.1:5000/api/export \
  -H "Content-Type: application/json" \
  -d '{
    "data": {...},
    "format": "mermaid",
    "filename": "lineage_diagram"
  }'
```

---

### 6. Download File

**Endpoint:** `GET /download/<filename>`

Download previously exported file.

**Parameters:**
| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `filename` | string | URL path | Name of file to download |

**Example:**
```bash
curl -O http://127.0.0.1:5000/download/my_lineage.json
```

---

### 7. Health Check

**Endpoint:** `GET /api/health`

Check if service is running.

**Response:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "service": "DDL Lineage Analyzer Web Interface"
}
```

**Example:**
```bash
curl http://127.0.0.1:5000/api/health
```

---

## Data Structures

### DDLObject

```json
{
  "name": "users",
  "type": "TABLE",
  "schema": "public",
  "columns": [
    {
      "name": "id",
      "type": "SERIAL",
      "pk": true,
      "fk": ""
    }
  ]
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Object name |
| `type` | string | TABLE, VIEW, MATERIALIZED_VIEW, FUNCTION, PROCEDURE |
| `schema` | string | Schema name (if specified) |
| `columns` | array | Column definitions |

### Column

```json
{
  "name": "id",
  "type": "INT",
  "pk": true,
  "fk": "users.id"
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Column name |
| `type` | string | Data type |
| `pk` | boolean | Primary key |
| `fk` | string | Foreign key reference (table.column) |

### LineageEdge

```json
{
  "source": "users",
  "target": "orders",
  "type": "FK",
  "via": "",
  "details": ""
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Source object |
| `target` | string | Target object |
| `type` | string | FK, READ, WRITE, INHERITS |
| `via` | string | Intermediate object (view/function) |
| `details` | string | INSERT, UPDATE, DELETE, MERGE, TRUNCATE |

### Statistics

```json
{
  "total_objects": 5,
  "total_edges": 8,
  "has_cycles": false
}
```

---

## Error Handling

### Common Errors

**400 Bad Request:**
```json
{
  "success": false,
  "error": "Missing DDL content"
}
```

**404 Not Found:**
```json
{
  "success": false,
  "error": "File not found"
}
```

**500 Internal Server Error:**
```json
{
  "success": false,
  "error": "SQL parsing error: ..."
}
```

---

## Rate Limiting

Currently no rate limiting. For production:

```python
from flask_limiter import Limiter

limiter = Limiter(
    app=app,
    key_func=lambda: request.remote_addr,
    default_limits=["200 per day", "50 per hour"]
)
```

---

## Caching

Results can be cached for performance:

```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'redis'})

@cache.cached(timeout=300)
def analyze():
    # ...
```

---

## CORS Support

To enable cross-origin requests:

```python
from flask_cors import CORS

CORS(app, origins=["http://example.com"])
```

---

## Testing

### Using curl

```bash
# Test health
curl -I http://127.0.0.1:5000/api/health

# Analyze SQL
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"ddl": "CREATE TABLE t (id INT);"}'
```

### Using Python

```python
import requests

url = "http://127.0.0.1:5000/api/analyze"
payload = {
    "ddl": "CREATE TABLE users (id INT PRIMARY KEY);"
}

response = requests.post(url, json=payload)
result = response.json()

print(result['data']['stats'])
```

### Using JavaScript

```javascript
fetch('/api/analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    ddl: 'CREATE TABLE users (id INT PRIMARY KEY);'
  })
})
.then(r => r.json())
.then(data => console.log(data.data.stats))
```

---

## Changelog

### v1.0.0
- Initial web interface
- Basic analysis endpoint
- Impact analysis
- Topological sort
- Mermaid diagram generation
- File upload support
- Result export (JSON, Mermaid, Text)
