"""Postgres job-state store (workstream A): migrations, doc-mode `Store`, outbox.

Importing this package never imports the Postgres driver (``connection`` loads psycopg lazily), so
processes that do not select Postgres pay nothing.
"""

from database.jobstore import connection, migrate, postgres_store
from database.jobstore.postgres_store import PostgresStore

__all__ = ['PostgresStore', 'connection', 'migrate', 'postgres_store']
