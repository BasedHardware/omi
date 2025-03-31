from flask import Flask, request, jsonify, send_from_directory, redirect, session, url_for
import requests
import json
import os
import datetime
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import httplib2
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request


# Load environment variables from .env file
load_dotenv()

# Configuration spécifique au développement
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
if os.getenv('FLASK_ENV') == 'development' and 'OAUTHLIB_INSECURE_TRANSPORT' not in os.environ:
    raise ValueError("OAuth doit être en mode HTTP uniquement en développement. Configurez OAUTHLIB_INSECURE_TRANSPORT=1")


app = Flask(__name__, static_url_path='/static')
# Utiliser une clé secrète fixe pour que les sessions persistent entre les redémarrages
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'gcal-omi-integration-secret-key')
# Configuration des cookies de session pour améliorer la persistance
app.config['SESSION_COOKIE_SECURE'] = False  # Mettre à True en production avec HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=5)  # Durée de vie de la session
app.config['SESSION_COOKIE_DOMAIN'] = None  # Allow cross-subdomain access
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # Renew session timestamp

# API configuration for Omi
APP_ID = "test_app_id"  # Add your Omi App ID here
API_KEY = "test_api_key"  # Add your Omi API key here
API_URL = f"https://api.omi.me/v2/integrations/{APP_ID}/user/facts"

# Google Calendar API configuration
CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI")
AUTH_URL = os.getenv("GOOGLE_CALENDAR_AUTH_URL")
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

@app.route('/')
def index():
    """Serve the main HTML page"""
    # Check if uid is provided, if not, redirect to the same page with a default test user ID
    user_id = request.args.get('uid')
    if not user_id:
        # For development/testing purposes, redirect with a default test user ID
        return redirect('/?uid=test_user_123')
    
    # Check if OAuth credentials are properly configured
    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({
            "error": "OAuth configuration incomplete", 
            "message": "Please set GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET in your .env file."
        }), 500
        
    return send_from_directory('.', 'index.html')

@app.route('/auth')
def auth():
    """Initiate the OAuth flow"""
    # Get user ID from query parameter
    user_id = request.args.get('uid')
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    # Check if OAuth credentials are properly configured
    if not CLIENT_ID or not CLIENT_SECRET or CLIENT_SECRET == "YOUR_CLIENT_SECRET_HERE":
        return jsonify({
            "error": "OAuth configuration incomplete", 
            "message": "Please set GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET in your .env file with valid credentials."
        }), 403
    
    # Store user ID in session and make session permanent
    session.permanent = True
    session['user_id'] = user_id
    # Force immediate session save
    session.modified = True
    # Regenerate session ID to prevent fixation
    try:
        session.regenerate()
    except AttributeError:
        # Fallback for environments without regenerate
        session.clear()
        session['user_id'] = user_id
        session.modified = True
    
    # Create OAuth flow instance
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": AUTH_URL,
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES
    )
    
    flow.redirect_uri = REDIRECT_URI
    
    # Generate authorization URL
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Store state in session
    session['state'] = state
    session.modified = True
    
    # Redirect to Google's OAuth page
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    """Handle the OAuth callback"""
    # Get state from session and request
    session_state = session.get('state')
    request_state = request.args.get('state')
    user_id = session.get('user_id')
    
    # Enhanced session validation with error prevention
    if not session_state or not request_state:
        # Clear invalid session and redirect to restart auth flow
        session.clear()
        return redirect(url_for('index'))
        
    if session_state != request_state:
        # Log mismatch and regenerate session ID
        app.logger.error(f"State mismatch: Session {session_state} vs Request {request_state}")
        session.clear()
        if hasattr(session, 'regenerate'):
            session.regenerate()
        return redirect(url_for('index'))
    
    # Create OAuth flow instance
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": AUTH_URL,
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        state=request_state
    )
    
    flow.redirect_uri = REDIRECT_URI
    
    # Exchange authorization code for credentials
    flow.fetch_token(authorization_response=request.url)
    
    # Get credentials
    credentials = flow.credentials
    
    # Store credentials in session
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    
    # Redirect to calendar selection page
    return redirect(f'/select_calendar?uid={user_id}')

