from flask import Flask, request, jsonify
import logging
import time
import os
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import threading

app = Flask(__name__)

# Create logs directory if it doesn't exist
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.FileHandler(log_dir / "mentor.log"),
                       logging.StreamHandler()
                   ])
logger = logging.getLogger(__name__)

class MessageBuffer:
    def __init__(self):
        self.buffers = {}
        self.lock = threading.Lock()
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
        self.silence_threshold = 120  # 2 minutes silence threshold
        self.min_words_after_silence = 5  # minimum words needed after silence

    def get_buffer(self, session_id):
        current_time = time.time()
        
        # Cleanup old sessions periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup_old_sessions()
        
        with self.lock:
            if session_id not in self.buffers:
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
                    self.buffers[session_id]['silence_detected'] = True
                    self.buffers[session_id]['words_after_silence'] = 0
                    self.buffers[session_id]['messages'] = []  # Clear old messages after silence
                
                self.buffers[session_id]['last_activity'] = current_time
                
        return self.buffers[session_id]

    def cleanup_old_sessions(self):
        current_time = time.time()
        with self.lock:
            expired_sessions = [
                session_id for session_id, data in self.buffers.items()
                if current_time - data['last_activity'] > 3600  # Remove sessions older than 1 hour
            ]
            for session_id in expired_sessions:
                del self.buffers[session_id]
            self.last_cleanup = current_time

# Initialize message buffer
message_buffer = MessageBuffer()

ANALYSIS_INTERVAL = 120  # 30 seconds between analyses

def create_notification_prompt(messages: list) -> dict:
    """Create notification with prompt template"""
    
    # Format the discussion with speaker labels
    formatted_discussion = []
    for msg in messages:
        speaker = "{{{{user_name}}}}" if msg.get('is_user') else "other"
        formatted_discussion.append(f"{msg['text']} ({speaker})")
    
    discussion_text = "\n".join(formatted_discussion)
    
    system_prompt = """You are {{{{user_name}}}}'s personal AI mentor. Your FIRST task is to determine if this conversation warrants interruption. 

STEP 1 - Evaluate SILENTLY if ALL these conditions are met:
1. {{{{user_name}}}} is participating in the conversation (not just listening)
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

Remember: First evaluate silently, then either respond with empty string OR give direct, opinionated advice.""".format(text=discussion_text)

    return {
        "notification": {
            "prompt": system_prompt,
            "params": ["user_name", "user_facts"]
        }
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        data = request.json
        session_id = data.get('session_id')
        segments = data.get('segments', [])
        
        if not session_id:
            logger.error("No session_id provided in request")
            return jsonify({"message": "No session_id provided"}), 400

        current_time = time.time()
        buffer_data = message_buffer.get_buffer(session_id)

        # Process new messages
        for segment in segments:
            if not segment.get('text'):
                continue

            text = segment['text'].strip()
            if text:
                timestamp = segment.get('start', 0) or current_time
                is_user = segment.get('is_user', False)

                # Count words after silence
                if buffer_data['silence_detected']:
                    words_in_segment = len(text.split())
                    buffer_data['words_after_silence'] += words_in_segment
                    
                    # If we have enough words, start fresh conversation
                    if buffer_data['words_after_silence'] >= message_buffer.min_words_after_silence:
                        buffer_data['silence_detected'] = False
                        buffer_data['last_analysis_time'] = current_time  # Reset analysis timer
                        logger.info(f"Silence period ended for session {session_id}, starting fresh conversation")

                can_append = (
                    buffer_data['messages'] and 
                    abs(buffer_data['messages'][-1]['timestamp'] - timestamp) < 2.0 and
                    buffer_data['messages'][-1].get('is_user') == is_user
                )

                if can_append:
                    buffer_data['messages'][-1]['text'] += ' ' + text
                else:
                    buffer_data['messages'].append({
                        'text': text,
                        'timestamp': timestamp,
                        'is_user': is_user
                    })

        # Check if it's time to analyze
        time_since_last_analysis = current_time - buffer_data['last_analysis_time']

        if (time_since_last_analysis >= ANALYSIS_INTERVAL and 
            buffer_data['messages'] and 
            not buffer_data['silence_detected']):  # Only analyze if not in silence period
            
            # Sort messages by timestamp
            sorted_messages = sorted(buffer_data['messages'], key=lambda x: x['timestamp'])
            
            # Create notification with formatted discussion
            notification = create_notification_prompt(sorted_messages)
            
            buffer_data['last_analysis_time'] = current_time
            buffer_data['messages'] = []  # Clear buffer after analysis

            logger.info(f"Sending notification with prompt template for session {session_id}")
            logger.info(notification)
            
            return jsonify(notification), 200

        return jsonify({}), 202

@app.route('/webhook/setup-status', methods=['GET'])
def setup_status():
    return jsonify({"is_setup_completed": True}), 200

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "active_sessions": len(message_buffer.buffers),
        "uptime": time.time() - start_time
    })

# Add start time tracking
start_time = time.time()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
