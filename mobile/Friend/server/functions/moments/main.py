import json
import os
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import jsonify

headers = {"Access-Control-Allow-Origin": "*"}
load_dotenv()

# Google clouds file structure is different
if os.getenv('LOCAL_DEV') == 'True':
    from .mongo_service import MongoService
else:
    from mongo_service import MongoService

mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client['paxxium']

def cors_preflight_response():
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE, PUT, PATCH",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, Project-ID",
        "Access-Control-Max-Age": "3600",
    }
    return ("", 204, cors_headers)

def handle_fetch_moments():
    # Get all moments from the database
    db_client = MongoService()
    moments_list = db_client.get_all_moments()
    print(moments_list)
    return jsonify({'moments': moments_list}), 200, headers

def handle_add_moment(request):
    db_client = MongoService()
    data = request.json
    new_moment = data['newMoment']
    db_client.add_moment(new_moment)
    return ('Moment Added', 200, headers)

def moments(request):
    if request.method == "OPTIONS":
        return cors_preflight_response()

    if request.path in ('/', '/moments'):
       print('Request path is /moments')
       if request.method == 'GET':
            return handle_fetch_moments()
       
       if request.method == 'POST':
            handle_add_moment(request)
            return ('Moment Added', 200, headers)