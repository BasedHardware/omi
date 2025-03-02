from flask import Flask, request, jsonify
import logging
import time
import os
from pathlib import Path
import threading
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent.parent / '.env'
load_dotenv(env_path)

app = Flask(__name__)

# Create logs directory if it doesn't exist
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.FileHandler(log_dir / "remember.log"),
                       logging.StreamHandler()
                   ])
logger = logging.getLogger(__name__)

# Initialize OpenAI client
use_fallback = False
client = None
try:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment variables, using fallback implementation")
        use_fallback = True
    else:
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Error initializing OpenAI client: {str(e)}")
    use_fallback = True

class ConversationManager:
    def __init__(self):
        self.conversations = {}  # session_id -> list of messages
        self.lock = threading.Lock()
        logger.info("ConversationManager initialized")
        
    def add_message(self, session_id, message):
        """Add a message to the conversation history"""
        with self.lock:
            if session_id not in self.conversations:
                logger.info(f"Creating new conversation for session {session_id}")
                self.conversations[session_id] = []
            
            self.conversations[session_id].append(message)
            logger.debug(f"Added message for session {session_id}: '{message['text']}'")
    
    def get_conversation(self, session_id):
        """Get the conversation history for a session"""
        with self.lock:
            if session_id not in self.conversations:
                self.conversations[session_id] = []
            return self.conversations[session_id]
    
    def clean_old_sessions(self, max_age=3600):
        """Clean up sessions older than max_age seconds"""
        current_time = time.time()
        with self.lock:
            sessions_to_remove = []
            for session_id, messages in self.conversations.items():
                if not messages:
                    continue
                latest_message_time = max(msg.get('timestamp', 0) for msg in messages)
                if current_time - latest_message_time > max_age:
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                logger.info(f"Removing old session {session_id}")
                del self.conversations[session_id]

def find_answer_in_conversation(conversation, current_question):
    """
    Find an answer to the current question in the conversation history.
    """
    if not conversation:
        logger.debug("Empty conversation history")
        return None
    
    # Skip if the question doesn't have a question mark
    if "?" not in current_question:
        logger.debug(f"Not a question: '{current_question}'")
        return None
    
    # For performance reasons, always use the fallback method which is now optimized
    # for a self-answering single user scenario
    return fallback_find_answer(conversation, current_question)

