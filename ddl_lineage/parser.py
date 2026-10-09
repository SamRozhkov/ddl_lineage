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


# Oracle PL/SQL routine header, up to the IS / AS that opens its declarations
_PLSQL_HEAD_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?(?:PROCEDURE|FUNCTION)\s+"
    r"(?:[\w$#\"]+\s*\.\s*)?[\w$#\"]+\s*"
    r"(?:\((?:[^()]|\([^()]*\))*\)\s*)?"
    r"(?:RETURN\s+[\w.%]+(?:\s*\([^)]*\))?\s*)?"
    r"(?:(?:AUTHID\s+\w+|DETERMINISTIC|PIPELINED|PARALLEL_ENABLE|RESULT_CACHE)\s*)*"
    r"(?P<kw>IS|AS)\b",
    re.IGNORECASE,
)
# What may follow AS in PL/SQL (T-SQL's "AS SET NOCOUNT ON; …" must not match)
_PLSQL_AFTER_AS_RE = re.compile(
    r"\s*(?:BEGIN\b|CURSOR\b|TYPE\b|PRAGMA\b|PROCEDURE\b|FUNCTION\b"
    r"|[A-Za-z_]\w*\s+(?:CONSTANT\s+)?[A-Za-z_][\w.%]*(?:\s*\([^)]*\))?\s*(?:;|:=|NOT\s+NULL|DEFAULT\b))",
    re.IGNORECASE,
)


def _plsql_body_start(text: str, pos: int = 0) -> int | None:
    """
    Index just after the IS / AS of an Oracle-style routine header starting at
    *pos*, or None (PostgreSQL ``AS $$``, MySQL, T-SQL ``AS <statement>``…).
    """
    m = _PLSQL_HEAD_RE.match(text, pos)
    if not m:
        return None
    rest = text[m.end():]
    if re.match(r"\s*(?:\$|'|LANGUAGE\b|EXTERNAL\b)", rest, re.IGNORECASE):
        return None
    if m.group("kw").upper() == "AS" and not _PLSQL_AFTER_AS_RE.match(rest):
        return None
    return m.end()


_DOLLAR_TAG_RE = re.compile(r"\$([^$]*)\$")
_SLASH_LINE_RE = re.compile(r"[ \t]*/[ \t]*(?:\n|$)")

# Block keywords for _split_statements. A transaction ``BEGIN;`` / ``BEGIN
# TRANSACTION`` is not a block, and ``END IF`` / ``END LOOP`` … close blocks
# whose openers are not counted.
_BLOCK_WORD_RE = re.compile(
    r"(?P<open>BEGIN\b(?!\s*(?:;|TRANSACTION\b|TRAN\b|WORK\b|ISOLATION\b|DISTRIBUTED\b))|CASE\b)"
    r"|(?P<close>END\b(?!\s+(?:IF|LOOP|WHILE|REPEAT|FOR)\b))"
    r"|\w+",
    re.IGNORECASE,
)


