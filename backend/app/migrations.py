"""One narrowly scoped SQLite migration for photo-less historical imports."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

from sqlalchemy import MetaData, inspect


def migrate_nullable_import_fields(engine, issue_table) -> Path | None:
    """Preserve submissions and take a consistent backup before changing schema."""
    inspector = inspect(engine)
    if not inspector.has_table("issues"):
        return None
    columns = inspector.get_columns("issues")
    optional = {"description", "reporter_email", "photo_filename", "photo_media_type"}
    if not any(column["name"] in optional and not column["nullable"] for column in columns):
        return None
    expected = set(issue_table.columns.keys())
    if {column["name"] for column in columns} != expected:
        raise RuntimeError("Unexpected issues schema; refusing migration to preserve existing data")
    path = Path(engine.url.database)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(f"issues.pre-nullable-{stamp}-{uuid4().hex[:8]}.sqlite3")
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    temporary = issue_table.to_metadata(MetaData(), name="issues_nullable_migration")
    with engine.connect() as connection:
        # Explicit BEGIN keeps SQLite DDL and copying in one atomic transaction.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            sequence = connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='issues'").scalar()
            temporary.create(connection)
            names = ", ".join(f'"{name}"' for name in issue_table.columns.keys())
            connection.exec_driver_sql(f"INSERT INTO issues_nullable_migration ({names}) SELECT {names} FROM issues")
            connection.exec_driver_sql("DROP TABLE issues")
            connection.exec_driver_sql("ALTER TABLE issues_nullable_migration RENAME TO issues")
            if sequence is not None:
                connection.exec_driver_sql("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'issues'", (sequence,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return backup
