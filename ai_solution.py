```python
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..models.folders import Folder
from ..models.conversations import Conversation
from ..models.users import User
from ..database import db

router = APIRouter()

class FolderUpdate(BaseModel):
    name: Optional[str]

@router.get("/v1/folders/{folder_id}")
async def get_folder(folder_id: str) -> Folder:
    try:
        if not folder_id.strip():
            raise HTTPException(status_code=400, detail="folder_id must not be empty or whitespace")
        folder = db.get_folder(folder_id)
        return Folder.from_dict(folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/v1/folders/{folder_id}")
async def update_folder(folder_id: str, body: FolderUpdate) -> Folder:
    try:
        if not folder_id.strip():
            raise HTTPException(status_code=400, detail="folder_id must not be empty or whitespace")
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="name must not be empty or whitespace")
        folder = db.update_folder(folder_id, body.dict())
        return Folder.from_dict(folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v1/folders")
async def create_folder(name: str) -> Folder:
    try:
        if not name.strip():
            raise HTTPException(status_code=400, detail="name must not be empty or whitespace")
        folder = db.create_folder(name)
        return Folder.from_dict(folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/folders/{folder_id}/conversations")
async def get_folder_conversations(folder_id: str, move_to_folder_id: Optional[str] = None) -> List[Conversation]:
    try:
        if folder_id and not folder_id.strip():
            raise HTTPException(status_code=400, detail="folder_id must not be empty or whitespace")
        if move_to_folder_id and not move_to_folder_id.strip():
            raise HTTPException(status_code=400, detail="move_to_folder_id must not be empty or whitespace")
        conversations = db.get_folder_conversations(folder_id, move_to_folder_id)
        return [Conversation.from_dict(conv) for conv in conversations]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```