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
    _extract_select_list,
    _QUALIFIED_IDENT,
    _extract_table_definition_body,
    _parse_ctas_columns,
    _parse_column_lineage,
    _parse_foreign_keys,
    _parse_returns_table_columns,
    _parse_select_columns,
    _parse_table_columns,
    _read_references,
    _remove_comments,
    _strip_create_options,
    _select_expression_name,
    _split_top_level_csv,
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
        r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?\s*(?:\([^)]*\)\s*)?VALUES[^;]+",
        "INSERT_VALUES",
    ),
    # UPDATE
    # UPDATE [ONLY] t [[AS] alias] [JOIN …] SET   (not SELECT … FOR UPDATE)
    (
        r"(?<!\bFOR\s)\bUPDATE\s+(?:ONLY\s+)?(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?(?=[^;]*?\bSET\b)",
        "UPDATE",
    ),
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
_BODY_CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL|LOCAL)\s+)?"
    r"(?:(?P<temp>TEMP(?:ORARY)?)\s+|UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:`?\"?(?P<schema>\w+)\"?`?\.)?`?\"?(?P<name>\w+)\"?`?",
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
        # Statement-level data flow inside function bodies: source -> target
        self.flows:      list[LineageEdge]     = []
        # Tables created inside function bodies (registered unless defined top-level)
        self.fn_tables:  dict[str, DDLObject]  = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, ddl: str) -> dict:
        """
        Parse *ddl* and return a lineage result dict.

        Result schema
        -------------
        {
            "objects":     [{"name", "type", "schema", "temporary", "parent", "columns": [...]}],
            "edges":       [{"source", "target", "type", "via", "details", "col_lineage"}],
            "col_lineage": [{"src_table", "src_col", "tgt_table", "tgt_col", "via"}],
            "flows":       [{"source", "target", "type", "via", "details"}],  # data flow in function bodies
            "cycles":      [["a", "b", "c", "a"], …],
            "topo_order":  ["users", "orders", …],
            "stats":       {"total_objects", "total_edges", "has_cycles"},
        }
        """
        # Reset state so the instance is reusable
        self.objects.clear()
        self.edges.clear()
        self.col_lineage.clear()
        self.flows.clear()
        self.fn_tables.clear()

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
        stmt = _strip_create_options(stmt.strip())
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

        body = _extract_table_definition_body(stmt)
        columns = _parse_table_columns(_remove_comments(body)) if body else self._parse_derived_columns(stmt)
        temporary = bool(_CREATE_TEMP_TABLE_RE.match(stmt))
        self.objects[name] = DDLObject(
            name=name, type="TABLE", schema=schema,
            columns=columns, temporary=temporary, raw=stmt[:100],
        )

        # FK edges: one per referenced table, from inline REFERENCES and
        # table-level FOREIGN KEY constraints (both end up in Column.fk_to)
        fk_details: dict[str, list[str]] = defaultdict(list)
        for col in columns:
            if col.fk_to:
                fk_details[col.fk_to.split(".")[0]].append(f"{col.name} -> {col.fk_to}")
        for ref_table, details in fk_details.items():
            self._add_edge(LineageEdge(
                source=name, target=ref_table, edge_type="FK",
                via=name, details=", ".join(details),
            ))

        # LIKE parent (inside the column list) / INHERITS (parents) after it
        parents = [m.group(1) for m in re.finditer(
            rf"(?:^|,)\s*LIKE\s+{_QUALIFIED_IDENT}", body, re.IGNORECASE,
        )]
        inh = re.search(r"\)\s*INHERITS\s*\(([^)]*)\)", stmt, re.IGNORECASE)
        if inh:
            parents += [p.strip().split(".")[-1].strip('`"[]') for p in inh.group(1).split(",")]
        for parent in parents:
            if parent:
                self._add_edge(LineageEdge(
                    source=name, target=parent.lower(), edge_type="INHERITS", via=name,
                ))

    def _parse_view(self, stmt: str, obj_type: str) -> None:
        schema, name = _extract_object_name(stmt)
        if not name:
            return
        body_m = re.search(r"\bAS\b(.+)", stmt, re.IGNORECASE | re.DOTALL)
        body = body_m.group(1) if body_m else ""
        self.objects[name] = DDLObject(
            name=name, type=obj_type, schema=schema,
            columns=self._parse_derived_columns(body), raw=stmt[:100],
        )
        if body_m:
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
        columns = _parse_returns_table_columns(stmt)
        if not columns:
            columns = self._columns_from_returns_setof(stmt)
        self.objects[name] = DDLObject(name=name, type=obj_type, columns=columns, raw=stmt[:100])

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

        # Tables created in the body + statement-level data flow
        for body_stmt in _split_statements(body, track_blocks=False):
            self._parse_function_statement(body_stmt, name, ctes)

    def _parse_function_statement(self, stmt: str, fn: str, ctes: set[str]) -> None:
        """
        Record data flow of one statement inside a function body.

        Flows go from the tables a statement reads to the tables it creates or
        writes. A write with nothing read flows out of the function itself; a
        read with nothing written (RETURN, SELECT INTO var, IF …) flows into it.
        """
        targets: dict[str, str] = {}   # table -> detail label

        create_m = _BODY_CREATE_TABLE_RE.search(stmt)
        if create_m:
            table = create_m.group("name").lower()
            self._register_function_table(stmt[create_m.start():], create_m, fn)
            targets[table] = "CREATE"
            self._add_edge(LineageEdge(
                source=fn, target=table, edge_type="WRITE", via=fn, details="CREATE",
            ))

        for pat, detail in _WRITE_PATTERNS:
            for m in re.finditer(pat, stmt, re.IGNORECASE | re.DOTALL):
                t = m.group(1).lower()
                if t and t not in ctes and t.upper() not in SQL_KW:
                    targets.setdefault(t, detail)

        sources = [e.target for e in _read_references(stmt, fn, ctes) if e.target not in targets]

        if not targets:
            for src in sources:
                self._add_flow(LineageEdge(source=src, target=fn, edge_type="READ", via=fn))
            return
        for tgt, detail in targets.items():
            for src in sources or [fn]:
                self._add_flow(LineageEdge(
                    source=src, target=tgt, edge_type="WRITE", via=fn, details=detail,
                ))

    def _register_function_table(self, stmt: str, create_m: re.Match, fn: str) -> None:
        name = create_m.group("name").lower()
        if name in self.fn_tables:
            return
        body = _extract_table_definition_body(stmt)
        columns = _parse_table_columns(_remove_comments(body)) if body else self._parse_derived_columns(stmt)
        self.fn_tables[name] = DDLObject(
            name=name, type="TABLE", schema=(create_m.group("schema") or "").lower(),
            columns=columns, temporary=bool(create_m.group("temp")),
            raw=stmt[:100], parent=fn,
        )

    def _add_flow(self, flow: LineageEdge) -> None:
        if flow.source != flow.target:
            self.flows.append(flow)

    def _parse_derived_columns(self, stmt: str) -> list[Column]:
        select_list = _extract_select_list(stmt)
        if not select_list:
            return _parse_ctas_columns(stmt) or _parse_select_columns(stmt)

        sources = self._select_sources(stmt)
        columns: list[Column] = []
        used_names: set[str] = set()

        for index, expr in enumerate(_split_top_level_csv(select_list), start=1):
            source_expr = self._select_source_expression(expr)
            expanded = self._expand_wildcard_columns(source_expr, sources)
            if expanded:
                for source_col in expanded:
                    name = self._unique_column_name(source_col.name, used_names, len(columns) + 1)
                    columns.append(Column(name=name, data_type=source_col.data_type))
                continue

            name = self._unique_column_name(_select_expression_name(expr, index), used_names, index)
            columns.append(Column(
                name=name,
                data_type=self._select_expression_type(source_expr, sources),
            ))

        return columns

    def _select_sources(self, stmt: str) -> dict[str, str]:
        sources: dict[str, str] = {}
        for m in re.finditer(
            r"\b(?:FROM|JOIN)\s+(?:`?\"?\w+\"?`?\.)?`?\"?(\w+)\"?`?"
            r"(?:\s+(?:AS\s+)?`?\"?(\w+)\"?`?)?",
            stmt,
            re.IGNORECASE,
        ):
            table = m.group(1).lower()
            alias = (m.group(2) or "").lower()
            sources[table] = table
            if alias and alias.upper() not in SQL_KW:
                sources[alias] = table
        return sources

    def _select_source_expression(self, expr: str) -> str:
        expr = expr.strip().rstrip(";")
        alias_m = re.search(r"\bAS\s+`?\"?\w+\"?`?$", expr, re.IGNORECASE)
        if alias_m:
            return expr[: alias_m.start()].strip()

        trailing_alias_m = re.search(r"\s+`?\"?(\w+)\"?`?$", expr)
        if trailing_alias_m:
            alias = trailing_alias_m.group(1)
            prefix = expr[: trailing_alias_m.start()].strip()
            if prefix and alias.upper() not in SQL_KW and not re.search(r"[()+*/-]", alias):
                return prefix

        return expr

    def _expand_wildcard_columns(self, expr: str, sources: dict[str, str]) -> list[Column]:
        expr = expr.strip()
        if expr == "*":
            result: list[Column] = []
            for table in dict.fromkeys(sources.values()):
                result.extend(self.objects.get(table, DDLObject(table, "TABLE")).columns)
            return result

        m = re.match(r"`?\"?(\w+)\"?`?\.\*$", expr)
        if not m:
            return []

        table = sources.get(m.group(1).lower(), m.group(1).lower())
        return list(self.objects.get(table, DDLObject(table, "TABLE")).columns)

    def _select_expression_type(self, expr: str, sources: dict[str, str]) -> str:
        qualified_m = re.match(r"(?:`?\"?(\w+)\"?`?\.)?`?\"?(\w+)\"?`?$", expr.strip())
        if not qualified_m:
            return ""

        qualifier = (qualified_m.group(1) or "").lower()
        column_name = qualified_m.group(2).lower()
        if qualifier:
            return self._source_column_type(sources.get(qualifier, qualifier), column_name)

        matches = {
            self._source_column_type(table, column_name)
            for table in dict.fromkeys(sources.values())
            if self._source_column_type(table, column_name)
        }
        return next(iter(matches)) if len(matches) == 1 else ""

    def _source_column_type(self, table: str, column_name: str) -> str:
        obj = self.objects.get(table)
        if not obj:
            return ""

        for column in obj.columns:
            if column.name == column_name:
                return column.data_type
        return ""

    def _unique_column_name(self, name: str, used_names: set[str], index: int) -> str:
        unique = name or f"column_{index}"
        if unique in used_names:
            unique = f"{unique}_{index}"
        used_names.add(unique)
        return unique

    def _columns_from_returns_setof(self, stmt: str) -> list[Column]:
        m = re.search(
            r"\bRETURNS\s+SETOF\s+(?:`?\"?\w+\"?`?\.)?`?\"?(\w+)\"?`?",
            stmt,
            re.IGNORECASE,
        )
        if not m:
            return []

        table = self.objects.get(m.group(1).lower())
        return list(table.columns) if table else []

    def _parse_alter_table(self, stmt: str) -> None:
        m = re.search(
            r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?",
            stmt, re.IGNORECASE,
        )
        if not m:
            return
        table = m.group(1).lower()

        # ADD [CONSTRAINT …] FOREIGN KEY (cols) REFERENCES t(cols)
        fks = _parse_foreign_keys(stmt)
        obj_columns = {c.name: c for c in self.objects[table].columns} if table in self.objects else {}
        for cols, ref_table, ref_cols in fks:
            details = []
            for col_name, ref_col in zip(cols, ref_cols):
                details.append(f"{col_name} -> {ref_table}.{ref_col}")
                if col_name in obj_columns:
                    obj_columns[col_name].fk_to = f"{ref_table}.{ref_col}"
            self._add_edge(LineageEdge(
                source=table, target=ref_table, edge_type="FK", via=table, details=", ".join(details),
            ))
        if fks:
            return

        # ADD COLUMN … REFERENCES
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

        # Tables created inside functions, unless also defined at top level
        for nm, obj in self.fn_tables.items():
            if nm not in self.objects:
                self.objects[nm] = obj

        flows: list[LineageEdge] = []
        seen_flows: set[tuple] = set()
        for f in self.flows:
            key = (f.source, f.target, f.edge_type, f.details, f.via)
            if key not in seen_flows:
                seen_flows.add(key)
                flows.append(f)

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
                    "parent":    o.parent,
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
            "flows": [
                {
                    "source":  f.source,
                    "target":  f.target,
                    "type":    f.edge_type,
                    "via":     f.via,
                    "details": f.details,
                }
                for f in flows
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
                marks = (["TEMP"] if o.get("temporary") else []) + (
                    [f"created in {o['parent']}"] if o.get("parent") else []
                )
                mark = f"  [{', '.join(marks)}]" if marks else ""
                lines.append(f"    * {pfx}{o['name']}{mark}")
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

        if result.get("flows"):
            lines.append(f"  Data flows in function bodies  ({len(result['flows'])})")
            lines.append("  " + "-" * 52)
            for f in sorted(result["flows"], key=lambda x: (x["via"], x["source"], x["target"])):
                detail = f" ({f['details']})" if f.get("details") else ""
                lines.append(
                    f"    {f['source']:24} ==[{f['type']}{detail}]==> {f['target']}  (in {f['via']})"
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
        groups = _function_groups(result)
        grouped = {m for members in groups.values() for m in members}
        node_lines: dict[str, str] = {}

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
            node_lines[o["name"]] = f'"{o["name"]}" [label="{label}" {style} {border}];'

        for name, line in node_lines.items():
            if name not in grouped:
                lines.append(f"  {line}")
        for fn, members in groups.items():
            lines.append(f'  subgraph "cluster_{fn}" {{')
            lines.append(f'    label="ƒ {fn}"; style="rounded,dashed"; color="#E8A33D"; fontcolor="#B5741A";')
            lines.extend(f"    {node_lines[m]}" for m in members)
            lines.append("  }")

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

        if result.get("flows"):
            lines.append("")
            lines.append("  // data flow inside function bodies")
            for f in result["flows"]:
                label = f"flow {f['details']}" if f.get("details") else "flow"
                lines.append(
                    f'  "{f["source"]}" -> "{f["target"]}"'
                    f' [color="#E8A33D" penwidth=1.6 style=bold label="{label}"];'
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
        def node(name: str, indent: str = "  ") -> str:
            return f'{indent}{_mermaid_id(name)}["{_mermaid_text(name)}<br/>{types[name]}"]'

        lines = ["graph LR"]
        groups = _function_groups(result)
        grouped = {m for members in groups.values() for m in members}
        types = {o["name"]: o["type"] for o in result["objects"]}
        for o in sorted(result["objects"], key=lambda x: x["name"]):
            if o["name"] not in grouped:
                lines.append(node(o["name"]))
        for fn, members in groups.items():
            lines.append(f'  subgraph {_mermaid_id(fn)}_group["ƒ {_mermaid_text(fn)}"]')
            lines.extend(node(m, "    ") for m in members)
            lines.append("  end")
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
            lines.append(
                f'  {_mermaid_id(e["source"])} -->|"{_mermaid_text(lbl)}"| {_mermaid_id(e["target"])}'
            )
        for f in result.get("flows", []):
            lbl = f.get("details") or f["type"].lower()
            lines.append(
                f'  {_mermaid_id(f["source"])} ==>|"{_mermaid_text(lbl)}"| {_mermaid_id(f["target"])}'
            )
        if result.get("cycles"):
            cycle_nodes = sorted({n for cyc in result["cycles"] for n in cyc if n in types})
            lines.append("  %% WARNING: circular dependencies detected:")
            lines.extend(f"  %% {' -> '.join(cyc)}" for cyc in result["cycles"])
            lines.append("  classDef cycle stroke:#d33,stroke-width:3px")
            lines.append(f"  class {','.join(_mermaid_id(n) for n in cycle_nodes)} cycle")
        return "\n".join(lines)

    def to_json(self, result: dict) -> str:
        """JSON serialisation of the full result dict."""
        import json
        return json.dumps(result, indent=2, ensure_ascii=False)


def _function_groups(result: dict) -> dict[str, list[str]]:
    """Function/procedure -> [itself, tables created in its body], for clustered output."""
    groups: dict[str, list[str]] = defaultdict(list)
    names = {o["name"] for o in result["objects"]}
    for o in sorted(result["objects"], key=lambda x: x["name"]):
        if o.get("parent") and o["parent"] in names:
            groups[o["parent"]].append(o["name"])
    return {fn: [fn, *tables] for fn, tables in sorted(groups.items())}


# Words Mermaid's flowchart grammar reserves; a node named like this breaks parsing
_MERMAID_RESERVED = {
    "end", "graph", "flowchart", "subgraph", "style", "class", "classdef", "click",
    "linkstyle", "direction", "call", "href", "default", "interpolate",
}


def _mermaid_id(name: str) -> str:
    node_id = re.sub(r"\W", "_", name)
    if node_id.lower() in _MERMAID_RESERVED or not node_id[:1].isalpha():
        node_id = f"n_{node_id}"
    return node_id


def _mermaid_text(text: str) -> str:
    """Text inside a quoted Mermaid label."""
    return text.replace('"', "#quot;")
