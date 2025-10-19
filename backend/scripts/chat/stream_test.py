import asyncio
import os
import threading
import pprint

from dotenv import load_dotenv

dotenv_dir = os.path.join(os.path.dirname(__file__), '../../')
load_dotenv(dotenv_path=f'{dotenv_dir}/.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = f"{dotenv_dir}/google-credentials.json"

# pprint.pprint(dict(os.environ))

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from models.conversation import Conversation

llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
import database.conversations as conversations_db
import models.chat as chat_models
import routers.chat as chat_routers


async def test_stream():
    uid = "GPW9***"
    response = chat_routers.send_message(
        # data=chat_models.SendMessageRequest(
        #    text="Did i discuss anything abt yacht party recently? If yes do you think that partnership makes sense for us",
        #    file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss 2 hour ago",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss today",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss on oct 17",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss at 520 pm",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        data=chat_models.SendMessageRequest(
            text="summarise my week",
            file_ids=[],  # ['x']
        ),
        uid=uid,
        ### MEMORIES TOOLS
        #
        # data=chat_models.SendMessageRequest(
        #     text="what memories do i have 2 hours ago",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what memories do i have on oct 13",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what memories do i have at 520pm oct 17",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        ### ACTION ITEMS
        #
        # data=chat_models.SendMessageRequest(
        #     text="what action items do i have 2 hours ago",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #    text="what action items do i have on oct 19",
        #    file_ids=[],  # ['x']
        # ),
        # uid=uid,
    )

    # Read the stream
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            print(chunk.decode('utf-8'))
        else:
            print(chunk)  # Already a string


if __name__ == '__main__':
    asyncio.run(test_stream())
