"""
PostgreSQL database connector.
"""

from typing import List, Optional, Dict, Any
import sqlalchemy as sa
from sqlalchemy import text
from . import DatabaseConnector


class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL database connector implementation."""

    def connect(self) -> None:
        """Establish connection to PostgreSQL database."""
        url = self.get_connection_url()
        self.engine = sa.create_engine(url)

    def get_connection_url(self) -> str:
        """Get PostgreSQL connection URL."""
        config = self.config
        return (
            f"postgresql://{config['username']}:{config['password']}"
            f"@{config['host']}:{config['port']}/{config['database']}"
        )

    def extract_ddl(self, objects: Optional[List[str]] = None) -> str:
        """Extract DDL from PostgreSQL database."""
        if not self.engine:
            raise ConnectionError("Not connected to database")

        schema = self.config.get('schema', 'public')
        object_filter = ""
        if objects:
            quoted_objects = [f"'{obj}'" for obj in objects]
            object_filter = f" AND table_name IN ({','.join(quoted_objects)})"

        ddl_statements = []

        with self.engine.connect() as conn:
            # Extract tables and views
            query = f"""
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
            WHERE t.table_schema = '{schema}' {object_filter}
            GROUP BY table_schema, table_name, table_type
            ORDER BY table_name;
            """

            result = conn.execute(text(query))
            for row in result:
                ddl_statements.append(row.ddl)

            # Extract foreign keys
            fk_query = f"""
            SELECT
                'ALTER TABLE ' || tc.table_schema || '.' || tc.table_name ||
                ' ADD CONSTRAINT ' || tc.constraint_name ||
                ' FOREIGN KEY (' || string_agg(kcu.column_name, ', ') || ')' ||
                ' REFERENCES ' || ccu.table_schema || '.' || ccu.table_name ||
                ' (' || string_agg(ccu.column_name, ', ') || ');' as fk_ddl
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = '{schema}' {object_filter.replace('table_name', 'tc.table_name')}
            GROUP BY tc.table_schema, tc.table_name, tc.constraint_name, ccu.table_schema, ccu.table_name;
            """

            fk_result = conn.execute(text(fk_query))
            for row in fk_result:
                ddl_statements.append(row.fk_ddl)

        return '\n\n'.join(ddl_statements)