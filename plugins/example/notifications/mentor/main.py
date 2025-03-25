from flask import Flask, request, jsonify
import logging
import time
import os
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import threading
from openai import OpenAI
import json
import requests
from dotenv import load_dotenv

# API configuration
APP_ID = "01JFFC690S2B89MJYPPM5TTM1Q"
API_KEY = "sk_dab4c83dd1b3c996482de27cd54f5c84"

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Constants
ANALYSIS_INTERVAL = 5  # seconds between analyses
REMINDER_INTERVAL = 10  # remind user 60 seconds after last notification
REMINDER_CHECK_INTERVAL = 2  # check for reminders every x seconds
REMINDER_MESSAGE = "Hey! How's it going with my previous suggestion? Have you had a chance to try it out?"

# Create logs directory if it doesn't exist
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# Set up logging with more detailed format
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(module)s:%(lineno)d - %(message)s',
                   handlers=[
                       logging.FileHandler(log_dir / "mentor.log"),
                       logging.StreamHandler()
                   ])

logger.info("Starting Mentor Notification Service")

# Initialize OpenAI client (updated initialization)
try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    if not os.getenv('OPENAI_API_KEY'):
        logger.error("OPENAI_API_KEY not found in environment variables")
        raise ValueError("OPENAI_API_KEY environment variable is required")
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize OpenAI client: {str(e)}", exc_info=True)
    raise

class MessageBuffer:
    def __init__(self):
        logger.info("Initializing MessageBuffer")
        self.buffers = {}
        self.lock = threading.Lock()
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
        self.silence_threshold = 120  # 2 minutes silence threshold
        self.min_words_after_silence = 5  # minimum words needed after silence
        self.last_notification_times = defaultdict(dict)  # Track last notification time per message per session
        self.last_reminder_times = defaultdict(dict)  # Track last reminder time per message per session
        logger.debug(f"MessageBuffer initialized with cleanup_interval={self.cleanup_interval}, silence_threshold={self.silence_threshold}")


    def get_buffer(self, session_id):
        logger.debug(f"Getting buffer for session_id: {session_id}")
        current_time = time.time()
        
        # Cleanup old sessions periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            logger.info("Triggering cleanup of old sessions")
            self.cleanup_old_sessions()
        
        with self.lock:
            if session_id not in self.buffers:
                logger.info(f"Creating new buffer for session_id: {session_id}")
                self.buffers[session_id] = {
                    'messages': [],
                    'last_analysis_time': time.time(),
                    'last_activity': current_time,
                    'words_after_silence': 0,
                    'silence_detected': False
                }
            else:
                # Check for silence period
                time_since_activity = current_time - self.buffers[session_id]['last_activity']
                if time_since_activity > self.silence_threshold:
                    logger.info(f"Silence period detected for session {session_id}. Time since activity: {time_since_activity:.2f}s")
                    self.buffers[session_id]['silence_detected'] = True
                    self.buffers[session_id]['words_after_silence'] = 0
                    self.buffers[session_id]['messages'] = []  # Clear old messages after silence
                
                self.buffers[session_id]['last_activity'] = current_time
                
        return self.buffers[session_id]

    def cleanup_old_sessions(self):
        logger.info("Starting cleanup of old sessions")
        current_time = time.time()
        with self.lock:
            initial_count = len(self.buffers)
            expired_sessions = [
                session_id for session_id, data in self.buffers.items()
                if current_time - data['last_activity'] > 3600  # Remove sessions older than 1 hour
            ]
            for session_id in expired_sessions:
                logger.info(f"Removing expired session: {session_id}")
                del self.buffers[session_id]
                if session_id in self.last_notification_times:
                    del self.last_notification_times[session_id]
                if session_id in self.last_reminder_times:
                    del self.last_reminder_times[session_id]
            self.last_cleanup = current_time
            logger.info(f"Cleanup complete. Removed {len(expired_sessions)} sessions. Active sessions: {len(self.buffers)}")

    def set_last_notification_time(self, session_id, message_id):
        with self.lock:
            self.last_notification_times[session_id][message_id] = time.time()
            
    def get_sessions_needing_reminder(self):
        current_time = time.time()
        messages_to_remind = []
        with self.lock:
            #logger.info(f"Checking reminders. Active notification sessions: {list(self.last_notification_times.keys())}")
            sessions_to_remove = []
            messages_to_remove = []
            
            for session_id, message_dict in self.last_notification_times.items():
                for message_id, last_time in message_dict.items():
                    last_reminder = self.last_reminder_times.get(session_id, {}).get(message_id, 0)
                    time_since_notification = current_time - last_time
                    time_since_reminder = current_time - last_reminder
                    
                    logger.info(f"Session {session_id}, Message {message_id}:")
                    logger.info(f"  - Time since last notification: {time_since_notification:.1f}s (threshold: {REMINDER_INTERVAL}s)")
                    logger.info(f"  - Time since last reminder: {time_since_reminder:.1f}s (threshold: {REMINDER_INTERVAL}s)")
                    
                    if time_since_notification >= REMINDER_INTERVAL and last_reminder == 0:  # Only if no reminder sent yet
                        logger.info(f"  -> Adding message {message_id} from session {session_id} to reminder list")
                        messages_to_remind.append((session_id, message_id))
                        self.last_reminder_times[session_id][message_id] = current_time
                        if session_id not in sessions_to_remove:
                            sessions_to_remove.append(session_id)
                        messages_to_remove.append((session_id, message_id))
                    else:
                        logger.info("  -> Not yet time for reminder or reminder already sent")
            
            # Remove messages that have been reminded
            for session_id, message_id in messages_to_remove:
                logger.info(f"Removing message {message_id} from notification tracking after scheduling reminder")
                if message_id in self.last_notification_times[session_id]:
                    del self.last_notification_times[session_id][message_id]
                # Clean up empty session entries
                if not self.last_notification_times[session_id]:
                    del self.last_notification_times[session_id]
                
            #logger.info(f"Final messages to remind: {messages_to_remind}")
        return messages_to_remind

