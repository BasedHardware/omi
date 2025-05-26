# import json
# import os
#
# from fastapi import APIRouter
# from mem0 import MemoryClient
#
# from models import Memory, EndpointResponse
#
# router = APIRouter()
#
#
# # **************************************************
# # ************ On Memory Created Plugin ************
# # **************************************************
#
#
# @router.post("/mem0", response_model=EndpointResponse, tags=["mem0"])
# def mem0_add(memory: Memory, uid: str):
#     transcript_segments = memory.transcriptSegments
#     messages = []
#     for segment in transcript_segments:
#         messages.append(
#             {
#                 "role": "user" if segment.is_user else "assistant",
#                 "content": segment.text,
#             }
#         )
#     # Had to move here because initialization causes issues with modal
#     if not messages:
#         return {"message": "No messages found"}
#
#     mem0 = MemoryClient(api_key=os.getenv("MEM0_API_KEY"))
#     mem0.add(messages, user_id=uid)
#     memories = mem0.search(json.dumps(messages), user_id=uid)
#     response = [row["memory"] for row in memories]
#     response_str = "\n".join(response)
#     # TODO: make response 10-15 words. This will be triggered as notification.
#     return {"message": f"User memories: {response_str}"}
