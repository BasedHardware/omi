from typing import List

from fastapi import HTTPException, Request, APIRouter, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_zapier_user_status, store_zapier_user_status, store_zapier_subscribes, get_zapier_subscribes, \
    remove_zapier_subscribes
from models import Memory, WorkflowCreateMemory, EndpointResponse
from .client import get_zapier, get_friend
from .models import ZapierSubcribeModel, ZapierCreateMemory, ZapierActionCreateMemory

router = APIRouter()
# noinspection PyRedeclaration
templates = Jinja2Templates(directory="templates")


def response_setup_page(request: Request, uid: str, status: str):
    return templates.TemplateResponse("setup_zapier.html",
                                      {"request": request, "uid": uid, "status": status if status is not None else ""})


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
    # Should validate uid is valid user on Friend backend before insert
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

    # Should validate uid is valid user on Friend backend before insert
    store_zapier_user_status(uid, status)

    return response_setup_page(request, uid, status)


@router.post('/zapier/trigger/subscribe', tags=['zapier'], response_model=EndpointResponse)
async def subscribe_zapier_trigger(subscriber: ZapierSubcribeModel, uid: str):
    """
    Subcribe a zapier trigger
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    if not subscriber.target_url or subscriber.target_url == "":
        raise HTTPException(status_code=400, detail='Target url is invalid.')
        return

    # Validate user status
    status = get_zapier_user_status(uid)
    if status != "enabled":
        raise HTTPException(status_code=401, detail="Unauthorized")

    print({'uid': uid, 'target_url': subscriber.target_url})
    store_zapier_subscribes(uid, subscriber.target_url)
    return {}


@router.delete('/zapier/trigger/subscribe', tags=['zapier'], response_model=EndpointResponse)
async def unsubscribe_zapier_trigger(subscriber: ZapierSubcribeModel, uid: str):
    """
    Subcribe a zapier trigger
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    if not subscriber.target_url or subscriber.target_url == "":
        raise HTTPException(status_code=400, detail='Target url is invalid.')

    # Validate user status
    status = get_zapier_user_status(uid)
    if status != "enabled":
        raise HTTPException(status_code=401, detail="Unauthorized")

    print({'uid': uid, 'target_url': subscriber.target_url})
    remove_zapier_subscribes(uid, subscriber.target_url)
    return {}


@router.get('/zapier/trigger/memory/sample', tags=['zapier'], response_model=List[ZapierCreateMemory])
async def get_trigger_memory_sample(request: Request, uid: str):
    """
    Get the latest memory or a sample to fullfill the triggers On memory created
    """

    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')

    # Genrate sample
    sample = ZapierCreateMemory(
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
    ok = get_friend().get_latest_memory(uid)
    print(ok)
    if "error" in ok:
        err = ok["error"]
        print(err)
        raise HTTPException(
            status_code=err["status"] if "status" in err else 500,
            detail='Can not create memory'
        )

    memory = ok["result"]
    if memory is not None:
        try:
            emoji = memory.structured.emoji.encode('latin1').decode('utf-8')
        except UnicodeEncodeError:
            emoji = memory.structured.emoji

        sample = ZapierCreateMemory(
            icon={
                "type": "emoji",
                "emoji": f"{emoji}"
            },
            title=f'{memory.structured.title}',
            speakers=len(
                set(map(lambda x: x.speaker, memory.transcript_segments))),
            category=memory.structured.category,
            duration=int((memory.finished_at -
                          memory.started_at).total_seconds() if memory.finished_at is not None else 0),
            overview=memory.structured.overview,
            transcript=memory.get_transcript(),
        )

    return [sample]


@router.get('/zapier/me', tags=['zapier'], response_model=EndpointResponse)
async def auth_zapier_me(request: Request, uid: str):
    """
    User - Zapier authentication status.
    """

    print({'uid': uid, })
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
def zapier_memories(memory: Memory, uid: str):
    """
    The actual plugin that gets triggered when a memory gets created, and adds the memory to the Zapier.
    """

    # Not enabled Zapier plugin
    status = get_zapier_user_status(uid)
    if status != "enabled":
        return {}

    # Send to Zapier
    ok = create_zapier_memory(uid, memory)
    if not ok:
        return {}

    return {}


@router.post('/zapier/action/memories', tags=['zapier'], response_model=EndpointResponse)
def zapier_action_memories(create_memory: ZapierActionCreateMemory, uid: str):
    """
    Create new memory by action from Zapier.
    """

    memory = WorkflowCreateMemory(
        text=create_memory.text,
        text_source=create_memory.source,
        started_at=create_memory.started_at,
        finished_at=create_memory.finished_at,
        language=create_memory.language,
        geolocation=create_memory.geolocation,
    )

    ok = get_friend().create_memory(memory, uid)
    print(ok)
    if "error" in ok:
        err = ok["error"]
        print(err)
        raise HTTPException(status_code=err["status"] if "status" in err else 500,
                            detail='Can not create memory')
        return
    result = ok["result"]
    print(result)

    return EndpointResponse(message="Your memories are synced with Omi.")


def create_zapier_memory(uid: str, memory: Memory):
    subscribes = get_zapier_subscribes(uid)
    for sub in subscribes:
        target_url = sub.decode()

        # modeling
        try:
            emoji = memory.structured.emoji.encode('latin1').decode('utf-8')
        except UnicodeEncodeError:
            emoji = memory.structured.emoji

        data = ZapierCreateMemory(
            icon={
                "type": "emoji",
                "emoji": f"{emoji}"
            },
            title=f'{memory.structured.title}',
            speakers=len(
                set(map(lambda x: x.speaker, memory.transcript_segments))),
            category=memory.structured.category,
            duration=int((memory.finished_at -
                          memory.started_at).total_seconds() if memory.finished_at is not None else 0),
            overview=memory.structured.overview,
            transcript=memory.get_transcript(),
        )
        ok = get_zapier().send_hook_memory_created(target_url, data)
        # with graceful error
        if "error" in ok:
            err = ok["error"]
            print(sub)
            print(err)

            continue

    return True
