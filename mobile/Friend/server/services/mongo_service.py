import os
from pymongo import MongoClient
from dotenv import load_dotenv

class MongoService:
    def __init__(self):
        load_dotenv()
        mongo_uri = os.getenv('MONGO_URI')
        self.client = MongoClient(mongo_uri)
        self.db = self.client['friend']

    def get_all_moments(self):
        # Fetch all moments from the database
        moments_collection = self.db['moments']
        moments = list(moments_collection.find({}))
        # Convert ObjectId to string and change key _id to id
        for moment in moments:
            moment['id'] = str(moment.pop('_id'))
        return moments

    def add_moment(self, moment_data):
        # Add a new moment to the database
        moments_collection = self.db['moments']
        result = moments_collection.insert_one(moment_data)
        return result.inserted_id

    def close_connection(self):
        # Close the MongoDB connection
        self.client.close()