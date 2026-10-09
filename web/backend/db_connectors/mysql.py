"""
MySQL database connector.
"""

from typing import List, Optional, Any
import sqlalchemy as sa
from sqlalchemy import bindparam, text
from sqlalchemy.engine import URL
from . import DatabaseConnector


class MySQLConnector(DatabaseConnector):
    """MySQL database connector implementation."""

    def connect(self) -> None:
        """Establish connection to MySQL database."""
        url = self.get_connection_url()
        self.engine = sa.create_engine(url)

    def get_connection_url(self) -> URL:
        """Get MySQL connection URL."""
        config = self.config
        return URL.create(
            'mysql+pymysql',
            username=config['username'],
            password=config['password'],
            host=config['host'],
            port=int(config.get('port', 3306)),
            database=config['database'],
        )

    def extract_ddl(self, objects: Optional[List[str]] = None) -> str:
        """
        Extract DDL of tables, views, procedures and functions of the database
        via ``SHOW CREATE …``, so views and routines keep their definitions
        and the analyzer can build READ/WRITE lineage.
        """
        if not self.engine:
            raise ConnectionError("Not connected to database")

        database = self.config['database']
        params: dict[str, Any] = {'database': database}
        if objects:
            params['objects'] = list(objects)

        def query(sql: str, name_column: str) -> sa.TextClause:
            object_filter = f" AND {name_column} IN :objects" if objects else ""
            stmt = text(sql + object_filter + f" ORDER BY {name_column}")
            return stmt.bindparams(bindparam('objects', expanding=True)) if objects else stmt

        ddl_statements = []
        with self.engine.connect() as conn:
            tables = conn.execute(query(
                "SELECT TABLE_NAME AS name, TABLE_TYPE AS kind FROM information_schema.TABLES"
                " WHERE TABLE_SCHEMA = :database", 'TABLE_NAME',
            ), params).all()
            # Tables first, then views: views may read from tables and other views
            for row in sorted(tables, key=lambda r: r.kind == 'VIEW'):
                kind = 'VIEW' if row.kind == 'VIEW' else 'TABLE'
                ddl = self._show_create(conn, kind, database, row.name)
                if ddl:
                    ddl_statements.append(ddl)

            routines = conn.execute(query(
                "SELECT ROUTINE_NAME AS name, ROUTINE_TYPE AS kind FROM information_schema.ROUTINES"
                " WHERE ROUTINE_SCHEMA = :database", 'ROUTINE_NAME',
            ), params).all()
            for row in routines:
                ddl = self._show_create(conn, row.kind, database, row.name)
                if ddl:
                    ddl_statements.append(ddl)

        return '\n\n'.join(ddl_statements)

    @staticmethod
    def _show_create(conn: sa.Connection, kind: str, database: str, name: str) -> Optional[str]:
        """``SHOW CREATE <kind>``; None when the definition is not visible to this user."""
        qualified = f"{_quote_ident(database)}.{_quote_ident(name)}"
        row = conn.exec_driver_sql(f"SHOW CREATE {kind} {qualified}").mappings().first()
        if not row:
            return None
        ddl = row.get(f"Create {kind.title()}")
        return ddl.strip().rstrip(';') + ';' if ddl else None


def _quote_ident(name: str) -> str:
    return '`' + name.replace('`', '``') + '`'
