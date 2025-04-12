from flask import Flask, request, jsonify, send_from_directory, redirect, session, url_for
import requests
import json
import os
import datetime
from dotenv import load_dotenv
from composio_google import ComposioToolset
from composio import App, Composio
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
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

# Composio configuration
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_APP_ID = os.getenv("COMPOSIO_APP_ID")

# Google OAuth configuration
CLIENT_ID = os.getenv('GOOGLE_CALENDAR_CLIENT_ID')
CLIENT_SECRET = os.getenv('GOOGLE_CALENDAR_CLIENT_SECRET')

# OAuth endpoints configuration
REDIRECT_URI = 'http://localhost:5001/callback'
AUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
# Include both read and write scopes to prevent scope change warnings
SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/calendar.readonly']

# Initialize Composio client with error handling
try:
    # Initialize Composio integration with environment variables
    # Initialize integration with environment checks
    integration_id = os.getenv("COMPOSIO_INTEGRATION_ID")
    if not integration_id:
        raise ValueError("COMPOSIO_INTEGRATION_ID environment variable must be set in .env file")

    composio_client = Composio(
        api_key=COMPOSIO_API_KEY
    )

    # Initialize Composio toolset for Google integration
    composio_google = ComposioToolset(
        api_key=COMPOSIO_API_KEY
    )
    # Test API connection
    try:
        # Check if the API key is valid by making a simple request
        integration_info = composio_client.integrations.get(integration_id)
        print(f"Successfully connected to Composio. Integration: {integration_info.name}")
    except Exception as e:
        print(f"Warning: Could not connect to Composio: {str(e)}")



except Exception as e:
    raise RuntimeError(f"Failed to initialize Composio client: {str(e)}")

