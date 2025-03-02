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
try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    if not os.getenv('OPENAI_API_KEY'):
        logger.warning("OPENAI_API_KEY not found in environment variables, using fallback implementation")
        use_fallback = True
except Exception as e:
    logger.warning(f"Error initializing OpenAI client: {str(e)}, using fallback implementation")
    use_fallback = True

class ConversationHistory:
    def __init__(self):
        self.histories = {}  # session_id -> list of messages
        self.lock = threading.Lock()
        self.example_qa_pairs = [
            {"question": "What is the cat's name?", "answer": "Tom"},
            {"question": "Where is the book?", "answer": "The book is on the table."},
            {"question": "Who is the president?", "answer": "Joe Biden"},
            {"question": "What time is it?", "answer": "It's 3:30 PM."},
            {"question": "What is the table made of?", "answer": "The table is made of wood."},
            {"question": "Where is the box?", "answer": "The box is on the ground."}
        ]
        logger.info(f"Initialized ConversationHistory with {len(self.example_qa_pairs)} example QA pairs")
        
    def add_message(self, session_id, message):
        """Add a message to the conversation history"""
        with self.lock:
            if session_id not in self.histories:
                logger.info(f"Creating new conversation history for session {session_id}")
                self.histories[session_id] = []
            
            self.histories[session_id].append(message)
            logger.debug(f"Added message to history for session {session_id}: '{message['text']}'")
            logger.debug(f"Session {session_id} now has {len(self.histories[session_id])} messages in history")
    
    def get_history(self, session_id):
        """Get the conversation history for a session"""
        with self.lock:
            if session_id not in self.histories:
                logger.debug(f"No history found for session {session_id}, creating empty history")
                self.histories[session_id] = []
            return self.histories[session_id]
    
    def clean_old_sessions(self, max_age=3600):
        """Clean up sessions older than max_age seconds"""
        current_time = time.time()
        with self.lock:
            sessions_to_remove = []
            for session_id, messages in self.histories.items():
                if not messages:
                    continue
                latest_message_time = max(msg.get('timestamp', 0) for msg in messages)
                if current_time - latest_message_time > max_age:
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                logger.info(f"Removing old session {session_id}")
                del self.histories[session_id]
            
            if sessions_to_remove:
                logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")

def analyze_conversation(history, current_question):
    """
    Analyze the conversation history to see if the current question has been asked before
    and if there's a relevant answer in the history.
    """
    if not history or not current_question:
        return None
    
    logger.info(f"Analyzing conversation history for question: '{current_question}'")
    
    if use_fallback:
        return fallback_analyze_conversation(history, current_question)
    
    try:
        # Prepare the conversation history for the LLM
        conversation_text = []
        for msg in history:
            speaker = "User" if msg.get('is_user', False) else "Assistant"
            conversation_text.append(f"{speaker}: {msg['text']}")
        
        conversation_str = "\n".join(conversation_text)
        
        # Ask OpenAI to analyze the conversation
        logger.debug(f"Sending conversation history to OpenAI for analysis")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are analyzing a conversation to determine if a question has been asked and answered before. If the latest message is a question and a similar question was asked and answered earlier in the conversation, extract the previous answer. If not, or if the latest message isn't a question, return 'No answer found'."},
                {"role": "user", "content": f"Here's the conversation history:\n\n{conversation_str}\n\nThe latest message is: {current_question}\n\nIs this latest message a question that was asked and answered before in this conversation? If yes, what was the answer? Format your response as JSON with fields 'is_repeated_question' (boolean) and 'previous_answer' (string)."}
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        is_repeated = result.get('is_repeated_question', False)
        previous_answer = result.get('previous_answer', None)
        
        if is_repeated and previous_answer and previous_answer != "No answer found":
            logger.info(f"Found repeated question with answer: '{previous_answer}'")
            return previous_answer
        else:
            logger.debug(f"No repeated question found or no relevant answer")
            return None
            
    except Exception as e:
        logger.error(f"Error in LLM analysis: {str(e)}")
        return fallback_analyze_conversation(history, current_question)

