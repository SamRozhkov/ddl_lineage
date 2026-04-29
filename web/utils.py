"""
Utility functions for web interface
"""

import json
from datetime import datetime
from pathlib import Path


def save_analysis_result(result: dict, filename: str | None = None) -> str:
    """
    Save analysis result to a JSON file.
    
    :param result: Analysis result from analyzer
    :param filename: Optional filename, defaults to timestamp
    :return: Path to saved file
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"lineage_result_{timestamp}.json"
    
    # Create results directory if needed
    results_dir = Path(__file__).parent / 'results'
    results_dir.mkdir(exist_ok=True)
    
    filepath = results_dir / filename
    
    with open(filepath, 'w') as f:
        json.dump(result, f, indent=2)
    
    return str(filepath)


def load_sql_file(filepath: str) -> str:
    """
    Load SQL from a file.
    
    :param filepath: Path to SQL file
    :return: SQL content
    """
    with open(filepath, 'r') as f:
        return f.read()


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal.
    
    :param filename: Original filename
    :return: Sanitized filename
    """
    return filename.replace('/', '_').replace('\\', '_').replace('..', '_')


def format_lineage_text(result: dict) -> str:
    """
    Format lineage result as readable text.
    
    :param result: Analysis result
    :return: Formatted text
    """
    lines = []
    
    lines.append("=" * 70)
    lines.append("DDL LINEAGE ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")
    
    # Statistics
    stats = result['stats']
    lines.append("STATISTICS")
    lines.append("-" * 70)
    lines.append(f"Total Objects:  {stats['total_objects']}")
    lines.append(f"Total Edges:    {stats['total_edges']}")
    lines.append(f"Has Cycles:     {stats['has_cycles']}")
    lines.append("")
    
    # Objects
    lines.append("OBJECTS")
    lines.append("-" * 70)
    for obj in result['objects']:
        lines.append(f"  {obj['type']:20} {obj['name']}")
        if obj['columns']:
            for col in obj['columns'][:5]:  # First 5 columns
                flags = []
                if col['pk']:
                    flags.append("PK")
                if col['fk']:
                    flags.append(f"FK→{col['fk']}")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                lines.append(f"    - {col['name']:20} {col['type']}{flag_str}")
            if len(obj['columns']) > 5:
                lines.append(f"    ... and {len(obj['columns']) - 5} more columns")
    lines.append("")
    
    # Edges
    lines.append("RELATIONSHIPS (EDGES)")
    lines.append("-" * 70)
    for edge in result['edges']:
        detail = f" ({edge['details']})" if edge['details'] else ""
        via = f" via {edge['via']}" if edge['via'] else ""
        lines.append(f"  {edge['source']:25} --[{edge['type']:8}]--> {edge['target']:25}{detail}{via}")
    lines.append("")
    
    # Cycles
    if result['cycles']:
        lines.append("CYCLES DETECTED (ISSUES)")
        lines.append("-" * 70)
        for i, cycle in enumerate(result['cycles'], 1):
            lines.append(f"  Cycle {i}: {' → '.join(cycle)}")
        lines.append("")
    
    lines.append("=" * 70)
    
    return "\n".join(lines)


def merge_results(*results) -> dict:
    """
    Merge multiple analysis results.
    
    Useful for analyzing multiple SQL files together.
    
    :param results: Multiple analysis result dictionaries
    :return: Merged result
    """
    merged = {
        'objects': [],
        'edges': [],
        'cycles': [],
        'stats': {
            'total_objects': 0,
            'total_edges': 0,
            'has_cycles': False
        }
    }
    
    seen_objects = set()
    seen_edges = set()
    
    for result in results:
        for obj in result.get('objects', []):
            obj_key = (obj['name'], obj['type'])
            if obj_key not in seen_objects:
                merged['objects'].append(obj)
                seen_objects.add(obj_key)
        
        for edge in result.get('edges', []):
            edge_key = (edge['source'], edge['target'], edge['type'])
            if edge_key not in seen_edges:
                merged['edges'].append(edge)
                seen_edges.add(edge_key)
        
        merged['cycles'].extend(result.get('cycles', []))
    
    merged['stats']['total_objects'] = len(merged['objects'])
    merged['stats']['total_edges'] = len(merged['edges'])
    merged['stats']['has_cycles'] = len(merged['cycles']) > 0
    
    return merged
