import asyncio
import os
from typing import Any, cast

from dotenv import load_dotenv

dotenv_dir = os.path.join(os.path.dirname(__file__), '../../')
load_dotenv(dotenv_path=f'{dotenv_dir}/.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = f"{dotenv_dir}/google-credentials.json"

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
import routers.chat as chat_routers


async def test_stream():
    # uid = "eLCx***"
    response: Any = chat_routers.send_message(  # type: ignore[reportCallIssue]  # test script with commented-out params
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
        # data=chat_models.SendMessageRequest(
        #     text="summarise my month",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss in the last 3 hours ago",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        #
        # data=chat_models.SendMessageRequest(
        #     text="I talked to a guy today who has experience hosting events, what does their startup do",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="where did i have dinner last night",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i talk about firmware recently",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="i have talked to my team about rolling out the subscription plan. can you check my discussions and suggest what the better plan is ?",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
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
        # data=chat_models.SendMessageRequest(
        #   text="remind me to check the omi chat discussion on github",
        #   file_ids=[],  # ['x']
        # ),
        # uid=uid,
        #
        # OMI docs
        #
        # data=chat_models.SendMessageRequest(
        #    text="how to flash the omi consumer cv1 firmware ?",
        #    file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss 3 hours ago",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
        # data=chat_models.SendMessageRequest(
        #     text="what did i discuss in the last 3 hours ago",
        #     file_ids=[],  # ['x']
        # ),
        # uid=uid,
    )

    # Read the stream
    async for chunk in cast(Any, response).body_iterator:
        if isinstance(chunk, bytes):
            print(chunk.decode('utf-8'))
        else:
            print(chunk)  # Already a string


if __name__ == '__main__':
    asyncio.run(test_stream())