def is_question(text):
    """Determine if text is a question"""
    logger.debug(f"Checking if text is a question: '{text}'")
    if not text:
        return False
        
    # Simple fallback implementation - check for question marks or common question words
    text_lower = text.lower()
    
    # Filter out rhetorical questions and common phrases
    rhetorical_patterns = [
        "you know?", "right?", "isn't it?", "don't you think?", "wouldn't you?", 
        "wouldn't it?", "ain't it?", "okay?", "correct?", "got it?"
    ]
    
    # If it's a short phrase ending with a question mark and matches a rhetorical pattern
    if len(text_lower.split()) <= 5 and any(text_lower.endswith(pattern) for pattern in rhetorical_patterns):
        logger.debug(f"Detected rhetorical question: '{text}'")
        return False
    
    # Check for actual question indicators
    question_words = ["what", "where", "when", "who", "why", "how", "is", "are", "can", "could", "would", "will"]
    has_question_mark = "?" in text
    starts_with_question_word = any(text_lower.startswith(word) for word in question_words)
    
    # Require more evidence for actual questions
    if has_question_mark:
        if starts_with_question_word:
            result = True
        elif len(text.split()) >= 4:  # Longer questions with question marks are likely real questions
            result = True
        else:
            # Short phrases with just question marks might be rhetorical
            result = False
    else:
        # Without a question mark, be more strict
        result = starts_with_question_word and len(text.split()) >= 4
    
    logger.debug(f"Question detection result for '{text}': {result}")
    return result

