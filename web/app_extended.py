"""
Enhanced DDL Lineage Web Interface with file upload and project management
Optional: use this instead of app.py for more features
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

# Add parent directory to path to import ddl_lineage
sys.path.insert(0, str(Path(__file__).parent.parent))

from ddl_lineage import DDLLineageAnalyzer
from web.utils import save_analysis_result, load_sql_file, format_lineage_text

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['RESULTS_FOLDER'] = Path(__file__).parent / 'results'

# Create folders
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['RESULTS_FOLDER'].mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'sql', 'txt'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def handle_errors(f):
    """Decorator to handle common errors in API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    return decorated_function


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/api/analyze', methods=['POST'])
@handle_errors
def analyze():
    """
    Analyze DDL and return lineage data.
    
    Request JSON:
    {
        "ddl": "CREATE TABLE ...",
        "save_result": true/false,
        "project_name": "my_project"
    }
    """
    payload = request.get_json()
    if not payload or 'ddl' not in payload:
        return jsonify({'success': False, 'error': 'Missing DDL content'}), 400
    
    ddl = payload.get('ddl', '').strip()
    if not ddl:
        return jsonify({'success': False, 'error': 'DDL content is empty'}), 400
    
    # Analyze
    analyzer = DDLLineageAnalyzer()
    result = analyzer.analyze(ddl)
    
    # Save result if requested
    if payload.get('save_result', False):
        project_name = payload.get('project_name', 'analysis')
        filename = f"{secure_filename(project_name)}_result.json"
        save_analysis_result(result, filename)
    
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
        'text_report': format_lineage_text(result),
        'error': None
    }
    
    return jsonify(response), 200


@app.route('/api/upload', methods=['POST'])
@handle_errors
def upload_file():
    """
    Upload SQL file for analysis.
    
    Returns the file content.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Only .sql and .txt files allowed'}), 400
    
    # Read file content
    content = file.read().decode('utf-8')
    
    return jsonify({
        'success': True,
        'filename': file.filename,
        'content': content,
        'size': len(content)
    }), 200


@app.route('/api/impact/<obj_name>', methods=['POST'])
@handle_errors
def get_impact(obj_name):
    """Get impact analysis for a specific object."""
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


@app.route('/api/topo', methods=['POST'])
@handle_errors
def get_topo():
    """Get topological sort order."""
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


@app.route('/api/export', methods=['POST'])
@handle_errors
def export_results():
    """
    Export analysis results in various formats.
    
    Request JSON:
    {
        "data": {...},
        "format": "json|mermaid|text",
        "filename": "output"
    }
    """
    payload = request.get_json()
    data = payload.get('data', {})
    format_type = payload.get('format', 'json')
    filename = payload.get('filename', 'lineage_result')
    
    if format_type == 'json':
        content = json.dumps(data, indent=2)
        mimetype = 'application/json'
        ext = 'json'
    elif format_type == 'mermaid':
        content = _to_mermaid(data)
        mimetype = 'text/plain'
        ext = 'mmd'
    elif format_type == 'text':
        content = format_lineage_text(data)
        mimetype = 'text/plain'
        ext = 'txt'
    else:
        return jsonify({'success': False, 'error': 'Unknown format'}), 400
    
    # Save to temp file
    filepath = app.config['RESULTS_FOLDER'] / f"{secure_filename(filename)}.{ext}"
    with open(filepath, 'w') as f:
        f.write(content)
    
    return jsonify({
        'success': True,
        'download_url': f'/download/{filepath.name}'
    }), 200


@app.route('/download/<filename>')
def download(filename):
    """Download exported result file."""
    try:
        filepath = app.config['RESULTS_FOLDER'] / filename
        if not filepath.exists():
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filepath.name
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'version': '2.0.0',
        'service': 'DDL Lineage Analyzer Web Interface'
    }), 200


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
    
    return '\n'.join(lines)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
