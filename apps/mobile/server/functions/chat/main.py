import os
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
cred = None
if os.getenv('LOCAL_DEV') == 'True':
    from .ChatService import ChatService
else:
    from apps.mobile.server.functions.chat.ChatService import ChatService

# MongoDB URI
mongo_uri = os.getenv('MONGO_URI')
# Create a new MongoClient and connect to the server
client = MongoClient(mongo_uri, tlsCAFile=certifi.where())

db = client['paxxium']

chat_service = ChatService(db)

def chat(request):
    response = {}
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE, PUT, PATCH",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Max-Age": "3600",
        }

        return ("", 204, headers)
    headers = {"Access-Control-Allow-Origin": "*"}
    uid = request.headers.get('uid')
    if request.path in ('/', '/chat'):
        chat_data_list = chat_service.get_all_chats(uid)
        return (chat_data_list, 200, headers)
    
    if request.path in ('/create', '/chat/create'):
        data = request.get_json()
        chat_name = data['chatName']
        agent_model = data['agentModel']

        chat_id = chat_service.create_chat_in_db(uid, chat_name, agent_model, )
        chat_data = {
            'chatId': chat_id,
            'chat_name': chat_name,
            'agent_model': agent_model,
        }
        return (chat_data, 200, headers)
    
    if request.path in ('/delete', '/chat/delete'):
        data = request.get_json()
        chat_id = data['chatId']
        chat_service.delete_conversation(uid, chat_id)
        return ('Conversation deleted', 200, headers)

    
    

    
