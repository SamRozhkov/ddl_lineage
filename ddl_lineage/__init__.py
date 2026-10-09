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
from .models import Column, ColumnLineage, DDLObject, LineageEdge
from .parser import (  # noqa: F401  (kept for old imports)
    _remove_comments,
    _split_statements,
    parseDDL,
)

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