def _split_statements(sql: str, track_blocks: bool = True) -> list[str]:
    """
    Split a SQL script into individual statements on ';'.

    Correctly handles:
      - PostgreSQL dollar-quoting   ($tag$ … $tag$)
      - Single-quoted string literals with escaped quotes ('')
      - Nested parentheses
      - BEGIN … END / CASE … END blocks of routines without dollar-quoting
        (MySQL, T-SQL), so their inner ';' do not end the statement.
        Pass ``track_blocks=False`` to split a routine body into its statements.
    """
    parts: list[str] = []
    cur: list[str] = []
    in_dollar, dollar_tag = False, ""
    in_sq = False
    depth = 0
    blocks = 0
    pending_begin = False   # PL/SQL IS/AS already opened the block its BEGIN belongs to
    at_start = True
    i = 0

    def flush() -> None:
        nonlocal cur, at_start
        if "".join(cur).strip():
            parts.append("".join(cur))
        cur = []
        at_start = True

    while i < len(sql):
        ch = sql[i]

        if track_blocks and not in_dollar and not in_sq and (i == 0 or sql[i - 1] == "\n"):
            # SQL*Plus "/" line ends the statement
            slash = _SLASH_LINE_RE.match(sql, i)
            if slash:
                flush()
                depth = blocks = 0
                pending_begin = False
                i = slash.end()
                continue

        if track_blocks and at_start and not in_dollar and not in_sq and ch.isalpha():
            at_start = False
            body_start = _plsql_body_start(sql, i)
            if body_start is not None:
                cur.append(sql[i:body_start])
                i = body_start
                blocks += 1
                pending_begin = True
                continue

        if not ch.isspace():
            at_start = False

        if not in_dollar and not in_sq:
            m = _DOLLAR_TAG_RE.match(sql, i) if ch == "$" else None
            if m:
                in_dollar, dollar_tag = True, m.group(0)
                cur.append(dollar_tag)
                i += len(dollar_tag)
                continue
            if track_blocks and ch.isalpha() and (i == 0 or not _is_identifier_char(sql[i - 1])):
                word = _BLOCK_WORD_RE.match(sql, i)
                if word:
                    if word.group("open"):
                        if pending_begin and word.group(0).upper() == "BEGIN":
                            pending_begin = False
                        else:
                            blocks += 1
                    elif word.group("close"):
                        blocks = max(0, blocks - 1)
                    cur.append(word.group(0))
                    i = word.end()
                    continue
            if ch == "'":
                in_sq = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == ";" and depth == 0 and blocks == 0:
                parts.append("".join(cur))
                cur = []
                at_start = True
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


# MySQL options between CREATE and the object kind (SHOW CREATE / mysqldump)
_CREATE_OPTIONS_RE = re.compile(
    r"^(\s*CREATE\s+(?:OR\s+REPLACE\s+)?)"
    r"(?:(?:ALGORITHM\s*=\s*\w+"
    r"|DEFINER\s*=\s*(?:`[^`]*`|'[^']*'|\"[^\"]*\"|\w+)"
    r"(?:\s*@\s*(?:`[^`]*`|'[^']*'|\"[^\"]*\"|[\w.%-]+))?"
    r"|SQL\s+SECURITY\s+\w+)\s+)+",
    re.IGNORECASE,
)


def _strip_create_options(stmt: str) -> str:
    """``CREATE DEFINER=`u`@`%` SQL SECURITY DEFINER VIEW v`` -> ``CREATE VIEW v``"""
    return _CREATE_OPTIONS_RE.sub(r"\1", stmt, count=1)


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


def _extract_table_definition_body(stmt: str) -> str:
    """Return CREATE TABLE column definitions when they immediately follow the table name."""
    m = re.search(
        r"\bTABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:`?\"?\w+\"?`?\.)?`?\"?\w+\"?`?",
        stmt,
        re.IGNORECASE,
    )
    if not m:
        return ""

    i = m.end()
    while i < len(stmt) and stmt[i].isspace():
        i += 1
    if i >= len(stmt) or stmt[i] != "(":
        return ""

    return _extract_balanced_paren_body(stmt, i)


def _extract_balanced_paren_body(text: str, start: int) -> str:
    """Return the body of a balanced parenthesized block starting at *start*."""
    depth = 0
    in_sq = False
    in_dq = False
    in_bt = False
    body_start = start + 1
    i = start

    while i < len(text):
        ch = text[i]

        if in_sq:
            if ch == "'" and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            if ch == "'":
                in_sq = False
        elif in_dq:
            if ch == '"':
                in_dq = False
        elif in_bt:
            if ch == "`":
                in_bt = False
        else:
            if ch == "'":
                in_sq = True
            elif ch == '"':
                in_dq = True
            elif ch == "`":
                in_bt = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[body_start:i]

        i += 1

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
    # Oracle PL/SQL: everything after IS / AS, declarations (cursors) included
    head = re.match(r"\s*", stmt).end()
    body_start = _plsql_body_start(stmt, head)
    if body_start is not None:
        return stmt[body_start:]
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


