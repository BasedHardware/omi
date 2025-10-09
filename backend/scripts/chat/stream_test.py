import asyncio
import os
import threading

from dotenv import load_dotenv

load_dotenv('../../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "../../google-credentials.json"

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from models.conversation import Conversation

llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
import database.conversations as conversations_db
import models.chat as chat_models
import routers.chat as chat_routers


async def test_stream():
    response = chat_routers.send_message(
        data=chat_models.SendMessageRequest(
            text="i use shopify but for some reason the cost of shipping is incredibly high. I think it uses DDP. Someone enabled flavorcloud (i don't know why) and im not sure it allows to ship without ddp. how to decrease cost of shipping?",
            file_ids=[],  # ['x']
        ),
        uid="uid",
    )

    # Read the stream
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            print(chunk.decode('utf-8'))
        else:
            print(chunk)  # Already a string


if __name__ == '__main__':
    asyncio.run(test_stream())