@app.route('/select_calendar')
def select_calendar():
    """Show calendar selection page"""
    # Get user ID from query parameter
    user_id = request.args.get('uid')
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    # Get credentials from session
    credentials_dict = session.get('credentials')
    if not credentials_dict:
        app.logger.error('No credentials found in session for user %s', user_id)
        return jsonify({'error': 'Authentication required'}), 401

    # Validate credentials structure
    required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']
    for field in required_fields:
        if field not in credentials_dict:
            app.logger.error('Missing %s in credentials for user %s', field, user_id)
            return jsonify({'error': 'Invalid credentials format'}), 500

    # Create credentials object with validation
    try:
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        if not credentials.valid:
            app.logger.warning('Credentials expired for user %s, attempting refresh', user_id)
            credentials.refresh(Request())
    except Exception as e:
        app.logger.error('Credential creation failed: %s', str(e))
        return jsonify({'error': 'Invalid authentication credentials'}), 401

    # Build Google Calendar API service
    try:
        # Validate credentials and refresh if needed
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                session['credentials'] = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                session.modified = True
        
        # Build service with validated credentials
        service = build('calendar', 'v3', credentials=credentials)
        
        # Get list of calendars with timeout
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])
        
        if not calendars:
            app.logger.warning(f'No calendars found for user {user_id}')
            return jsonify({'error': 'No calendars found'}), 404
        
        # Prepare calendar data for frontend
        calendar_data = [{
            'id': calendar['id'],
            'summary': calendar['summary']
        } for calendar in calendars]
        
        # Store calendar data in session
        session['calendars'] = calendar_data
        session.modified = True
        
        # Return calendar selection page
        return send_from_directory('.', 'select_calendar.html')
        
    except HttpError as error:
        app.logger.error(f'Google API Error: {error}')
        return jsonify({'error': f'Google API error: {error}'}), 500
    except requests.exceptions.RequestException as e:
        app.logger.error(f'Request timeout: {e}')
        return jsonify({'error': 'Calendar service timeout'}), 504
    except Exception as e:
        app.logger.error(f'Service initialization failed: {str(e)}')
        return jsonify({'error': 'Failed to initialize calendar service', 'details': str(e)}), 500

@app.route('/get_calendars')
def get_calendars():
    """Get list of calendars from session"""
    calendars = session.get('calendars', [])
    return jsonify(calendars)

@app.route('/import_events', methods=['POST'])
def import_events():
    """Import events from selected calendar"""
    # Get request data
    data = request.json
    calendar_id = data.get('calendar_id')
    user_id = data.get('user_id')
    days_back = int(data.get('days_back', 30))  # Default to 30 days
    
    if not calendar_id or not user_id:
        return jsonify({"error": "Calendar ID and User ID are required"}), 400
    
    # Get credentials from session
    credentials_dict = session.get('credentials')
    if not credentials_dict:
        return jsonify({"error": "No credentials found"}), 400
    
    # Validate credentials structure
    required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']
    for field in required_fields:
        if field not in credentials_dict:
            app.logger.error('Missing %s in credentials for user %s', field, user_id)
            return jsonify({'error': 'Invalid credentials format'}), 500

    # Create and validate credentials
    try:
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        if not credentials.valid:
            app.logger.warning('Credentials expired for user %s, attempting refresh', user_id)
            credentials.refresh(Request())
            # Update session with new credentials
            session['credentials'] = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            session.modified = True
    except Exception as e:
        app.logger.error('Credential creation failed: %s', str(e))
        return jsonify({'error': 'Invalid authentication credentials'}), 401

    # Build calendar service
    try:
        service = build('calendar', 'v3', credentials=credentials)
    except Exception as e:
        app.logger.error(f'Service build failed: {str(e)}')
        return jsonify({'error': 'Failed to initialize calendar service', 'details': str(e)}), 500
    
    try:
        # Calculate time range
        now = datetime.datetime.utcnow()
        start_time = (now - datetime.timedelta(days=days_back)).isoformat() + 'Z'  # 'Z' indicates UTC time
        
        # Get events from calendar
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            maxResults=100,  # Adjust as needed
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return jsonify({"message": "No events found"}), 200
        
        # Process events and submit to Omi
        results = []
        for event in events:
            # Extract event details
            event_id = event.get('id')
            summary = event.get('summary', 'Untitled Event')
            description = event.get('description', '')
            location = event.get('location', '')
            
            # Get start and end time
            start = event.get('start', {})
            end = event.get('end', {})
            start_time = start.get('dateTime', start.get('date', ''))
            end_time = end.get('dateTime', end.get('date', ''))
            
            # Format event as fact
            fact_text = f"Calendar Event: {summary}"
            if description:
                fact_text += f". Description: {description}"
            if location:
                fact_text += f". Location: {location}"
            if start_time:
                fact_text += f". Start: {start_time}"
            if end_time:
                fact_text += f". End: {end_time}"
            
            # Submit fact to Omi
            result = submit_fact_to_omi(user_id, fact_text)
            results.append({
                'event_id': event_id,
                'summary': summary,
                'fact_text': fact_text,
                'result': result
            })
        
        return jsonify({
            "message": f"Imported {len(results)} events",
            "results": results
        })
    
    except HttpError as error:
        return jsonify({"error": f"An error occurred: {error}"}), 500

def submit_fact_to_omi(user_id, fact_text):
    """Submit a fact to the Omi API"""
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    }
    
    payload = {
        'user_id': user_id,
        'facts': [fact_text]
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        return {
            'success': True,
            'response': response.json()
        }
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)