from services import conversation_frame_evidence


def test_conversation_frame_read_requires_owner_conversation_and_photo(monkeypatch):
    monkeypatch.setattr(conversation_frame_evidence.conversations_db, "get_conversation", lambda uid, cid: {"id": cid})
    monkeypatch.setattr(
        conversation_frame_evidence.conversations_db,
        "get_conversation_photos",
        lambda uid, cid: [{"id": "photo-1", "storage_id": "permanent/uid/frame", "content_type": "image/webp"}],
    )
    reads = []
    monkeypatch.setattr(
        conversation_frame_evidence,
        "download_frame_request_pixels",
        lambda uid, storage_id: reads.append((uid, storage_id)) or b"pixels",
    )

    payload, content_type = conversation_frame_evidence.read_conversation_frame("uid-1", "conv-1", "photo-1")

    assert (payload, content_type) == (b"pixels", "image/webp")
    assert reads == [("uid-1", "permanent/uid/frame")]


def test_conversation_frame_deletion_outboxes_before_metadata_and_retries_failed_pixels(monkeypatch):
    events = []
    monkeypatch.setattr(
        conversation_frame_evidence.conversations_db,
        "get_conversation_photos",
        lambda *_args: [{"storage_id": "permanent/photo"}],
    )
    monkeypatch.setattr(
        conversation_frame_evidence.frame_requests_db,
        "list_all_frame_request_storage_ids",
        lambda *_args, **_kwargs: ["permanent/photo", "temporary/request"],
    )
    monkeypatch.setattr(
        conversation_frame_evidence.frame_requests_db,
        "persist_conversation_frame_deletion_outbox",
        lambda uid, cid, ids: events.append(("outbox", uid, cid, ids)),
    )
    monkeypatch.setattr(
        conversation_frame_evidence,
        "delete_frame_request_pixels_for_user",
        lambda uid, ids: (
            (_ for _ in ()).throw(RuntimeError("transient"))
            if ids == ["temporary/request"]
            else events.append(("pixels", uid, ids))
        ),
    )
    monkeypatch.setattr(
        conversation_frame_evidence.frame_requests_db,
        "acknowledge_conversation_frame_deletion",
        lambda uid, cid, sid: events.append(("ack", uid, cid, sid)),
    )
    monkeypatch.setattr(
        conversation_frame_evidence.frame_requests_db,
        "delete_frame_requests_for_conversation",
        lambda uid, cid: events.append(("request-metadata", uid, cid)),
    )

    conversation_frame_evidence.delete_conversation_and_frame_evidence(
        "uid-1", "conv-1", delete_conversation=lambda uid, cid: events.append(("conversation", uid, cid))
    )

    assert events == [
        ("outbox", "uid-1", "conv-1", ["permanent/photo", "temporary/request"]),
        ("conversation", "uid-1", "conv-1"),
        ("pixels", "uid-1", ["permanent/photo"]),
        ("ack", "uid-1", "conv-1", "permanent/photo"),
        ("request-metadata", "uid-1", "conv-1"),
    ]
