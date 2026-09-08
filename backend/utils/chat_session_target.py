"""Which chat session a request targets, and which app that session belongs to.

Split out of `routers/chat.py`: this is the resolution contract every `/v2/messages`
handler shares, and it is worth reading and testing without a router around it.
"""

from typing import NamedTuple, Optional

from fastapi import HTTPException

import database.chat as chat_db


def resolve_chat_session(uid: str, app_id: Optional[str], chat_session_id: Optional[str]) -> Optional[dict]:
    """Pick the chat session a request targets.

    With an explicit `chat_session_id` the caller is addressing one specific
    session, so a missing or foreign id is an error rather than a silent
    fallback to the current session — writing a message into a different
    conversation than the client asked for is worse than failing. Without one,
    behaviour is unchanged: the user's current session for the app.
    """
    if chat_session_id:
        session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if not session:
            raise HTTPException(status_code=404, detail='Chat session not found')
        return session
    return chat_db.get_chat_session(uid, app_id=app_id)


class ResolvedChatTarget(NamedTuple):
    """The session a request addresses, plus the app identity that session owns.

    A session is created under one app and every message in it carries that
    app's id. When the caller names a session explicitly, the session — not the
    query string — is the authority on which app the turn belongs to: clients
    address a thread by id and are not required to restate its app. Deriving the
    app id from the query string instead let a request read, write, and delete
    against the wrong app: history queries and the `plugin_id` delete filter are
    both app-scoped, and the chat flow picks the persona from it.
    """

    session: Optional[dict]
    app_id: Optional[str]

    @property
    def session_id(self) -> Optional[str]:
        return self.session.get('id') if self.session else None


def resolve_chat_target(uid: str, app_id: Optional[str], chat_session_id: Optional[str]) -> ResolvedChatTarget:
    session = resolve_chat_session(uid, app_id, chat_session_id)
    if chat_session_id and session:
        session_app_id = session.get('app_id') or session.get('plugin_id')
        if session_app_id in ['null', '']:
            session_app_id = None
        return ResolvedChatTarget(session, session_app_id)
    return ResolvedChatTarget(session, app_id)
