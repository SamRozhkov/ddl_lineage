"""
PostgreSQL database connector.
"""

from typing import List, Optional, Dict, Any
import sqlalchemy as sa
from sqlalchemy import bindparam, text
from sqlalchemy.engine import URL
from . import DatabaseConnector


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

    def extract_ddl(self, objects: Optional[List[str]] = None) -> str:
        """Extract DDL from PostgreSQL database."""
        if not self.engine:
            raise ConnectionError("Not connected to database")

        schema = self.config.get('schema', 'public')
        object_filter = ""
        params: dict[str, Any] = {'schema': schema}
        if objects:
            object_filter = " AND table_name IN :objects"
            params['objects'] = list(objects)

        ddl_statements = []

        with self.engine.connect() as conn:
            # Extract tables and views
            query = text(f"""
            SELECT
                table_schema,
                table_name,
                table_type,
                'CREATE ' || CASE WHEN table_type = 'VIEW' THEN 'VIEW' ELSE 'TABLE' END ||
                ' ' || table_schema || '.' || table_name || ' (' ||
                string_agg(
                    column_name || ' ' || data_type ||
                    CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
                    CASE WHEN column_default IS NOT NULL THEN ' DEFAULT ' || column_default ELSE '' END,
                    ', '
                ) || ')' as ddl
            FROM information_schema.columns c
            JOIN information_schema.tables t ON c.table_name = t.table_name
                AND c.table_schema = t.table_schema
            WHERE t.table_schema = :schema {object_filter}
            GROUP BY table_schema, table_name, table_type
            ORDER BY table_name;
            """)
            if objects:
                query = query.bindparams(bindparam('objects', expanding=True))

            result = conn.execute(query, params)
            for row in result:
                ddl_statements.append(row.ddl)

            # Extract foreign keys
            fk_object_filter = " AND tc.table_name IN :objects" if objects else ""
            fk_query = text(f"""
            SELECT
                'ALTER TABLE ' || tc.table_schema || '.' || tc.table_name ||
                ' ADD CONSTRAINT ' || tc.constraint_name ||
                ' FOREIGN KEY (' || string_agg(kcu.column_name, ', ') || ')' ||
                ' REFERENCES ' || ccu.table_schema || '.' || ccu.table_name ||
                ' (' || string_agg(ccu.column_name, ', ') || ');' as fk_ddl
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = :schema {fk_object_filter}
            GROUP BY tc.table_schema, tc.table_name, tc.constraint_name, ccu.table_schema, ccu.table_name;
            """)
            if objects:
                fk_query = fk_query.bindparams(bindparam('objects', expanding=True))

            fk_result = conn.execute(fk_query, params)
            for row in fk_result:
                ddl_statements.append(row.fk_ddl)

        return '\n\n'.join(ddl_statements)
