"""Concrete DocumentStore implementations (adapters) behind the neutral port.

Each module here implements ``database.store.ports.DocumentStore`` for one backend. None is
privileged in the domain; selection is by configuration (``STORAGE_BACKEND``), see
``database.store.factory``. Firestore is the default first-class backend (ADR-0003); Mongo is the
second implementation that proves the port abstracts rather than emulates (ADR-0002/0004).
"""