_IDENT_TOKEN = r'(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_][\w$]*)'
_TABLE_REF_RE = re.compile(rf"\s*((?:{_IDENT_TOKEN}\s*\.\s*)*)({_IDENT_TOKEN})")
_ALIAS_RE = re.compile(rf"\s+(?:AS\s+)?({_IDENT_TOKEN})", re.IGNORECASE)
# Words that can follow a table reference and are not its alias
_NOT_ALIAS = SQL_KW | {"JOIN", "WINDOW", "RETURNING", "QUALIFY", "SAMPLE", "STRAIGHT_JOIN"}
# FROM inside these calls is part of the syntax, not a table source
_FROM_FUNCTIONS = {"EXTRACT", "SUBSTRING", "SUBSTR", "TRIM", "OVERLAY", "POSITION"}


def _unquote_ident(token: str) -> str:
    return token[1:-1] if token[:1] in '`"[' else token


def _enclosing_call(text: str, pos: int) -> str:
    """Upper-cased name of the function whose parentheses enclose *pos* ('' if none)."""
    depth = 0
    for i in range(pos - 1, -1, -1):
        if text[i] == ")":
            depth += 1
        elif text[i] == "(":
            if depth == 0:
                m = re.search(r"(\w+)\s*$", text[:i])
                return m.group(1).upper() if m else ""
            depth -= 1
    return ""


