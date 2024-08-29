from fastapi import FastAPI, Request, Form, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import List
from pydantic import BaseModel
from modal import Image, Mount, Secret, asgi_app, Stub
import db
import uuid
from fastapi.responses import RedirectResponse
import os
from dotenv import load_dotenv
from models import TranscriptSegment

load_dotenv()

# Import the router and the process_transcript_task function
from .router import router as multion_router, process_transcript_task

# Define the Image
image = (
    Image.debian_slim()
    .pip_install("fastapi", "uvicorn", "jinja2", "httpx", "redis", "python-dotenv")
)

# Create the Stub (Note: Consider updating to App in the future as per the deprecation warning)
stub = Stub("friend-demo")

# Create FastAPI app
app = FastAPI()

# Add the Multion router
app.include_router(multion_router)

# Setup templates
templates = Jinja2Templates(directory="/app/templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    org_id = os.getenv('MULTION_ORG_ID')
    print(f"Debug: org_id = {org_id}") 
    return templates.TemplateResponse("setup_multion_desktop.html", {"request": request, "org_id": org_id})

@app.get("/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request):
    user_id = request.query_params.get("user_id")
    if user_id:
        return templates.TemplateResponse("setup_multion_userid.html", {"request": request, "user_id": user_id})
    return "User ID not found in redirect."

@app.get("/uid_input", response_class=HTMLResponse)
async def uid_input_page(request: Request):
    uid = request.query_params.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="UID not provided in the URL")
    return templates.TemplateResponse("setup_multion_phone.html", {"request": request, "uid": uid})

@app.post("/submit_uid/")
async def submit_uid(request: Request, user_id: str = Form(...), uid: str = Form(...)):
    db.store_multion_user_id(uid, user_id)
    is_setup_completed = db.get_multion_user_id(uid) is not None
    return templates.TemplateResponse("setup_multion_complete.html", {
        "request": request,
        "is_setup_completed": is_setup_completed,
        "user_id": user_id
    })

@app.get("/check_setup_completion")
async def check_setup_completion(uid: str = Query(...)):
    user_id = db.get_multion_user_id(uid)
    is_setup_completed = user_id is not None
    return {"is_setup_completed": is_setup_completed}

@app.post("/process_transcript")
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

@app.get("/check_status/{task_id}")
async def check_status(task_id: str):
    status = db.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    response = {"status": status}
    
    if status in ["COMPLETED", "ERROR", "TIMEOUT"]:
        result = db.get_task_result(task_id)
        response["result"] = result
    
    return response

@app.post("/test_endpoint")
async def test_endpoint(uid: str):
    user_id = db.get_multion_user_id(uid)
    if user_id:
        return {"message": f"Mapped USERID: {user_id}"}
    return {"message": "Invalid UID or USERID not found."}

@stub.function(
    image=image,
    secrets=[Secret.from_name("multion_friend")],
    mounts=[
        Mount.from_local_dir(".", remote_path="/app"),
    ],
)
@asgi_app()
def fastapi_app():
    app.mount("/static", StaticFiles(directory="/app/static"), name="static")
    return app

@stub.local_entrypoint()
def main():
    stub.serve()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)