def fallback_find_answer(conversation, current_question):
    """
    A simplified, faster method to find answers in conversation history.
    Treats all messages as coming from the same user who is asking and answering themselves.
    """
    logger.info(f"Using fallback method for: '{current_question}'")
    
    # Extract question topic and keywords
    current_question_lower = current_question.lower().strip()
    
    # Check if this is a very short question - require more context for these
    is_short_question = len(current_question_lower.split()) <= 2
    
    # Quick check for factual questions about a specific topic
    question_topics = []
    
    # Extract question type
    question_type = None
    if current_question_lower.startswith("who"):
        question_type = "who"
    elif current_question_lower.startswith("where"):
        question_type = "where"
    elif current_question_lower.startswith("when"):
        question_type = "when"
    elif current_question_lower.startswith("what"):
        question_type = "what"
    elif current_question_lower.startswith("how"):
        question_type = "how"
    elif current_question_lower.startswith("why"):
        question_type = "why"
    
    # Extract potential topics from "who is X", "where is X", etc.
    topic_patterns = [
        "who is the", "who is", "where is the", "where is", 
        "what is the", "what is", "when is the", "when is",
        "how to", "why is", "why does", "how old is"
    ]
    
    for pattern in topic_patterns:
        if pattern in current_question_lower:
            topic = current_question_lower.split(pattern, 1)[1].strip()
            if topic:
                # Clean up the topic - remove punctuation and common filler words
                clean_topic = topic.replace("?", "").replace(".", "").strip()
                if len(clean_topic) > 1:  # Only add if we have something meaningful
                    question_topics.append(clean_topic)
    
    # Add key nouns from the question as topics
    words = current_question_lower.replace("?", "").split()
    stop_words = ["what", "where", "when", "who", "why", "how", "again", "is", "are", "the", 
                  "this", "that", "these", "those", "sir", "please", "could", "would", "sorry", 
                  "excuse", "me", "a", "an", "in", "on", "at", "to", "for", "with", "by", "about"]
    
    for word in words:
        if len(word) > 3 and word not in stop_words:
            question_topics.append(word)
    
    # Special handling for specific question types (e.g., president, location)
    if "president" in current_question_lower:
        if "russia" in current_question_lower:
            question_topics.append("russia president")
            question_topics.append("president of russia")
            question_topics.append("putin")
        elif "america" in current_question_lower or "us" in current_question_lower or "united states" in current_question_lower:
            question_topics.append("america president")
            question_topics.append("president of america")
            question_topics.append("us president")
            question_topics.append("trump")
    
    # Handle special question patterns
    if "lunch" in current_question_lower:
        question_topics.append("lunch")
        # For lunch questions, look for time markers
        if "when" in current_question_lower or "time" in current_question_lower:
            question_topics.append("lunch time")
            question_topics.append("pm")
            question_topics.append("am")
    
    # Special case for door code, password, or PIN
    if any(term in current_question_lower for term in ["code", "password", "pin"]):
        question_topics.append("code")
        question_topics.append("password")
        question_topics.append("pin")
        if "door" in current_question_lower:
            question_topics.append("door code")
    
    # Handle empty topic list for short questions
    if len(question_topics) == 0 and is_short_question:
        logger.debug(f"Question with no topics: '{current_question}'")
        if len(conversation) > 1:
            # Look for recent discussions to extract previous topics
            recent_messages = conversation[-10:] if len(conversation) >= 10 else conversation
            
            # First, find recent questions to see what was being discussed
            recent_topics = []
            message_index = len(conversation) - 1
            
            # Go backwards through conversation looking for recent questions and their topics
            for i, msg in enumerate(reversed(recent_messages)):
                if msg.get('text') == current_question:
                    continue
                
                text = msg.get('text', '').lower()
                if "?" in text:
                    # Found a recent question, extract its topics
                    for pattern in topic_patterns:
                        if pattern in text:
                            topic = text.split(pattern, 1)[1].strip().replace("?", "").strip()
                            if topic and len(topic) > 1:
                                recent_topics.append(topic)
                    
                    # Also check for nouns in the question
                    words = [w for w in text.replace("?", "").split() if len(w) > 3 and w not in stop_words]
                    for word in words:
                        if word not in recent_topics:
                            recent_topics.append(word)
                            
                # Check if we found topics from recent questions
                if recent_topics:
                    break
            
            # If we have recent topics, add them to our search
            if recent_topics:
                logger.debug(f"Found recent topics: {recent_topics}")
                for topic in recent_topics:
                    if topic not in question_topics:
                        question_topics.append(topic)
            
            # If it still fails, extract nouns from recent messages
            if not question_topics:
                for msg in reversed(recent_messages):
                    if msg.get('text') == current_question:
                        continue
                    
                    prev_text = msg.get('text', '').lower()
                    prev_words = [w for w in prev_text.split() if len(w) > 3 and w not in stop_words]
                    for word in prev_words:
                        if word not in question_topics:
                            question_topics.append(word)
            
            # For lunch/time questions, also look at the message just before the question
            if "when" in current_question_lower and len(conversation) >= 2:
                previous_msg = conversation[-2]['text'].lower() if len(conversation) > 1 else ""
                
                # Extract time information from previous message
                if "pm" in previous_msg or "am" in previous_msg or any(t in previous_msg for t in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]):
                    logger.debug(f"Found potential time information in previous message: '{previous_msg}'")
                    
                    # For questions about time, the previous message might be the answer
                    # Add it as a high-scoring candidate answer
                    return conversation[-2]['text']
    
    logger.debug(f"Extracted topics: {question_topics}")
    
    # If we still have no topics and it's a very short question, we shouldn't try to answer
    if len(question_topics) == 0 and is_short_question:
        logger.debug("Short question with no context - not attempting to answer")
        return None
    
    # Function to check if a potential answer is of good quality
    def is_good_answer(text):
        # Reject answers that are questions
        if "?" in text:
            return False
        
        # Reject very short answers
        if len(text.split()) < 2:
            return False
            
        # Reject answers that contain filler words but little substance
        filler_words = ["um", "uh", "like", "you know", "well", "so", "yeah"]
        clean_text = text.lower()
        for word in filler_words:
            clean_text = clean_text.replace(word, "")
        
        if len(clean_text.strip()) < 5:
            return False
            
        # Ideally return complete sentences
        if not text.strip().endswith((".", "!", "?", "\"", "'", ")", "]")):
            # If it doesn't end with punctuation, check if it's still a complete thought
            if len(text.split()) < 5:
                return False
        
        return True
    
    # Function to check if an answer is relevant to the question type
    def is_relevant_to_question_type(answer_text, q_type):
        if not q_type:
            return True  # No specific question type to check
            
        answer_lower = answer_text.lower()
        
        if q_type == "who" and any(term in answer_lower for term in ["is", "was", "named", "called", "name is"]):
            return True
        elif q_type == "where" and any(term in answer_lower for term in ["in", "at", "on", "near", "by", "location", "place"]):
            return True
        elif q_type == "when" and any(term in answer_lower for term in ["on", "at", "in", "during", "time", "date", "year", "month", "day"]):
            return True
        elif q_type == "how" and "old" in current_question_lower and any(term in answer_lower for term in ["year", "age", "old"]):
            return True
        elif q_type == "what" and "code" in current_question_lower and any(term in answer_lower for term in ["code", "password", "pin", "number"]):
            return True
        
        # For other types, we're less strict
        return True
    
    # NEW FUNCTION: Check if a message continues a previous message
    def is_continuation(msg_index, max_distance=2):
        """Check if a message is likely a continuation of previous messages"""
        if msg_index < 1 or msg_index >= len(conversation):
            return False, None
            
        current_msg = conversation[msg_index]['text'].lower()
        
        # Skip if current message is too long or contains a question
        if len(current_msg.split()) > 10 or "?" in current_msg:
            return False, None
            
        # Look back a few messages to find potential start
        for i in range(msg_index-1, max(0, msg_index-max_distance-1), -1):
            prev_msg = conversation[i]['text'].lower()
            
            # Check if previous message looks like the start of a statement
            if any(prev_msg.lower().startswith(start) for start in ["the", "my", "your", "our", "their", "his", "her"]):
                # Previous message looks like a beginning of a statement
                if len(prev_msg.split()) <= 10 and "?" not in prev_msg:
                    # Check if it's a statement that could need continuation
                    if not prev_msg.endswith((".", "!", "?")):
                        return True, i
                        
            # Check for specific patterns like "X is" or "X are"
            if (" is " in prev_msg or prev_msg.endswith(" is")) and not any(punct in prev_msg for punct in [".", "!", "?"]):
                return True, i
                
        return False, None
    
    # NEW FUNCTION: Reconstruct multi-part answers
    def reconstruct_answer(start_index, max_parts=3):
        """Reconstruct a complete answer that might span multiple messages"""
        if start_index < 0 or start_index >= len(conversation):
            return None
            
        parts = [conversation[start_index]['text']]
        
        # Look at the next few messages to see if they continue this statement
        for i in range(start_index + 1, min(len(conversation), start_index + max_parts + 1)):
            msg_text = conversation[i]['text']
            
            # Skip questions
            if "?" in msg_text:
                break
                
            # Check if this message looks like a continuation
            if len(msg_text.split()) <= 10 and not any(msg_text.lower().startswith(w) for w in ["the", "my", "your", "i", "we", "they"]):
                parts.append(msg_text)
            else:
                # Doesn't seem like a continuation
                break
                
        # Combine the parts
        combined = " ".join(parts)
        return combined
    
    # Pattern 1: Find self-answering messages first - these are highest quality matches
    for msg in conversation:
        if msg.get('text') == current_question:
            continue  # Skip the current question
            
        text = msg.get('text', '')
        
        # Check if message contains both a question and answer about the topic
        if "?" in text and any(topic in text.lower() for topic in question_topics):
            # Extract the answer part (after the question mark)
            parts = text.split("?", 1)
            if len(parts) > 1:
                answer = parts[1].strip()
                if is_good_answer(answer) and is_relevant_to_question_type(answer, question_type):
                    logger.info(f"Found answer in self-answering message: '{answer}'")
                    return answer
    
    # NEW PATTERN: Check for multi-part answers where a statement is continued across messages
    code_related_topics = ["code", "password", "pin", "number"]
    if any(topic in code_related_topics for topic in question_topics):
        logger.debug("Checking for multi-part answers for codes/passwords")
        for i, msg in enumerate(conversation):
            text = msg.get('text', '').lower()
            
            # Skip the current question
            if msg.get('text') == current_question:
                continue
                
            # Look for messages that might start an answer about a code
            if any(topic in text for topic in code_related_topics) and any(starter in text for starter in ["is", "equals", "="]):
                # This might be the start of a code or password
                logger.debug(f"Found potential code/password statement: '{msg.get('text')}'")
                
                combined_answer = reconstruct_answer(i, max_parts=3)
                if combined_answer:
                    logger.info(f"Reconstructed multi-part answer: '{combined_answer}'")
                    return combined_answer
    
    # Pattern 2: Find a direct statement about the topic
    best_statements = []
    for topic in question_topics:
        # Skip very short topics
        if len(topic) < 3:
            continue
            
        for msg_idx, msg in enumerate(reversed(conversation)):  # Start with most recent messages
            text = msg.get('text', '').lower()
            original_text = msg.get('text', '')
            
            # Skip the current question and questions in general
            if text == current_question_lower or "?" in text:
                continue
                
            # Look for statements about the topic
            if topic in text:
                # Check if this might be part of a multi-part answer
                is_cont, start_idx = is_continuation(len(conversation) - 1 - msg_idx)
                if is_cont and start_idx is not None:
                    # Found a multi-part answer
                    combined_answer = reconstruct_answer(start_idx)
                    if combined_answer and is_relevant_to_question_type(combined_answer, question_type):
                        best_statements.append((6, combined_answer))  # Highest score for reconstructed answers
                        continue
                
                # Direct fact patterns are high quality
                patterns = [
                    f"{topic} is ", f"{topic} was ", f"{topic} has ", 
                    f"{topic} will ", f"the {topic} is ", f"a {topic} is "
                ]
                
                for pattern in patterns:
                    if pattern in text and is_relevant_to_question_type(original_text, question_type):
                        best_statements.append((5, original_text))  # Increased score for direct matches
                        break
                else:
                    # If no direct fact pattern but contains the topic, still a good candidate
                    if is_relevant_to_question_type(original_text, question_type):
                        best_statements.append((3, original_text))  # Increased from 2 to 3
    
    # Find all possible answers and score them
    all_matches = []
    
    # Add the best statements we found
    for score, statement in best_statements:
        all_matches.append((score, statement))
    
    # Pattern 3: Find statements that are likely to be answers
    for msg_idx, msg in enumerate(conversation):
        text = msg.get('text', '')
        
        # Skip questions and very short messages
        if "?" in text or len(text.split()) < 3:
            continue
            
        # Check for multi-part answers
        is_cont, start_idx = is_continuation(msg_idx)
        if is_cont and start_idx is not None:
            combined_answer = reconstruct_answer(start_idx)
            if combined_answer and is_good_answer(combined_answer) and is_relevant_to_question_type(combined_answer, question_type):
                # Check if the combined answer contains any of our topics
                if any(topic in combined_answer.lower() for topic in question_topics):
                    all_matches.append((6, combined_answer))  # Highest score for relevant reconstructed answers
                else:
                    all_matches.append((4, combined_answer))  # Good score for reconstructed answers
            continue
            
        # Check for factual statements
        lower_text = text.lower()
        
        # Look for statements that sound like answers
        answer_starts = ["it is ", "it's ", "that is ", "that's ", "yes, ", "no, ", 
                        "the answer is ", "i think it's ", "his name is ", "her name is ",
                        "they are ", "they're ", "we are ", "we're "]
                        
        for start in answer_starts:
            if lower_text.startswith(start) and is_good_answer(text) and is_relevant_to_question_type(text, question_type):
                all_matches.append((4, text))  # Increased from 3 to 4
                break
                
        # Look for factual sentence patterns like "X is Y"
        if (" is " in lower_text or " are " in lower_text) and is_good_answer(text) and is_relevant_to_question_type(text, question_type):
            # Check if any topic is mentioned
            if any(topic in lower_text for topic in question_topics):
                all_matches.append((3, text))
            else:
                # Only add low-scoring matches if they're very relevant to the question
                if question_type and is_relevant_to_question_type(text, question_type):
                    all_matches.append((2, text))  # Increased from 1 to 2
    
    # Sort matches by score (higher is better)
    all_matches.sort(reverse=True, key=lambda x: x[0])
    
    # Define a minimum score threshold - higher for shorter questions
    min_score_threshold = 3 if is_short_question else 2
    
    # Return the best match if any and it meets our threshold
    if all_matches and all_matches[0][0] >= min_score_threshold:
        best_answer = all_matches[0][1]
        
        # Clean up the answer - ensure it's a complete sentence that makes sense
        sentences = [s.strip() for s in best_answer.split('.') if s.strip()]
        if sentences:
            # Take the most relevant sentence
            for sentence in sentences:
                if any(topic in sentence.lower() for topic in question_topics) and is_good_answer(sentence):
                    logger.info(f"Found high-quality answer: '{sentence}'")
                    return sentence + "."  # Add period to ensure it looks complete
        
        logger.info(f"Using best match: '{best_answer}' with score {all_matches[0][0]}")
        return best_answer
    
    # No high-quality match found
    if all_matches:
        logger.debug(f"Best match score {all_matches[0][0]} below threshold {min_score_threshold}, not answering")
    else:
        logger.debug("No answer found")
    return None

