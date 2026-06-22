import os
import sys

# Add the current directory to sys.path so we can import from the backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database._client import db
import database.users as users_db

def check_recent_integrations():
    # Get 10 most recent users who have been active
    print("Checking recent users...")
    docs = db.collection('users').order_by('last_active_at', direction='DESCENDING').limit(10).stream()
    
    for doc in docs:
        uid = doc.id
        user_data = doc.to_dict()
        name = user_data.get('name') or user_data.get('given_name') or 'Unknown'
        print(f"\nUser: {uid} ({name})")
        
        # Check integrations
        integrations_ref = db.collection('users').document(uid).collection('integrations')
        integrations = integrations_ref.stream()
        
        has_integrations = False
        for int_doc in integrations:
            has_integrations = True
            key = int_doc.id
            data = int_doc.to_dict()
            connected = data.get('connected', False)
            has_access = 'access_token' in data
            has_refresh = 'refresh_token' in data
            
            print(f"  Integration: {key}")
            print(f"    Connected: {connected}")
            print(f"    Has Access Token: {has_access}")
            print(f"    Has Refresh Token: {has_refresh}")
            
        if not has_integrations:
            print("  No integrations found.")

if __name__ == "__main__":
    check_recent_integrations()