def are_questions_similar(q1, q2):
    """Check if two questions are similar using semantic comparison"""
    # Log the comparison being made
    logger.debug(f"Comparing questions for similarity: '{q1}' and '{q2}'")
    
    # Normalize questions
    q1 = q1.lower().replace("'s", " is").replace("?", "").strip()
    q2 = q2.lower().replace("'s", " is").replace("?", "").strip()
    
    # Check for exact match
    if q1 == q2:
        logger.debug(f"Exact match between '{q1}' and '{q2}'")
        return True
    
    # Get question types
    q1_type = get_question_type(q1)
    q2_type = get_question_type(q2)
    
    # Log question types for debugging
    logger.debug(f"Question type for '{q1}': {q1_type}")
    logger.debug(f"Question type for '{q2}': {q2_type}")
    
    # If the questions are of different types, they're less likely to be similar
    if q1_type and q2_type and q1_type != q2_type:
        logger.debug(f"Different question types: '{q1}' type: {q1_type}, '{q2}' type: {q2_type}")
        return False
    
    # Special case for where questions
    if q1_type == "where" and q2_type == "where":
        # Extract the object being asked about
        q1_obj = q1.replace("where is", "").strip().replace("the", "").strip()
        q2_obj = q2.replace("where is", "").strip().replace("the", "").strip()
        
        # If asking about the same object, they're similar
        if q1_obj == q2_obj:
            logger.debug(f"Where-question object match: '{q1_obj}' and '{q2_obj}'")
            return True
        
        # If objects are similar enough (e.g., box/boxes)
        if q1_obj.startswith(q2_obj) or q2_obj.startswith(q1_obj):
            # Make sure they're actually related (e.g., "box" and "boxing" aren't related)
            if len(q1_obj) - len(q2_obj) <= 2 or len(q2_obj) - len(q1_obj) <= 2:
                logger.debug(f"Where-question similar objects: '{q1_obj}' and '{q2_obj}'")
                return True
    
    # Normalize "what is X made of" and "what is X made from" patterns
    q1_normalized = q1.replace("made of", "made from").replace("made from", "made of")
    q2_normalized = q2.replace("made of", "made from").replace("made from", "made of")
    
    if q1_normalized == q2_normalized:
        logger.debug(f"Normalized match between '{q1}' and '{q2}'")
        return True
    
    # Create a function to extract the subject of "what is X made of" questions
    def extract_made_of_subject(q):
        import re
        match = re.search(r"what is (?:the )?(.*?) made", q)
        if match:
            return match.group(1)
        return None
    
    # Check for "what is X made of" pattern
    q1_subject = extract_made_of_subject(q1)
    q2_subject = extract_made_of_subject(q2)
    
    if q1_subject and q2_subject and q1_subject == q2_subject:
        logger.debug(f"Made-of subject match between '{q1}' and '{q2}': both about '{q1_subject}'")
        return True
    
    # Extract key entities and question types
    q1_entities = extract_entities(q1)
    q2_entities = extract_entities(q2)
    
    # Log entities for debugging
    logger.debug(f"Entities in '{q1}': {q1_entities}")
    logger.debug(f"Entities in '{q2}': {q2_entities}")
    
    # If the questions are about different entities, they're not similar
    common_entities = q1_entities.intersection(q2_entities)
    if not common_entities:
        logger.debug(f"Different entities in questions: '{q1}' entities: {q1_entities}, '{q2}' entities: {q2_entities}")
        return False
    else:
        # Check if the common entities are significant enough
        # If there are multiple entities in each question but only one in common, they're likely not similar
        if len(q1_entities) >= 2 and len(q2_entities) >= 2 and len(common_entities) < 2:
            logger.debug(f"Not enough common entities: '{common_entities}' out of '{q1_entities}' and '{q2_entities}'")
            return False
        logger.debug(f"Common entities: {common_entities}")
    
    # Check for word overlap
    words1 = set(q1.split())
    words2 = set(q2.split())
    common_words = words1.intersection(words2)
    
    # Filter out stop words from common words
    stop_words = {"what", "where", "when", "who", "why", "how", "is", "are", "the", "a", "an", "in", "on", "at", "to", "for", "with", "by", "about"}
    meaningful_common_words = [w for w in common_words if w not in stop_words]
    
    # Require at least some meaningful common words
    if not meaningful_common_words:
        logger.debug(f"No meaningful common words between '{q1}' and '{q2}'")
        return False
    
    # If more than 75% of words match and they share entities, consider them similar
    overlap_ratio = len(common_words) / min(len(words1), len(words2))
    logger.debug(f"Word overlap ratio: {overlap_ratio:.2f}, common words: {common_words}")
    
    if overlap_ratio >= 0.75:
        logger.debug(f"High word overlap ({overlap_ratio:.2f}) between '{q1}' and '{q2}'")
        return True
    
    logger.debug(f"Questions not similar: '{q1}' and '{q2}' (overlap: {overlap_ratio:.2f})")
    return False

def extract_entities(text):
    """Extract potential entities (nouns) from text"""
    # Simple entity extraction - just get potential nouns
    # More extensive stop words list to filter out common words
    stop_words = {
        "what", "where", "when", "who", "why", "how", "is", "are", "the", "a", "an", "in", "on", 
        "at", "to", "for", "with", "by", "about", "like", "from", "of", "that", "this", "these", 
        "those", "it", "they", "them", "their", "there", "here", "you", "your", "my", "mine", 
        "our", "ours", "his", "her", "hers", "its", "have", "has", "had", "get", "got", "been",
        "was", "were", "be", "being", "am", "go", "going", "went", "gone", "come", "coming",
        "just", "very", "really", "quite", "so", "much", "many", "few", "little", "some", "any",
        "all", "most", "more", "less", "too", "also", "as", "well", "good", "bad", "nice", 
        "great", "big", "small", "high", "low", "tall", "short", "long", "see", "saw", "seen",
        "now", "then", "when", "where", "why", "how", "if", "but", "and", "or", "not", "no",
        "yes", "yeah", "okay", "ok", "right", "left", "up", "down", "out", "in", "over", 
        "under", "yet", "still", "only", "even", "ever", "never", "always", "sometimes"
    }
    
    words = text.lower().split()
    entities = set()
    
    for word in words:
        if word not in stop_words and len(word) > 2:  # Skip short words and common words
            # Remove any trailing punctuation
            word = word.rstrip(".,;:!?")
            if word:  # Check if the word is not empty after stripping
                entities.add(word)
    
    return entities

