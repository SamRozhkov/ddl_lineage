"""
DDL Lineage Web Interface
Flask application for interactive SQL lineage visualization
"""

from __future__ import annotations

from datetime import datetime
from flask import Flask, render_template, request, jsonify
import sys
from pathlib import Path

# Add parent directories to path to import ddl_lineage
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ddl_lineage import DDLLineageAnalyzer
from db_connectors import DatabaseConnectorFactory
from project_store import ProjectStore

FRONTEND_BUILD_DIR = Path(__file__).parent.parent / 'frontend' / 'build'

app = Flask(__name__,
            template_folder=str(FRONTEND_BUILD_DIR),
            static_folder=str(FRONTEND_BUILD_DIR / 'static'))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

project_store = ProjectStore()

def add_cors_headers(response):
    """Add CORS headers to response."""
    allowed_origins = {
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5000',
        'http://127.0.0.1:5001',
        'http://localhost:3000',
        'http://localhost:5000',
        'http://localhost:5001',
    }
    origin = request.headers.get('Origin')
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


app.after_request(add_cors_headers)


@app.route('/')
def index():
    """Serve the main page."""
    if (FRONTEND_BUILD_DIR / 'index.html').exists():
        return render_template('index.html')
    return jsonify({
        'success': True,
        'service': 'DDL Lineage API',
        'frontend': 'Run `npm start` in web/frontend for the React UI.',
    }), 200


@app.route('/api/projects', methods=['GET', 'POST', 'OPTIONS'])
def manage_projects():
    if request.method == 'OPTIONS':
        return '', 200

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'projects': project_store.list_projects()
        }), 200

    payload = request.get_json()
    if not payload or 'project_name' not in payload:
        return jsonify({'success': False, 'error': 'Missing project_name'}), 400

    project_name = payload.get('project_name', '').strip()
    if not project_name:
        return jsonify({'success': False, 'error': 'Project name cannot be empty'}), 400

    if project_store.project_exists(project_name):
        return jsonify({'success': False, 'error': 'Project already exists'}), 400

    project_store.ensure_project(project_name, {
        'name': project_name,
        'created_at': datetime.utcnow().isoformat() + 'Z',
    })

    return jsonify({
        'success': True,
        'project_name': project_name,
        'projects': project_store.list_projects()
    }), 201


@app.route('/api/project/<project_name>', methods=['GET', 'POST', 'DELETE', 'OPTIONS'])
def project_state(project_name):
    if request.method == 'OPTIONS':
        return '', 200

    if request.method == 'DELETE':
        try:
            project_store.delete_project(project_name)
            return jsonify({'success': True, 'projects': project_store.list_projects()}), 200
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    if request.method == 'GET':
        if not project_store.project_exists(project_name):
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        return jsonify({
            'success': True,
            'project': project_store.load_state(project_name)
        }), 200

    payload = request.get_json() or {}
    state = payload.get('state')
    if not isinstance(state, dict):
        return jsonify({'success': False, 'error': 'Missing state payload'}), 400

    saved = project_store.save_state(project_name, state, action=payload.get('action', 'update'))
    return jsonify({'success': True, 'project': saved}), 200


@app.route('/api/project/<project_name>/history', methods=['GET', 'OPTIONS'])
def project_history(project_name):
    if request.method == 'OPTIONS':
        return '', 200

    if not project_store.project_exists(project_name):
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    return jsonify({
        'success': True,
        'history': project_store.list_history(project_name)
    }), 200


@app.route('/api/project/<project_name>/history/<int:entry_id>', methods=['GET', 'OPTIONS'])
def project_history_entry(project_name, entry_id):
    if request.method == 'OPTIONS':
        return '', 200

    if not project_store.project_exists(project_name):
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    state = project_store.load_history_entry(project_name, entry_id)
    if not state:
        return jsonify({'success': False, 'error': 'History entry not found'}), 404

    return jsonify({'success': True, 'project': state}), 200


