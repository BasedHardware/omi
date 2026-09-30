import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

import database.trends as trends_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/v1/trends", response_model=List[Dict[str, Any]], tags=['trends'])
def get_trends() -> List[Dict[str, Any]]:
    try:
        return trends_db.get_trends_data()
    except Exception as e:
        logger.error(f"Failed to retrieve trends data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trends data",
        ) from e
