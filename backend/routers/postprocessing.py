# from fastapi import APIRouter, Depends, HTTPException, UploadFile
#
# from models.memory import *
# from utils.memories.postprocess_memory import postprocess_memory as postprocess_memory_util
# from utils.other import endpoints as auth
#
# router = APIRouter()
#
#
# @router.post("/v1/memories/{memory_id}/post-processing", response_model=Memory, tags=['memories'])
# def postprocess_memory(
#         memory_id: str, file: Optional[UploadFile], emotional_feedback: Optional[bool] = False,
#         uid: str = Depends(auth.get_current_user_uid)
# ):
#     """
#     The objective of this endpoint, is to get the best possible transcript from the audio file.
#     Instead of storing the initial deepgram result, doing a full post-processing with whisper-x.
#     This increases the quality of transcript by at least 20%.
#     Which also includes a better summarization.
#     Which helps us create better vectors for the memory.
#     And improves the overall experience of the user.
#     """
#
#     # Save file
#     file_path = f"_temp/{memory_id}_{file.filename}"
#     with open(file_path, 'wb') as f:
#         f.write(file.file.read())
#
#     # Process
#     status_code, result = postprocess_memory_util(
#         memory_id=memory_id, uid=uid, file_path=file_path, emotional_feedback=emotional_feedback,
#         streaming_model="deepgram_streaming"
#     )
#     if status_code != 200:
#         raise HTTPException(status_code=status_code, detail=result)
#
#     return result
