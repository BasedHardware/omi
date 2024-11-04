from google.cloud.firestore_v1 import FieldFilter
from typing import Optional

from ._client import db

class TaskDB:
    def __init__(self, db_client):
        self.db = db_client
        self.collection = self.db.get_collection("tasks")

    async def create_task(self, task_data: dict) -> dict:
        result = await self.collection.insert_one(task_data)
        return await self.collection.find_one({"_id": result.inserted_id})

    async def get_task(self, task_id: str) -> Optional[dict]:
        return await self.collection.find_one({"task_id": task_id})

    async def update_task_status(self, task_id: str, status: str) -> dict:
        await self.collection.update_one({"task_id": task_id}, {"$set": {"status": status}})
        return await self.get_task(task_id)

def get_task_by_action_request(action: str, request_id: str):
    query = (db.collection('tasks').where(filter=FieldFilter('action', '==', action))
             .where(filter=FieldFilter('request_id', '==', request_id))
             .limit(1)
             )
    tasks = [item.to_dict() for item in query.stream()]
    if len(tasks) > 0:
        return tasks[0]

    return None
