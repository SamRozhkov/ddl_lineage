"""
PostgreSQL database connector.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import bindparam, text
from sqlalchemy.engine import URL

from . import DatabaseConnector

# Objects owned by an extension (e.g. pg_stat_statements) are not user DDL
_NOT_FROM_EXTENSION = """
    NOT EXISTS (
        SELECT 1 FROM pg_depend d
        WHERE d.classid = {catalog}::regclass AND d.objid = {oid} AND d.deptype = 'e'
    )
"""

_TABLES_SQL = f"""
SELECT c.oid, n.nspname AS schema, c.relname AS name,
       (SELECT string_agg(quote_ident(pn.nspname) || '.' || quote_ident(p.relname), ', ' ORDER BY i.inhseqno)
          FROM pg_inherits i
          JOIN pg_class p ON p.oid = i.inhparent
          JOIN pg_namespace pn ON pn.oid = p.relnamespace
         WHERE i.inhrelid = c.oid) AS inherits
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :schema AND c.relkind IN ('r', 'p') AND NOT c.relispartition
  AND {_NOT_FROM_EXTENSION.format(catalog="'pg_class'", oid='c.oid')}
  {{object_filter}}
ORDER BY c.relname
"""

# Only columns declared on the table itself; inherited ones come via INHERITS
_COLUMNS_SQL = """
SELECT a.attrelid AS oid, quote_ident(a.attname) AS name,
       format_type(a.atttypid, a.atttypmod) AS type,
       a.attnotnull AS not_null,
       pg_get_expr(d.adbin, d.adrelid) AS default_expr
FROM pg_attribute a
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attrelid = ANY(:oids) AND a.attnum > 0 AND NOT a.attisdropped AND a.attislocal
ORDER BY a.attrelid, a.attnum
"""

_CONSTRAINTS_SQL = """
SELECT conrelid AS oid, quote_ident(conname) AS name, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = ANY(:oids) AND contype IN ('p', 'u', 'f', 'c') AND conislocal
ORDER BY conrelid, contype = 'f', conname
"""

_VIEWS_SQL = f"""
SELECT n.nspname AS schema, c.relname AS name, c.relkind AS kind,
       pg_get_viewdef(c.oid, true) AS definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :schema AND c.relkind IN ('v', 'm')
  AND {_NOT_FROM_EXTENSION.format(catalog="'pg_class'", oid='c.oid')}
  {{object_filter}}
ORDER BY c.oid
"""

_ROUTINES_SQL = f"""
SELECT p.proname AS name, pg_get_functiondef(p.oid) AS definition
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = :schema AND p.prokind IN ('f', 'p')
  AND {_NOT_FROM_EXTENSION.format(catalog="'pg_proc'", oid='p.oid')}
  {{object_filter}}
ORDER BY p.proname, p.oid
"""


def _qualified(schema: str, name: str) -> str:
    return f"{_quote_ident(schema)}.{_quote_ident(name)}"


def _quote_ident(name: str) -> str:
    if name.isidentifier() and name == name.lower():
        return name
    return '"' + name.replace('"', '""') + '"'


class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL database connector implementation."""

    def connect(self) -> None:
        """Establish connection to PostgreSQL database."""
        url = self.get_connection_url()
        self.engine = sa.create_engine(url)

    def get_connection_url(self) -> URL:
        """Get PostgreSQL connection URL."""
        config = self.config
        return URL.create(
            'postgresql+psycopg2',
            username=config['username'],
            password=config['password'],
            host=config['host'],
            port=int(config.get('port', 5432)),
            database=config['database'],
        )

    def extract_ddl(self, objects: list[str] | None = None) -> str:
        """
        Extract DDL of tables, views, materialized views, functions and
        procedures of one schema (``config['schema']``, default ``public``).

        Views and routines are dumped with their full definitions so that the
        analyzer can build READ/WRITE lineage, not just the column lists.
        """
        if not self.engine:
            raise ConnectionError("Not connected to database")

        schema = self.config.get('schema') or 'public'
        params: dict[str, Any] = {'schema': schema}
        if objects:
            params['objects'] = list(objects)

        def query(sql: str, name_column: str) -> sa.TextClause:
            object_filter = f"AND {name_column} IN :objects" if objects else ""
            stmt = text(sql.format(object_filter=object_filter))
            return stmt.bindparams(bindparam('objects', expanding=True)) if objects else stmt

        with self.engine.connect() as conn:
            tables = conn.execute(query(_TABLES_SQL, 'c.relname'), params).all()
            ddl_statements = self._table_ddl(conn, tables)

            for row in conn.execute(query(_VIEWS_SQL, 'c.relname'), params):
                kind = 'MATERIALIZED VIEW' if row.kind == 'm' else 'VIEW'
                definition = row.definition.strip().rstrip(';')
                ddl_statements.append(f"CREATE {kind} {_qualified(row.schema, row.name)} AS\n{definition};")

            for row in conn.execute(query(_ROUTINES_SQL, 'p.proname'), params):
                ddl_statements.append(row.definition.strip().rstrip(';') + ';')

        return '\n\n'.join(ddl_statements)

    @staticmethod
    def _table_ddl(conn: sa.Connection, tables: list) -> list[str]:
        if not tables:
            return []
        oids = [t.oid for t in tables]
        columns: dict[int, list[str]] = {oid: [] for oid in oids}
        for col in conn.execute(text(_COLUMNS_SQL), {'oids': oids}):
            line = f"{col.name} {col.type}"
            if col.not_null:
                line += " NOT NULL"
            if col.default_expr is not None:
                line += f" DEFAULT {col.default_expr}"
            columns[col.oid].append(line)
        for con in conn.execute(text(_CONSTRAINTS_SQL), {'oids': oids}):
            columns[con.oid].append(f"CONSTRAINT {con.name} {con.definition}")

        ddl = []
        for t in tables:
            body = ",\n    ".join(columns[t.oid])
            inherits = f" INHERITS ({t.inherits})" if t.inherits else ""
            ddl.append(f"CREATE TABLE {_qualified(t.schema, t.name)} (\n    {body}\n){inherits};")
        return ddl
