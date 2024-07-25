import os

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from modal import Image, App, Secret, asgi_app, mount

from models import Memory
from mem0 import MemoryClient

app = FastAPI()

modal_app = App(
    name="plugins_examples",
    secrets=[Secret.from_dotenv(".env")],
    mounts=[
        mount.Mount.from_local_dir("templates/", remote_path="templates/"),
    ],
)

mem0 = MemoryClient(api_key=os.getenv("MEM0_API_KEY", "123"))


@modal_app.function(
    image=Image.debian_slim().pip_install_from_requirements("requirements.txt"),
    keep_warm=1,  # need 7 for 1rps
    memory=(1024, 2048),
    cpu=4,
    allow_concurrent_inputs=10,
)
@asgi_app()
def plugins_app():
    return app


# **************************************************
# ************ On Memory Created Plugin ************
# **************************************************


@app.post("/mem0")
def mem0_add(memory: Memory, uid: str):
    transcript_segments = memory.transcriptSegments
    messages = []
    for segment in transcript_segments:
        messages.append(
            {
                "role": "user" if segment.is_user else "assistant",
                "content": segment.text,
            }
        )
    if not messages:
        return {"message": "No messages found"}

    mem0.add(messages, user_id=uid)
    memories = mem0.search(messages, user_id=uid)
    response = [row["memory"] for row in memories]
    response_str = "\n".join(response)
    return {"message": f"User memories: {response_str}"}
