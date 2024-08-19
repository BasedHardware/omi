import base64
import os

from fastapi import APIRouter
from langchain_openai import ChatOpenAI

from models import Memory, EndpointResponse

router = APIRouter()


def base64_to_file(base64_url, file_path):
    _, base64_content = base64_url.split(',')
    file_content = base64.b64decode(base64_content)
    # Write the content to the file
    with open(file_path, 'wb') as file:
        file.write(file_content)


api_key = os.getenv('HUME_API_KEY')
chat = ChatOpenAI(model='gpt-4o', temperature=0)


@router.post('/audio/emotional', tags=['basic', 'memory_created'], response_model=EndpointResponse)
def emotional_supporter(memory: Memory):
    return {}

# https://camel-lucky-reliably.ngrok-free.app
