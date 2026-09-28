from fastapi import HTTPException, status
from typing import List
from pydantic import ValidationError
from logging import getLogger
from .models import DeveloperFolder
from ..utils import firestore

logger = getLogger(__name__)

async def get_user_folders(user_id: str) -> List[DeveloperFolder]:
    folders = []
    docs = await firestore.get_user_folders_collection(user_id)

    for doc in docs:
        try:
            folder = DeveloperFolder.model_validate(doc)
            folders.append(folder)
        except ValidationError as e:
            logger.error(f"Skipping corrupt user folder record {doc.get('id', 'unknown')}: {str(e)}")
            continue

    return folders