from google.cloud import firestore

from _shared import *

db = firestore.Client()


def get_memories_json():
    memories_ref = (db.collection('users').document(uid).collection('memories'))
    memories_ref = memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    memories = [doc.to_dict() for doc in memories_ref.stream()]
    with open('memories.json', 'w') as f:
        f.write(json.dumps(memories, indent=4, default=str))


if __name__ == '__main__':
    get_memories_json()