@app.route('/get_connections')
def get_connections():
    """Get connected accounts from Composio"""
    try:
        from .google_calendar_integration import GoogleCalendarIntegration

        toolset = GoogleCalendarIntegration()
        if not toolset.integration:
            raise RuntimeError("Failed to initialize Google Calendar integration")
        # Generate entity_id from user context
        if 'user_id' not in session:
            raise RuntimeError("User not authenticated")
        user_context = {'user_id': session['user_id']}
        connection_request = toolset.initiate_connection(user_context)
        connections = toolset.get_connected_accounts()
        return jsonify({"connections": connections})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    """Serve the main HTML page"""
    # Check if uid is provided
    user_id = request.args.get('uid')
    if not user_id:
        return redirect('/?uid=test_user_123')
    
    # Validate OAuth credentials
    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({
            "error": "OAuth configuration incomplete",
            "message": "Please set Google Calendar credentials in .env"
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
    if not CLIENT_ID or not CLIENT_SECRET:
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
    
    # Create OAuth flow instance using Google's OAuth library directly
    from google_auth_oauthlib.flow import Flow
    
    # Create a flow instance with client config
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
    try:
        flow.fetch_token(authorization_response=request.url)
        
        # Get credentials
        credentials = flow.credentials
        
        # Log scope changes for debugging
        if set(credentials.scopes) != set(SCOPES):
            app.logger.info(f"Scope changed from {SCOPES} to {credentials.scopes}")
        
        # Store credentials in session
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
    except Exception as e:
        # Handle OAuth errors
        app.logger.error(f"OAuth error: {str(e)}")
        session.clear()
        return jsonify({"error": "Authentication failed", "details": str(e)}), 400
    
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
        
        # Build service with validated credentials using Google API client library
        calendar_service = build('calendar', 'v3', credentials=credentials)
        
        # Get list of calendars with timeout
        calendar_list = calendar_service.calendarList().list().execute()
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

@app.route('/check_auth')
def check_auth():
    """Check if user is authenticated with Google Calendar"""
    # Get credentials from session
    credentials_dict = session.get('credentials')
    
    # If no credentials found, user is not authenticated
    if not credentials_dict:
        return jsonify({"authenticated": False}), 200
    
    # Validate credentials structure
    required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']
    for field in required_fields:
        if field not in credentials_dict:
            return jsonify({"authenticated": False}), 200
    
    # Create credentials object and check validity
    try:
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # Try to refresh token if expired
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                # Update session with refreshed credentials
                session['credentials'] = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                session.modified = True
        
        # If we got here without errors, authentication is valid
        return jsonify({"authenticated": True}), 200
    except Exception as e:
        app.logger.error(f'Authentication check failed: {str(e)}')
        return jsonify({"authenticated": False}), 200

@app.route('/get_calendars')
def get_calendars():
    """Get list of calendars from session"""
    calendars = session.get('calendars', [])
    return jsonify(calendars)

@app.route('/import_events', methods=['POST'])
def import_events():
    """Import events from selected calendar (one-time import)"""
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
        calendar_service = build('calendar', 'v3', credentials=credentials)
    except Exception as e:
        app.logger.error(f'Service build failed: {str(e)}')
        return jsonify({'error': 'Failed to initialize calendar service', 'details': str(e)}), 500
    
    try:
        # Calculate time range
        now = datetime.datetime.utcnow()
        start_time = (now - datetime.timedelta(days=days_back)).isoformat() + 'Z'  # 'Z' indicates UTC time
        
        # Get events from calendar
        events_result = calendar_service.events().list(
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

# Replace manual import route with real-time sync
@app.route('/sync_calendar', methods=['POST'])
def sync_calendar():
    """Set up continuous synchronization using Composio"""
    data = request.json
    calendar_id = data.get('calendar_id')
    user_id = data.get('user_id')
    
    if not calendar_id or not user_id:
        return jsonify({"error": "Calendar ID and User ID are required"}), 400
    
    try:
        # Initialize the Google Calendar integration with Composio
        from google_calendar_integration import GoogleCalendarIntegration
        
        # Create integration instance
        integration = GoogleCalendarIntegration()
        
        # Get credentials from session
        credentials_dict = session.get('credentials')
        if not credentials_dict:
            return jsonify({"error": "No credentials found"}), 400
        
        # Create user context
        user_context = {'user_id': user_id}
        
        # Get or create connection
        try:
            # Check if user already has a connection
            connections = integration.get_connected_accounts()
            user_connection = next((conn for conn in connections 
                                if conn.get('entity_id') == f"user_{user_id}"), None)
            
            if not user_connection:
                # Initiate new connection
                connection_request = integration.initiate_connection(user_context)
                
                # Store connection details in session
                # The connection_request is now a dictionary with the necessary attributes
                session['composio_connection'] = {
                    'id': connection_request['id'],
                    'entity_id': connection_request['entity_id'],
                    'calendar_id': calendar_id
                }
                session.modified = True
                
                # Set up webhook for real-time updates
                # This will use Composio's webhook system instead of direct Google Calendar webhooks
                integration.setup_webhook(
                    entity_id=f"user_{user_id}",
                    callback_url=f"{request.host_url.rstrip('/')}/composio_webhook"
                )
                
                return jsonify({
                    "status": "sync_setup",
                    "message": "Calendar synchronization has been set up successfully"
                })
            else:
                # User already has a connection, update it
                session['composio_connection'] = {
                    'id': user_connection.get('id'),
                    'entity_id': user_connection.get('entity_id'),
                    'calendar_id': calendar_id
                }
                session.modified = True
                
                return jsonify({
                    "status": "sync_active",
                    "message": "Calendar synchronization is already active"
                })
                
        except Exception as e:
            app.logger.error(f"Composio connection error: {str(e)}")
            return jsonify({"error": f"Failed to set up synchronization: {str(e)}"}), 500
            
    except Exception as e:
        app.logger.error(f"Sync setup error: {str(e)}")
        return jsonify({"error": f"Failed to set up synchronization: {str(e)}"}), 500

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Legacy webhook handler for direct Google Calendar webhooks"""
    # Verify the webhook signature if needed
    # For Google Calendar webhooks, you typically verify using the headers
    channel_id = request.headers.get('X-Goog-Channel-ID')
    resource_id = request.headers.get('X-Goog-Resource-ID')
    
    if not channel_id or not resource_id:
        return jsonify({"error": "Invalid webhook request"}), 400
    
    # Process the event
    event = request.json
    
    # You would need to implement this function to handle the event
    # handle_event_change(event)
    
    return jsonify({"status": "processed"})

@app.route('/composio_webhook', methods=['POST'])
def composio_webhook_handler():
    """Handle webhooks from Composio for real-time calendar event updates"""
    # Verify the webhook signature if provided by Composio
    signature = request.headers.get('X-Composio-Signature')
    
    # Get the webhook payload
    try:
        webhook_data = request.json
        
        # Extract event data
        event_type = webhook_data.get('event_type')
        entity_id = webhook_data.get('entity_id')
        event_data = webhook_data.get('data', {})
        
        # Extract user_id from entity_id (format: "user_{user_id}")
        if entity_id and entity_id.startswith('user_'):
            user_id = entity_id[5:]  # Remove 'user_' prefix
        else:
            app.logger.error(f"Invalid entity_id format: {entity_id}")
            return jsonify({"error": "Invalid entity_id format"}), 400
        
        # Process different event types
        if event_type == 'calendar.event.created' or event_type == 'calendar.event.updated':
            # Extract event details
            calendar_event = event_data.get('event', {})
            summary = calendar_event.get('summary', 'Untitled Event')
            description = calendar_event.get('description', '')
            location = calendar_event.get('location', '')
            start_time = calendar_event.get('start', {}).get('dateTime', calendar_event.get('start', {}).get('date', ''))
            end_time = calendar_event.get('end', {}).get('dateTime', calendar_event.get('end', {}).get('date', ''))
            
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
            app.logger.info(f"Processed {event_type} for user {user_id}: {summary}")
            
        elif event_type == 'calendar.event.deleted':
            # For deleted events, we could potentially add a fact about the deletion
            # or remove the corresponding fact if we had a way to track which facts correspond to which events
            calendar_event = event_data.get('event', {})
            summary = calendar_event.get('summary', 'Untitled Event')
            app.logger.info(f"Event deleted for user {user_id}: {summary}")
            
        return jsonify({"status": "processed"})
        
    except Exception as e:
        app.logger.error(f"Error processing Composio webhook: {str(e)}")
        return jsonify({"error": f"Webhook processing error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)