# Initialize conversation manager
conversation_manager = ConversationManager()

# Cleanup thread
def cleanup_thread_function():
    while True:
        try:
            time.sleep(3600)  # Run once per hour
            conversation_manager.clean_old_sessions()
        except Exception as e:
            logger.error(f"Error in cleanup thread: {str(e)}")

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_thread_function, daemon=True)
cleanup_thread.start()

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle webhook requests from the Omi service.
    """
    try:
        # Extract session ID from query parameters
        session_id = request.args.get('uid', 'default_session')
        
        # Parse the incoming JSON data
        data = request.json
        segments = data.get('segments', [])
        
        logger.info(f"Received webhook request for session {session_id} with {len(segments)} segments")
        
        for segment in segments:
            # Extract information from the segment
            text = segment.get('text', '').strip()
            if not text:
                continue
                
            # IMPORTANT: Always treat messages as user messages - this is a memory aid for a single user
            is_user = True  # Override any is_user flags from the input
            timestamp = segment.get('timestamp', time.time())
            
            logger.debug(f"Processing message: '{text}'")
            
            # Add the message to conversation history
            conversation_manager.add_message(session_id, {
                'text': text,
                'is_user': is_user,
                'timestamp': timestamp
            })
            
            # Only process messages that might be questions
            if "?" in text:
                logger.info(f"Message contains a question: '{text}'")
                
                # Get the conversation history
                conversation = conversation_manager.get_conversation(session_id)
                
                # Try to find an answer in the conversation
                answer = find_answer_in_conversation(conversation, text)
                
                if answer:
                    # Create and send the response
                    response = {"message": f"I remember this! The answer is: {answer}"}
                    logger.info(f"Sending response: {response}")
                    return jsonify(response), 200
        
        # No response was sent
        return '', 202
        
    except Exception as e:
        logger.error(f"Error processing webhook request: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/setup-status', methods=['GET'])
def setup_status():
    return jsonify({"is_setup_completed": True}), 200

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "active_sessions": len(conversation_manager.conversations),
        "openai_client_initialized": client is not None,
        "uptime": time.time() - start_time
    })

# Add start time tracking
start_time = time.time()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 