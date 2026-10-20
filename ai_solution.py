```python
from fastapi import HTTPException
from typing import Optional

async def delete_focus_session(session_id: str) -> None:
    try:
        result = focus_sessions_db.delete_focus_session(uid, session_id)
        if not result:
            raise HTTPException(status_code=404, detail="Focus session not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def create_focus_session(data: CreateFocusSessionRequest) -> None:
    try:
        data_dict = data.dict()
        data_dict["app_or_site"] = data_dict["app_or_site"].strip()
        data_dict["description"] = data_dict["description"].strip()
        await focus_sessions_db.create_focus_session(uid, data_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_focus_sessions(app_filter: Optional[str] = None) -> dict:
    try:
        app_filter = app_filter.strip() if app_filter else None
        if app_filter == "":
            app_filter = None
        sessions = await focus_sessions_db.get_focus_sessions(uid, app_filter)
        return {"focus_sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_focus_stats() -> dict:
    try:
        stats = await focus_sessions_db.get_focus_stats(uid)
        return {"focus_stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def list_screen_activity(app_filter: Optional[str] = None) -> dict:
    try:
        app_filter = app_filter.strip() if app_filter else None
        if app_filter == "":
            app_filter = None
        activities = await focus_sessions_db.list_screen_activity(uid, app_filter)
        return {"screen_activity": activities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def screen_activity_summary(app_filter: Optional[str] = None) -> dict:
    try:
        app_filter = app_filter.strip() if app_filter else None
        if app_filter == "":
            app_filter = None
        summary = await focus_sessions_db.screen_activity_summary(uid, app_filter)
        return {"screen_activity_summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

```python
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

router = APIRouter()

class CreateFocusSessionRequest(BaseModel):
    app_or_site: str
    description: str
    duration: int
    session_id: str

@router.delete("/v1/focus-sessions/{session_id}")
async def delete_focus_session(session_id: str) -> None:
    try:
        result = focus_sessions_db.delete_focus_session(uid, session_id)
        if not result:
            raise HTTPException(status_code=404, detail="Focus session not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v1/focus-sessions")
async def create_focus_session(data: CreateFocusSessionRequest) -> None:
    try:
        data_dict = data.dict()
        data_dict["app_or_site"] = data_dict["app_or_site"].strip()
        data_dict["description"] = data_dict["description"].strip()
        await focus_sessions_db.create_focus_session(uid, data_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/focus-sessions")
async def get_focus_sessions(app_filter: Optional[str] = None) -> dict:
    try:
        app_filter = app_filter.strip() if app_filter else None
        if app_filter == "":
            app_filter = None
        sessions = await focus_sessions_db.get_focus_sessions(uid, app_filter)
        return {"focus_sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/focus-stats")
async def get_focus_stats() -> dict:
    try:
        stats = await focus_sessions_db.get_focus_stats(uid)
        return {"focus_stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/screen-activity")
async def list_screen_activity(app_filter: Optional[str] = None) -> dict:
    try:
        app_filter = app_filter.strip() if app_filter else None
        if app_filter == "":
            app_filter = None
        activities = await focus_sessions_db.list_screen_activity(uid, app_filter)
        return {"screen_activity": activities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/screen-activity/summary")
async def screen_activity_summary(app_filter: Optional[str] = None) -> dict:
    try:
        app_filter = app_filter.strip() if app_filter else None
        if app_filter == "":
            app_filter = None
        summary = await focus_sessions_db.screen_activity_summary(uid, app_filter)
        return {"screen_activity_summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```