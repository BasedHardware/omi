# generate_all_tokens.py
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pathlib import Path
import os

# Get credentials directory (scripts -> backend -> credentials)
BASE_DIR = Path(__file__).resolve().parent.parent
CREDS_DIR = BASE_DIR / 'credentials'
TOKEN_PATH = CREDS_DIR / 'token.json'
CREDENTIALS_PATH = CREDS_DIR / 'credentials.json'

# Combined scopes for all services
SCOPES = [
    # Gmail 
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    
    # Drive 
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata',
    'https://www.googleapis.com/auth/drive.readonly',
    
    # Calendar 
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar.readonly',
]

def main():
    creds = None
    
    # Check if token exists
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Check if credentials.json exists
            if not CREDENTIALS_PATH.exists():
                print(f"❌ ERROR: credentials.json not found at {CREDENTIALS_PATH}")
                print(f"   Please place your credentials.json in: {CREDS_DIR}")
                return
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the token
        with open(str(TOKEN_PATH), 'w') as token:
            token.write(creds.to_json())
    
    print("✅ Token generated successfully!")
    print(f"✅ Token saved to: {TOKEN_PATH}")
    print("✅ All services (Gmail, Drive, Calendar) are now authenticated!")

if __name__ == '__main__':
    main()