"""
Database connector modules for DDL extraction.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import sqlalchemy as sa
from sqlalchemy.engine import Engine


class DatabaseConnector(ABC):
    """Abstract base class for database connectors."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.engine: Optional[Engine] = None

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""
        pass

    @abstractmethod
    def extract_ddl(self, objects: Optional[List[str]] = None) -> str:
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


# Import factory for easy access
from .factory import DatabaseConnectorFactory