def send_reminder_notification(session_id, message_id):
    """Send a reminder notification to the main app"""
    logger.info(f"Attempting to send reminder for session {session_id}, message {message_id}")
    
    api_base_url = os.getenv('API_BASE_URL')  # Get API key from environment variable
    
    if not api_base_url:
        logger.error("API_BASE_URL environment variable not set")
        return

    notification_url = f"{api_base_url.rstrip('/')}/v2/integrations/{APP_ID}/notification"
    
    try:
        # Use Bearer token authentication
        headers = {
            'Authorization': f'Bearer {API_KEY}'
        }
        
        params = {
            "uid": session_id,
            "message": REMINDER_MESSAGE
        }
        
        logger.info(f"Sending reminder notification to {notification_url} for session {session_id}, message {message_id} with aid {APP_ID}")
        response = requests.post(notification_url, headers=headers, params=params)
        if response.status_code == 200:
            logger.info(f"Successfully sent reminder notification for session {session_id}, message {message_id}")
        else:
            logger.error(f"Failed to send reminder notification. Status code: {response.status_code}, Response: {response.text}")
            
    except Exception as e:
        logger.error(f"Error sending reminder notification: {str(e)}", exc_info=True)

def reminder_check_loop():
    """Background task to check and send reminders"""
    while True:
        try:
            #logger.info("Checking for messages needing reminders...")
            messages = message_buffer.get_sessions_needing_reminder()
            if messages:
                logger.info(f"Found {len(messages)} messages needing reminders: {messages}")
                for session_id, message_id in messages:
                    send_reminder_notification(session_id, message_id)
            #else:
                #logger.debug("No messages need reminders at this time")
        except Exception as e:
            logger.error(f"Error in reminder check loop: {str(e)}", exc_info=True)
        
        #logger.debug(f"Sleeping for {REMINDER_CHECK_INTERVAL} seconds before next reminder check")
        time.sleep(REMINDER_CHECK_INTERVAL)

