import asyncio
import os
import threading
import time
# from deepgram import (
#     DeepgramClient,
#     PrerecordedOptions,
#     FileSource,
# )

from fastapi import APIRouter, FastAPI,Depends, HTTPException, UploadFile

app = FastAPI()


@app.get("/memory")
async def root():
    return {"message": "sexp"}

@app.post("/download_wav")
async def download_wav(file: UploadFile):
    with open("downloaded_wav_file.wav", "wb") as f:
        f.write(file.file.read())
        # try:
        # deepgram = DeepgramClient("DEEPGRAM_API_KEY")

        # with open(AUDIO_FILE, "rb") as file:
        #     buffer_data = file.read()

        # payload: FileSource = {
        #     "buffer": buffer_data,
        # }

        # options = PrerecordedOptions(
        #     model="nova-2",
        #     smart_format=True,
        # )

        # response = deepgram.listen.rest.v("1").transcribe_file(payload, options)

        # print(response.to_json(indent=4))

        # except Exception as e:
        #     print(f"Exception: {e}")
  