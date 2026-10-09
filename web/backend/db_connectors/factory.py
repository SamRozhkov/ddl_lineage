"""
Database connector factory.
"""

from __future__ import annotations

from typing import Any

from . import DatabaseConnector
from .mysql import MySQLConnector
from .postgresql import PostgreSQLConnector


class DatabaseConnectorFactory:
    """Factory for creating database connectors."""

    @staticmethod
    def create_connector(db_type: str, config: dict[str, Any]) -> DatabaseConnector:
        """Create a database connector instance."""
        if db_type.lower() == 'postgresql':
            return PostgreSQLConnector(config)
        elif db_type.lower() == 'mysql':
            return MySQLConnector(config)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    @staticmethod
    def get_supported_types() -> list:
        """Get list of supported database types."""
        return ['postgresql', 'mysql']
