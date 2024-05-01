import re
import os
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import jsonify

headers = {"Access-Control-Allow-Origin": "*"}
load_dotenv()

# Google clouds file structure is different
if os.getenv('LOCAL_DEV') == 'True':
    from .MomentService import MomentService
    from .BossAgent import BossAgent
else:
    from MomentService import MomentService
    from BossAgent import BossAgent

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
    db_client = MomentService()
    moments_list = db_client.get_all_moments()
    return moments_list

def handle_add_moment(request):
    db_client = MomentService()
    boss_agent = BossAgent()
    data = request.json
    new_moment = data['newMoment']
    summary, title, action_items = boss_agent.extract_content(new_moment)

    # Use regex to extract only the content within square brackets
    action_items_cleaned = re.findall(r'\[.*?\]', action_items)
    if action_items_cleaned:
        action_items = action_items_cleaned[0]
    else:
        action_items = '[]' 

    new_moment['summary'] = summary
    new_moment['title'] = title
    new_moment['actionItems'] = action_items

    db_client.add_moment(new_moment)
    return new_moment

def handle_delete_moment(request):
    db_client = MomentService()
    data = request.json
    moment_id = data['id']
    db_client.delete_moment(moment_id)
    return 'Moment Deleted'

def moments(request):
    if request.method == "OPTIONS":
        return cors_preflight_response()

    if request.path in ('/', '/moments'):
       if request.method == 'GET':
            moments_list = handle_fetch_moments()
            return jsonify({'moments': moments_list}), 200, headers
       
       if request.method == 'POST':
            new_moment = handle_add_moment(request)
            return jsonify({'moment': new_moment}), 200, headers
       
       if request.method == 'DELETE':
            handle_delete_moment(request)
            return ('Delete Moment', 200, headers)