def get_question_type(text):
    """Get the type of question (what, where, when, who, why, how)"""
    question_types = {"what", "where", "when", "who", "why", "how"}
    words = text.lower().split()
    
    if words:
        if words[0] in question_types:
            return words[0]
    
    return None

def has_location_indicators(text):
    """
    Check if the text contains indicators of a location.
    This helps determine if a text is answering a 'where' question.
    """
    text = text.lower()
    
    # Common location prepositions and indicators
    location_indicators = [
        ' in ', ' on ', ' at ', ' under ', ' above ', ' below ', ' beside ', 
        ' next to ', ' near ', ' by ', ' inside ', ' outside ', ' behind ',
        ' in front of ', ' across from ', ' around ', ' between ', ' left ',
        ' right ', ' top ', ' bottom ', ' north ', ' south ', ' east ', ' west ',
        ' upstairs ', ' downstairs ', ' here ', ' there ', ' somewhere ',
        ' location ', ' place ', ' area ', ' region ', ' room ', ' building '
    ]
    
    # Common words that might appear in "on" phrases that aren't locations
    non_location_words = ['wait', 'hold on', 'going on', 'come on', 'hang on', 'depends on', 
                          'carry on', 'later on', 'based on', 'working on', 'keep on',
                          'going on', 'rely on', 'count on', 'put on', 'taking on',
                          'from now on', 'right on']
    
    # First check if any non-location phrases are in the text
    for phrase in non_location_words:
        if phrase in text:
            # If the phrase is in the text, remove it before continuing
            text = text.replace(phrase, '')
    
    # Now check for location indicators
    for indicator in location_indicators:
        if indicator in text:
            # Make sure it's not just a false positive
            words_after = text.split(indicator)[-1].strip()
            if words_after and len(words_after) > 1:  # Ensure there's meaningful content after the indicator
                return True
    
    # Additional check for common location nouns often used to answer "where" questions
    location_nouns = [
        'table', 'desk', 'chair', 'floor', 'wall', 'ceiling', 'room', 'house', 
        'apartment', 'office', 'building', 'street', 'road', 'avenue', 'store',
        'shop', 'mall', 'market', 'school', 'university', 'library', 'park',
        'garden', 'yard', 'kitchen', 'bathroom', 'bedroom', 'living room',
        'home', 'work', 'car', 'bus', 'train', 'plane', 'cabinet', 'drawer',
        'closet', 'shelf', 'counter', 'couch', 'sofa', 'corner', 'window',
        'door', 'hallway', 'corridor', 'stairway', 'elevator', 'garage'
    ]
    
    for noun in location_nouns:
        if f" {noun} " in f" {text} " or text.endswith(f" {noun}") or text.startswith(f"{noun} "):
            return True
    
    return False

def create_faq_response(question, answer):
    """Create a response with the answer"""
    logger.info(f"Creating response for question: '{question}' with answer: '{answer}'")
    return {
        "message": f"I remember this! The answer is: {answer}"
    }

