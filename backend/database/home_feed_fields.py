"""Home feed field names shared with writers that must not import the Firestore commit hook."""

# Fields augment_home_writes stamps onto every conversation write at the Commit boundary. A writer that
# reads its own write back must not mistake them for an external change.
COMMIT_STAMPED_FIELDS = frozenset(
    {
        'home_source_version',
        'home_content_invalidated',
        'home_list_transcript_source_version',
    }
)

# Encrypted transcript-derived Home list evidence and its source-version binding.
LIST_TRANSCRIPT = 'home_list_transcript'
LIST_TRANSCRIPT_SOURCE_VERSION = 'home_list_transcript_source_version'
