"""
ddl_lineage.parser
==================
Dialect-agnostic SQL parsing utilities.

Supports: PostgreSQL, MySQL/MariaDB, SQLite, T-SQL (SQL Server),
          Oracle PL/SQL, BigQuery standard SQL.
"""

from __future__ import annotations

import re
from .models import Column, ColumnLineage, LineageEdge

# ---------------------------------------------------------------------------
# SQL keywords that must never be treated as table / column names
# ---------------------------------------------------------------------------

SQL_KW: frozenset[str] = frozenset({
    "SELECT", "WHERE", "AND", "OR", "IN", "NOT", "NULL", "IS", "ON", "SET",
    "VALUES", "DUAL", "UNNEST", "LATERAL", "ONLY", "INTO", "CASE", "WHEN",
    "THEN", "ELSE", "END", "GROUP", "ORDER", "HAVING", "LIMIT", "OFFSET",
    "UNION", "INTERSECT", "EXCEPT", "AS", "WITH", "BY", "DISTINCT", "ALL",
    "EXISTS", "BETWEEN", "LIKE", "ILIKE", "SIMILAR", "OVER", "PARTITION",
    "ROWS", "RANGE", "PRECEDING", "FOLLOWING", "CURRENT", "UNBOUNDED",
    "TABLE", "VIEW", "FUNCTION", "PROCEDURE", "INDEX", "TRUE", "FALSE",
    "NEW", "OLD", "LANGUAGE", "RETURNS", "RETURN", "DECLARE", "BEGIN",
    "END", "IF", "ELSIF", "ELSE", "LOOP", "WHILE", "FOR", "FOREACH",
    "PERFORM", "EXECUTE", "RAISE", "NOTICE", "EXCEPTION", "USING", "FOUND",
    "RECURSIVE", "TOP", "ROWNUM", "ROWID", "NOCOUNT", "TRAN", "TRANSACTION",
    "COMMIT", "ROLLBACK", "GO", "USE", "TEMPORARY", "TEMP", "GLOBAL",
    "VOLATILE", "REPLACE", "IGNORE", "STRAIGHT_JOIN", "CROSS", "NATURAL",
    "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "APPLY", "TABLESAMPLE",
    "PIVOT", "UNPIVOT", "CONNECT", "NOCYCLE", "PRIOR", "LEVEL", "SYSDATE",
    "SYSTIMESTAMP", "NEXTVAL", "CURRVAL", "SEQUENCE", "ROWTYPE", "TYPE",
    "CURSOR", "OPEN", "FETCH", "CLOSE", "BULK", "COLLECT", "FORALL",
    "MULTISET", "PIPE", "ROW", "PIPELINED", "DETERMINISTIC",
    "PARALLEL_ENABLE", "AUTONOMOUS_TRANSACTION",
})


# ---------------------------------------------------------------------------
# Low-level SQL text utilities
# ---------------------------------------------------------------------------

