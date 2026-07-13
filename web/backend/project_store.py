from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    select,
)


class ProjectStore:
    def __init__(self, db_url: str | None = None):
        self.db_path = Path(__file__).parent / 'metadata.db'
        self.db_url = db_url or f'sqlite:///{self.db_path}'
        self.engine = create_engine(self.db_url, connect_args={'check_same_thread': False})
        self.metadata = MetaData()

        self.projects = Table(
            'projects',
            self.metadata,
            Column('project_name', String, primary_key=True),
            Column('display_name', String, nullable=False),
            Column('description', String, nullable=True),
            Column('created_at', String, nullable=False),
            Column('updated_at', String, nullable=False),
            Column('has_state', Boolean, nullable=False, default=False),
        )

        self.project_state = Table(
            'project_state',
            self.metadata,
            Column('project_name', String, primary_key=True),
            Column('state_json', Text, nullable=False),
        )

        self.project_history = Table(
            'project_history',
            self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('project_name', String, nullable=False),
            Column('timestamp', String, nullable=False),
            Column('action', String, nullable=False),
            Column('state_json', Text, nullable=False),
        )

        self.metadata.create_all(self.engine, checkfirst=True)

        inspector = inspect(self.engine)
        existing_tables = inspector.get_table_names()
        for table in (self.projects, self.project_state, self.project_history):
            if table.name not in existing_tables:
                table.create(self.engine, checkfirst=True)

    def sanitize_name(self, name: str) -> str:
        sanitized = ''.join(
            ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in name.strip()
        ).strip('_')
        return sanitized or 'project'

    def project_exists(self, name: str) -> bool:
        sanitized = self.sanitize_name(name)
        query = select(self.projects).where(self.projects.c.project_name == sanitized)
        with self.engine.begin() as conn:
            result = conn.execute(query).first()
        return result is not None

    def ensure_project(self, name: str, metadata: dict | None = None) -> str:
        sanitized = self.sanitize_name(name)
        now = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        project_meta = {
            'project_name': sanitized,
            'display_name': sanitized,
            'description': '',
            'created_at': now,
            'updated_at': now,
            'has_state': False,
        }

        if metadata is not None:
            project_meta['display_name'] = metadata.get('name', sanitized)
            project_meta['description'] = metadata.get('description', '')
            project_meta['created_at'] = metadata.get('created_at', now)
            project_meta['updated_at'] = metadata.get('created_at', now)

        with self.engine.begin() as conn:
            existing = conn.execute(
                select(self.projects).where(self.projects.c.project_name == sanitized)
            ).first()
            if existing is None:
                conn.execute(self.projects.insert().values(project_meta))
            elif metadata is not None:
                conn.execute(
                    self.projects.update()
                    .where(self.projects.c.project_name == sanitized)
                    .values(
                        display_name=project_meta['display_name'],
                        description=project_meta['description'],
                        updated_at=project_meta['updated_at'],
                    )
                )

        return sanitized

    def save_metadata(self, name: str, metadata: dict) -> None:
        sanitized = self.ensure_project(name)
        now = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        with self.engine.begin() as conn:
            conn.execute(
                self.projects.update()
                .where(self.projects.c.project_name == sanitized)
                .values(
                    display_name=metadata.get('name', sanitized),
                    description=metadata.get('description', ''),
                    updated_at=metadata.get('updated_at', now),
                )
            )

    def load_metadata(self, name: str) -> dict:
        sanitized = self.sanitize_name(name)
        query = select(self.projects).where(self.projects.c.project_name == sanitized)
        with self.engine.begin() as conn:
            row = conn.execute(query).first()
        if row is None:
            return {}
        return {
            'project_name': row.project_name,
            'name': row.display_name,
            'description': row.description,
            'created_at': row.created_at,
            'updated_at': row.updated_at,
            'has_state': bool(row.has_state),
        }

    def list_projects(self) -> list[dict]:
        query = select(self.projects).order_by(self.projects.c.updated_at.desc())
        with self.engine.begin() as conn:
            rows = conn.execute(query).all()
        return [
            {
                'project_name': row.project_name,
                'display_name': row.display_name or row.project_name,
                'description': row.description or '',
                'updated_at': row.updated_at,
                'has_state': bool(row.has_state),
            }
            for row in rows
        ]

    def save_state(self, name: str, state: dict, action: str = 'update') -> dict:
        sanitized = self.ensure_project(name)
        now = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        state_to_save = dict(state)
        state_to_save['project_name'] = sanitized
        state_to_save['updated_at'] = now
        state_to_save['action'] = action
        state_json = json.dumps(state_to_save, default=str)

        with self.engine.begin() as conn:
            conn.execute(self.project_state.delete().where(self.project_state.c.project_name == sanitized))
            conn.execute(
                self.project_state.insert().values(
                    project_name=sanitized,
                    state_json=state_json,
                )
            )
            conn.execute(
                self.project_history.insert().values(
                    project_name=sanitized,
                    timestamp=now,
                    action=action,
                    state_json=state_json,
                )
            )
            conn.execute(
                self.projects.update()
                .where(self.projects.c.project_name == sanitized)
                .values(updated_at=now, has_state=True)
            )

        return state_to_save

    def load_state(self, name: str) -> dict:
        sanitized = self.sanitize_name(name)
        query = select(self.project_state).where(self.project_state.c.project_name == sanitized)
        with self.engine.begin() as conn:
            row = conn.execute(query).first()
        if row is None:
            return {}
        return json.loads(row.state_json)

    def list_history(self, name: str) -> list[dict]:
        sanitized = self.sanitize_name(name)
        query = (
            select(self.project_history)
            .where(self.project_history.c.project_name == sanitized)
            .order_by(self.project_history.c.id.desc())
        )
        with self.engine.begin() as conn:
            rows = conn.execute(query).all()
        history = []
        for row in rows:
            state = json.loads(row.state_json)
            analysis = state.get('analysis') or {}
            history.append(
                {
                    'timestamp': row.timestamp,
                    'action': row.action,
                    'summary': analysis.get('stats', {}),
                    'filename': None,
                }
            )
        return history
