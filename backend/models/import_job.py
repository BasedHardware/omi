from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ImportJobStatus(str, Enum):
    pending = 'pending'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'


class ImportSourceType(str, Enum):
    limitless = 'limitless'
    omi = 'omi'


class ImportJob(BaseModel):
    id: str = Field(description="Unique identifier for the import job")
    uid: str = Field(description="User ID who initiated the import")
    status: ImportJobStatus = Field(default=ImportJobStatus.pending)
    source_type: ImportSourceType = Field(description="Type of import source")
    total_files: int = Field(default=0, description="Total number of files to process")
    processed_files: int = Field(default=0, description="Number of files processed so far")
    conversations_created: int = Field(default=0, description="Number of conversations created")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None, description="When processing started")
    completed_at: Optional[datetime] = Field(default=None, description="When processing completed")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    def dict(self, **kwargs):
        d = super().dict(**kwargs)
        # Convert datetime objects to ISO format strings for Firestore
        if d.get('created_at'):
            d['created_at'] = d['created_at'].isoformat()
        if d.get('started_at'):
            d['started_at'] = d['started_at'].isoformat()
        if d.get('completed_at'):
            d['completed_at'] = d['completed_at'].isoformat()
        return d


class ImportJobResponse(BaseModel):
    job_id: str
    status: ImportJobStatus
    total_files: Optional[int] = None
    processed_files: Optional[int] = None
    conversations_created: Optional[int] = None
    created_at: Optional[str] = None
    error: Optional[str] = None
