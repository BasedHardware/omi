import re
import os
import json
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
    moment_service = MomentService()
    moments_list = moment_service.get_all_moments()
    return moments_list

def handle_add_moment(request):
    """
    This function handles the addition of a new moment.
    """
    moment_service = MomentService()
    boss_agent = BossAgent()
    data = request.json
    new_moment = data['newMoment']
    new_moment = {**new_moment, **boss_agent.extract_content(new_moment)}
    # Add the moment to the database
    new_moment = moment_service.add_moment(new_moment)
    # Create the first snapshot for the moment
    action_items_str = "Action Items:\n" + "\n".join(new_moment['actionItems'])
    combined_content = f"Transcript: {new_moment['transcript']}\n{action_items_str}\nSummary: {new_moment['summary']}"
    snapshot_data = new_moment.copy()
    snapshot_data['embeddings'] = boss_agent.embed_content(combined_content)
    moment_service.create_snapshot(snapshot_data)
    
    return new_moment

def handle_update_moment(request):
    boss_agent = BossAgent()
    moment_service = MomentService()
    data = request.json

    current_moment = data['moment']
    moment_id = current_moment['momentId']
    current_snapshot = {**current_moment, **boss_agent.extract_content(current_moment)}
    current_snapshot['momentId'] = moment_id
    previous_snapshot = moment_service.get_previous_snapshot(moment_id)

    # Combine and embed the current snapshot
    action_items_str = "Action Items:\n" + "\n".join(current_snapshot['actionItems'])
    combined_content = f"Transcript: {current_moment['transcript']}\n{action_items_str}\nSummary: {current_snapshot['summary']}"
    current_snapshot['embeddings'] = boss_agent.embed_content(combined_content)
    
    # Create snapshot in the db
    moment_service.create_snapshot(current_snapshot)

    # diff the current snapshot with the previous snapshot
    new_snapshot = boss_agent.diff_snapshots(previous_snapshot, current_snapshot)

    new_snapshot['momentId'] = moment_id
    new_snapshot['date'] = current_moment['date']
    new_snapshot['transcript'] = current_moment['transcript']

    new_transcript = moment_service.update_moment(new_snapshot)
    new_snapshot['transcript'] = new_transcript
    
    return new_snapshot

def handle_delete_moment(request):
    moment_service = MomentService()
    data = request.json
    moment_id = data['id']
    moment_service.delete_moment(moment_id)
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
       
       if request.method == 'PUT':
            updated_moment = handle_update_moment(request)
            return jsonify({'moment': updated_moment}), 200, headers
       
       if request.method == 'DELETE':
            handle_delete_moment(request)
            return ('Delete Moment', 200, headers)