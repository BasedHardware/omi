from flask import Flask, request, jsonify
import logging
import time
import os
from collections import defaultdict
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from pathlib import Path

# Instead, set the API key directly
api_key = "your_openaikey_here"

print(f"API key loaded (last 4 chars): ...{api_key[-4:]}")

client = OpenAI(api_key=api_key)

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store for aggregating messages
message_buffer = defaultdict(list)
last_print_time = defaultdict(float)
AGGREGATION_INTERVAL = 30  # seconds

# Add at the top with other global variables
notification_cooldowns = defaultdict(float)
NOTIFICATION_COOLDOWN = 300  # 5 minutes cooldown between notifications for each session

# Add these near the top of the file, after the imports
if os.getenv('HTTPS_PROXY'):
    os.environ['OPENAI_PROXY'] = os.getenv('HTTPS_PROXY')

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def analyze_drinking_intent(text):
    """Analyze text for drinking intent using OpenAI"""
    try:
        # Add debug logging
        logger.info("Attempting to connect to OpenAI API...")
        if not api_key:
            raise ValueError("OpenAI API key is not set")
        
        # Only log the last 4 characters of the API key for security
        key_preview = f"...{api_key[-4:]}" if api_key else "None"
        logger.info(f"API key check (last 4 chars): {key_preview}")
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an AI that analyzes conversations to detect if someone is planning to drink alcohol. Respond with 'YES' if you detect intent to drink alcohol, and 'NO' if you don't."},
                {"role": "user", "content": f"Analyze this conversation for intent to drink alcohol: {text}"}
            ],
            temperature=0.7,
            max_tokens=50,
            timeout=30  # Add timeout parameter
        )
        
        answer = response.choices[0].message.content.strip().upper()
        logger.info(f"Successfully received response from OpenAI: {answer}")
        return answer == "YES"
    except Exception as e:
        logger.error(f"Error analyzing drinking intent: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        # Print full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False

def print_aggregated_messages(session_id):
    """Print aggregated messages for logging purposes only"""
    if not message_buffer[session_id]:
        return
    
    # Sort messages by start time
    sorted_messages = sorted(message_buffer[session_id], key=lambda x: x['start'])
    
    # Combine all text
    combined_text = ' '.join(msg['text'] for msg in sorted_messages if msg['text'])
    time_range = f"{sorted_messages[0]['start']:.2f}s - {sorted_messages[-1]['end']:.2f}s"
    
    # Just log the transcript without analyzing
    logger.info(f"\n=== Transcript chunk ({time_range}) ===\n{combined_text}\n")
    
    # Clear buffer after processing
    message_buffer[session_id].clear()

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        # Log incoming request
        logger.info("Received webhook POST request")
        data = request.json
        logger.info(f"Received data: {data}")
        
        # Extract session ID and segments
        session_id = data.get('session_id')
        if not session_id:
            logger.error("No session_id provided in request")
            return jsonify({"status": "error", "message": "No session_id provided"}), 400
            
        segments = data.get('segments', [])
        logger.info(f"Processing session_id: {session_id}, number of segments: {len(segments)}")
        
        current_time = time.time()
        
        # Check notification cooldown for this session
        time_since_last_notification = current_time - notification_cooldowns[session_id]
        if time_since_last_notification < NOTIFICATION_COOLDOWN:
            logger.info(f"Notification cooldown active for session {session_id}. {NOTIFICATION_COOLDOWN - time_since_last_notification:.0f}s remaining")
            return jsonify({"status": "success"}), 200
        
        for segment in segments:
            if segment['text']:  # Only store non-empty segments
                message_buffer[session_id].append({
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'],
                    'speaker': segment['speaker']
                })
                logger.info(f"Added segment text for session {session_id}: {segment['text']}")
        
        # Check if it's time to process messages
        time_since_last = current_time - last_print_time[session_id]
        logger.info(f"Time since last process: {time_since_last}s (threshold: {AGGREGATION_INTERVAL}s)")
        
        if time_since_last >= AGGREGATION_INTERVAL and message_buffer[session_id]:
            logger.info(f"Processing aggregated messages for session {session_id}...")
            sorted_messages = sorted(message_buffer[session_id], key=lambda x: x['start'])
            combined_text = ' '.join(msg['text'] for msg in sorted_messages if msg['text'])
            logger.info(f"Analyzing combined text for session {session_id}: {combined_text}")
            
            # Clear the buffer immediately after combining text
            message_buffer[session_id].clear()
            last_print_time[session_id] = current_time
            
            if analyze_drinking_intent(combined_text):
                logger.warning(f"🚨 Drinking intent detected for session {session_id}!")
                # Update notification cooldown for this session
                notification_cooldowns[session_id] = current_time
                return jsonify({
                    "message": "Hey, you shouldn't drink alcohol!"
                }), 200
        
        # Return empty response when no drinking intent detected
        return jsonify({"status": "success"}), 200

@app.route('/webhook/setup-status', methods=['GET'])
def setup_status():
    try:
        # Always return true for setup status
        return jsonify({
            "is_setup_completed": True
        }), 200
    except Exception as e:
        logger.error(f"Error checking setup status: {str(e)}")
        return jsonify({
            "is_setup_completed": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
