"""
ddl_lineage — SQL DDL lineage analyzer.

Quick start
-----------
>>> from ddl_lineage import DDLLineageAnalyzer
>>> analyzer = DDLLineageAnalyzer()
>>> result = analyzer.analyze(open("schema.sql").read())
>>> print(analyzer.to_text(result))
"""

from .analyzer import DDLLineageAnalyzer
from .models import DDLObject, LineageEdge, Column, ColumnLineage
from .parser import parseDDL, _remove_comments, _split_statements

__all__ = [
    "DDLLineageAnalyzer",
    "DDLObject",
    "LineageEdge",
    "Column",
    "ColumnLineage",
    "parseDDL",
]

__version__ = "2.0.0"
__author__ = "DDL Lineage Project"
