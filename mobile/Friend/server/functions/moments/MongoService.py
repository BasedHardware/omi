import os
from pymongo import MongoClient
from dotenv import load_dotenv

class MongoService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MongoService, cls).__new__(cls)
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
        if self.db:
            moments_collection = self.db['moments']
            moments = list(moments_collection.find({}))
            for moment in moments:
                moment['id'] = str(moment.pop('_id'))
            return moments
        else:
            print("MongoDB connection is not initialized.")
            return []

    def add_moment(self, moment_data):
        self._initialize_client()
        if self.db:
            moments_collection = self.db['moments']
            result = moments_collection.insert_one(moment_data)
            return result.inserted_id
        else:
            print("MongoDB connection is not initialized.")
            return None

    def close_connection(self):
        if self.client:
            self.client.close()

    def __enter__(self):
        self._initialize_client()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()