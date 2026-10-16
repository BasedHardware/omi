"""Client-visible sync job response shapes shared by both dispatch protocols."""

from typing import List

from pydantic import BaseModel, Field
from utils.sync.lanes import SyncLane


class SyncLocalFilesResultResponse(BaseModel):
    new_memories: list[str] = Field(default_factory=list)
    updated_memories: list[str] = Field(default_factory=list)
    failed_segments: int = 0
    total_segments: int = 0
    errors: list[str] = Field(default_factory=list)
    held_audio: bool | None = None


class SyncJobStartResponse(BaseModel):
    job_id: str
    status: str
    total_files: int
    total_segments: int
    poll_after_ms: int
    lane: str = SyncLane.FRESH.value


class SyncJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_segments: int = 0
    processed_segments: int = 0
    successful_segments: int = 0
    failed_segments: int = 0
    result: SyncLocalFilesResultResponse | None = None
    error: str | None = None
    lane: str = SyncLane.FRESH.value
    reason_code: str | None = None
    retry_after: int | None = None
    recording_age_seconds: int | None = None
    poll_after_ms: int | None = None


class SyncCaptureManifestFile(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r'^[0-9a-fA-F]{64}$')


class SyncCaptureManifestRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    files: List[SyncCaptureManifestFile] = Field(min_length=1, max_length=20)


class SyncCaptureManifestResponse(BaseModel):
    manifest: str
