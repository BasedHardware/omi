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


def sync_transcript_chunks(uid, conversation_id, *, firestore_client):
    """Rebuild only this conversation's transcript vectors from its projection."""
    from database import vector_db, conversations
    from utils.conversations.transcript_chunks import build_transcript_chunks

    if vector_db.index is None:
        return
    raw = (
        firestore_client.collection('users')
        .document(uid)
        .collection('conversations')
        .document(conversation_id)
        .get()
        .to_dict()
    )
    if not raw or raw.get('deleted'):
        return
    current = conversations.prepare_conversation_for_read(
        {**raw, 'id': conversation_id}, uid, firestore_client=firestore_client
    )
    if current is None:
        return
    chunks = build_transcript_chunks(
        current.get('transcript_segments') or [], current.get('started_at') or current.get('created_at')
    )
    vector_db.delete_transcript_chunk_vectors(uid, conversation_id)
    vector_db.upsert_transcript_chunk_vectors(uid, conversation_id, chunks)