def _remove_comments(sql: str) -> str:
    """Strip -- line comments and /* block */ comments."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def _split_statements(sql: str) -> list[str]:
    """
    Split a SQL script into individual statements on ';'.

    Correctly handles:
      - PostgreSQL dollar-quoting   ($tag$ … $tag$)
      - Single-quoted string literals with escaped quotes ('')
      - Nested parentheses
    """
    parts: list[str] = []
    cur: list[str] = []
    in_dollar, dollar_tag = False, ""
    in_sq = False
    depth = 0
    i = 0

    while i < len(sql):
        ch = sql[i]

        if not in_dollar and not in_sq:
            m = re.match(r"\$([^$]*)\$", sql[i:])
            if m:
                in_dollar, dollar_tag = True, m.group(0)
                cur.append(dollar_tag)
                i += len(dollar_tag)
                continue
            if ch == "'":
                in_sq = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == ";" and depth == 0:
                parts.append("".join(cur))
                cur = []
                i += 1
                continue

        elif in_sq:
            # escaped single-quote: ''
            if ch == "'" and i + 1 < len(sql) and sql[i + 1] == "'":
                cur.append("''")
                i += 2
                continue
            if ch == "'":
                in_sq = False

        elif in_dollar:
            if sql[i : i + len(dollar_tag)] == dollar_tag:
                in_dollar = False
                cur.append(dollar_tag)
                i += len(dollar_tag)
                continue

        cur.append(ch)
        i += 1

    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_object_name(stmt: str) -> tuple[str, str]:
    """
    Return (schema, name) of the first database object named after a DDL keyword.

    Handles optional double-quotes and MySQL backticks.
    """
    m = re.search(
        r"(?:TABLE|VIEW|MATERIALIZED\s+VIEW|FUNCTION|PROCEDURE)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:`?\"?(\w+)\"?`?\.)?`?\"?(\w+)\"?`?",
        stmt, re.IGNORECASE,
    )
    if m:
        return (m.group(1) or "").lower(), m.group(2).lower()
    return "", ""


def _extract_paren_body(stmt: str) -> str:
    """Return the content between the outermost ( and ) in *stmt*."""
    depth, start = 0, -1
    for i, ch in enumerate(stmt):
        if ch == "(":
            depth += 1
            if depth == 1:
                start = i + 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start != -1:
                return stmt[start:i]
    return ""


def _extract_function_body(stmt: str) -> str:
    """
    Extract the executable body from a CREATE FUNCTION / PROCEDURE statement.

    Dialect coverage:
      PostgreSQL  — $tag$ … $tag$, AS '…'
      T-SQL       — AS BEGIN … END
      MySQL       — BEGIN … END
      Oracle      — AS BEGIN … END, RETURN …
    """
    # PostgreSQL dollar-quoting
    m = re.search(r"\$([^$]*)\$(.*?)\$\1\$", stmt, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(2)
    # Single-quoted body  AS '…'
    m = re.search(r"\bAS\b\s+'(.*?)'", stmt, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    # T-SQL / Oracle:  AS BEGIN … END
    m = re.search(r"\bAS\b\s*(BEGIN\b.*)", stmt, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    # MySQL:  BEGIN … END  (no AS prefix)
    m = re.search(r"\bBEGIN\b(.*)\bEND\b", stmt, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    # Oracle / BigQuery RETURN expr
    m = re.search(r"\bRETURN\b(.+)", stmt, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    return stmt


def _cte_names(body: str) -> set[str]:
    """Return the set of CTE alias names defined with WITH … AS (…)."""
    names: set[str] = set()
    for m in re.finditer(r"\bWITH\b\s+`?\"?(\w+)\"?`?\s+AS\s*\(", body, re.IGNORECASE):
        names.add(m.group(1).lower())
    for m in re.finditer(r",\s*`?\"?(\w+)\"?`?\s+AS\s*\(", body, re.IGNORECASE):
        names.add(m.group(1).lower())
    return names


def _read_references(body: str, via: str, exclude: set[str]) -> list[LineageEdge]:
    """
    Scan *body* for FROM / JOIN references and return READ LineageEdges.

    :param via:     Name of the view / function that contains the query.
    :param exclude: Set of CTE aliases to ignore.
    """
    edges: list[LineageEdge] = []
    seen: set[str] = set()
    patterns = [
        r"\bFROM\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?(?:\s+(?:AS\s+)?`?\"?\w+\"?`?)?",
        r"\bJOIN\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?(?:\s+(?:AS\s+)?`?\"?\w+\"?`?)?",
    ]
    for pat in patterns:
        for m in re.finditer(pat, body, re.IGNORECASE):
            t = m.group(1).lower()
            if not t or t.upper() in SQL_KW or t in exclude or t in seen or t == via:
                continue
            seen.add(t)
            edges.append(LineageEdge(source=via, target=t, edge_type="READ", via=via))
    return edges


# ---------------------------------------------------------------------------
# Column-level lineage
# ---------------------------------------------------------------------------

def _parse_column_lineage(insert_stmt: str, tgt_table: str, via: str) -> list[ColumnLineage]:
    """
    Parse  INSERT INTO t (c1, c2) SELECT a, b FROM src
    and map source columns to target columns.
    """
    result: list[ColumnLineage] = []

    tgt_m = re.search(
        r"INSERT\s+(?:OR\s+\w+\s+)?(?:INTO\s+)?(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?\s*\(([^)]+)\)",
        insert_stmt, re.IGNORECASE,
    )
    if not tgt_m:
        return result

    tgt_cols = [c.strip().strip('"').strip("`").lower() for c in tgt_m.group(2).split(",")]

    sel_m = re.search(r"\bSELECT\b(.+?)\bFROM\b", insert_stmt, re.IGNORECASE | re.DOTALL)
    if not sel_m:
        return result

    src_cols_raw = [c.strip() for c in sel_m.group(1).strip().split(",")]
    from_m = re.search(r"\bFROM\s+(?:`?\"?\w+\"?`?\.)*`?\"?(\w+)\"?`?", insert_stmt, re.IGNORECASE)
    src_table = from_m.group(1).lower() if from_m else ""

    for i, tgt_col in enumerate(tgt_cols):
        if i >= len(src_cols_raw):
            break
        raw = src_cols_raw[i]
        # Strip trailing  AS alias
        alias_m = re.search(r"\bAS\b\s+`?\"?(\w+)\"?`?$", raw, re.IGNORECASE)
        if alias_m:
            raw = raw[: alias_m.start()].strip()
        # table.col form
        col_m = re.match(r"(?:`?\"?\w+\"?`?\.)?`?\"?(\w+)\"?`?$", raw.strip())
        src_col = col_m.group(1).lower() if col_m else raw.strip().lower()
        if src_col.upper() not in SQL_KW and src_table:
            result.append(ColumnLineage(
                src_table=src_table, src_col=src_col,
                tgt_table=tgt_table, tgt_col=tgt_col,
                via=via,
            ))
    return result


# ---------------------------------------------------------------------------
# Column definition parser
# ---------------------------------------------------------------------------

def _parse_table_columns(body: str) -> list[Column]:
    """
    Parse column definitions inside CREATE TABLE ( … ).

    Handles PostgreSQL, MySQL, SQLite, T-SQL column syntax including:
      - NOT NULL / NULL
      - PRIMARY KEY  (inline and table-level)
      - SERIAL / IDENTITY (auto-increment patterns)
      - UNIQUE
      - DEFAULT value
      - REFERENCES table(col)  (inline FK)
    """
    columns: list[Column] = []

    # Split at commas that are at depth 0
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Skip table-level constraints
        if re.match(r"(PRIMARY|UNIQUE|CHECK|FOREIGN|CONSTRAINT|INDEX|KEY\s)", part, re.IGNORECASE):
            continue

        # Match:  col_name  data_type  [modifiers…]
        cm = re.match(
            r'`?"?(\w+)"?`?\s+([\w\s()]+?)(?:\s+(.*))?$',
            part, re.IGNORECASE,
        )
        if not cm:
            continue

        col_name = cm.group(1).lower()
        col_type = cm.group(2).strip().upper()
        modifiers = (cm.group(3) or "").upper()

        if col_name.upper() in SQL_KW:
            continue

        col = Column(name=col_name, data_type=col_type)

        if "NOT NULL" in modifiers:
            col.nullable = False
        if "PRIMARY KEY" in modifiers or re.search(r"\bSERIAL\b|\bIDENTITY\b", col_type):
            col.pk = True
            col.nullable = False
        if "UNIQUE" in modifiers:
            col.unique = True

        # Inline REFERENCES table(col)
        ref_m = re.search(
            r"REFERENCES\s+`?\"?(\w+)\"?`?\s*(?:\(\s*`?\"?(\w+)\"?`?\s*\))?",
            part, re.IGNORECASE,
        )
        if ref_m:
            ref_t = ref_m.group(1).lower()
            ref_c = (ref_m.group(2) or "id").lower()
            col.fk_to = f"{ref_t}.{ref_c}"

        # DEFAULT
        def_m = re.search(r"DEFAULT\s+(\S+)", part, re.IGNORECASE)
        if def_m:
            col.default = def_m.group(1).strip("'\"")

        columns.append(col)

    return columns


# ---------------------------------------------------------------------------
# Convenience alias (matches the JS widget naming)
# ---------------------------------------------------------------------------

def parseDDL(ddl: str) -> dict:
    """Parse DDL and return a raw dict (same format as DDLLineageAnalyzer.analyze)."""
    from .analyzer import DDLLineageAnalyzer
    a = DDLLineageAnalyzer()
    return a.analyze(ddl)
