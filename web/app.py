"""
DDL Lineage Web Interface
Flask application for interactive SQL lineage visualization
"""

from __future__ import annotations

import json
from flask import Flask, render_template, request, jsonify
import sys
from pathlib import Path

# Add parent directory to path to import ddl_lineage
sys.path.insert(0, str(Path(__file__).parent.parent))

from ddl_lineage import DDLLineageAnalyzer
from ddl_lineage.models import LineageEdge

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/api/analyze', methods=['POST'])
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
        
        # Build response
        response = {
            'success': True,
            'data': {
                'objects': result['objects'],
                'edges': result['edges'],
                'cycles': result['cycles'],
                'stats': result['stats'],
            },
            'mermaid': _to_mermaid(result),
            'error': None
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/impact/<obj_name>', methods=['POST'])
def get_impact(obj_name):
    """
    Get impact analysis for a specific object.
    
    Request JSON:
    {
        "ddl": "CREATE TABLE ...",
    }
    """
    try:
        payload = request.get_json()
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


@app.route('/api/topo', methods=['POST'])
def get_topo():
    """
    Get topological sort order.
    
    Request JSON:
    {
        "ddl": "CREATE TABLE ...",
    }
    """
    try:
        payload = request.get_json()
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


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
