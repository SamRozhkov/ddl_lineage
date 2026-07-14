"""
ddl_lineage.analyzer
====================
The main DDLLineageAnalyzer class — the primary public interface.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .models import Column, ColumnLineage, DDLObject, LineageEdge
from .parser import (
    SQL_KW,
    _cte_names,
    _extract_function_body,
    _extract_object_name,
    _extract_paren_body,
    _parse_column_lineage,
    _parse_table_columns,
    _read_references,
    _remove_comments,
    _split_statements,
)
from .graph import detect_cycles, impact_analysis, topological_sort, ImpactResult

# ---------------------------------------------------------------------------
# Write-statement patterns  (source, detail label)
# ---------------------------------------------------------------------------

_WRITE_PATTERNS: list[tuple[str, str]] = [
    # INSERT … SELECT  (enables column-level lineage)
    (
        r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?"
        r"[^;]*?SELECT[^;]+",
        "INSERT",
    ),
    # INSERT … VALUES
    (
        r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?\s+VALUES[^;]+",
        "INSERT_VALUES",
    ),
    # UPDATE
    (r"UPDATE\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?\s+SET", "UPDATE"),
    # DELETE
    (r"DELETE\s+FROM\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?", "DELETE"),
    # MERGE / UPSERT
    (r"MERGE\s+INTO\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?", "MERGE"),
    # TRUNCATE
    (r"TRUNCATE\s+(?:TABLE\s+)?(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?", "TRUNCATE"),
]

_CREATE_TABLE_RE = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL|LOCAL)\s+)?"
    r"(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
    re.IGNORECASE,
)
_CREATE_TEMP_TABLE_RE = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL|LOCAL)\s+)?"
    r"TEMP(?:ORARY)?\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
    re.IGNORECASE,
)


class DDLLineageAnalyzer:
    """
    Parse a SQL DDL script and build a data lineage graph.

    Supported statement types
    -------------------------
    * CREATE TABLE          — columns, PK, FK, INHERITS / LIKE
    * CREATE VIEW           — FROM / JOIN references
    * CREATE MATERIALIZED VIEW
    * CREATE FUNCTION       — READ + WRITE references, column lineage
    * CREATE PROCEDURE      — READ + WRITE references, column lineage
    * ALTER TABLE           — ADD COLUMN … REFERENCES, ADD FOREIGN KEY

    Supported dialects
    ------------------
    PostgreSQL, MySQL / MariaDB, SQLite, T-SQL (SQL Server),
    Oracle PL/SQL, BigQuery standard SQL.

    Example
    -------
    >>> analyzer = DDLLineageAnalyzer()
    >>> result   = analyzer.analyze(open("schema.sql").read())
    >>> print(analyzer.to_text(result))
    >>> imp = analyzer.impact("orders")
    >>> print(imp.summary())
    """

    def __init__(self) -> None:
        self.objects:    dict[str, DDLObject]  = {}
        self.edges:      list[LineageEdge]     = []
        self.col_lineage: list[ColumnLineage]  = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, ddl: str) -> dict:
        """
        Parse *ddl* and return a lineage result dict.

        Result schema
        -------------
        {
            "objects":     [{"name", "type", "schema", "columns": [...]}],
            "edges":       [{"source", "target", "type", "via", "details", "col_lineage"}],
            "col_lineage": [{"src_table", "src_col", "tgt_table", "tgt_col", "via"}],
            "cycles":      [["a", "b", "c", "a"], …],
            "topo_order":  ["users", "orders", …],
            "stats":       {"total_objects", "total_edges", "has_cycles"},
        }
        """
        # Reset state so the instance is reusable
        self.objects.clear()
        self.edges.clear()
        self.col_lineage.clear()

        ddl = _remove_comments(ddl)
        for stmt in _split_statements(ddl):
            stmt = stmt.strip()
            if not stmt:
                continue
            self._dispatch(stmt)

        return self._finalize()

    def impact(self, target: str, edge_types: set[str] | None = None) -> ImpactResult:
        """
        Run impact analysis for *target*.

        Calls ``analyze`` internally if no edges are recorded yet
        (idempotent — safe to call repeatedly).

        :param edge_types: Restrict traversal; None = all types.
        """
        return impact_analysis(target.lower(), self.edges, edge_types)

    def topo_sort(self) -> list[str]:
        """Return object names in dependency order (leaves first)."""
        return topological_sort(list(self.objects), self.edges)

    # ------------------------------------------------------------------
    # Statement dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, stmt: str) -> None:
        if _CREATE_TABLE_RE.match(stmt):
            self._parse_table(stmt)
        elif re.match(r"CREATE\s+(OR\s+REPLACE\s+)?MATERIALIZED\s+VIEW", stmt, re.IGNORECASE):
            self._parse_view(stmt, "MATERIALIZED_VIEW")
        elif re.match(r"CREATE\s+(OR\s+REPLACE\s+)?VIEW", stmt, re.IGNORECASE):
            self._parse_view(stmt, "VIEW")
        elif re.match(r"CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE)", stmt, re.IGNORECASE):
            self._parse_function(stmt)
        elif re.match(r"ALTER\s+TABLE", stmt, re.IGNORECASE):
            self._parse_alter_table(stmt)

    # ------------------------------------------------------------------
    # Statement parsers
    # ------------------------------------------------------------------

    def _parse_table(self, stmt: str) -> None:
        schema, name = _extract_object_name(stmt)
        if not name:
            return

        body = _extract_paren_body(stmt)
        columns = _parse_table_columns(_remove_comments(body))
        temporary = bool(_CREATE_TEMP_TABLE_RE.match(stmt))
        self.objects[name] = DDLObject(
            name=name, type="TABLE", schema=schema,
            columns=columns, temporary=temporary, raw=stmt[:100],
        )

        # FK edges derived from column-level inline REFERENCES
        for col in columns:
            if col.fk_to:
                ref_table = col.fk_to.split(".")[0]
                if ref_table != name:
                    self._add_edge(LineageEdge(
                        source=name, target=ref_table, edge_type="FK",
                        via=name, details=f"{col.name} -> {col.fk_to}",
                    ))

        # Explicit FOREIGN KEY (…) REFERENCES table  constraints
        for m in re.finditer(
            r"FOREIGN\s+KEY\s*\([^)]+\)\s*REFERENCES\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?",
            body, re.IGNORECASE,
        ):
            self._add_edge(LineageEdge(
                source=name, target=m.group(1).lower(), edge_type="FK", via=name,
            ))

        # LIKE / INHERITS (table inheritance)
        for m in re.finditer(
            r"\bLIKE\s+`?\"?(\w+)\"?`?|\bINHERITS\s*\(\s*`?\"?(\w+)\"?`?",
            body, re.IGNORECASE,
        ):
            parent = (m.group(1) or m.group(2) or "").lower()
            if parent:
                self._add_edge(LineageEdge(
                    source=name, target=parent, edge_type="INHERITS", via=name,
                ))

    def _parse_view(self, stmt: str, obj_type: str) -> None:
        schema, name = _extract_object_name(stmt)
        if not name:
            return
        self.objects[name] = DDLObject(
            name=name, type=obj_type, schema=schema, raw=stmt[:100],
        )
        body_m = re.search(r"\bAS\b(.+)", stmt, re.IGNORECASE | re.DOTALL)
        if body_m:
            body = body_m.group(1)
            ctes = _cte_names(body)
            for edge in _read_references(body, name, ctes):
                self._add_edge(edge)

    def _parse_function(self, stmt: str) -> None:
        m = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE)\s+"
            r"(?:`?\"?\w+\"?`?\.)?`?\"?(\w+)\"?`?",
            stmt, re.IGNORECASE,
        )
        if not m:
            return
        obj_type = m.group(1).upper()
        name = m.group(2).lower()
        self.objects[name] = DDLObject(name=name, type=obj_type, raw=stmt[:100])

        body = _extract_function_body(stmt)
        ctes = _cte_names(body)

        # READ references
        for edge in _read_references(body, name, ctes):
            self._add_edge(edge)

        # WRITE references
        for pat, detail in _WRITE_PATTERNS:
            for m2 in re.finditer(pat, body, re.IGNORECASE | re.DOTALL):
                t = m2.group(1).lower()
                if not t or t in ctes or t.upper() in SQL_KW:
                    continue
                col_lin: list[ColumnLineage] = []
                if detail == "INSERT":
                    col_lin = _parse_column_lineage(m2.group(0), t, name)
                    self.col_lineage.extend(col_lin)
                self._add_edge(LineageEdge(
                    source=name, target=t, edge_type="WRITE",
                    via=name, details=detail, col_lineage=col_lin,
                ))

    def _parse_alter_table(self, stmt: str) -> None:
        m = re.search(
            r"ALTER\s+TABLE\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?",
            stmt, re.IGNORECASE,
        )
        if not m:
            return
        table = m.group(1).lower()

        # ADD FOREIGN KEY / ADD COLUMN … REFERENCES
        for m2 in re.finditer(
            r"REFERENCES\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?",
            stmt, re.IGNORECASE,
        ):
            self._add_edge(LineageEdge(
                source=table, target=m2.group(1).lower(), edge_type="FK", via=table,
            ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_edge(self, edge: LineageEdge) -> None:
        if edge.source != edge.target:
            self.edges.append(edge)

    def _finalize(self) -> dict:
        # Deduplicate edges (same source / target / type / detail)
        seen: set[tuple] = set()
        unique: list[LineageEdge] = []
        for e in self.edges:
            key = (e.source, e.target, e.edge_type, e.details)
            if key not in seen:
                seen.add(key)
                unique.append(e)

        # Auto-register objects that are referenced but never defined
        for e in unique:
            for nm in (e.source, e.target):
                if nm not in self.objects:
                    self.objects[nm] = DDLObject(name=nm, type="TABLE")

        node_names = list(self.objects)
        cycles = detect_cycles(node_names, unique)
        topo = topological_sort(node_names, unique)

        return {
            "objects": [
                {
                    "name": o.name,
                    "type": o.type,
                    "schema": o.schema,
                    "temporary": o.temporary,
                    "columns": [
                        {
                            "name":     c.name,
                            "type":     c.data_type,
                            "nullable": c.nullable,
                            "pk":       c.pk,
                            "fk_to":   c.fk_to,
                            "unique":   c.unique,
                            "default":  c.default,
                        }
                        for c in o.columns
                    ],
                }
                for o in self.objects.values()
            ],
            "edges": [
                {
                    "source":     e.source,
                    "target":     e.target,
                    "type":       e.edge_type,
                    "via":        e.via,
                    "details":    e.details,
                    "col_lineage": [
                        {
                            "src_table": cl.src_table,
                            "src_col":   cl.src_col,
                            "tgt_table": cl.tgt_table,
                            "tgt_col":   cl.tgt_col,
                            "via":       cl.via,
                        }
                        for cl in e.col_lineage
                    ],
                }
                for e in unique
            ],
            "col_lineage": [
                {
                    "src_table": cl.src_table,
                    "src_col":   cl.src_col,
                    "tgt_table": cl.tgt_table,
                    "tgt_col":   cl.tgt_col,
                    "via":       cl.via,
                }
                for cl in self.col_lineage
            ],
            "cycles":     cycles,
            "topo_order": topo,
            "stats": {
                "total_objects": len(self.objects),
                "total_edges":   len(unique),
                "has_cycles":    bool(cycles),
            },
        }

    # ------------------------------------------------------------------
    # Output renderers
    # ------------------------------------------------------------------

    def to_text(self, result: dict) -> str:
        """Human-readable plain-text report."""
        lines = ["=" * 58, "  DDL Lineage Analyzer  v2.0", "=" * 58, ""]

        by_type: dict[str, list] = defaultdict(list)
        for o in result["objects"]:
            by_type[o["type"]].append(o)

        for t, objs in sorted(by_type.items()):
            lines.append(f"  {t}s  ({len(objs)})")
            for o in sorted(objs, key=lambda x: x["name"]):
                pfx = f"{o['schema']}." if o["schema"] else ""
                lines.append(f"    * {pfx}{o['name']}")
                for c in o.get("columns", [])[:6]:
                    flags = " ".join(f for f in [
                        "PK" if c["pk"] else "",
                        "FK" if c["fk_to"] else "",
                        "UNIQUE" if c["unique"] else "",
                        "NOT NULL" if not c["nullable"] else "",
                    ] if f)
                    ref = f"  -> {c['fk_to']}" if c["fk_to"] else ""
                    lines.append(f"        {c['name']:24} {c['type']:20} {flags}{ref}")
                extra = len(o.get("columns", [])) - 6
                if extra > 0:
                    lines.append(f"        ... +{extra} more columns")
            lines.append("")

        lines.append(f"  Lineage edges  ({len(result['edges'])})")
        lines.append("  " + "-" * 52)
        _order = {"FK": 0, "READ": 1, "WRITE": 2, "INHERITS": 3}
        for e in sorted(
            result["edges"],
            key=lambda x: (_order.get(x["type"], 9), x["source"], x["target"]),
        ):
            detail = f" ({e['details']})" if e.get("details") else ""
            lines.append(f"    {e['source']:24} --[{e['type']}{detail}]--> {e['target']}")
            for cl in e.get("col_lineage", [])[:4]:
                lines.append(
                    f"        {cl['src_table']}.{cl['src_col']}  ->  "
                    f"{cl['tgt_table']}.{cl['tgt_col']}"
                )
        lines.append("")

        if result.get("col_lineage"):
            lines.append(f"  Column-level lineage  ({len(result['col_lineage'])})")
            lines.append("  " + "-" * 52)
            for cl in result["col_lineage"]:
                lines.append(
                    f"    {cl['src_table']}.{cl['src_col']:24} ->  "
                    f"{cl['tgt_table']}.{cl['tgt_col']}  (via {cl['via']})"
                )
            lines.append("")

        if result.get("cycles"):
            lines.append(f"  WARNING: {len(result['cycles'])} circular dependency cycle(s) detected!")
            for cyc in result["cycles"]:
                lines.append("    " + " -> ".join(cyc))
            lines.append("")

        if result.get("topo_order"):
            lines.append("  Topological order (leaves first)")
            lines.append("    " + " -> ".join(result["topo_order"]))
            lines.append("")

        s = result["stats"]
        lines.append(
            f"  Summary: {s['total_objects']} objects, {s['total_edges']} edges"
            + ("  [CYCLES DETECTED]" if s["has_cycles"] else "")
        )
        lines.append("")
        return "\n".join(lines)

    def to_dot(self, result: dict) -> str:
        """Graphviz DOT format (pipe through `dot -Tsvg` to render)."""
        lines = [
            "digraph lineage {",
            '  rankdir=LR;',
            '  graph [fontname="Helvetica" fontsize=11 bgcolor=transparent];',
            '  node  [fontname="Helvetica" fontsize=11 shape=box'
            '         style="rounded,filled" penwidth=1.2];',
            '  edge  [fontname="Helvetica" fontsize=9  penwidth=1.2];',
            "",
        ]
        node_styles = {
            "TABLE":             'fillcolor="#E6F1FB" color="#185FA5" fontcolor="#0C447C"',
            "VIEW":              'fillcolor="#E1F5EE" color="#0F6E56" fontcolor="#085041"',
            "MATERIALIZED_VIEW": 'fillcolor="#9FE1CB" color="#0F6E56" fontcolor="#04342C"',
            "FUNCTION":          'fillcolor="#EEEDFE" color="#534AB7" fontcolor="#3C3489"',
            "PROCEDURE":         'fillcolor="#FAEEDA" color="#854F0B" fontcolor="#633806"',
        }
        cycle_nodes = {n for cyc in result.get("cycles", []) for n in cyc}

        for o in sorted(result["objects"], key=lambda x: x["name"]):
            col_lines = []
            for c in o.get("columns", [])[:8]:
                fl = (" PK" if c["pk"] else "") + (f" -> {c['fk_to']}" if c["fk_to"] else "")
                col_lines.append(f"{c['name']} {c['type']}{fl}")
            col_block = "\\l".join(col_lines)
            label = (
                f"{o['name']}\\n({o['type']})"
                + (f"\\n---\\l{col_block}\\l" if col_block else "")
            )
            style = node_styles.get(o["type"], "")
            border = 'penwidth=2.5 color=red' if o["name"] in cycle_nodes else ""
            lines.append(f'  "{o["name"]}" [label="{label}" {style} {border}];')

        lines.append("")
        edge_styles = {
            "FK":       'color="#888780" style=dashed',
            "READ":     'color="#185FA5"',
            "WRITE":    'color="#993C1D"',
            "INHERITS": 'color="#3B6D11" style=dotted',
        }
        for e in result["edges"]:
            style = edge_styles.get(e["type"], "")
            detail = f" ({e['details']})" if e.get("details") else ""
            col_lbl = ""
            if e.get("col_lineage"):
                col_lbl = "\\n" + "\\n".join(
                    f"{cl['src_col']} -> {cl['tgt_col']}"
                    for cl in e["col_lineage"][:4]
                )
            lines.append(
                f'  "{e["source"]}" -> "{e["target"]}"'
                f' [{style} label="{e["type"]}{detail}{col_lbl}"];'
            )

        if result.get("cycles"):
            lines.append("")
            for cyc in result["cycles"]:
                for a, b in zip(cyc, cyc[1:]):
                    lines.append(
                        f'  "{a}" -> "{b}" [color=red penwidth=2.5 label="CYCLE!"];'
                    )

        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self, result: dict) -> str:
        """Mermaid flowchart (paste into mermaid.live or any Markdown renderer)."""
        lines = ["graph LR"]
        for o in sorted(result["objects"], key=lambda x: x["name"]):
            lines.append(f'  {o["name"]}["{o["name"]}\\n{o["type"]}"]')
        labels = {
            "FK":       "FK",
            "READ":     "reads",
            "WRITE":    "writes",
            "INHERITS": "inherits",
        }
        for e in result["edges"]:
            lbl = labels.get(e["type"], e["type"])
            if e.get("details"):
                lbl = f"{lbl} ({e['details']})"
            lines.append(f'  {e["source"]} -->|"{lbl}"| {e["target"]}')
        if result.get("cycles"):
            lines.append("\n%% WARNING: Circular dependencies detected:")
            for cyc in result["cycles"]:
                lines.append(f"%% {' -> '.join(cyc)}")
        return "\n".join(lines)

    def to_json(self, result: dict) -> str:
        """JSON serialisation of the full result dict."""
        import json
        return json.dumps(result, indent=2, ensure_ascii=False)