def is_answer_relevant(question, answer):
    """
    Check if an answer is relevant to the question.
    
    Returns:
        bool: True if answer seems relevant, False otherwise
    """
    if not answer or len(answer.strip()) < 3:
        return False
    
    # Check for generic non-answers
    non_answers = ["i don't know", "not sure", "no idea", "i'm not", "wait", "one second", 
                  "just a moment", "ask", "let me", "okay", "yeah", "cool", "never mind",
                  "not enough time"]
    
    lower_answer = answer.lower()
    for phrase in non_answers:
        if phrase in lower_answer:
            return False
    
    # Get question type and check for appropriate answer patterns
    question_type = get_question_type(question)
    
    # For 'where' questions, check if answer contains location indicators
    if question_type == 'where':
        return has_location_indicators(answer)
    
    # For 'what is' questions, check if answer seems like a definition or description
    elif question_type == 'what' and 'what is' in question.lower():
        # Answer should be longer than just a few words for a definition
        if len(answer.split()) < 3:
            return False
            
        # Answer should not be a question
        if is_question(answer):
            return False
            
        # Answer should contain nouns or be descriptive
        subject = extract_entities(question)
        if subject and any(entity in answer.lower() for entity in subject):
            return True
            
        # If the answer has enough content, it's likely relevant
        return len(answer.split()) >= 5
        
    # For 'who' questions, check if answer likely refers to a person
    elif question_type == 'who':
        person_indicators = ['he', 'she', 'they', 'name is', 'person', 'mr', 'ms', 'mrs', 'dr']
        return any(indicator in answer.lower() for indicator in person_indicators)
    
    # For 'how' questions, check for explanatory answers
    elif question_type == 'how':
        if len(answer.split()) < 5:  # Explanations are usually longer
            return False
        return True
        
    # For 'when' questions, check for time indicators
    elif question_type == 'when':
        time_indicators = ['today', 'tomorrow', 'yesterday', 'morning', 'afternoon', 'evening', 
                          'night', 'day', 'week', 'month', 'year', 'minute', 'hour', 'am', 'pm',
                          'january', 'february', 'march', 'april', 'may', 'june', 'july', 
                          'august', 'september', 'october', 'november', 'december']
        return any(indicator in answer.lower() for indicator in time_indicators)
    
    # Default: answer should be reasonably long and not be a question itself
    if is_question(answer):
        return False
        
    # Default check - answer should be substantial
    return len(answer.split()) >= 3

