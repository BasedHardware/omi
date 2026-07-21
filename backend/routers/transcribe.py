"""Public WebSocket routes for the listen transcription pipeline.

The long-lived implementation lives in :mod:`routers.listen`.  This module is
deliberately kept as the stable route and monkeypatch facade for app and test
callers that have historically imported ``routers.transcribe._stream_handler``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, cast

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from firebase_admin.auth import InvalidIdTokenError

from routers.listen.contracts import CustomSttMode, ListenRequest
from routers.listen.runtime import run_listen_session
from utils.client_device import (
    ClientDeviceContext,
    resolve_client_device_from_websocket_auth_message,
)
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


async def _stream_handler(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[str] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt_mode: CustomSttMode = CustomSttMode.disabled,
    onboarding_mode: bool = False,
    speaker_auto_assign_enabled: bool = False,
    create_speakers: bool = True,
    vad_gate_override: Optional[str] = None,
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
    client_device_context: Optional[ClientDeviceContext] = None,
) -> None:
    """Compatibility facade for the accepted-socket listen session."""
    await run_listen_session(
        ListenRequest(
            websocket=websocket,
            uid=uid,
            language=language,
            sample_rate=sample_rate,
            codec=codec,
            channels=channels,
            include_speech_profile=include_speech_profile,
            stt_service=stt_service,
            conversation_timeout=conversation_timeout,
            source=source,
            custom_stt_mode=custom_stt_mode,
            onboarding_mode=onboarding_mode,
            speaker_auto_assign_enabled=speaker_auto_assign_enabled,
            create_speakers=create_speakers,
            vad_gate_override=vad_gate_override,
            call_id=call_id,
            client_conversation_id=client_conversation_id,
            client_device_context=client_device_context,
        )
    )


async def _listen(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[str] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt_mode: CustomSttMode = CustomSttMode.disabled,
    onboarding_mode: bool = False,
    speaker_auto_assign_enabled: bool = False,
    create_speakers: bool = True,
    vad_gate_override: Optional[str] = None,
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
) -> None:
    try:
        await websocket.accept()
    except RuntimeError as error:
        logger.error('listen accept failed uid=%s error_type=%s', uid, type(error).__name__)
        return
    await _stream_handler(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        stt_service,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=custom_stt_mode,
        onboarding_mode=onboarding_mode,
        speaker_auto_assign_enabled=speaker_auto_assign_enabled,
        create_speakers=create_speakers,
        vad_gate_override=vad_gate_override,
        call_id=call_id,
        client_conversation_id=client_conversation_id,
    )


@router.websocket('/v4/listen')
async def listen_handler(
    websocket: WebSocket,
    uid: str = Depends(auth.get_current_user_uid_ws_listen),
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[str] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt: str = 'disabled',
    onboarding: str = 'disabled',
    speaker_auto_assign: str = 'disabled',
    create_speakers: bool = True,
    vad_gate: str = '',
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
) -> None:
    await _listen(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        stt_service,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=CustomSttMode.enabled if custom_stt == 'enabled' else CustomSttMode.disabled,
        onboarding_mode=onboarding == 'enabled',
        speaker_auto_assign_enabled=speaker_auto_assign == 'enabled',
        create_speakers=create_speakers,
        vad_gate_override=vad_gate if vad_gate in ('enabled', 'disabled') else None,
        call_id=call_id,
        client_conversation_id=client_conversation_id,
    )


@router.websocket('/v4/web/listen')
async def web_listen_handler(
    websocket: WebSocket,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt: str = 'disabled',
    onboarding: str = 'disabled',
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
) -> None:
    try:
        await websocket.accept()
    except RuntimeError as error:
        logger.error('web listen accept failed error_type=%s', type(error).__name__)
        return
    try:
        first_message = await asyncio.wait_for(websocket.receive(), timeout=5.0)
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason='Auth timeout')
        return
    except WebSocketDisconnect:
        return
    try:
        uid = auth.get_current_user_uid_from_ws_message(cast(Dict[str, Any], first_message))
    except ValueError as error:
        await websocket.close(code=1008, reason=str(error))
        return
    except InvalidIdTokenError:
        await websocket.send_json({'type': 'auth_response', 'success': False})
        await websocket.close(code=1008, reason='Invalid token')
        return
    except Exception as error:
        logger.error('web listen auth failed error_type=%s', type(error).__name__)
        await websocket.send_json({'type': 'auth_response', 'success': False})
        await websocket.close(code=1008, reason='Auth error')
        return
    context = resolve_client_device_from_websocket_auth_message(first_message)
    await websocket.send_json({'type': 'auth_response', 'success': True})
    await _stream_handler(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        None,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=CustomSttMode.enabled if custom_stt == 'enabled' else CustomSttMode.disabled,
        onboarding_mode=onboarding == 'enabled',
        call_id=call_id,
        client_conversation_id=client_conversation_id,
        client_device_context=context,
    )
