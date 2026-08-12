from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import llm_oauth as llm_oauth_db
from utils.byok import invalidate_byok_state_cache
from utils.executors import critical_executor, db_executor, llm_executor, run_blocking
from utils.other.endpoints import enforce_rate_limit
from utils.llm.oauth import LLMOAuthError, exchange_authorization_code, oauth_configuration, supported_provider
from utils.other import endpoints as auth

router = APIRouter()


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    code: str = Field(min_length=1, max_length=4096)
    code_verifier: str = Field(min_length=43, max_length=128)
    redirect_uri: str


class StatusResponse(BaseModel):
    connected: List[str]
    selected_provider: Optional[str]
    configurations: Dict[str, 'ProviderConfiguration']


class ProviderConfiguration(BaseModel):
    authorization_url: str
    client_id: str
    redirect_uri: str
    scope: str
    authorization_parameters: Dict[str, str]


async def _status_response(uid: str) -> dict:
    status = await run_blocking(db_executor, llm_oauth_db.get_status, uid)
    status['configurations'] = {
        provider: configuration
        for provider in ('chatgpt', 'grok')
        if (configuration := oauth_configuration(provider)) is not None
    }
    return status


@router.get('/v1/users/me/llm-oauth', tags=['v1'], response_model=StatusResponse)
async def get_status(uid: str = Depends(auth.get_current_user_uid)):
    await run_blocking(critical_executor, enforce_rate_limit, uid, 'llm_oauth:status', fail_closed=True)
    return await _status_response(uid)


@router.post('/v1/users/me/llm-oauth/{provider}', tags=['v1'], response_model=StatusResponse)
async def complete(
    provider: str,
    data: CompletionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    configuration = oauth_configuration(provider)
    if not supported_provider(provider) or configuration is None or data.redirect_uri != configuration['redirect_uri']:
        raise HTTPException(status_code=400, detail='Unsupported LLM OAuth provider or redirect URI')
    await run_blocking(critical_executor, enforce_rate_limit, uid, 'llm_oauth:exchange', fail_closed=True)
    try:
        credential = await run_blocking(
            llm_executor,
            exchange_authorization_code,
            provider,
            data.code,
            data.code_verifier,
            data.redirect_uri,
        )
        await run_blocking(db_executor, llm_oauth_db.save_credential, uid, provider, credential)
    except LLMOAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    invalidate_byok_state_cache(uid)
    return await _status_response(uid)


@router.delete('/v1/users/me/llm-oauth/{provider}', tags=['v1'], response_model=StatusResponse)
async def delete(provider: str, uid: str = Depends(auth.get_current_user_uid)):
    if not supported_provider(provider):
        raise HTTPException(status_code=404, detail='Unsupported LLM OAuth provider')
    await run_blocking(critical_executor, enforce_rate_limit, uid, 'llm_oauth:exchange', fail_closed=True)
    await run_blocking(db_executor, llm_oauth_db.delete_credential, uid, provider)
    invalidate_byok_state_cache(uid)
    return await _status_response(uid)