def fallback_analyze_conversation(history, current_question):
    """
    Analyze the conversation history to find an answer to the current question using simple text matching.
    This is used when the LLM is not available or as a fallback method.
    """
    logger.debug(f"Using fallback method to analyze conversation for question: '{current_question}'")
    
    if not is_question(current_question):
        return None
    
    # Track all previously asked questions and their answers
    previous_qa_pairs = []
    
    # Extract subject of current question for better matching
    question_type = get_question_type(current_question)
    question_entities = extract_entities(current_question)
    logger.debug(f"Current question type: {question_type}, entities: {question_entities}")
    
    # First, check example QA pairs for an exact or similar match
    for qa_pair in conversation_history.example_qa_pairs:
        if are_questions_similar(current_question, qa_pair["question"]):
            logger.info(f"Found matching example QA pair: Q: '{qa_pair['question']}' A: '{qa_pair['answer']}'")
            return qa_pair["answer"]
    
    # Special handling for repeated questions - look for exact matches first
    for i, msg in enumerate(history):
        if i == len(history) - 1:  # Skip the last message (current one)
            continue
            
        text = msg.get('text', '').strip()
        
        # If this is the exact same question as the current one
        if text.lower() == current_question.lower():
            logger.debug(f"Found exact repeat of the current question at index {i}")
            
            # Look for an answer after this question
            # Try to combine consecutive messages that might form a complete answer
            combined_answer = ""
            last_speaker = None
            
            for j in range(i + 1, min(i + 5, len(history))):
                if j >= len(history):
                    break
                    
                answer_msg = history[j]
                current_speaker = "user" if answer_msg.get('is_user', False) else "other"
                answer_text = answer_msg.get('text', '').strip()
                
                # Skip if it's a question itself
                if is_question(answer_text):
                    # If we already started building an answer, break to use what we have
                    if combined_answer:
                        break
                    # Otherwise, skip this question and continue looking
                    continue
                
                # Handle speaker changes - if different person starts talking, likely end of previous answer
                if last_speaker and current_speaker != last_speaker and combined_answer:
                    break
                    
                last_speaker = current_speaker
                
                # Append this message to our combined answer
                if combined_answer:
                    combined_answer += " " + answer_text
                else:
                    combined_answer = answer_text
                
                # Check if we have a relevant answer now
                if is_answer_relevant(text, combined_answer):
                    logger.info(f"Found combined answer to repeat question: '{combined_answer}'")
                    return combined_answer
            
            # If we collected some text but it didn't pass the relevance check,
            # try anyways for "where" questions since they might have simple answers
            if combined_answer and question_type == "where" and len(combined_answer.split()) >= 2:
                # For "where" questions, check if the answer contains the entity being asked about
                # and a location indicator
                entity_mentioned = any(entity in combined_answer.lower() for entity in question_entities)
                has_location = has_location_indicators(combined_answer)
                
                if entity_mentioned and has_location:
                    logger.info(f"Found partial location answer: '{combined_answer}'")
                    return combined_answer
    
    # Process the history to collect all question-answer pairs
    for i, msg in enumerate(history):
        if i >= len(history) - 1:  # Skip the last message (current one)
            continue
            
        text = msg.get('text', '').strip()
        
        # Skip exact matches with current question as they were checked above
        if text.lower() == current_question.lower():
            continue
            
        if is_question(text):
            # For each question, look for answers in subsequent messages
            combined_answer = ""
            last_speaker = None
            answer_start_idx = 0
            
            for j in range(i + 1, min(i + 5, len(history))):
                if j >= len(history):
                    break
                    
                answer_msg = history[j]
                current_speaker = "user" if answer_msg.get('is_user', False) else "other"
                answer_text = answer_msg.get('text', '').strip()
                
                # If this is a question and we haven't started building an answer yet, it's likely
                # not an answer to the previous question
                if is_question(answer_text):
                    if not combined_answer:  # No answer started yet
                        answer_start_idx = j + 1  # Start with the next message
                        continue
                    else:
                        # If we already have part of an answer, stop here
                        break
                
                # Handle speaker changes - unless it's a short continuation
                if last_speaker and current_speaker != last_speaker:
                    # Allow short continuations (like "Ukraine." after "Alex is in")
                    if len(answer_text.split()) <= 2 and combined_answer and not is_question(answer_text):
                        # Continue building the answer
                        pass
                    elif combined_answer:
                        # If we have an answer and speaker changed with a longer message, end the answer
                        break
                
                last_speaker = current_speaker
                
                # Append this message to our combined answer
                if combined_answer:
                    combined_answer += " " + answer_text
                else:
                    combined_answer = answer_text
                    answer_start_idx = j
                
                # Check if we have a relevant answer now
                if is_answer_relevant(text, combined_answer):
                    previous_qa_pairs.append({
                        'question': text,
                        'answer': combined_answer,
                        'index': i,
                        'answer_index': answer_start_idx
                    })
                    break

            # Special handling for "where" questions that might have short or split answers
            if not previous_qa_pairs and question_type == "where" and get_question_type(text) == "where":
                q_entities = extract_entities(text)
                if combined_answer and len(combined_answer.split()) >= 2:
                    entity_mentioned = any(entity in combined_answer.lower() for entity in q_entities)
                    has_location = has_location_indicators(combined_answer)
                    
                    if entity_mentioned and has_location:
                        previous_qa_pairs.append({
                            'question': text,
                            'answer': combined_answer,
                            'index': i,
                            'answer_index': answer_start_idx
                        })
    
    # Now evaluate all collected QA pairs against the current question
    potential_matches = []
    
    for qa_pair in previous_qa_pairs:
        similarity = are_questions_similar(current_question, qa_pair['question'])
        if similarity:
            # Score based on similarity and recency (higher index = more recent)
            score = similarity * (0.8 + 0.2 * (qa_pair['index'] / len(history)))
            potential_matches.append({
                'question': qa_pair['question'],
                'answer': qa_pair['answer'],
                'score': score
            })
    
    # Log all potential matches for debugging
    if potential_matches:
        logger.debug(f"Found {len(potential_matches)} potential matches for '{current_question}'")
        for i, match in enumerate(potential_matches):
            logger.debug(f"Match {i+1}: Q: '{match['question']}' A: '{match['answer']}' Score: {match['score']:.2f}")
    
    # Sort by score (higher is better)
    potential_matches.sort(key=lambda x: x['score'], reverse=True)
    
    if potential_matches:
        best_match = potential_matches[0]
        logger.info(f"Found similar question in history: Q: '{best_match['question']}' A: '{best_match['answer']}'")
        return best_match['answer']
    
    # Last resort: look for entity-based answers for "where" questions
    if question_type == "where" and question_entities:
        entity_name = list(question_entities)[0] if question_entities else None
        if entity_name:
            logger.debug(f"Searching for location of entity: '{entity_name}'")
            
            # Look for messages mentioning this entity and locations
            location_fragments = []
            
            for i, msg in enumerate(history):
                if i == len(history) - 1:  # Skip current message
                    continue
                    
                text = msg.get('text', '').strip().lower()
                if entity_name in text and (
                    "is in" in text or 
                    "is at" in text or 
                    "is on" in text or
                    has_location_indicators(text)
                ):
                    location_fragments.append(text)
                    
                    # Also check the next message in case the location continues there
                    if i+1 < len(history)-1:
                        next_text = history[i+1].get('text', '').strip()
                        if not is_question(next_text) and len(next_text.split()) <= 3:
                            location_fragments.append(next_text)
            
            if location_fragments:
                combined_location = " ".join(location_fragments)
                logger.info(f"Found location fragments for entity '{entity_name}': '{combined_location}'")
                return combined_location
    
    logger.debug(f"No similar question found in history for '{current_question}'")
    return None

