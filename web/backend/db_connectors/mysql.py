"""
MySQL database connector.
"""

from typing import List, Optional, Dict, Any
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
        """Extract DDL from MySQL database."""
        if not self.engine:
            raise ConnectionError("Not connected to database")

        database = self.config['database']
        object_filter = ""
        params: dict[str, Any] = {'database': database}
        if objects:
            object_filter = " AND TABLE_NAME IN :objects"
            params['objects'] = list(objects)

        ddl_statements = []

        with self.engine.connect() as conn:
            # Extract tables and views
            query = text(f"""
            SELECT
                TABLE_SCHEMA,
                TABLE_NAME,
                TABLE_TYPE,
                CONCAT(
                    'CREATE ',
                    CASE WHEN TABLE_TYPE = 'VIEW' THEN 'VIEW' ELSE 'TABLE' END,
                    ' ', TABLE_SCHEMA, '.', TABLE_NAME, ' (',
                    GROUP_CONCAT(
                        CONCAT(
                            COLUMN_NAME, ' ', DATA_TYPE,
                            CASE WHEN IS_NULLABLE = 'NO' THEN ' NOT NULL' ELSE '' END,
                            CASE WHEN COLUMN_DEFAULT IS NOT NULL THEN CONCAT(' DEFAULT ', COLUMN_DEFAULT) ELSE '' END
                        ) SEPARATOR ', '
                    ),
                    ')'
                ) as ddl
            FROM information_schema.COLUMNS c
            JOIN information_schema.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
                AND c.TABLE_SCHEMA = t.TABLE_SCHEMA
            WHERE t.TABLE_SCHEMA = :database {object_filter}
            GROUP BY TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            ORDER BY TABLE_NAME;
            """)
            if objects:
                query = query.bindparams(bindparam('objects', expanding=True))

            result = conn.execute(query, params)
            for row in result:
                ddl_statements.append(row.ddl)

            # Extract foreign keys
            fk_object_filter = " AND k.TABLE_NAME IN :objects" if objects else ""
            fk_query = text(f"""
            SELECT
                CONCAT(
                    'ALTER TABLE ', k.TABLE_SCHEMA, '.', k.TABLE_NAME,
                    ' ADD CONSTRAINT ', k.CONSTRAINT_NAME,
                    ' FOREIGN KEY (', GROUP_CONCAT(k.COLUMN_NAME SEPARATOR ', '),
                    ') REFERENCES ', k.REFERENCED_TABLE_SCHEMA, '.', k.REFERENCED_TABLE_NAME,
                    ' (', GROUP_CONCAT(k.REFERENCED_COLUMN_NAME SEPARATOR ', '), ');'
                ) as fk_ddl
            FROM information_schema.KEY_COLUMN_USAGE k
            WHERE k.REFERENCED_TABLE_NAME IS NOT NULL AND k.TABLE_SCHEMA = :database {fk_object_filter}
            GROUP BY k.TABLE_SCHEMA, k.TABLE_NAME, k.CONSTRAINT_NAME, k.REFERENCED_TABLE_SCHEMA, k.REFERENCED_TABLE_NAME;
            """)
            if objects:
                fk_query = fk_query.bindparams(bindparam('objects', expanding=True))

            fk_result = conn.execute(fk_query, params)
            for row in fk_result:
                ddl_statements.append(row.fk_ddl)

        return '\n\n'.join(ddl_statements)
