"""Post-commit search convergence for reversible Review conversation edits."""


def sync_conversations(uid, edits, *, firestore_client):
    # Import lazily: unconfigured indexing returns before all provider I/O.
    from utils.conversations.typesense_index import sync_conversation_index_after_write

    for key in sorted(
        {
            edit['document_id'] if isinstance(edit, dict) else edit.document_id
            for edit in edits
            if (edit.get('collection') if isinstance(edit, dict) else edit.collection) == 'conversations'
        }
    ):
        sync_conversation_index_after_write(uid, key, firestore_client=firestore_client)
