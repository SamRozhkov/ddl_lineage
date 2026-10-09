"""
Database connector modules for DDL extraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.engine import Engine


class DatabaseConnector(ABC):
    """Abstract base class for database connectors."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.engine: Engine | None = None

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""
        pass

    @abstractmethod
    def extract_ddl(self, objects: list[str] | None = None) -> str:
        """Extract DDL from the database."""
        pass

    @abstractmethod
    def get_connection_url(self) -> str:
        """Get database connection URL."""
        pass

    def disconnect(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            self.engine = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# Re-export for `from db_connectors import DatabaseConnectorFactory`; imported last
# because factory.py imports DatabaseConnector from this module
from .factory import DatabaseConnectorFactory  # noqa: E402, F401
