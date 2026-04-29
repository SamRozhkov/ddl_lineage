"""
ddl_lineage.models
==================
Core data classes used throughout the package.
"""

from dataclasses import dataclass, field


@dataclass
class Column:
    """Represents a single column inside a CREATE TABLE statement."""

    name: str
    data_type: str = ""
    nullable: bool = True
    pk: bool = False
    fk_to: str = ""       # "referenced_table.column", e.g. "users.id"
    default: str = ""
    unique: bool = False

    def __repr__(self) -> str:
        flags = []
        if self.pk:
            flags.append("PK")
        if self.fk_to:
            flags.append(f"FK->{self.fk_to}")
        if self.unique:
            flags.append("UNIQUE")
        if not self.nullable:
            flags.append("NOT NULL")
        return f"Column({self.name} {self.data_type}{' [' + ', '.join(flags) + ']' if flags else ''})"


@dataclass
class DDLObject:
    """Represents a database object: TABLE, VIEW, MATERIALIZED_VIEW, FUNCTION, PROCEDURE."""

    name: str
    type: str               # TABLE | VIEW | MATERIALIZED_VIEW | FUNCTION | PROCEDURE
    schema: str = ""
    columns: list = field(default_factory=list)   # list[Column]
    raw: str = ""           # first 100 chars of the original statement

    def __repr__(self) -> str:
        schema_pfx = f"{self.schema}." if self.schema else ""
        return f"DDLObject({self.type} {schema_pfx}{self.name}, {len(self.columns)} cols)"


@dataclass
class ColumnLineage:
    """Maps a source column to a target column through a transformation."""

    src_table: str
    src_col: str
    tgt_table: str
    tgt_col: str
    via: str = ""           # function or procedure that performs the mapping

    def __repr__(self) -> str:
        return f"ColumnLineage({self.src_table}.{self.src_col} -> {self.tgt_table}.{self.tgt_col} via {self.via})"


@dataclass
class LineageEdge:
    """
    Directed relationship between two database objects.

    edge_type values:
      FK       — foreign key constraint
      READ     — SELECT / FROM / JOIN reference
      WRITE    — INSERT / UPDATE / DELETE / MERGE / TRUNCATE
      INHERITS — INHERITS or LIKE clause (table inheritance)
    """

    source: str
    target: str
    edge_type: str          # FK | READ | WRITE | INHERITS
    via: str = ""           # intermediate object (function / view name)
    details: str = ""       # INSERT | UPDATE | DELETE | MERGE | TRUNCATE
    col_lineage: list = field(default_factory=list)   # list[ColumnLineage]

    def __repr__(self) -> str:
        detail = f" ({self.details})" if self.details else ""
        return f"LineageEdge({self.source} --[{self.edge_type}{detail}]--> {self.target})"
