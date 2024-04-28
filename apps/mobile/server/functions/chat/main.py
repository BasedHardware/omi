import os
from pymongo import MongoClient
from dotenv import load_dotenv

headers = {"Access-Control-Allow-Origin": "*"}
load_dotenv()

# Google clouds file structure is different
if os.getenv('LOCAL_DEV') == 'True':
    from .ChatService import ChatService
else:
    from ChatService import ChatService

mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client['paxxium']
chat_service = ChatService(db)

def cors_preflight_response():
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE, PUT, PATCH",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, Project-ID",
        "Access-Control-Max-Age": "3600",
    }
    return ("", 204, cors_headers)

def handle_fetch_chats(request):
    uid = request.headers.get('uid')
    # Get all moments from the database
    chat_data_list = chat_service.get_all_chats(uid)
    return chat_data_list

def handle_add_chat(request):
    data = request.get_json()
    uid = request.headers.get('uid')
    chat_name = data['chatName']
    agent_model = data['agentModel']

    chat_id = chat_service.create_chat_in_db(uid, chat_name, agent_model, )
    chat_data = {
        'chatId': chat_id,
        'chat_name': chat_name,
        'agent_model': agent_model,
    }
    return chat_data

def handle_delete_chat(request):
    data = request.get_json()
    uid = request.headers.get('uid')
    chat_id = data['chatId']
    chat_service.delete_conversation(uid, chat_id)
    return 'Conversation deleted'

def chat(request):
    if request.method == "OPTIONS":
        return cors_preflight_response()
    
    if request.method == 'GET':
        chat_data = handle_fetch_chats(request)
        return (chat_data, 200, headers)
    
    if request.method == 'POST':
        chat_data = handle_add_chat(request)
        return (chat_data, 200, headers)
    
    if request.method == 'DELETE':
        handle_delete_chat(request)
        return ('Conversation deleted', 200, headers)

    
    

    
