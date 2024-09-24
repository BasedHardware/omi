import math
import time
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from database._client import db
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1 import FieldFilter

class MemoryTime(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


def migration_incorrect_start_finish_time():
    user_offset = 0
    user_limit = 400
    while True:
        print(f"running...user...{user_offset}")
        users_ref = (
            db.collection('users')
            .order_by(FieldPath.document_id(), direction=firestore.Query.ASCENDING)
        )
        users_ref = users_ref.limit(user_limit).offset(user_offset)
        users = list(users_ref.stream())
        if not users or len(users) == 0:
            print("no users")
            break
        for user in users:
            offset = 0
            limit = 400
            while True:
                print(f"running...user...{user.id}...memories...{offset}")
                memories_ref = (
                    db.collection('users').document(user.id).collection("memories")
                    .order_by(FieldPath.document_id(), direction=firestore.Query.ASCENDING)
                )
                memories_ref = memories_ref.limit(limit).offset(offset)
                docs = list(memories_ref.stream())
                if not docs or len(docs) == 0:
                    break
                batch = db.batch()
                for doc in docs:
                    if not doc:
                        continue

                    memory = MemoryTime(**doc.to_dict())
                    if not memory.started_at:
                        continue

                    delta = memory.created_at.timestamp() - memory.started_at.timestamp()
                    if math.fabs(delta) < 15*60:  # gaps in 15' is ok
                        continue
                    td = None
                    if delta > 0:
                        td = timedelta(seconds=math.fabs(delta))
                    else:
                        td = -timedelta(seconds=math.fabs(delta))
                    if memory.finished_at:
                        memory.finished_at = memory.finished_at + td
                    memory.started_at = memory.started_at + td

                    memory_ref = db.collection('users').document(user.id).collection('memories').document(memory.id)

                    batch.update(memory_ref, memory.dict())

                batch.commit()
                offset += len(docs)
                time.sleep(.01)  # sleep 100ms

        user_offset = user_offset + len(users)
