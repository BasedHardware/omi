"""Home feed field names shared with writers that must not import the Firestore commit hook."""

# Fields augment_home_writes stamps onto every conversation write at the Commit boundary. A writer that
# reads its own write back must not mistake them for an external change.
COMMIT_STAMPED_FIELDS = frozenset({'home_source_version', 'home_content_invalidated'})
