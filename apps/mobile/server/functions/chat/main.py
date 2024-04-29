import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import Response

headers = {"Access-Control-Allow-Origin": "*"}
load_dotenv()

# Google clouds file structure is different
if os.getenv('LOCAL_DEV') == 'True':
    from .ChatService import ChatService
    from .BossAgent import BossAgent
else:
    from ChatService import ChatService
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

def handle_fetch_chats(request):
    chat_service = ChatService()
    user_id = request.headers.get('userId')
    chat_data_list = chat_service.get_all_chats(user_id)
    return chat_data_list

def handle_create_chat(request):
    chat_service = ChatService()
    data = request.get_json()
    user_id = data['userId']
    chat_name = data['chatName']
    model = data['model']

    chat_id = chat_service.create_chat_in_db(user_id, chat_name, model)
    chat_data = {
        'chatId': chat_id,
        'chat_name': chat_name,
        'model': model,
        'userId': user_id,
    }
    return chat_data

def handle_delete_chat(request):
    chat_service = ChatService()
    data = request.get_json()
    user_id = data['userId']
    chat_id = data['chatId']
    chat_service.delete_conversation(user_id, chat_id)
    return 'Conversation deleted'

def handle_post_message(request):
    boss_agent = BossAgent()
    chat_service = ChatService()
    data = request.json
    user_message = data.get('userMessage')
    chat_history = data.get('chatHistory')
    chat_id = data.get('chatId')
    message_content = user_message['content']
    chat_service.create_message(chat_id, 'user', message_content)

    complete_message = ''
    
    response_generator = boss_agent.process_message(chat_id, user_message, chat_history)

    # Create a generator to handle streaming and compile the complete message
    def compile_and_stream():
        nonlocal complete_message
        for response in response_generator:
            complete_message += response['content']
            json_response = json.dumps(response) + '\n'
            yield json_response

    # Stream responses to client
    streamed_responses = compile_and_stream()
    response = Response(streamed_responses, mimetype='application/json')
    # After streaming, store the complete message
    response.call_on_close(lambda: chat_service.create_message(chat_id, 'agent', complete_message))

    return response

def chat(request):
    if request.method == "OPTIONS":
        return cors_preflight_response()

    if request.path in ('/', '/chat'):
        if request.method == 'GET':
            chat_data = handle_fetch_chats(request)
            return (chat_data, 200, headers)

        if request.method == 'POST':
            chat_data = handle_create_chat(request)
            return (chat_data, 200, headers)

        if request.method == 'DELETE':
            handle_delete_chat(request)
            return ('Conversation deleted', 200, headers)

    if request.path in ('/messages', '/chat/messages'):
        if request.method == 'POST':
            response = handle_post_message(request)
            return (response, 200, headers)
    
        if request.method == 'DELETE':
            chat_service = ChatService()
            data = request.json
            chat_id = data.get('chatId')
            chat_service.delete_all_messages(chat_id)
            return ('Memory Cleared', 200, headers)
    




    
    

    
