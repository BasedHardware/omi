import os
from bson.objectid import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv

class MomentService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MomentService, cls).__new__(cls)
        return cls._instance

    def __init__(self, mongo_uri=None, db_name='friend'):
        if not hasattr(self, 'is_initialized'):
            self.is_initialized = True
            self.mongo_uri = mongo_uri or self._load_mongo_uri()
            self.db_name = db_name
            self.client = None
            self.db = None

    def _load_mongo_uri(self):
        load_dotenv()
        return os.getenv('MONGO_URI')

    def _initialize_client(self):
        if self.client is None:
            try:
                self.client = MongoClient(self.mongo_uri)
                self.db = self.client[self.db_name]
            except Exception as e:
                print(f"Failed to connect to MongoDB: {e}")
                self.client = None
                self.db = None

    def get_all_moments(self):
        self._initialize_client()
        if self.db is not None:  
            moments_collection = self.db['moments']
            moments = list(moments_collection.find({}))
            for moment in moments:
                moment['id'] = str(moment.pop('_id'))
            return moments
        else:
            print("MongoDB connection is not initialized.")
            return []

    def get_previous_snapshot(self, moment_id):
        self._initialize_client()
        if self.db is not None:
            snapshots_collection = self.db['snapshots']
            snapshots = list(snapshots_collection.find({'momentId': moment_id}))
            if len(snapshots) > 0:
                most_recent_snapshot = snapshots[-1]
                most_recent_snapshot['id'] = str(most_recent_snapshot.pop('_id'))
                return most_recent_snapshot
            else:
                return None
        else:
            print("MongoDB connection is not initialized.")
            return None
    
    def create_snapshot(self, snapshot_data):
        self._initialize_client()
        if self.db is not None:
            snapshots_collection = self.db['snapshots']
            snapshots_collection.insert_one(snapshot_data)
            # Convert _id to string and rename it to id
            snapshot_data['id'] = str(snapshot_data.pop('_id'))
            return snapshot_data
        else:
            print("MongoDB connection is not initialized.")
            return None
        
    def add_moment(self, moment_data):
        self._initialize_client()
        if self.db is not None:
            moments_collection = self.db['moments']
            moments_collection.insert_one(moment_data)
            # Convert _id to string and rename it to id
            moment_data['momentId'] = str(moment_data.pop('_id'))
            return moment_data
        else:
            print("MongoDB connection is not initialized.")
            return None
    
    def update_moment(self, moment_data):
        self._initialize_client()
        if self.db is not None:
            moments_collection = self.db['moments']
            moment_id = moment_data['momentId']

            # Fetch the current transcript
            current_moment = moments_collection.find_one({'_id': ObjectId(moment_id)})
            if current_moment:
                current_transcript = current_moment.get('transcript', '')
                new_transcript = current_transcript + moment_data['transcript']

                update_data = {
                    '$set': {
                        'actionItems': moment_data['actionItems'],
                        'summary': moment_data['summary'],
                        'transcript': new_transcript 
                    }
                }
                result = moments_collection.update_one({'_id': ObjectId(moment_id)}, update_data)
                return result.modified_count
            else:
                print("Moment not found.")
                return 0
        else:
            print("MongoDB connection is not initialized.")
            return 0
        
    def delete_moment(self, moment_id):
        self._initialize_client()
        if self.db is not None:
            moments_collection = self.db['moments']
            result = moments_collection.delete_one({'_id': ObjectId(moment_id)})
            return result.deleted_count
        else:
            print("MongoDB connection is not initialized.")
            return 0

    def close_connection(self):
        if self.client:
            self.client.close()

    def __enter__(self):
        self._initialize_client()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()