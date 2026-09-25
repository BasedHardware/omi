from typing import Any, List

from fastapi import HTTPException, Request, APIRouter, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import (
    get_zapier_user_status,
    store_zapier_user_status,
    store_zapier_subscribes,
    get_zapier_subscribes,
    remove_zapier_subscribes,
)
from models import Conversation, ExternalIntegrationCreateConversation, EndpointResponse
# Fallback to direct package import when running outside parent package context (e.g. test harness)
try:
    from .client import get_zapier, get_omi
    from .models import ZapierSubcribeModel, ZapierCreateConversation, ZapierActionCreateConversation
except (ImportError, ValueError):
    from zapier.client import get_zapier, get_omi
    from zapier.models import ZapierSubcribeModel, ZapierCreateConversation, ZapierActionCreateConversation

router = APIRouter()
# noinspection PyRedeclaration
templates = Jinja2Templates(directory="templates")


def response_setup_page(request: Request, uid: str, status: str):
    return templates.TemplateResponse(
        "setup_zapier.html", {"request": request, "uid": uid, "status": status if status is not None else ""}
    )


@router.get('/setup-zapier', response_class=HTMLResponse, tags=['zapier'])
async def setup_zapier_workflow(request: Request, uid: str):
    """
    Simple setup page Form page for Zapier Workflow plugin.
    """
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    status = get_zapier_user_status(uid)
    return response_setup_page(request, uid, status)


@router.post('/zapier/connect', tags=['zapier'], response_model=EndpointResponse)
async def connect(request: Request, uid: str = Form(...)):
    """
    Enable Zapier App
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    status = "enabled"

    print({'uid': uid, 'status': status})
    # Should validate uid is valid user on Omi backend before insert
    store_zapier_user_status(uid, status)

    return response_setup_page(request, uid, status)


@router.post('/zapier/disconnect', tags=['zapier'], response_model=EndpointResponse)
async def disconnect(request: Request, uid: str = Form(...)):
    """
    Disable Zapier App
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    status = "disabled"

    print({'uid': uid, 'status': status})

    # Should validate uid is valid user on Omi backend before insert
    store_zapier_user_status(uid, status)

    return response_setup_page(request, uid, status)


@router.post('/zapier/trigger/subscribe', tags=['zapier'], response_model=EndpointResponse)
async def subscribe_zapier_trigger(subscriber: ZapierSubcribeModel, uid: str):
    """
    Subcribe a zapier trigger
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    if not subscriber or not subscriber.target_url or not subscriber.target_url.strip():
        raise HTTPException(status_code=400, detail='Target url is invalid.')

    target_url = subscriber.target_url.strip()
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        raise HTTPException(status_code=400, detail='Target url must start with http:// or https://')

    # Validate user status
    status = get_zapier_user_status(uid)
    if status != "enabled":
        raise HTTPException(status_code=401, detail="Unauthorized")

    store_zapier_subscribes(uid, target_url)
    return {}


@router.delete('/zapier/trigger/subscribe', tags=['zapier'], response_model=EndpointResponse)
async def unsubscribe_zapier_trigger(subscriber: ZapierSubcribeModel, uid: str):
    """
    Unsubcribe a zapier trigger
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    if not subscriber or not subscriber.target_url or not subscriber.target_url.strip():
        raise HTTPException(status_code=400, detail='Target url is invalid.')

    # Validate user status
    status = get_zapier_user_status(uid)
    if status != "enabled":
        raise HTTPException(status_code=401, detail="Unauthorized")

    remove_zapier_subscribes(uid, subscriber.target_url.strip())
    return {}


def _build_zapier_conversation_payload(conversation: Any) -> ZapierCreateConversation:
    if conversation is None:
        raise ValueError("Conversation cannot be None")

    # Safe emoji extraction
    emoji = "🧠"
    structured = getattr(conversation, "structured", None)
    if structured is not None:
        raw_emoji = getattr(structured, "emoji", None)
        if raw_emoji:
            try:
                emoji = str(raw_emoji).encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
                emoji = str(raw_emoji)

    # Safe title
    title = ""
    if structured is not None and getattr(structured, "title", None):
        title = str(structured.title)
    if not title:
        title = "Omi Conversation"

    # Safe category
    category = "other"
    if structured is not None and getattr(structured, "category", None):
        cat = structured.category
        category = str(getattr(cat, "value", cat))

    # Safe speakers count
    segments = getattr(conversation, "transcript_segments", None) or []
    speakers_set = set()
    for seg in segments:
        if seg is None:
            continue
        spk = getattr(seg, "speaker", None)
        if spk is not None:
            speakers_set.add(spk)
        elif isinstance(seg, dict) and "speaker" in seg:
            speakers_set.add(seg["speaker"])
    speakers = len(speakers_set)

    # Safe duration
    started_at = getattr(conversation, "started_at", None)
    finished_at = getattr(conversation, "finished_at", None)
    duration = 0
    if started_at is not None and finished_at is not None:
        try:
            delta = (finished_at - started_at).total_seconds()
            duration = max(0, int(delta))
        except (TypeError, ValueError, AttributeError):
            duration = 0

    # Safe overview
    overview = ""
    if structured is not None and getattr(structured, "overview", None):
        overview = str(structured.overview)

    # Safe transcript
    transcript = ""
    if hasattr(conversation, "get_transcript") and callable(conversation.get_transcript):
        try:
            transcript = conversation.get_transcript() or ""
        except Exception:
            transcript = ""
    elif hasattr(conversation, "transcript"):
        transcript = str(getattr(conversation, "transcript", "") or "")

    return ZapierCreateConversation(
        icon={"type": "emoji", "emoji": f"{emoji}"},
        title=title,
        speakers=speakers,
        category=category,
        duration=duration,
        overview=overview,
        transcript=transcript,
    )