def _skip_parens(text: str, start: int) -> int:
    """Index just after the parenthesis group opened at *start*."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _read_references(body: str, via: str, exclude: set[str]) -> list[LineageEdge]:
    """
    Scan *body* for FROM / JOIN references and return READ LineageEdges.

    Understands comma-separated FROM lists, parenthesised join trees
    (``FROM ((a JOIN b ON …) JOIN c ON …)`` as MySQL stores views), schema-
    qualified and quoted names, and skips subqueries, table functions and the
    ``FROM`` keyword of EXTRACT / SUBSTRING / TRIM ….

    :param via:     Name of the view / function that contains the query.
    :param exclude: Set of CTE aliases to ignore.
    """
    edges: list[LineageEdge] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        # A quoted name is an identifier even when it spells a keyword ("order")
        quoted = token[:1] in '`"['
        t = _unquote_ident(token).lower()
        if not t or (not quoted and t.upper() in SQL_KW) or t in exclude or t in seen or t == via:
            return
        seen.add(t)
        edges.append(LineageEdge(source=via, target=t, edge_type="READ", via=via))

    for kw in re.finditer(r"\b(FROM|JOIN)\b", body, re.IGNORECASE):
        is_from = kw.group(1).upper() == "FROM"
        if is_from and _enclosing_call(body, kw.start()) in _FROM_FUNCTIONS:
            continue
        i = kw.end()
        while True:
            # Opening parentheses of a join tree; a subquery is skipped whole
            while True:
                j = len(body) - len(body[i:].lstrip())
                if j < len(body) and body[j] == "(":
                    if re.match(r"\(\s*(?:SELECT|WITH|VALUES)\b", body[j:], re.IGNORECASE):
                        i = _skip_parens(body, j)
                        break
                    i = j + 1
                    continue
                i = j
                tm = _TABLE_REF_RE.match(body, i)
                if tm and _unquote_ident(tm.group(2)).upper() in ("ONLY", "LATERAL"):
                    i = tm.end()
                    continue
                if tm:
                    i = tm.end()
                    rest = body[i:].lstrip()
                    if rest.startswith("("):          # table function: unnest(…), generate_series(…)
                        i = _skip_parens(body, len(body) - len(rest))
                    elif _unquote_ident(tm.group(2)).upper() not in ("SELECT", "WITH", "VALUES"):
                        add(tm.group(2))
                break

            am = _ALIAS_RE.match(body, i)
            if am and _unquote_ident(am.group(1)).upper() not in _NOT_ALIAS:
                i = am.end()
                if body[i:].lstrip().startswith("("):  # alias column list: vals(x, y)
                    i = _skip_parens(body, len(body) - len(body[i:].lstrip()))

            nxt = re.match(r"\s*,", body[i:])
            if not (is_from and nxt and _enclosing_call(body, kw.start()) == _enclosing_call(body, i)):
                break
            i += nxt.end()
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

# Optionally schema-qualified, optionally quoted identifier; group 1 = bare name
_QUALIFIED_IDENT = r"(?:[`\"\[]?\w+[`\"\]]?\.)*[`\"\[]?(\w+)[`\"\]]?"
_IDENT_LIST = r"\(([^)]*)\)"

# First keyword after a column's data type
_COLUMN_MODIFIER_RE = re.compile(
    r"\b(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|DEFAULT|REFERENCES|CHECK|CONSTRAINT|"
    r"COLLATE|GENERATED|AUTO_INCREMENT|AUTOINCREMENT|IDENTITY|COMMENT|ON\s+UPDATE|"
    r"CHARACTER\s+SET|CHARSET)\b",
    re.IGNORECASE,
)
_DEFAULT_RE = re.compile(
    r"\bDEFAULT\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|REFERENCES|CHECK|"
    r"CONSTRAINT|COLLATE|GENERATED|ON\s+UPDATE|COMMENT|AUTO_INCREMENT)\b|\s*$)",
    re.IGNORECASE | re.DOTALL,
)
_INLINE_REFERENCES_RE = re.compile(
    rf"\bREFERENCES\s+{_QUALIFIED_IDENT}\s*(?:\(\s*[`\"\[]?(\w+)[`\"\]]?\s*\))?",
    re.IGNORECASE,
)
_FOREIGN_KEY_RE = re.compile(
    rf"\bFOREIGN\s+KEY\s*(?:[`\"\[]?\w+[`\"\]]?\s*)?{_IDENT_LIST}\s*"
    rf"REFERENCES\s+{_QUALIFIED_IDENT}\s*(?:{_IDENT_LIST})?",
    re.IGNORECASE,
)
_TABLE_CONSTRAINT_RE = re.compile(
    r"^(?:CONSTRAINT\s+[`\"\[]?\w+[`\"\]]?\s+)?"
    r"(?P<kind>PRIMARY\s+KEY|UNIQUE(?:\s+(?:KEY|INDEX))?|FOREIGN\s+KEY|CHECK|EXCLUDE)"
    r"(?:\s+[`\"\[]?\w+[`\"\]]?)?\s*(?:\((?P<cols>[^)]*)\))?",
    re.IGNORECASE,
)


def _ident_list(text: str) -> list[str]:
    return [c.strip().strip('`"[]').lower() for c in text.split(",") if c.strip()]


def _parse_foreign_keys(text: str) -> list[tuple[list[str], str, list[str]]]:
    """
    Find ``FOREIGN KEY (cols) REFERENCES [schema.]table [(ref_cols)]`` clauses.

    Returns ``(columns, referenced_table, referenced_columns)`` triples;
    missing referenced columns default to ``id`` (single column) or to the
    same column names.
    """
    fks = []
    for m in _FOREIGN_KEY_RE.finditer(text):
        cols = _ident_list(m.group(1))
        ref_cols = _ident_list(m.group(3) or "") or (["id"] if len(cols) == 1 else cols)
        fks.append((cols, m.group(2).lower(), ref_cols))
    return fks


def _find_top_level(pattern: re.Pattern, text: str) -> re.Match | None:
    """First match of *pattern* that is outside parentheses and string literals."""
    for m in pattern.finditer(text):
        prefix = re.sub(r"'(?:[^']|'')*'", "", text[:m.start()])
        if prefix.count("'") % 2 == 0 and prefix.count("(") == prefix.count(")"):
            return m
    return None


def _normalize_type(data_type: str) -> str:
    t = re.sub(r"\s+", " ", data_type.strip()).upper()
    return re.sub(r"\s*([(),])\s*", r"\1", t)


def _clean_default(expr: str) -> str:
    expr = expr.strip()
    # 'new'::character varying  ->  'new'
    expr = re.sub(r"^('(?:[^']|'')*')::[\w\s]+(?:\([^)]*\))?$", r"\1", expr)
    if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "'\"":
        expr = expr[1:-1]
    return expr


def _parse_table_columns(body: str) -> list[Column]:
    """
    Parse column definitions inside CREATE TABLE ( … ).

    Handles PostgreSQL, MySQL, SQLite, T-SQL column syntax including:
      - multi-word / parameterised types (``character varying(255)``, ``numeric(10,2)``)
      - NOT NULL / NULL
      - PRIMARY KEY  (inline and table-level, also composite)
      - SERIAL / IDENTITY (auto-increment patterns)
      - UNIQUE  (inline and single-column table-level)
      - DEFAULT value
      - REFERENCES [schema.]table(col)  (inline FK)
      - FOREIGN KEY (cols) REFERENCES [schema.]table(cols)  (table-level FK)
    """
    columns: list[Column] = []
    constraints: list[tuple[str, str]] = []

    for part in _split_top_level_csv(body):
        part = part.strip()
        if not part:
            continue

        con = _TABLE_CONSTRAINT_RE.match(part)
        if con:
            constraints.append((con.group("kind").upper(), part))
            continue
        if re.match(r"(INDEX|KEY|FULLTEXT|SPATIAL|LIKE|PERIOD)\b", part, re.IGNORECASE):
            continue

        cm = re.match(r'[`"\[]?(\w+)[`"\]]?(?:\s+(.*))?$', part, re.IGNORECASE | re.DOTALL)
        if not cm:
            continue
        col_name = cm.group(1).lower()
        if col_name.upper() in SQL_KW:
            continue

        rest = cm.group(2) or ""
        mod = _find_top_level(_COLUMN_MODIFIER_RE, rest)
        col_type = _normalize_type(rest[:mod.start()] if mod else rest)
        modifiers = re.sub(r"\s+", " ", rest[mod.start():]).upper() if mod else ""

        col = Column(name=col_name, data_type=col_type)

        if "NOT NULL" in modifiers:
            col.nullable = False
        if (
            "PRIMARY KEY" in modifiers
            or re.search(r"\bSERIAL\b|\bIDENTITY\b", col_type)
            or re.search(r"\bIDENTITY\b", modifiers)
        ):
            col.pk = True
            col.nullable = False
        if re.search(r"\bUNIQUE\b", modifiers):
            col.unique = True

        ref_m = _INLINE_REFERENCES_RE.search(rest)
        if ref_m:
            col.fk_to = f"{ref_m.group(1).lower()}.{(ref_m.group(2) or 'id').lower()}"

        def_m = _DEFAULT_RE.search(rest)
        if def_m and def_m.group(1).strip().upper() != "NULL":
            col.default = _clean_default(def_m.group(1))

        columns.append(col)

    by_name = {c.name: c for c in columns}
    for kind, part in constraints:
        if kind == "FOREIGN KEY":
            for cols, ref_table, ref_cols in _parse_foreign_keys(part):
                for col_name, ref_col in zip(cols, ref_cols):
                    if col_name in by_name:
                        by_name[col_name].fk_to = f"{ref_table}.{ref_col}"
            continue
        cols_m = _TABLE_CONSTRAINT_RE.match(part)
        names = _ident_list(cols_m.group("cols") or "") if cols_m else []
        if kind == "PRIMARY KEY":
            for col_name in names:
                if col_name in by_name:
                    by_name[col_name].pk = True
                    by_name[col_name].nullable = False
        elif kind.startswith("UNIQUE") and len(names) == 1 and names[0] in by_name:
            by_name[names[0]].unique = True

    return columns


def _parse_ctas_columns(stmt: str) -> list[Column]:
    """Infer CREATE TABLE AS SELECT output columns from the SELECT list."""
    return _parse_select_columns(stmt)


def _parse_select_columns(stmt: str) -> list[Column]:
    """Infer output columns from the top-level SELECT list in *stmt*."""
    select_list = _extract_select_list(stmt)
    if not select_list:
        return []

    columns: list[Column] = []
    used_names: set[str] = set()
    for index, expr in enumerate(_split_top_level_csv(select_list), start=1):
        name = _select_expression_name(expr, index)
        if name in used_names:
            name = f"{name}_{index}"
        used_names.add(name)
        columns.append(Column(name=name))

    return columns


def _parse_returns_table_columns(stmt: str) -> list[Column]:
    """Parse column declarations from a PostgreSQL RETURNS TABLE (...) clause."""
    m = re.search(r"\bRETURNS\s+TABLE\s*\(", stmt, re.IGNORECASE)
    if not m:
        return []

    body = _extract_balanced_paren_body(stmt, m.end() - 1)
    return _parse_table_columns(body)


def _extract_select_list(stmt: str) -> str:
    start = _find_top_level_keyword(stmt, 0, {"SELECT"})
    if start == -1:
        return ""

    start += len("SELECT")
    end = _find_top_level_keyword(
        stmt,
        start,
        {"FROM", "WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION", "INTERSECT", "EXCEPT"},
    )
    return stmt[start:end].strip() if end != -1 else stmt[start:].strip().rstrip(";")


def _find_top_level_keyword(text: str, start: int, keywords: set[str]) -> int:
    depth = 0
    in_sq = False
    in_dq = False
    in_bt = False
    i = start

    while i < len(text):
        ch = text[i]
        if in_sq:
            if ch == "'" and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            if ch == "'":
                in_sq = False
        elif in_dq:
            if ch == '"':
                in_dq = False
        elif in_bt:
            if ch == "`":
                in_bt = False
        else:
            if ch == "'":
                in_sq = True
            elif ch == '"':
                in_dq = True
            elif ch == "`":
                in_bt = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0 and (i == 0 or not _is_identifier_char(text[i - 1])):
                for keyword in keywords:
                    if (
                        text[i : i + len(keyword)].upper() == keyword
                        and (i + len(keyword) == len(text) or not _is_identifier_char(text[i + len(keyword)]))
                    ):
                        return i
        i += 1

    return -1


def _split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_sq = False
    in_dq = False
    in_bt = False
    i = 0

    while i < len(text):
        ch = text[i]
        if in_sq:
            cur.append(ch)
            if ch == "'" and i + 1 < len(text) and text[i + 1] == "'":
                cur.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                in_sq = False
        elif in_dq:
            cur.append(ch)
            if ch == '"':
                in_dq = False
        elif in_bt:
            cur.append(ch)
            if ch == "`":
                in_bt = False
        else:
            if ch == "'":
                in_sq = True
                cur.append(ch)
            elif ch == '"':
                in_dq = True
                cur.append(ch)
            elif ch == "`":
                in_bt = True
                cur.append(ch)
            elif ch == "(":
                depth += 1
                cur.append(ch)
            elif ch == ")":
                depth = max(0, depth - 1)
                cur.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        i += 1

    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _select_expression_name(expr: str, index: int) -> str:
    expr = expr.strip().rstrip(";")
    alias_m = re.search(r"\bAS\s+`?\"?(\w+)\"?`?$", expr, re.IGNORECASE)
    if alias_m:
        return alias_m.group(1).lower()

    trailing_alias_m = re.search(r"\s+`?\"?(\w+)\"?`?$", expr)
    if trailing_alias_m:
        alias = trailing_alias_m.group(1)
        prefix = expr[: trailing_alias_m.start()].strip()
        if prefix and alias.upper() not in SQL_KW:
            return alias.lower()

    identifier_m = re.match(r"(?:`?\"?\w+\"?`?\.)?`?\"?(\w+)\"?`?$", expr)
    if identifier_m:
        return identifier_m.group(1).lower()

    return f"column_{index}"


def _is_identifier_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


# ---------------------------------------------------------------------------
# Convenience alias (matches the JS widget naming)
# ---------------------------------------------------------------------------

def parseDDL(ddl: str) -> dict:
    """Parse DDL and return a raw dict (same format as DDLLineageAnalyzer.analyze)."""
    from .analyzer import DDLLineageAnalyzer
    a = DDLLineageAnalyzer()
    return a.analyze(ddl)
