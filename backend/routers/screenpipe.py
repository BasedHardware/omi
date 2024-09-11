# import os
# import uuid
# from datetime import datetime, timezone
#
# from fastapi import APIRouter
# from fastapi import Request, HTTPException
#
# from database.memories import upsert_memory
# from models.integrations import ScreenPipeCreateMemory
# from models.memory import Memory
# from utils.llm import get_transcript_structure, summarize_screen_pipe
#
# router = APIRouter()
#
#
# @router.post('/v1/integrations/screenpipe', response_model=Memory)
# def create_memory(request: Request, uid: str, data: ScreenPipeCreateMemory):
#     if request.headers.get('api_key') != os.getenv('SCREENPIPE_API_KEY'):
#         raise HTTPException(status_code=401, detail="Invalid API Key")
#
#     if data.source == 'screen':
#         structured = summarize_screen_pipe(data.text)
#     elif data.source == 'audio':
#         structured = get_transcript_structure(data.text, datetime.now(timezone.utc), 'en')
#     else:
#         raise HTTPException(status_code=400, detail='Invalid memory source')
#
#     memory = Memory(
#         id=str(uuid.uuid4()),
#         uid=uid,
#         structured=structured,
#         started_at=datetime.now(timezone.utc),
#         finished_at=datetime.now(timezone.utc),
#         created_at=datetime.now(timezone.utc),
#         discarded=False,
#         deleted=False,
#         source='screenpipe',
#     )
#
#     output = memory.dict()
#     output['external_data'] = data.dict()
#     upsert_memory(uid, output)
#     return output
