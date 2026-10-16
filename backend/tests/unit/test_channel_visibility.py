from unittest.mock import MagicMock
from database.channel_visibility import visible_sessions


def test_visible_sessions_empty_or_whitespace_uid():
    mock_client = MagicMock()
    assert visible_sessions("", firestore_client=mock_client) == []
    assert visible_sessions("   ", firestore_client=mock_client) == []
    mock_client.collection.assert_not_called()


def test_visible_sessions_cohort_disabled(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: False)
    mock_client = MagicMock()
    assert visible_sessions("user_123", firestore_client=mock_client) == []
    mock_client.collection.assert_not_called()


def test_visible_sessions_none_client(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: True)
    monkeypatch.setattr(cv, "get_firestore_client", lambda: None)
    assert visible_sessions("user_123", firestore_client=None) == []


def test_visible_sessions_success(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: True)

    mock_client = MagicMock()
    mock_user_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc

    # Channel links: link_1 visible, link_2 not visible
    link_1 = MagicMock()
    link_1.id = "link_1"
    link_1.to_dict.return_value = {"visible_in_app": True}

    link_2 = MagicMock()
    link_2.id = "link_2"
    link_2.to_dict.return_value = {"visible_in_app": False}

    # Chat sessions: session_1 on link_1, session_2 on link_2
    session_1 = MagicMock()
    session_1.id = "sess_1"
    session_1.to_dict.return_value = {"channel_link_id": "link_1", "title": "Chat 1"}

    session_2 = MagicMock()
    session_2.id = "sess_2"
    session_2.to_dict.return_value = {"channel_link_id": "link_2", "title": "Chat 2"}

    def mock_collection(name):
        col = MagicMock()
        if name == "channel_links":
            col.stream.return_value = [link_1, link_2]
        elif name == "chat_sessions":
            col.stream.return_value = [session_1, session_2]
        return col

    mock_user_doc.collection.side_effect = mock_collection

    sessions = visible_sessions("user_123", firestore_client=mock_client)
    assert len(sessions) == 1
    assert sessions[0]["id"] == "sess_1"
    assert sessions[0]["channel_link_id"] == "link_1"
    assert sessions[0]["title"] == "Chat 1"
    mock_client.collection.assert_called_with("users")
    mock_client.collection.return_value.document.assert_called_with("user_123")


def test_visible_sessions_strips_uid_whitespace(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: True)

    mock_client = MagicMock()
    mock_user_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc

    link_1 = MagicMock()
    link_1.id = "link_1"
    link_1.to_dict.return_value = {"visible_in_app": True}

    def mock_collection(name):
        col = MagicMock()
        col.stream.return_value = [link_1] if name == "channel_links" else []
        return col

    mock_user_doc.collection.side_effect = mock_collection

    visible_sessions("  user_space  ", firestore_client=mock_client)
    mock_client.collection.return_value.document.assert_called_with("user_space")


def test_visible_sessions_no_visible_links(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: True)

    mock_client = MagicMock()
    mock_user_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc

    link_1 = MagicMock()
    link_1.id = "link_1"
    link_1.to_dict.return_value = {"visible_in_app": False}

    col_links = MagicMock()
    col_links.stream.return_value = [link_1]
    mock_user_doc.collection.return_value = col_links

    res = visible_sessions("user_123", firestore_client=mock_client)
    assert res == []
    # Chat sessions collection must NOT be queried if no visible links exist
    mock_user_doc.collection.assert_called_once_with("channel_links")


def test_visible_sessions_handles_non_dict_data_safely(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: True)

    mock_client = MagicMock()
    mock_user_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc

    link_valid = MagicMock()
    link_valid.id = "link_valid"
    link_valid.to_dict.return_value = {"visible_in_app": True}

    link_malformed = MagicMock()
    link_malformed.id = "link_malformed"
    link_malformed.to_dict.return_value = None

    sess_malformed = MagicMock()
    sess_malformed.id = "sess_malformed"
    sess_malformed.to_dict.return_value = "not_a_dict"

    sess_valid = MagicMock()
    sess_valid.id = "sess_valid"
    sess_valid.to_dict.return_value = {"channel_link_id": "link_valid", "title": "Valid"}

    def mock_collection(name):
        col = MagicMock()
        if name == "channel_links":
            col.stream.return_value = [link_malformed, link_valid]
        elif name == "chat_sessions":
            col.stream.return_value = [sess_malformed, sess_valid]
        return col

    mock_user_doc.collection.side_effect = mock_collection

    sessions = visible_sessions("user_123", firestore_client=mock_client)
    assert len(sessions) == 1
    assert sessions[0]["id"] == "sess_valid"


def test_visible_sessions_exception_handling(monkeypatch):
    import database.channel_visibility as cv

    monkeypatch.setattr(cv, "cohort_enabled", lambda uid: True)

    mock_client = MagicMock()
    mock_client.collection.side_effect = RuntimeError("Firestore stream failure")

    assert visible_sessions("user_123", firestore_client=mock_client) == []
