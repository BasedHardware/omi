"""Introspection for the calling Developer API credential; no user content access."""

from fastapi import APIRouter, Depends, HTTPException

from database._client import get_firestore_client
from database.api_key_metadata import project_api_key_metadata
from dependencies import ApiKeyAuth, get_api_key_auth
from models.dev_api_key import DevApiKey
from utils.other.endpoints import with_rate_limit_context
from utils.scopes import READ_ONLY_SCOPES

router = APIRouter()


@router.get(
    "/v1/dev/key",
    response_model=DevApiKey,
    tags=["API Keys"],
    summary="Get calling API key",
    operation_id="getCallingApiKey",
    description="Return only the calling key's metadata and effective scopes. No data scope is required.",
)
def get_calling_api_key(
    auth: ApiKeyAuth = Depends(with_rate_limit_context(get_api_key_auth, "dev:key_read")),
):
    # Fetch exactly this credential, never an owner's key inventory or content.
    if not auth.key_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    snapshot = get_firestore_client().collection("dev_api_keys").document(auth.key_id).get()
    data = snapshot.to_dict() if snapshot.exists else None
    if not data or data.get("user_id") != auth.uid:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    projection = project_api_key_metadata(
        document_id=snapshot.id,
        raw=data,
        snapshot_create_time=getattr(snapshot, "create_time", None),
        key_kind="dev",
    )
    metadata = dict(projection.metadata)
    metadata["scopes"] = list(READ_ONLY_SCOPES if auth.scopes is None else auth.scopes)
    return DevApiKey.model_validate(metadata)
