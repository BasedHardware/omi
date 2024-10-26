import os
import threading

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from models.memory import Memory

llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

from database._client import get_users_uid
import database.memories as memories_db
from utils.memories.process_memory import save_structured_vector

if __name__ == '__main__':
    uids = get_users_uid()
    for uid in ['TtCJi59JTVXHmyUC6vUQ1d9U6cK2']:
        memories = memories_db.get_memories(uid, limit=2000)
        threads = []
        for memory in memories:
            threads.append(threading.Thread(target=save_structured_vector, args=(uid, Memory(**memory), True)))

        chunks = [threads[i:i + 10] for i in range(0, len(threads), 10)]
        for chunk in chunks:
            [t.start() for t in chunk]
            [t.join() for t in chunk]