@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    """
    Analyze DDL and return lineage data.
    
    Request JSON:
    {
        "ddl": "CREATE TABLE ...",
        "format": "json|mermaid|dot"
    }
    
    Response:
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
    """
    if request.method == 'OPTIONS':
        return '', 200
    try:
        payload = request.get_json()
        if not payload or 'ddl' not in payload:
            return jsonify({
                'success': False,
                'error': 'Missing DDL content'
            }), 400
        
        ddl = payload.get('ddl', '').strip()
        if not ddl:
            return jsonify({
                'success': False,
                'error': 'DDL content is empty'
            }), 400
        
        # Analyze
        analyzer = DDLLineageAnalyzer()
        result = analyzer.analyze(ddl)

        project_name = payload.get('project_name')
        if project_name:
            state = {
                'project_name': project_name,
                'ddl': ddl,
                'analysis': {
                    'objects': result['objects'],
                    'edges': result['edges'],
                    'cycles': result['cycles'],
                    'topo_order': result.get('topo_order', []),
                    'stats': result['stats'],
                },
                'mermaid': _to_mermaid(result),
            }
            project_store.save_state(project_name, state, action='analysis')

        # Build response
        response = {
            'success': True,
            'data': result,
            'mermaid': _to_mermaid(result),
            'error': None
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/impact/<obj_name>', methods=['POST', 'OPTIONS'])
def get_impact(obj_name):
    """
    Get impact analysis for a specific object.
    
    Request JSON:
    {
        "ddl": "CREATE TABLE ...",
    }
    """
    if request.method == 'OPTIONS':
        return '', 200
    try:
        payload = request.get_json() or {}
        ddl = payload.get('ddl', '').strip()
        
        if not ddl:
            return jsonify({'success': False, 'error': 'DDL is required'}), 400
        
        analyzer = DDLLineageAnalyzer()
        analyzer.analyze(ddl)
        impact = analyzer.impact(obj_name)
        
        return jsonify({
            'success': True,
            'target': obj_name,
            'upstream': list(impact.upstream),
            'downstream': list(impact.downstream),
            'summary': impact.summary()
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/topo', methods=['POST', 'OPTIONS'])
def get_topo():
    """
    Get topological sort order.
    
    Request JSON:
    {
        "ddl": "CREATE TABLE ...",
    }
    """
    if request.method == 'OPTIONS':
        return '', 200
    try:
        payload = request.get_json() or {}
        ddl = payload.get('ddl', '').strip()
        
        if not ddl:
            return jsonify({'success': False, 'error': 'DDL is required'}), 400
        
        analyzer = DDLLineageAnalyzer()
        analyzer.analyze(ddl)
        order = analyzer.topo_sort()
        
        return jsonify({
            'success': True,
            'order': order
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _to_mermaid(result: dict) -> str:
    """Convert lineage result to Mermaid diagram syntax."""
    lines = ['graph LR']
    
    # Add nodes
    for obj in result['objects']:
        node_id = obj['name'].replace('.', '_').replace('-', '_')
        label = f"{obj['type']}<br/>{obj['name']}"
        lines.append(f'    {node_id}["{label}"]')
    
    # Add edges with different styles
    for i, edge in enumerate(result.get('edges', [])):
        src_id = edge['source'].replace('.', '_').replace('-', '_')
        tgt_id = edge['target'].replace('.', '_').replace('-', '_')
        edge_label = edge['type']
        if edge.get('details'):
            edge_label += f" ({edge['details']})"
        lines.append(f'    {src_id} -->|{edge_label}| {tgt_id}')
    
    # Add style definitions
    if result.get('cycles'):
        lines.append('    linkStyle default stroke:orange,stroke-width:2px')
    
    return '\n'.join(lines)


@app.route('/api/connect', methods=['POST', 'OPTIONS'])
def connect_db():
    """
    Connect to database and extract DDL.
    
    Request JSON:
    {
        "type": "postgresql|mysql",
        "host": "localhost",
        "port": 5432,
        "database": "mydb",
        "username": "user",
        "password": "pass",
        "schema": "public",
        "objects": ["table1", "table2"]  // optional, if not provided - extract all
    }
    
    Response:
    {
        "success": true,
        "ddl": "CREATE TABLE...",
        "error": null
    }
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({'success': False, 'error': 'Missing connection data'}), 400
        payload = dict(payload)
        
        required_fields = ['type', 'host', 'database', 'username', 'password']
        for field in required_fields:
            if field not in payload:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        if 'port' not in payload or payload['port'] in (None, ''):
            payload['port'] = 5432 if payload['type'].lower() == 'postgresql' else 3306
        
        # Create database connector using factory
        connector = DatabaseConnectorFactory.create_connector(payload['type'], payload)
        
        # Extract DDL
        with connector:
            ddl = connector.extract_ddl(payload.get('objects'))

        project_name = payload.get('project_name')
        if project_name:
            state = {
                'project_name': project_name,
                'ddl': ddl,
                'connection': {
                    'type': payload['type'],
                    'host': payload['host'],
                    'port': payload['port'],
                    'database': payload['database'],
                    'username': payload['username'],
                    'schema': payload.get('schema'),
                    'objects': payload.get('objects'),
                },
                'analysis': None,
            }
            project_store.save_state(project_name, state, action='db_connect')
        
        return jsonify({
            'success': True,
            'ddl': ddl,
            'error': None
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5001)
