import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import redis

from backend.database.session import get_db
from backend.models.integration import Integration
from backend.schemas.integration import IntegrationCreate, IntegrationUpdate
from backend.dependencies.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

def get_redis_connection() -> redis.Redis:
    """Get Redis connection from environment variables."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)

@router.get("/")
def list_integrations(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all integrations for the current user."""
    integrations = db.query(Integration).filter(
        Integration.user_id == current_user.id
    ).all()
    return integrations

@router.post("/")
def create_integration(
    integration_data: IntegrationCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new integration for the current user."""
    redis = None
    try:
        redis = get_redis_connection()
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")

    try:
        integration = Integration(
            user_id=current_user.id,
            provider=integration_data.provider,
            config=integration_data.config
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        return integration
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create integration: {e}")
        raise HTTPException(status_code=500, detail="Failed to create integration")
    finally:
        if redis:
            redis.close()

@router.get("/{integration_id}")
def get_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a specific integration."""
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.user_id == current_user.id
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration

@router.put("/{integration_id}")
def update_integration(
    integration_id: int,
    integration_data: IntegrationUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update an integration."""
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.user_id == current_user.id
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    update_data = integration_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(integration, field, value)

    db.commit()
    db.refresh(integration)
    return integration

@router.delete("/{integration_id}")
def delete_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete an integration."""
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.user_id == current_user.id
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    db.delete(integration)
    db.commit()
    return {"message": "Integration deleted successfully"}
