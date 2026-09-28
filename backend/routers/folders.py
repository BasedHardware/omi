from fastapi import HTTPException, status
from typing import List
from pydantic import ValidationError
from logging import getLogger
from .models import Folder
from ..utils import firestore

logger = getLogger(__name__)

async def get_folders() -> List[Folder]:
    folders = []
    docs = await firestore.get_folders_collection()

    for doc in docs:
        try:
            folder = Folder.model_validate(doc)
            folders.append(folder)
        except ValidationError as e:
            logger.error(f"Skipping corrupt folder record {doc.get('id', 'unknown')}: {str(e)}")
            continue

    return folders