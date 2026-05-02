"""External integration sync helpers (Jira, Linear, etc.).

Each module here owns the ``read path`` for one integration: pull tasks /
issues / etc. from the upstream system and materialize them as Omi action
items via ``database.action_items.upsert_external_action_item``.
"""