# Initialize conversation history
conversation_history = ConversationHistory()

# Cleanup thread
def cleanup_thread_function():
    while True:
        try:
            time.sleep(3600)  # Run once per hour
            conversation_history.clean_old_sessions()
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
    global conversation_history
    
    try:
        # Extract session ID from query parameters
        session_id = request.args.get('uid', 'test_session')
        
        # Parse the incoming JSON data
        data = request.json
        segments = data.get('segments', [])
        
        logger.info(f"Received webhook request for session {session_id} with {len(segments)} segments")
        
        for segment in segments:
            # Extract information from the segment
            text = segment.get('text', '').strip()
            if not text:
                continue
                
            is_user = segment.get('is_user', False)
            timestamp = segment.get('timestamp', time.time())
            
            logger.debug(f"Processing segment from {'User' if is_user else 'Other'}: '{text}' with timestamp {timestamp}")
            
            # Add the message to conversation history
            conversation_history.add_message(session_id, {
                'text': text,
                'is_user': is_user,
                'timestamp': timestamp
            })
            
            history = conversation_history.get_history(session_id)
            logger.debug(f"Session {session_id} now has {len(history)} messages in history")
            
            # If this is a user message, check if it's a question
            if is_user:
                logger.debug(f"Checking if user message is a question: '{text}'")
                
                if is_question(text):
                    logger.info(f"User message is a question: '{text}'")
                    
                    # Check if this is a repeated question we've seen before
                    repeat_count = sum(1 for msg in history[:-1] if msg.get('text', '').lower().strip() == text.lower().strip())
                    if repeat_count > 0:
                        logger.info(f"This question has been asked {repeat_count} times before")
                    
                    # Check if it's similar to a previous question in the history
                    answer = analyze_conversation(history, text)
                    
                    if answer:
                        # Before sending the response, check if the answer is relevant
                        if is_answer_relevant(text, answer):
                            response = create_faq_response(text, answer)
                            logger.info(f"Found answer in conversation history, sending response: {response}")
                            return jsonify(response), 200
                        else:
                            logger.info(f"Found answer but it's not relevant: '{answer}'. Not sending a response.")
                            
                            # For "where" questions, make an extra attempt with lower threshold
                            question_type = get_question_type(text)
                            if question_type == "where":
                                logger.info("This is a 'where' question, trying with lower relevance threshold")
                                if answer and has_location_indicators(answer):
                                    logger.info(f"Answer has location indicators, accepting: '{answer}'")
                                    response = create_faq_response(text, answer)
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
        "active_sessions": len(conversation_history.histories),
        "uptime": time.time() - start_time
    })

# Add start time tracking
start_time = time.time()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 