@router.get('/zapier/trigger/memory/sample', tags=['zapier'], response_model=List[ZapierCreateConversation])
async def get_trigger_conversation_sample(request: Request, uid: str):
    """
    Get the latest conversation or a sample to fullfill the triggers On conversation created
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    # Default sample
    sample = ZapierCreateConversation(
        icon={
            "type": "emoji",
            "emoji": "🧠",
        },
        title='Omi\'s sammple memory',
        speakers=0,
        category="other",
        duration=300,
        overview="Meet Omi today, the world’s leading open-source AI wearables that revolutionize how you capture and manage conversations. Simply connect Omi to your mobile device and enjoy automatic, high-quality transcriptions of meetings, chats, and voice memos wherever you are.",
        transcript="User: Meet Omi today.",
    )

    # Get latest from Omi
    ok = get_omi().get_latest_conversation(uid)
    if isinstance(ok, dict) and "error" in ok:
        err = ok["error"]
        print(err)
        status_code = 500
        if isinstance(err, dict) and "status" in err:
            try:
                status_code = int(err["status"])
            except (ValueError, TypeError):
                status_code = 500
        raise HTTPException(status_code=status_code, detail='Can not create memory')

    conversation = ok.get("result") if isinstance(ok, dict) else None
    if conversation is not None:
        try:
            sample = _build_zapier_conversation_payload(conversation)
        except Exception as e:
            print(f"Error building sample conversation: {e}")

    return [sample]


@router.get('/zapier/me', tags=['zapier'], response_model=EndpointResponse)
async def auth_zapier_me(request: Request, uid: str):
    """
    User - Zapier authentication status.
    """

    print(
        {
            'uid': uid,
        }
    )
    status = get_zapier_user_status(uid)
    if status != "enabled":
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {}


@router.get('/setup/zapier', tags=['zapier'])
def is_setup_completed(uid: str):
    """
    Check if the user has setup the Zapier plugin.
    """
    status = get_zapier_user_status(uid)
    return {'is_setup_completed': status == "enabled"}


@router.post('/zapier/memories', tags=['zapier'], response_model=EndpointResponse)
def zapier_conversations(conversation: Conversation, uid: str):
    """
    The actual plugin that gets triggered when a conversation gets created, and adds the conversation to the Zapier.
    """

    # Not enabled Zapier plugin
    status = get_zapier_user_status(uid)
    if status != "enabled":
        return {}

    # Send to Zapier
    ok = create_zapier_conversation(uid, conversation)
    if not ok:
        return {}

    return {}


@router.post('/zapier/action/memories', tags=['zapier'], response_model=EndpointResponse)
def zapier_action_conversations(create_conversation: ZapierActionCreateConversation, uid: str):
    """
    Create new conversation by action from Zapier.
    """

    conversation = ExternalIntegrationCreateConversation(
        text=create_conversation.text,
        text_source=create_conversation.source,
        started_at=create_conversation.started_at,
        finished_at=create_conversation.finished_at,
        language=create_conversation.language,
        geolocation=create_conversation.geolocation,
    )

    ok = get_omi().create_conversation(conversation, uid)
    if isinstance(ok, dict) and "error" in ok:
        err = ok["error"]
        print(err)
        status_code = 500
        if isinstance(err, dict) and "status" in err:
            try:
                status_code = int(err["status"])
            except (ValueError, TypeError):
                status_code = 500
        raise HTTPException(status_code=status_code, detail='Can not create memory')

    return EndpointResponse(message="Your memories are synced with Omi.")


def create_zapier_conversation(uid: str, conversation: Conversation):
    subscribes = get_zapier_subscribes(uid) or []
    for sub in subscribes:
        target_url = sub.decode() if isinstance(sub, bytes) else str(sub)
        if not target_url or not target_url.strip():
            continue

        try:
            data = _build_zapier_conversation_payload(conversation)
        except Exception as e:
            print(f"Error modeling zapier conversation: {e}")
            continue

        ok = get_zapier().send_hook_conversation_created(target_url, data)
        # with graceful error
        if isinstance(ok, dict) and "error" in ok:
            err = ok["error"]
            print(err)
            continue

    return True
