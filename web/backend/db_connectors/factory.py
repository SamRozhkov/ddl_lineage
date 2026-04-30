"""
Database connector factory.
"""

from typing import Dict, Any
from . import DatabaseConnector
from .postgresql import PostgreSQLConnector
from .mysql import MySQLConnector


class DatabaseConnectorFactory:
    """Factory for creating database connectors."""

    @staticmethod
    def create_connector(db_type: str, config: Dict[str, Any]) -> DatabaseConnector:
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