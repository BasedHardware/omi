from fastapi import APIRouter, Request, Form, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
import db
import uuid
import os
from dotenv import load_dotenv
from models import TranscriptSegment

load_dotenv()

from .router import process_transcript_task

demo_router = APIRouter()

templates = Jinja2Templates(directory="/app/templates")

@demo_router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    org_id = os.getenv('MULTION_ORG_ID')
    print(f"Debug: org_id = {org_id}") 
    return templates.TemplateResponse("setup_multion_desktop.html", {"request": request, "org_id": org_id})

@demo_router.get("/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request):
    user_id = request.query_params.get("user_id")
    if user_id:
        return templates.TemplateResponse("setup_multion_userid.html", {"request": request, "user_id": user_id})
    return "User ID not found in redirect."

@demo_router.get("/uid_input", response_class=HTMLResponse)
async def uid_input_page(request: Request):
    uid = request.query_params.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="UID not provided in the URL")
    return templates.TemplateResponse("setup_multion_phone.html", {"request": request, "uid": uid})

@demo_router.post("/submit_uid/")
async def submit_uid(request: Request, user_id: str = Form(...), uid: str = Form(...)):
    db.store_multion_user_id(uid, user_id)
    is_setup_completed = db.get_multion_user_id(uid) is not None
    return templates.TemplateResponse("setup_multion_complete.html", {
        "request": request,
        "is_setup_completed": is_setup_completed,
        "user_id": user_id
    })

@demo_router.get("/check_setup_completion")
async def check_setup_completion(uid: str = Query(...)):
    user_id = db.get_multion_user_id(uid)
    is_setup_completed = user_id is not None
    return {"is_setup_completed": is_setup_completed}

@demo_router.post("/process_transcript")
async def initiate_process_transcript(
    background_tasks: BackgroundTasks,
    segments: List[TranscriptSegment],
    session_id: str = Query(...),
    uid: str = Query(...)
):
    user_id = db.get_multion_user_id(uid)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid UID or USERID not found.")
    
    task_id = str(uuid.uuid4())
    full_transcript = " ".join([segment.text for segment in segments])
    
    background_tasks.add_task(
        process_transcript_task,
        task_id,
        full_transcript,
        uid
    )
    
    return {"message": "Processing started", "task_id": task_id}

@demo_router.get("/check_status/{task_id}")
async def check_status(task_id: str):
    status = db.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    response = {"status": status}
    
    if status in ["COMPLETED", "ERROR", "TIMEOUT"]:
        result = db.get_task_result(task_id)
        response["result"] = result
    
    return response

@demo_router.post("/test_endpoint")
async def test_endpoint(uid: str):
    user_id = db.get_multion_user_id(uid)
    if user_id:
        return {"message": f"Mapped USERID: {user_id}"}
    return {"message": "Invalid UID or USERID not found."}