# Initialize message buffer first
message_buffer = MessageBuffer()
logger.info(f"Analysis interval set to {ANALYSIS_INTERVAL} seconds")

# Start the reminder check loop in a background thread AFTER message_buffer is initialized
reminder_thread = threading.Thread(target=reminder_check_loop, daemon=True)
reminder_thread.start()

def extract_topics(discussion_text: str) -> list:
    """Extract topics from the discussion using OpenAI"""
    logger.info("Starting topic extraction")
    logger.debug(f"Discussion text length: {len(discussion_text)} characters")
    
    try:
        logger.debug("Sending request to OpenAI API")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a topic extraction specialist. Extract all relevant topics from the conversation. Return ONLY a JSON array of topic strings, nothing else. Example format: [\"topic1\", \"topic2\"]"},
                {"role": "user", "content": f"Extract all topics from this conversation:\n{discussion_text}"}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        # Parse the response text as JSON
        response_text = response.choices[0].message.content.strip()
        topics = json.loads(response_text)
        logger.info(f"Successfully extracted {len(topics)} topics: {topics}")
        return topics
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {str(e)}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Error extracting topics: {str(e)}", exc_info=True)
        return []

def create_notification_prompt(messages: list) -> dict:
    """Create notification with prompt template"""
    logger.info(f"Creating notification prompt for {len(messages)} messages")
    
    # Format the discussion with speaker labels
    formatted_discussion = []
    for msg in messages:
        speaker = "{{{{user_name}}}}" if msg.get('is_user') else "other"
        formatted_discussion.append(f"{msg['text']} ({speaker})")
    
    discussion_text = "\n".join(formatted_discussion)
    logger.debug(f"Formatted discussion length: {len(discussion_text)} characters")
    
    # Extract topics from the discussion
    topics = extract_topics(discussion_text)
    
    system_prompt = """You are {{{{user_name}}}}'s personal AI mentor. Your FIRST task is to determine if this conversation warrants interruption. 

STEP 1 - Evaluate SILENTLY if ALL these conditions are met:
1. {{{{user_name}}}} is participating in the conversation (messages marked with '({{{{user_name}}}})' must be present)
2. {{{{user_name}}}} has expressed a specific problem, challenge, goal, or question
3. You have a STRONG, CLEAR opinion that would significantly impact {{{{user_name}}}}'s situation
4. The insight is time-sensitive and worth interrupting for

If ANY condition is not met, respond with an empty string and nothing else.

STEP 2 - Only if ALL conditions are met, provide feedback following these guidelines:
- Speak DIRECTLY to {{{{user_name}}}} - no analysis or third-person commentary
- Take a clear stance - no "however" or "on the other hand"
- Keep it under 300 chars
- Use simple, everyday words like you're talking to a friend
- Reference specific details from what {{{{user_name}}}} said
- Be bold and direct - {{{{user_name}}}} needs clarity, not options
- End with a specific question about implementing your advice

What we know about {{{{user_name}}}}: {{{{user_facts}}}}

Current discussion:
{text}

Previous discussions and context: {{{{user_context}}}}

Remember: First evaluate silently, then either respond with empty string OR give direct, opinionated advice.""".format(text=discussion_text)

    notification = {
        "notification": {
            "prompt": system_prompt,
            "params": ["user_name", "user_facts", "user_context"],
            "context": {
                "filters": {
                    "people": [],
                    "entities": [],
                    "topics": topics
                }
            }
        }
    }
    logger.info("Created notification prompt template")
    return notification

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info("Received webhook POST request")
    if request.method == 'POST':
        try:
            data = request.json
            session_id = data.get('session_id')
            segments = data.get('segments', [])
            message_id = data.get('message_id')  # Get message ID from request
            
            # Generate message_id if not provided
            if not message_id:
                message_id = f"{session_id}_{int(time.time())}"
                logger.info(f"Generated message_id: {message_id}")
            
            logger.info(f"Processing webhook for session_id: {session_id}, message_id: {message_id}, segments count: {len(segments)}, aid: {APP_ID}")
            
            if not session_id:
                logger.error("No session_id provided in request")
                return jsonify({"message": "No session_id provided"}), 400

            current_time = time.time()
            buffer_data = message_buffer.get_buffer(session_id)

            # Process new messages
            logger.info(f"Processing {len(segments)} segments for session {session_id}")
            for segment in segments:
                if not segment.get('text'):
                    logger.debug("Skipping empty segment")
                    continue

                text = segment['text'].strip()
                if text:
                    timestamp = segment.get('start', 0) or current_time
                    is_user = segment.get('is_user', False)
                    logger.info(f"Processing segment - is_user: {is_user}, timestamp: {timestamp}, text: {text[:50]}...")

                    # Count words after silence
                    if buffer_data['silence_detected']:
                        words_in_segment = len(text.split())
                        buffer_data['words_after_silence'] += words_in_segment
                        logger.info(f"Words after silence: {buffer_data['words_after_silence']}/{message_buffer.min_words_after_silence} needed")
                        
                        # If we have enough words, start fresh conversation
                        if buffer_data['words_after_silence'] >= message_buffer.min_words_after_silence:
                            logger.info(f"Silence period ended for session {session_id}, starting fresh conversation")
                            buffer_data['silence_detected'] = False
                            buffer_data['last_analysis_time'] = current_time  # Reset analysis timer

                    can_append = (
                        buffer_data['messages'] and 
                        abs(buffer_data['messages'][-1]['timestamp'] - timestamp) < 2.0 and
                        buffer_data['messages'][-1].get('is_user') == is_user
                    )

                    if can_append:
                        logger.info(f"Appending to existing message. Current length: {len(buffer_data['messages'][-1]['text'])}")
                        buffer_data['messages'][-1]['text'] += ' ' + text
                    else:
                        logger.info(f"Creating new message. Buffer now has {len(buffer_data['messages']) + 1} messages")
                        buffer_data['messages'].append({
                            'text': text,
                            'timestamp': timestamp,
                            'is_user': is_user
                        })

            # Check if it's time to analyze
            time_since_last_analysis = current_time - buffer_data['last_analysis_time']
            logger.info(f"Time since last analysis: {time_since_last_analysis:.2f}s (threshold: {ANALYSIS_INTERVAL}s)")
            logger.info(f"Current message count: {len(buffer_data['messages'])}")
            logger.info(f"Silence detected: {buffer_data['silence_detected']}")

            if ((time_since_last_analysis >= ANALYSIS_INTERVAL or buffer_data['last_analysis_time'] == 0) and
                buffer_data['messages'] and 
                not buffer_data['silence_detected'] and
                message_id):  # Only proceed if we have a message_id
                
                logger.info("Starting analysis of messages")
                # Sort messages by timestamp
                sorted_messages = sorted(buffer_data['messages'], key=lambda x: x['timestamp'])
                
                # Create notification with formatted discussion
                notification = create_notification_prompt(sorted_messages)
                
                buffer_data['last_analysis_time'] = current_time
                buffer_data['messages'] = []  # Clear buffer after analysis

                # Track notification time for reminders with message_id
                message_buffer.set_last_notification_time(session_id, message_id)

                logger.info(f"Sending notification with prompt template for session {session_id}, message {message_id}")
                return jsonify(notification), 200

            logger.debug("No analysis needed at this time")
            return jsonify({}), 202
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

@app.route('/webhook/setup-status', methods=['GET'])
def setup_status():
    logger.debug("Received setup-status GET request")
    return jsonify({"is_setup_completed": True}), 200

@app.route('/status', methods=['GET'])
def status():
    logger.debug("Received status GET request")
    active_sessions = len(message_buffer.buffers)
    uptime = time.time() - start_time
    logger.info(f"Status check - Active sessions: {active_sessions}, Uptime: {uptime:.2f}s")
    return jsonify({
        "active_sessions": active_sessions,
        "uptime": uptime
    })

# Add start time tracking
start_time = time.time()
logger.info(f"Application initialized. Start time: {datetime.fromtimestamp(start_time)}")

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=5010, debug=True)
