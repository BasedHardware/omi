"""
IQ Rating Plugin - Rate everyone you've met by IQ score

A simple, viral-optimized app that shows all people you've met
sorted by their IQ scores (smartest to dumbest).
"""

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Optional, Dict
import logging
import os
import requests
import hashlib
import random
import re
import time
import threading
import sqlite3
import json
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/iq-rating",
    tags=["iq-rating"],
)

# API credentials
OMI_APP_ID = os.getenv("OMI_APP_ID", "01KCMNCPS9K8EV50BEJ37C0RH7")
OMI_APP_SECRET = os.getenv("OMI_APP_SECRET", "sk_d151b7b791931b66b6781163ee3a5773")
OMI_BASE_API_URL = os.getenv("OMI_BASE_API_URL", "https://api.omi.me")

# OpenAI for name filtering
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Database path
DB_PATH = Path(__file__).parent / "iq_rating.db"

# In-memory cache for quick access
_cache = {}
_cache_loading = set()


# ============== DATABASE FUNCTIONS ==============

def init_db():
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Store raw memories/conversations data (downloaded once)
    c.execute('''CREATE TABLE IF NOT EXISTS user_raw_data (
        uid TEXT PRIMARY KEY,
        memories TEXT,
        conversations TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Store processed people with IQ scores
    c.execute('''CREATE TABLE IF NOT EXISTS people (
        id TEXT PRIMARY KEY,
        uid TEXT,
        name TEXT,
        iq INTEGER,
        mention_count INTEGER,
        is_hidden INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Index for faster lookups
    c.execute('CREATE INDEX IF NOT EXISTS idx_people_uid ON people(uid)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_people_hidden ON people(uid, is_hidden)')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


def has_user_data(uid: str) -> bool:
    """Check if we already have data for this user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM user_raw_data WHERE uid = ?', (uid,))
    result = c.fetchone() is not None
    conn.close()
    return result


def store_raw_data(uid: str, memories: List[dict], conversations: List[dict]):
    """Store raw memories and conversations for a user (once and for all)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO user_raw_data (uid, memories, conversations, fetched_at)
                 VALUES (?, ?, ?, CURRENT_TIMESTAMP)''',
              (uid, json.dumps(memories), json.dumps(conversations)))
    conn.commit()
    conn.close()
    logger.info(f"Stored raw data for {uid[:8]}: {len(memories)} memories, {len(conversations)} conversations")


def get_raw_data(uid: str) -> tuple:
    """Get stored raw data for a user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT memories, conversations FROM user_raw_data WHERE uid = ?', (uid,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), json.loads(row[1])
    return [], []


def store_people(uid: str, people: List[dict]):
    """Store processed people data."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    for person in people:
        c.execute('''INSERT OR REPLACE INTO people (id, uid, name, iq, mention_count, is_hidden)
                     VALUES (?, ?, ?, ?, ?, 
                            COALESCE((SELECT is_hidden FROM people WHERE id = ?), 0))''',
                  (person['id'], uid, person['name'], person['iq'], person['memory_count'], person['id']))
    
    conn.commit()
    conn.close()
    logger.info(f"Stored {len(people)} people for {uid[:8]}")


def get_people_from_db(uid: str, include_hidden: bool = False) -> List[dict]:
    """Get processed people for a user from database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if include_hidden:
        c.execute('SELECT id, name, iq, mention_count, is_hidden FROM people WHERE uid = ? ORDER BY iq DESC', (uid,))
    else:
        c.execute('SELECT id, name, iq, mention_count, is_hidden FROM people WHERE uid = ? AND is_hidden = 0 ORDER BY iq DESC', (uid,))
    
    rows = c.fetchall()
    conn.close()
    
    people = []
    for row in rows:
        category, emoji, color = get_iq_category(row[2])
        people.append({
            'id': row[0],
            'name': row[1],
            'iq': row[2],
            'memory_count': row[3],
            'is_hidden': bool(row[4]),
            'category': category,
            'category_emoji': emoji,
            'category_color': color
        })
    
    return people


def hide_person(uid: str, person_id: str) -> bool:
    """Hide a person from the list (mark as not a real name)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE people SET is_hidden = 1 WHERE uid = ? AND id = ?', (uid, person_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    # Clear cache
    if uid in _cache:
        del _cache[uid]
    return affected > 0


def adjust_iq(uid: str, person_id: str, delta: int) -> Optional[int]:
    """Adjust a person's IQ score by delta (+/- amount)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT iq FROM people WHERE uid = ? AND id = ?', (uid, person_id))
    row = c.fetchone()
    if row:
        new_iq = max(50, min(180, row[0] + delta))
        c.execute('UPDATE people SET iq = ? WHERE uid = ? AND id = ?', (new_iq, uid, person_id))
        conn.commit()
        # Clear cache
        if uid in _cache:
            del _cache[uid]
        conn.close()
        return new_iq
    conn.close()
    return None


def unhide_person(uid: str, person_id: str) -> bool:
    """Unhide a person."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE people SET is_hidden = 0 WHERE uid = ? AND id = ?', (uid, person_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    # Clear cache
    if uid in _cache:
        del _cache[uid]
    return affected > 0


def has_people_in_db(uid: str) -> bool:
    """Check if we have processed people for this user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM people WHERE uid = ?', (uid,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


# Initialize database on module load
init_db()


# ============== OPENAI NAME FILTERING ==============

def filter_names_with_openai(names: List[str]) -> List[str]:
    """Use OpenAI to filter out non-names from a list."""
    if not names:
        return []
    
    if not OPENAI_API_KEY:
        logger.warning("No OpenAI API key - names will not be AI-filtered")
        return names
    
    try:
        valid_names = []
        batch_size = 50  # Process in batches
        
        for i in range(0, len(names), batch_size):
            batch = names[i:i + batch_size]
            names_str = ", ".join(batch)
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are a name validator. Given a list of words, return ONLY the ones that are real human first names or last names.

Rules:
- Include common first names from any culture (English, Spanish, Russian, Chinese, Indian, Arabic, etc.)
- Include common last names (especially recognizable ones like "Draper", "Smith", "Chen")
- EXCLUDE: verbs, adjectives, common nouns, places, companies, products, brands
- EXCLUDE: words like "Forbes", "Finalizes", "Smart", "Quick", "Express"
- Be strict - when in doubt, exclude

Return as a comma-separated list. If none are names, return 'NONE'."""
                        },
                        {
                            "role": "user", 
                            "content": f"Which of these are real human names? {names_str}"
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result["choices"][0]["message"]["content"].strip()
                
                if answer.upper() != "NONE":
                    batch_valid = [n.strip() for n in answer.split(",") if n.strip()]
                    valid_names.extend(batch_valid)
            else:
                logger.error(f"OpenAI API error: {response.status_code}")
                # On error, skip this batch
        
        logger.info(f"AI filtered {len(names)} -> {len(valid_names)} names")
        return valid_names
        
    except Exception as e:
        logger.error(f"Error filtering names with AI: {e}")
        return names


# ============== DATA FETCHING ==============

def fetch_all_memories(uid: str) -> List[dict]:
    """Fetch ALL memories for a user."""
    try:
        all_memories = []
        offset = 0
        limit = 100
        
        while True:
            url = f"{OMI_BASE_API_URL}/v2/integrations/{OMI_APP_ID}/memories"
            params = {"uid": uid, "limit": limit, "offset": offset}
            headers = {
                "Authorization": f"Bearer {OMI_APP_SECRET}",
                "Content-Type": "application/json",
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                memories = data if isinstance(data, list) else data.get("memories", [])
                
                if not memories:
                    break
                
                all_memories.extend(memories)
                
                if len(memories) < limit:
                    break
                
                offset += limit
            elif response.status_code == 429:
                logger.warning("Rate limited, waiting 2 seconds...")
                time.sleep(2)
                continue
            else:
                logger.error(f"Failed to fetch memories: {response.status_code}")
                break
        
        logger.info(f"Fetched {len(all_memories)} total memories")
        return all_memories
    except Exception as e:
        logger.error(f"Error fetching memories: {e}")
        return []


def fetch_all_conversations(uid: str) -> List[dict]:
    """Fetch ALL conversations for a user."""
    try:
        all_conversations = []
        offset = 0
        limit = 100
        
        while True:
            url = f"{OMI_BASE_API_URL}/v2/integrations/{OMI_APP_ID}/conversations"
            params = {"uid": uid, "limit": limit, "offset": offset}
            headers = {
                "Authorization": f"Bearer {OMI_APP_SECRET}",
                "Content-Type": "application/json",
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                conversations = data if isinstance(data, list) else data.get("conversations", [])
                
                if not conversations:
                    break
                
                all_conversations.extend(conversations)
                
                if len(conversations) < limit:
                    break
                
                offset += limit
            elif response.status_code == 429:
                logger.warning("Rate limited, waiting 2 seconds...")
                time.sleep(2)
                continue
            else:
                logger.error(f"Failed to fetch conversations: {response.status_code}")
                break
        
        logger.info(f"Fetched {len(all_conversations)} total conversations")
        return all_conversations
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return []


# ============== NAME EXTRACTION ==============

def get_user_name_variations(memories: List[dict], conversations: List[dict]) -> set:
    """Extract the main user's name and common variations to exclude."""
    name_counts = {}
    
    nickname_groups = {
        'nik': {'nik', 'nick', 'nikita', 'nikolay', 'nikolai', 'nicky', 'nicolas', 'nicholas'},
        'alex': {'alex', 'alexander', 'alexis', 'alejandro', 'sasha', 'xander'},
        'mike': {'mike', 'michael', 'mick', 'mickey', 'mikey'},
        'dan': {'dan', 'daniel', 'danny', 'daniela'},
        'chris': {'chris', 'christopher', 'christian', 'kristopher'},
        'matt': {'matt', 'matthew', 'mateo', 'matthias', 'matteo'},
        'tom': {'tom', 'thomas', 'tommy', 'tomas'},
        'rob': {'rob', 'robert', 'robbie', 'bob', 'bobby', 'roberto'},
        'will': {'will', 'william', 'bill', 'billy', 'liam'},
        'joe': {'joe', 'joseph', 'joey', 'jose'},
        'sam': {'sam', 'samuel', 'sammy', 'samantha'},
        'ben': {'ben', 'benjamin', 'benji', 'benny'},
        'jake': {'jake', 'jacob', 'jacoby'},
        'andy': {'andy', 'andrew', 'drew', 'andre', 'andreas'},
        'dave': {'dave', 'david', 'davey'},
        'steve': {'steve', 'steven', 'stephen', 'stefan'},
        'john': {'john', 'johnny', 'jonathan', 'jon', 'johan'},
        'jim': {'jim', 'james', 'jimmy', 'jamie'},
        'tony': {'tony', 'anthony', 'antonio'},
        'paul': {'paul', 'paulo', 'pablo', 'pavel'},
    }
    
    name_to_group = {}
    for group_key, names in nickname_groups.items():
        for name in names:
            name_to_group[name] = group_key
    
    all_text = ""
    for memory in memories:
        all_text += " " + memory.get("content", "")
    for conv in conversations:
        structured = conv.get("structured", {})
        all_text += " " + structured.get("overview", "")
        all_text += " " + structured.get("title", "")
        for seg in conv.get("transcript_segments", []):
            all_text += " " + seg.get("text", "")
    
    words = re.findall(r'\b([A-Z][a-z]{2,14})\b', all_text)
    for word in words:
        word_lower = word.lower()
        name_counts[word_lower] = name_counts.get(word_lower, 0) + 1
    
    group_counts = {}
    for name, count in name_counts.items():
        if name in name_to_group:
            group = name_to_group[name]
            group_counts[group] = group_counts.get(group, 0) + count
    
    user_variations = set()
    if group_counts:
        top_group = max(group_counts, key=group_counts.get)
        if group_counts[top_group] >= 50:
            user_variations = nickname_groups[top_group]
            logger.info(f"Detected user name group: {top_group} with {group_counts[top_group]} mentions")
    
    if name_counts:
        top_name = max(name_counts, key=name_counts.get)
        if name_counts[top_name] >= 100 and top_name in name_to_group:
            user_variations.add(top_name)
            user_variations.update(nickname_groups[name_to_group[top_name]])
    
    user_variations = {v for v in user_variations if len(v) >= 2}
    logger.info(f"User name variations to exclude: {user_variations}")
    return user_variations


def extract_names_from_text(text: str) -> List[str]:
    """Extract potential names from text using patterns."""
    names = set()
    
    # Common name patterns
    # Pattern 1: "Name:" or "Name -" at start of line
    pattern1 = re.findall(r'(?:^|\n)\s*([A-Z][a-z]+)(?:\s*[:\-])', text)
    names.update(pattern1)
    
    # Pattern 2: Capitalized words that look like names (2-15 chars, not common words)
    common_words = {'The', 'This', 'That', 'What', 'When', 'Where', 'How', 'Why', 'Who', 
                    'Yes', 'Yeah', 'No', 'Not', 'But', 'And', 'Or', 'So', 'If', 'Then',
                    'Here', 'There', 'Now', 'Just', 'Like', 'Also', 'Very', 'Really',
                    'Okay', 'Right', 'Well', 'Actually', 'Basically', 'Maybe', 'Probably',
                    'Something', 'Everything', 'Nothing', 'Anything', 'Someone', 'Everyone',
                    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
                    'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                    'September', 'October', 'November', 'December', 'Today', 'Tomorrow', 'Yesterday',
                    'Morning', 'Afternoon', 'Evening', 'Night', 'Week', 'Month', 'Year',
                    'Because', 'However', 'Therefore', 'Although', 'Though', 'Since', 'Before',
                    'After', 'During', 'While', 'Until', 'Unless', 'Whether', 'Either', 'Neither',
                    'Both', 'Each', 'Every', 'Some', 'Any', 'All', 'Most', 'Many', 'Few', 'Several',
                    'Other', 'Another', 'Such', 'Same', 'Different', 'New', 'Old', 'Good', 'Bad',
                    'First', 'Last', 'Next', 'Best', 'Worst', 'More', 'Less', 'Much', 'Little',
                    'Sure', 'Hmm', 'Mhmm', 'Uhm', 'Uh', 'Oh', 'Ah', 'Wow', 'Hey', 'Hi', 'Hello',
                    'Thanks', 'Thank', 'Please', 'Sorry', 'Excuse', 'Bro', 'Dude', 'Man', 'Guy',
                    'People', 'Person', 'Thing', 'Things', 'Stuff', 'Way', 'Time', 'Place',
                    'App', 'Apps', 'Phone', 'Device', 'Video', 'Audio', 'Button', 'Screen',
                    'Company', 'Business', 'Work', 'Project', 'Team', 'Meeting', 'Call',
                    'Speaker', 'User', 'Users', 'Customer', 'Customers', 'Client', 'Clients',
                    # Tech/Companies/Products (not people)
                    'Google', 'Apple', 'Microsoft', 'Amazon', 'Facebook', 'Meta', 'Twitter',
                    'Gmail', 'Drive', 'Docs', 'Sheets', 'Slack', 'Zoom', 'Discord', 'Notion',
                    'Github', 'Gitlab', 'Figma', 'Canva', 'Stripe', 'Shopify', 'Salesforce',
                    'Deepgram', 'Rewind', 'Mixpanel', 'Segment', 'Amplitude', 'Firebase',
                    'Hardware', 'Software', 'Website', 'Database', 'Server', 'Cloud', 'Api',
                    'Mac', 'Windows', 'Linux', 'Ios', 'Android', 'Chrome', 'Safari', 'Firefox',
                    'Dropbox', 'Icloud', 'Onedrive', 'Box', 'Evernote', 'Trello', 'Asana', 'Jira',
                    # Places (not people) 
                    'America', 'Europe', 'Asia', 'Africa', 'Australia', 'Canada', 'Mexico',
                    'China', 'India', 'Japan', 'Korea', 'Russia', 'Brazil', 'Germany', 'France',
                    'London', 'Paris', 'Tokyo', 'Beijing', 'Dubai', 'Singapore', 'Sydney',
                    'Angeles', 'Francisco', 'York', 'Chicago', 'Miami', 'Boston', 'Seattle',
                    'Bay', 'Area', 'Valley', 'Hills', 'Beach', 'City', 'Town', 'Street',
                    'Koreatown', 'Hollywood', 'Downtown', 'Midtown', 'Uptown',
                    'Indian', 'Chinese', 'Japanese', 'Korean', 'Russian', 'Vietnamese', 'Mexican',
                    'American', 'European', 'Asian', 'African', 'Australian',
                    'Kazakhstan', 'Ukraine', 'Poland', 'Italy', 'Spain', 'England',
                    'German', 'French', 'Spanish', 'Italian', 'British', 'Dutch', 'Swedish',
                    'Turkish', 'Portuguese', 'Arabic', 'Hebrew', 'Thai',
                    'Florida', 'Georgia', 'Alabama', 'Texas', 'Nevada', 'Arizona', 'Ohio',
                    'Iowa', 'Maine', 'Utah', 'Idaho', 'Kansas', 'Montana', 'Wyoming', 'Vermont',
                    'Alaska', 'Hawaii', 'Delaware', 'Maryland', 'Virginia', 'Carolina', 'Dakota',
                    'Nebraska', 'Oklahoma', 'Arkansas', 'Louisiana', 'Mississippi', 'Tennessee',
                    'Kentucky', 'Indiana', 'Illinois', 'Wisconsin', 'Michigan', 'Missouri',
                    'Connecticut', 'Massachusetts', 'Pennsylvania', 'Minnesota', 'Oregon',
                    'Britain', 'California', 'Pakistan', 'Shanghai', 'Brooklyn', 'Sakhalin',
                    'Vancouver', 'Shenzhen', 'Basel', 'Vegas',
                    # Common non-name words
                    'Action', 'Capital', 'League', 'Ivy', 'Black', 'White', 'Red', 'Blue', 'Green',
                    'For', 'Looks', 'Thin', 'Omni', 'Geo', 'San', 'Los', 'Las', 'Del', 'La',
                    'Residency', 'Software', 'Butcher', 'Amish', 'Sikh',
                    'Jewish', 'Christian', 'Muslim', 'Hindu', 'Buddhist',
                    # Short common words that get capitalized
                    'In', 'On', 'At', 'To', 'Up', 'By', 'Is', 'It', 'As', 'Of', 'Be', 'Do', 'Go',
                    'Me', 'We', 'Us', 'He', 'My', 'An', 'Am', 'So', 'Or', 'If', 'No',
                    # More common words mistaken as names
                    'Plan', 'Chat', 'Later', 'Wearable', 'Founders', 'Founder', 'Device',
                    'Telegram', 'Airbnb', 'Uber', 'Lyft', 'Paypal', 'Venmo', 'Cashapp',
                    'Podcast', 'Recording', 'Conversation', 'Memory', 'Memories',
                    'Focus', 'Growth', 'Revenue', 'Startup', 'Startups', 'Investment',
                    'Feature', 'Features', 'Product', 'Products', 'Service', 'Services',
                    'Experience', 'Performance', 'Quality', 'Content', 'Context',
                    'Example', 'Examples', 'Process', 'System', 'Systems', 'Platform',
                    'Issue', 'Issues', 'Problem', 'Problems', 'Solution', 'Solutions',
                    'Question', 'Questions', 'Answer', 'Answers', 'Comment', 'Comments',
                    'Test', 'Tests', 'Build', 'Builds', 'Deploy', 'Release', 'Launch',
                    'Event', 'Events', 'Session', 'Sessions', 'Message', 'Messages',
                    'Update', 'Updates', 'Change', 'Changes', 'Version', 'Versions',
                    'Data', 'Info', 'Information', 'Details', 'Summary', 'Overview',
                    'Hadron', 'Omi', 'Api', 'Sdk', 'Cli', 'Ui', 'Ux',
                    'Ref', 'Doc', 'Docs', 'Log', 'Logs', 'Debug', 'Error', 'Errors',
                    # More non-person words
                    'Wi', 'Fi', 'Wifi', 'Bluetooth', 'Usb', 'Nfc', 'Gps',
                    'Friends', 'Friend', 'Family', 'Mom', 'Dad', 'Brother', 'Sister',
                    'Fundraise', 'Fundraising', 'Funding', 'Investment', 'Investors',
                    'Frontier', 'Spark', 'Labs', 'Lab', 'Studio', 'Studios', 'Agency',
                    'Stanford', 'Harvard', 'Mit', 'Berkeley', 'Yale', 'Princeton',
                    'Van', 'Von', 'De', 'Le', 'Al', 'El',
                    'Don', 'Dont', 'Its', 'Were', 'Been', 'Being', 'Have', 'Has', 'Had',
                    'Got', 'Get', 'Gets', 'Let', 'Lets', 'Use', 'Uses', 'Used',
                    'Try', 'Tries', 'Tried', 'Make', 'Makes', 'Made', 'Take', 'Takes', 'Took',
                    'See', 'Sees', 'Saw', 'Know', 'Knows', 'Knew', 'Think', 'Thinks', 'Thought',
                    'Feel', 'Feels', 'Felt', 'Want', 'Wants', 'Wanted', 'Need', 'Needs', 'Needed',
                    'Say', 'Says', 'Said', 'Tell', 'Tells', 'Told', 'Ask', 'Asks', 'Asked',
                    'Give', 'Gives', 'Gave', 'Put', 'Puts', 'Keep', 'Keeps', 'Kept',
                    'Find', 'Finds', 'Found', 'Show', 'Shows', 'Showed', 'Add', 'Adds', 'Added',
                    'Run', 'Runs', 'Ran', 'Move', 'Moves', 'Moved', 'Play', 'Plays', 'Played',
                    'Live', 'Lives', 'Lived', 'Look', 'Seem', 'Seems', 'Seemed',
                    'Talk', 'Talks', 'Talked', 'Meet', 'Meets', 'Met',
                    # Time-related
                    'Hour', 'Hours', 'Minute', 'Minutes', 'Second', 'Seconds',
                    'Day', 'Days', 'Ago', 'End', 'Start', 'Started', 'Ended',
                    # Numbers written out
                    'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
                    'Hundred', 'Thousand', 'Million', 'Billion',
                    # More common nouns/verbs that get capitalized
                    'Bowl', 'Fellowship', 'Aid', 'Party', 'Create', 'Together', 'Faith', 'Virality',
                    'Procrastination', 'Assistant', 'Super', 'Mega', 'Ultra', 'Pro', 'Max', 'Mini',
                    'Recording', 'Transcript', 'Segment', 'Segments', 'File', 'Files', 'Folder',
                    'Talk', 'Talks', 'Speech', 'Speeches', 'Voice', 'Voices', 'Sound', 'Sounds',
                    'Word', 'Words', 'Letter', 'Letters', 'Sentence', 'Sentences', 'Paragraph',
                    'Image', 'Images', 'Photo', 'Photos', 'Picture', 'Pictures', 'Video', 'Videos',
                    'Music', 'Song', 'Songs', 'Movie', 'Movies', 'Film', 'Films', 'Show', 'Shows',
                    'Book', 'Books', 'Article', 'Articles', 'Post', 'Posts', 'Blog', 'Blogs',
                    'Story', 'Stories', 'News', 'Report', 'Reports', 'Paper', 'Papers',
                    'List', 'Lists', 'Item', 'Items', 'Task', 'Tasks', 'Goal', 'Goals',
                    'Idea', 'Ideas', 'Thought', 'Thoughts', 'Mind', 'Brain', 'Head',
                    'Body', 'Heart', 'Hand', 'Hands', 'Eye', 'Eyes', 'Ear', 'Ears',
                    'Room', 'Rooms', 'House', 'Houses', 'Home', 'Homes', 'Office', 'Offices',
                    'Car', 'Cars', 'Bus', 'Buses', 'Train', 'Trains', 'Plane', 'Planes',
                    'Food', 'Foods', 'Water', 'Coffee', 'Tea', 'Wine', 'Beer', 'Drink', 'Drinks',
                    'Money', 'Cash', 'Dollar', 'Dollars', 'Price', 'Prices', 'Cost', 'Costs',
                    'Job', 'Jobs', 'Career', 'Careers', 'Role', 'Roles', 'Position', 'Positions',
                    'Level', 'Levels', 'Grade', 'Grades', 'Score', 'Scores', 'Point', 'Points',
                    'Game', 'Games', 'Sport', 'Sports', 'Match', 'Matches', 'Race', 'Races',
                    'Trip', 'Trips', 'Travel', 'Travels', 'Tour', 'Tours', 'Visit', 'Visits',
                    'School', 'Schools', 'College', 'Colleges', 'University', 'Universities',
                    'Class', 'Classes', 'Course', 'Courses', 'Lesson', 'Lessons', 'Study', 'Studies',
                    'Research', 'Science', 'Math', 'History', 'Art', 'Arts', 'Design', 'Designs',
                    'Code', 'Codes', 'Program', 'Programs', 'Script', 'Scripts', 'Function', 'Functions',
                    'Model', 'Models', 'Framework', 'Frameworks', 'Library', 'Libraries', 'Tool', 'Tools',
                    'Set', 'Sets', 'Group', 'Groups', 'Type', 'Types', 'Kind', 'Kinds', 'Sort', 'Sorts',
                    'Part', 'Parts', 'Piece', 'Pieces', 'Bit', 'Bits', 'Side', 'Sides', 'Half', 'Halves',
                    'Top', 'Bottom', 'Front', 'Back', 'Left', 'Right', 'Middle', 'Center',
                    'High', 'Low', 'Long', 'Short', 'Big', 'Small', 'Large', 'Tiny', 'Huge',
                    'Fast', 'Slow', 'Quick', 'Easy', 'Hard', 'Simple', 'Complex', 'Basic', 'Advanced',
                    'True', 'False', 'Real', 'Fake', 'Full', 'Empty', 'Open', 'Close', 'Closed',
                    'Free', 'Paid', 'Public', 'Private', 'Local', 'Global', 'Internal', 'External',
                    'Main', 'Core', 'Key', 'Keys', 'Primary', 'Secondary', 'Special', 'Normal',
                    'Current', 'Previous', 'Future', 'Past', 'Present', 'Recent', 'Latest', 'Oldest',
                    'Only', 'Even', 'Still', 'Already', 'Yet', 'Soon', 'Always', 'Never', 'Often',
                    'App', 'Web', 'Site', 'Page', 'Pages', 'Link', 'Links', 'Tab', 'Tabs',
                    'Menu', 'Menus', 'Icon', 'Icons', 'Logo', 'Logos', 'Brand', 'Brands',
                    'Fun', 'Cool', 'Great', 'Amazing', 'Awesome', 'Nice', 'Fine', 'Okay',
                    'Perfect', 'Excellent', 'Wonderful', 'Beautiful', 'Pretty', 'Cute', 'Sweet',
                    # More company/product/brand names
                    'Paradromics', 'Snapchat', 'Tiktok', 'Instagram', 'Youtube', 'Reddit', 'Linkedin',
                    'Whatsapp', 'Messenger', 'Signal', 'Wechat', 'Line', 'Skype', 'Teams',
                    'Netflix', 'Hulu', 'Disney', 'Spotify', 'Pandora', 'Soundcloud',
                    'Pinterest', 'Tumblr', 'Quora', 'Medium', 'Substack', 'Patreon',
                    # More common nouns
                    'Corp', 'Corporation', 'Park', 'Parks', 'Media', 'Ive', 'Clue', 'Upcoming',
                    'Sale', 'Sales', 'Choices', 'Choice', 'Quiet', 'Teammates', 'Teammate',
                    'Bank', 'Banks', 'Insurance', 'Finance', 'Trading', 'Crypto', 'Bitcoin',
                    'Camera', 'Cameras', 'Lens', 'Lenses', 'Battery', 'Batteries', 'Charger',
                    'Keyboard', 'Mouse', 'Monitor', 'Laptop', 'Desktop', 'Tablet', 'Smartphone',
                    'Light', 'Lights', 'Dark', 'Bright', 'Dim', 'Color', 'Colors', 'Colour',
                    'Hot', 'Cold', 'Warm', 'Cool', 'Fresh', 'Clean', 'Dirty', 'Clear', 'Cloudy',
                    'Crazy', 'Weird', 'Strange', 'Normal', 'Regular', 'Special', 'Extra', 'Standard',
                    'Powerful', 'Weak', 'Strong', 'Soft', 'Hard', 'Smooth', 'Rough', 'Sharp', 'Dull',
                    'Happy', 'Sad', 'Angry', 'Scared', 'Excited', 'Tired', 'Bored', 'Confused',
                    'Certain', 'Sure', 'Unsure', 'Confident', 'Nervous', 'Calm', 'Stressed',
                    'Busy', 'Idle', 'Active', 'Passive', 'Ready', 'Waiting', 'Pending', 'Done',
                    'Anyway', 'Somehow', 'Somewhat', 'Sometimes', 'Everywhere', 'Nowhere', 'Anywhere',
                    'Basically', 'Literally', 'Honestly', 'Seriously', 'Obviously', 'Apparently',
                    'Generally', 'Specifically', 'Exactly', 'Roughly', 'Approximately', 'Almost',
                    'Probably', 'Possibly', 'Certainly', 'Definitely', 'Surely', 'Clearly',
                    'Usually', 'Typically', 'Normally', 'Regularly', 'Frequently', 'Rarely',
                    'Currently', 'Previously', 'Recently', 'Eventually', 'Finally', 'Initially',
                    # Verbs that get capitalized
                    'Watching', 'Listening', 'Reading', 'Writing', 'Speaking', 'Talking', 'Walking',
                    'Running', 'Driving', 'Flying', 'Swimming', 'Playing', 'Working', 'Sleeping',
                    'Eating', 'Drinking', 'Cooking', 'Shopping', 'Traveling', 'Learning', 'Teaching',
                    'Building', 'Creating', 'Making', 'Doing', 'Being', 'Having', 'Getting',
                    'Coming', 'Going', 'Leaving', 'Staying', 'Moving', 'Changing', 'Growing',
                    'Starting', 'Ending', 'Beginning', 'Finishing', 'Continuing', 'Stopping',
                    'Opening', 'Closing', 'Turning', 'Showing', 'Hiding', 'Finding', 'Losing',
                    'Winning', 'Losing', 'Trying', 'Failing', 'Succeeding', 'Helping', 'Hurting',
                    # Place names
                    'Jersey', 'Bristol', 'Navajo', 'Avenue', 'Boulevard', 'Highway', 'Road',
                    'Mall', 'Plaza', 'Square', 'Center', 'Tower', 'Building', 'Bridge',
                    # More common words
                    'Pass', 'Avenir', 'Wick', 'Hobbies', 'Hobby', 'Hiring', 'Express',
                    'Offer', 'Offers', 'Deal', 'Deals', 'Discount', 'Discounts', 'Promo',
                    'Membership', 'Subscription', 'Plan', 'Plans', 'Tier', 'Tiers',
                    'Early', 'Late', 'Morning', 'Evening', 'Afternoon', 'Night', 'Midnight',
                    'Intro', 'Outro', 'Summary', 'Recap', 'Review', 'Preview', 'Overview',
                    'Setup', 'Config', 'Settings', 'Options', 'Preferences', 'Profile',
                    'Account', 'Accounts', 'Login', 'Logout', 'Signin', 'Signup', 'Register',
                    'Password', 'Username', 'Email', 'Phone', 'Address', 'Location',
                    'Notification', 'Notifications', 'Alert', 'Alerts', 'Warning', 'Warnings',
                    'Status', 'Progress', 'Loading', 'Pending', 'Complete', 'Completed',
                    'Success', 'Failure', 'Error', 'Errors', 'Bug', 'Bugs', 'Issue', 'Issues',
                    # Even more common words found in output
                    'Swap', 'Mission', 'Vegas', 'Equity', 'Lodge', 'Discussion', 'Twin', 'Brief',
                    'Others', 'Catch', 'Emergency', 'Alto', 'View', 'Views', 'Tech', 'Casual',
                    'Watch', 'Pitches', 'Pitch', 'Equinox', 'Plot', 'Plots', 'Multiple', 'With',
                    'Joke', 'Jokes', 'Personal', 'Airtable', 'Departure', 'Discusses', 'Knowledge',
                    'Discuss', 'Space', 'Spaces', 'Store', 'Stores', 'Comedy', 'They', 'Hunt',
                    'Limitless', 'Passengers', 'Peaks', 'Peak', 'Storage', 'Toward', 'Towards',
                    'Life', 'Fish', 'Gym', 'Gyms', 'Marketing', 'Partnership', 'Partnerships',
                    'Flutter', 'Planning', 'Near', 'States', 'State', 'Daily', 'Debates', 'Dating',
                    'Coordinate', 'Coordinates', 'Ambassador', 'Ambassadors', 'Ventures', 'Venture',
                    'Out', 'Sleep', 'Overall', 'React', 'Granola', 'Creator', 'Creators', 'Clarifying',
                    'Network', 'Networks', 'Advice', 'Contact', 'Contacts', 'Debate', 'Zero',
                    'Their', 'Share', 'Shares', 'Relationships', 'Relationship', 'Speakers',
                    'Demo', 'Demos', 'Workspace', 'Workspaces', 'Debugging', 'Highlight', 'Highlights',
                    'Tactics', 'Air', 'Academy', 'Debating', 'Devices', 'Chats', 'Dinner', 'Dinners',
                    'Haircut', 'General', 'Strategy', 'Strategies', 'Discussing', 'Ads', 'Rent',
                    'Lounge', 'Lounges', 'Payment', 'Payments', 'Podcasts', 'Series', 'Pay',
                    'Crowd', 'Crowds', 'Date', 'Dates', 'Celebration', 'Celebrations', 'Human', 'Humans',
                    'Southern', 'Northern', 'Eastern', 'Western', 'Central', 'United', 'International',
                    'Kazakh', 'Brazilian', 'Canadian', 'Fluticasone', 'Mercury', 'Santa', 'Zootopia',
                    'Ritz', 'Carlton', 'Haven', 'Ashby', 'Luma', 'Hipsy', 'Tron', 'Visa', 'Dev',
                    'Nano', 'About', 'Fifth', 'Basel', 'Shenzhen', 'Vancouver', 'Minnesota', 'Oregon',
                    'Britain', 'California', 'Pakistan', 'Shanghai', 'Brooklyn', 'Christmas', 'Sakhalin',
                    'Calhacks', 'Kickstarter', 'Tesla', 'Ness', 'East', 'West', 'South', 'North',
                    # Final cleanup
                    'Refines', 'Refine', 'Vietnam', 'English', 'Aurora', 'Palo',
                    # More words found in output
                    'Smart', 'Confusion', 'Specific', 'Projects', 'Custom', 'Strategic',
                    'Productivity', 'Starbucks', 'Entrepreneur', 'Discussions', 'Introduction',
                    'Amid', 'Seeking', 'Terms', 'Trends', 'Routine', 'Challenge', 'Challenges',
                    'Insights', 'Insight', 'Potential', 'Impact', 'Key', 'Keys', 'Point', 'Points',
                    'Topic', 'Topics', 'Theme', 'Themes', 'Aspect', 'Aspects', 'Factor', 'Factors',
                    'Element', 'Elements', 'Component', 'Components', 'Section', 'Sections',
                    'Chapter', 'Chapters', 'Episode', 'Episodes', 'Scene', 'Scenes',
                    'Moment', 'Moments', 'Period', 'Periods', 'Phase', 'Phases', 'Stage', 'Stages',
                    'Round', 'Rounds', 'Turn', 'Turns', 'Step', 'Steps', 'Move', 'Moves',
                    'Attempt', 'Attempts', 'Effort', 'Efforts', 'Progress', 'Result', 'Results',
                    'Outcome', 'Outcomes', 'Effect', 'Effects', 'Consequence', 'Consequences',
                    'Benefit', 'Benefits', 'Advantage', 'Advantages', 'Opportunity', 'Opportunities',
                    'Option', 'Options', 'Alternative', 'Alternatives', 'Approach', 'Approaches',
                    'Method', 'Methods', 'Technique', 'Techniques', 'Practice', 'Practices',
                    'Principle', 'Principles', 'Concept', 'Concepts', 'Theory', 'Theories',
                    'Lesson', 'Lessons', 'Tip', 'Tips', 'Trick', 'Tricks', 'Secret', 'Secrets',
                    'Rule', 'Rules', 'Law', 'Laws', 'Regulation', 'Regulations', 'Policy', 'Policies',
                    'Standard', 'Standards', 'Requirement', 'Requirements', 'Specification', 'Specifications',
                    'Criteria', 'Criterion', 'Condition', 'Conditions', 'Situation', 'Situations',
                    'Circumstance', 'Circumstances', 'Context', 'Contexts', 'Background', 'Backgrounds',
                    'History', 'Histories', 'Origin', 'Origins', 'Source', 'Sources', 'Root', 'Roots',
                    'Cause', 'Causes', 'Reason', 'Reasons', 'Purpose', 'Purposes', 'Intention', 'Intentions',
                    'Objective', 'Objectives', 'Target', 'Targets', 'Aim', 'Aims',
                    'Priority', 'Priorities', 'Focus', 'Focuses', 'Emphasis', 'Attention',
                    'Concern', 'Concerns', 'Interest', 'Interests', 'Preference', 'Preferences',
                    'Opinion', 'Opinions', 'Perspective', 'Perspectives', 'Viewpoint', 'Viewpoints',
                    'Stance', 'Stances', 'Position', 'Positions', 'Attitude', 'Attitudes',
                    'Belief', 'Beliefs', 'Value', 'Values', 'Ideal', 'Ideals', 'Vision', 'Visions',
                    'Dream', 'Dreams', 'Hope', 'Hopes', 'Wish', 'Wishes', 'Desire', 'Desires',
                    'Need', 'Needs', 'Want', 'Wants', 'Demand', 'Demands', 'Request', 'Requests',
                    'Suggestion', 'Suggestions', 'Recommendation', 'Recommendations', 'Proposal', 'Proposals',
                    'Offer', 'Offers', 'Invitation', 'Invitations', 'Call', 'Calls', 'Appeal', 'Appeals',
                    'Claim', 'Claims', 'Statement', 'Statements', 'Declaration', 'Declarations',
                    'Announcement', 'Announcements', 'Notice', 'Notices', 'Reminder', 'Reminders',
                    'Update', 'Updates', 'Revision', 'Revisions', 'Amendment', 'Amendments',
                    'Modification', 'Modifications', 'Adjustment', 'Adjustments', 'Correction', 'Corrections',
                    'Improvement', 'Improvements', 'Enhancement', 'Enhancements', 'Upgrade', 'Upgrades',
                    'Addition', 'Additions', 'Expansion', 'Expansions', 'Extension', 'Extensions',
                    'Integration', 'Integrations', 'Implementation', 'Implementations', 'Execution', 'Executions',
                    'Operation', 'Operations', 'Function', 'Functions', 'Activity', 'Activities',
                    'Transaction', 'Transactions', 'Interaction', 'Interactions', 'Communication', 'Communications',
                    'Connection', 'Connections', 'Relation', 'Relations', 'Association', 'Associations',
                    'Collaboration', 'Collaborations', 'Cooperation', 'Cooperations', 'Partnership', 'Partnerships',
                    'Alliance', 'Alliances', 'Coalition', 'Coalitions', 'Union', 'Unions',
                    'Organization', 'Organizations', 'Institution', 'Institutions', 'Agency', 'Agencies',
                    'Department', 'Departments', 'Division', 'Divisions', 'Branch', 'Branches',
                    'Unit', 'Units', 'Team', 'Teams', 'Group', 'Groups', 'Committee', 'Committees',
                    'Board', 'Boards', 'Council', 'Councils', 'Panel', 'Panels', 'Commission', 'Commissions',
                    # Conversational words (found in transcripts)
                    'Wait', 'Alright', 'Kinda', 'Gotta', 'Using', 'Gonna', 'Wanna', 'Lemme', 'Gimme',
                    'Addresses', 'Dreamforce', 'Draw', 'Draws', 'Shipping', 'Necklace', 'Enterprise',
                    'Download', 'Downloads', 'Holy', 'Brilliant', 'Write', 'Writes', 'Wrote',
                    'Essentially', 'Glad', 'Legal', 'Consumer', 'Consumers', 'Safety', 'Pricing',
                    'Completely', 'Sounds', 'Feels', 'Seems', 'Looks', 'Works', 'Means', 'Says',
                    'Thinks', 'Knows', 'Goes', 'Comes', 'Takes', 'Makes', 'Gets', 'Puts', 'Gives',
                    'Tells', 'Asks', 'Helps', 'Shows', 'Starts', 'Stops', 'Keeps', 'Lets',
                    'Probably', 'Maybe', 'Actually', 'Really', 'Basically', 'Literally', 'Seriously',
                    'Honestly', 'Definitely', 'Absolutely', 'Exactly', 'Totally', 'Completely', 'Entirely',
                    'Apparently', 'Obviously', 'Clearly', 'Simply', 'Basically', 'Essentially', 'Fundamentally',
                    'Yeah', 'Yep', 'Yup', 'Nope', 'Nah', 'Uh', 'Um', 'Uhm', 'Hmm', 'Huh', 'Wow',
                    'Ohh', 'Ahh', 'Ooh', 'Aah', 'Whoa', 'Woah', 'Geez', 'Gosh', 'Dang', 'Darn',
                    'Haha', 'Lol', 'Lmao', 'Omg', 'Omfg', 'Wtf', 'Btw', 'Idk', 'Imo', 'Tbh', 'Ngl',
                    'Through', 'Though', 'Although', 'However', 'Therefore', 'Otherwise', 'Meanwhile',
                    'Anyway', 'Anyways', 'Anywhere', 'Anytime', 'Anyone', 'Anything', 'Anybody',
                    'Somewhere', 'Sometime', 'Someone', 'Something', 'Somebody',
                    'Everywhere', 'Everyone', 'Everything', 'Everybody', 'Whatever', 'Wherever', 'Whenever',
                    'Whoever', 'Whichever', 'Whatsoever', 'Nonetheless', 'Nevertheless', 'Furthermore',
                    'Moreover', 'Besides', 'Instead', 'Rather', 'Either', 'Neither', 'Whether',
                    'Perhaps', 'Possibly', 'Certainly', 'Surely', 'Simply', 'Merely', 'Hardly', 'Barely',
                    'Almost', 'Nearly', 'Quite', 'Rather', 'Fairly', 'Pretty', 'Very', 'Extremely',
                    'Incredibly', 'Amazingly', 'Surprisingly', 'Shockingly', 'Interestingly',
                    'Fortunately', 'Unfortunately', 'Hopefully', 'Thankfully', 'Luckily',
                    'Especially', 'Particularly', 'Specifically', 'Generally', 'Usually', 'Typically',
                    'Normally', 'Commonly', 'Frequently', 'Regularly', 'Occasionally', 'Rarely', 'Seldom',
                    'Sometimes', 'Often', 'Always', 'Never', 'Ever', 'Still', 'Yet', 'Already',
                    'Just', 'Only', 'Even', 'Also', 'Too', 'Either', 'Neither', 'Both', 'Each',
                    'Every', 'Any', 'Some', 'Few', 'Many', 'Much', 'Most', 'All', 'None', 'Several',
                    'Certain', 'Other', 'Another', 'Such', 'Same', 'Different', 'Various', 'Numerous',
                    'Countless', 'Endless', 'Limitless', 'Boundless', 'Infinite', 'Numerous',
                    # More common words found
                    'Mine', 'Yours', 'Ours', 'Theirs', 'His', 'Hers', 'Its', 'Whose',
                    'Than', 'Then', 'Thus', 'Hence', 'Since', 'Until', 'Unless', 'While',
                    'Hackathon', 'Hackathons', 'Access', 'Dynamics', 'Creation', 'Outside',
                    'Reach', 'Interface', 'Assembly', 'Ban', 'Bans', 'Market', 'Markets',
                    'Fucking', 'Shit', 'Damn', 'Hell', 'Crap', 'Bullshit', 'Asshole',
                    'Called', 'Built', 'Living', 'Print', 'Prints', 'Printed',
                    'Fox', 'Toptel', 'Buying', 'Selling', 'Trading', 'Shipping', 'Receiving', 'Sending',
                    'Watching', 'Listening', 'Reading', 'Writing', 'Speaking', 'Talking',
                    'Running', 'Walking', 'Driving', 'Flying', 'Swimming', 'Climbing',
                    'Eating', 'Drinking', 'Sleeping', 'Working', 'Playing', 'Studying',
                    'Following', 'Leading', 'Joining', 'Leaving', 'Staying', 'Moving',
                    'Helping', 'Hurting', 'Loving', 'Hating', 'Liking', 'Wanting', 'Needing',
                    'Knowing', 'Thinking', 'Feeling', 'Seeing', 'Hearing', 'Touching',
                    'Saying', 'Telling', 'Asking', 'Answering', 'Explaining', 'Describing',
                    'Showing', 'Hiding', 'Finding', 'Losing', 'Winning', 'Trying', 'Failing',
                    'Succeeding', 'Achieving', 'Reaching', 'Growing', 'Shrinking', 'Expanding',
                    'Changing', 'Remaining', 'Becoming', 'Being', 'Having', 'Doing', 'Making',
                    'Getting', 'Going', 'Coming', 'Leaving', 'Arriving', 'Departing',
                    'Starting', 'Beginning', 'Ending', 'Finishing', 'Completing', 'Stopping',
                    'Continuing', 'Resuming', 'Pausing', 'Waiting', 'Expecting', 'Hoping',
                    # More from latest output
                    'Onboarding', 'Field', 'Fields', 'Sugar', 'Gaming', 'Cursor', 'Doesn',
                    'She', 'Sir', 'Rocket', 'Walk', 'Walks', 'Cheers', 'Medical', 'Virtual',
                    'Production', 'Improving', 'Improvement', 'Talking', 'Recording',
                    'Episode', 'Episodes', 'Podcast', 'Podcasts', 'Video', 'Videos',
                    'Audio', 'Sound', 'Sounds', 'Voice', 'Voices', 'Speech', 'Speeches',
                    'Memory', 'Memories', 'Thought', 'Thoughts', 'Idea', 'Ideas',
                    'Mind', 'Brain', 'Head', 'Heart', 'Soul', 'Spirit', 'Body',
                    'World', 'Earth', 'Planet', 'Universe', 'Space', 'Sky', 'Sea', 'Ocean',
                    'Mountain', 'River', 'Lake', 'Forest', 'Desert', 'Island', 'Country',
                    'Nation', 'State', 'City', 'Town', 'Village', 'Street', 'Road', 'Path',
                    # More common words
                    'Come', 'Comes', 'Coming', 'Came', 'Broad', 'Star', 'Stars', 'From',
                    'Sell', 'Sells', 'Selling', 'Sold', 'Connect', 'Connects', 'Connected',
                    'Compared', 'Compare', 'Compares', 'Speedrun', 'Far', 'Near', 'Close',
                    'Wasn', 'Weren', 'Isn', 'Aren', 'Doesn', 'Don', 'Won', 'Can',
                    'Management', 'Manager', 'Managers', 'Prepares', 'Prepare', 'Prepared',
                    'Soma', 'Professional', 'Professionals', 'Expert', 'Experts',
                    'Founder', 'Founders', 'Investor', 'Investors', 'Engineer', 'Engineers',
                    'Designer', 'Designers', 'Developer', 'Developers', 'Analyst', 'Analysts',
                    'Director', 'Directors', 'Executive', 'Executives', 'Officer', 'Officers',
                    'President', 'Vice', 'Chief', 'Head', 'Lead', 'Senior', 'Junior',
                    'Assistant', 'Associate', 'Intern', 'Interns', 'Employee', 'Employees',
                    'Staff', 'Worker', 'Workers', 'Member', 'Members', 'Partner', 'Partners',
                    # More non-names
                    'Compensation', 'Sheet', 'Sheets', 'Similar', 'Despite', 'Per', 'Arab',
                    'Teach', 'Teaching', 'Copy', 'Copies', 'Essentials', 'Grind', 'Editing',
                    'Cut', 'Cuts', 'Paste', 'Pastes', 'Delete', 'Deletes', 'Save', 'Saves',
                    'Load', 'Loads', 'Send', 'Sends', 'Receive', 'Receives', 'Return', 'Returns',
                    'Enter', 'Enters', 'Exit', 'Exits', 'Leave', 'Leaves', 'Join', 'Joins',
                    'Sign', 'Signs', 'Signed', 'Login', 'Logout', 'Submit', 'Submits',
                    'Accept', 'Accepts', 'Reject', 'Rejects', 'Approve', 'Approves',
                    'Cancel', 'Cancels', 'Confirm', 'Confirms', 'Verify', 'Verifies',
                    'Check', 'Checks', 'Test', 'Tests', 'Review', 'Reviews', 'Rate', 'Rates',
                    'Vote', 'Votes', 'Pick', 'Picks', 'Choose', 'Chooses', 'Select', 'Selects',
                    'Switch', 'Switches', 'Toggle', 'Toggles', 'Flip', 'Flips', 'Turn', 'Turns',
                    'Push', 'Pushes', 'Pull', 'Pulls', 'Drag', 'Drags', 'Drop', 'Drops',
                    'Click', 'Clicks', 'Tap', 'Taps', 'Swipe', 'Swipes', 'Scroll', 'Scrolls',
                    'Zoom', 'Zooms', 'Pinch', 'Pinches', 'Rotate', 'Rotates', 'Shake', 'Shakes',
                    'Launched', 'Released', 'Published', 'Posted', 'Shared', 'Uploaded',
                    'Downloaded', 'Installed', 'Updated', 'Upgraded', 'Fixed', 'Solved',
                    'Resolved', 'Completed', 'Finished', 'Ended', 'Closed', 'Archived',
                    # Even more common words
                    'Wrong', 'Which', 'Without', 'Straight', 'Quest', 'Quests', 'Stay',
                    'Toptal', 'Selection', 'Engineering', 'Listen', 'Listens', 'Bam',
                    'Companies', 'Company', 'Explore', 'Explores', 'Exploring',
                    'Where', 'What', 'When', 'Why', 'Who', 'Whom', 'Whose', 'How',
                    'Under', 'Over', 'Above', 'Below', 'Between', 'Among', 'Within',
                    'Against', 'Toward', 'Towards', 'Into', 'Onto', 'Upon', 'Along',
                    'Across', 'Around', 'Behind', 'Beyond', 'Inside', 'Outside',
                    'Throughout', 'During', 'Before', 'After', 'Since', 'Until',
                    'Behind', 'Beside', 'Besides', 'Except', 'Despite', 'Unlike', 'Regarding',
                    # Final batch
                    'Experiences', 'Third', 'Did', 'Couldn', 'Lost', 'Roll', 'Rolls',
                    'Christ', 'Ram', 'Turbo', 'Notes', 'Note', 'Xiaomi', 'Huawei', 'Samsung',
                    'Sony', 'Lenovo', 'Dell', 'Asus', 'Acer', 'Hp', 'Ibm', 'Intel', 'Amd',
                    'Nvidia', 'Qualcomm', 'Arm', 'Cisco', 'Oracle', 'Sap', 'Adobe', 'Vmware',
                    'Second', 'Fourth', 'Fifth', 'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth',
                    'Double', 'Triple', 'Quadruple', 'Single', 'Multiple', 'Several', 'Various',
                    'Whole', 'Entire', 'Complete', 'Total', 'Overall', 'Average', 'Typical',
                    'Generated', 'Generates', 'Generate', 'Automated', 'Automate', 'Automates',
                    'Forbes', 'Fortune', 'Times', 'Post', 'Journal', 'News', 'Daily', 'Finalizes',
                    'Finalize', 'Finalized', 'Apart', 'Separate', 'Separated', 'Separates',
                    # More non-names from latest output
                    'Meetings', 'Weekly', 'Sparks', 'Immigration', 'Approval', 'Thousands',
                    'Mentioned', 'Mentions', 'Mention', 'Billion', 'Millions', 'Hundreds',
                    'Briefly', 'Specifically', 'Primarily', 'Particularly', 'Generally',
                    'Minutes', 'Seconds', 'Hours', 'Weeks', 'Months', 'Years', 'Decades',
                    'Briefly', 'Quickly', 'Slowly', 'Carefully', 'Correctly', 'Properly',
                    'Positively', 'Negatively', 'Successfully', 'Effectively', 'Efficiently',
                    'Approval', 'Approvals', 'Rejection', 'Rejections', 'Permission', 'Permissions',
                    'Schedule', 'Schedules', 'Scheduling', 'Calendar', 'Calendars', 'Agenda',
                    'Budget', 'Budgets', 'Revenue', 'Revenues', 'Profit', 'Profits', 'Loss', 'Losses',
                    'Expense', 'Expenses', 'Income', 'Incomes', 'Salary', 'Salaries', 'Wage', 'Wages',
                    'Sparks', 'Spark', 'Ignite', 'Ignites', 'Trigger', 'Triggers', 'Cause', 'Causes',
                    'Immigration', 'Immigrant', 'Immigrants', 'Migration', 'Migrate', 'Migrates',
                    'Thousands', 'Thousand', 'Hundreds', 'Hundred', 'Dozens', 'Dozen',
                    'Weekly', 'Monthly', 'Yearly', 'Daily', 'Hourly', 'Quarterly', 'Annual',
                    'Internship', 'Internships', 'Residency', 'Fellowship', 'Fellowships',
                    'Referral', 'Referrals', 'Reference', 'References', 'Recommendation',
                    'Regarding', 'Concerning', 'Relating', 'Pertaining', 'Involving',
                    'Further', 'Closer', 'Deeper', 'Higher', 'Lower', 'Better', 'Worse',
                    'Bigger', 'Smaller', 'Larger', 'Tinier', 'Wider', 'Narrower', 'Longer', 'Shorter',
                    'Faster', 'Slower', 'Stronger', 'Weaker', 'Harder', 'Easier', 'Simpler', 'Complexer',
                    'Retired', 'Originally', 'Cleaning', 'Arc', 'Obi', 'Originally', 'Basically',
                    'Essentially', 'Literally', 'Apparently', 'Obviously', 'Clearly', 'Simply',
                    'Properly', 'Correctly', 'Possibly', 'Probably', 'Certainly', 'Definitely',
                    'Actually', 'Really', 'Truly', 'Fully', 'Completely', 'Entirely', 'Totally',
                    'Precisely', 'Exactly', 'Approximately', 'Roughly', 'Nearly', 'Almost',
                    'Cleaned', 'Cleaning', 'Cleans', 'Clean', 'Retired', 'Retiring', 'Retires',
                    'Original', 'Originally', 'Originals', 'Arc', 'Arcs', 'Obi', 'Via', 'Per',
                    'Etc', 'Vs', 'Via', 'Aka', 'Ie', 'Eg', 'Re', 'Fyi', 'Asap', 'Eta', 'Rsvp'}
    
    # Find capitalized words (3-12 chars - most names are in this range)
    words = re.findall(r'\b([A-Z][a-z]{2,11})\b', text)
    for word in words:
        if word not in common_words and 3 <= len(word) <= 12:
            names.add(word)
    
    return list(names)


def extract_people_from_content(memories: List[dict], conversations: List[dict], user_variations: set = None) -> Dict[str, dict]:
    """Extract all unique people names from memories and conversations."""
    from datetime import datetime, timedelta
    
    people_dict = {}
    user_variations = user_variations or set()
    
    # Only include data from last 3 months
    three_months_ago = datetime.now() - timedelta(days=90)
    
    def is_recent(item):
        """Check if item is from the last 3 months."""
        created = item.get("created_at") or item.get("started_at") or item.get("timestamp")
        if not created:
            return False  # EXCLUDE if no date - be strict
        try:
            if isinstance(created, str):
                # Parse ISO format - handle various formats
                clean = created.replace('Z', '').replace('+00:00', '').split('.')[0]
                created_dt = datetime.fromisoformat(clean)
            elif isinstance(created, (int, float)):
                created_dt = datetime.fromtimestamp(created)
            else:
                return False
            return created_dt >= three_months_ago
        except Exception as e:
            logger.debug(f"Date parse error: {e} for {created}")
            return False  # EXCLUDE if parsing fails - be strict
    
    # Filter to recent items
    recent_memories = [m for m in memories if is_recent(m)]
    recent_conversations = [c for c in conversations if is_recent(c)]
    
    logger.info(f"Filtered to {len(recent_memories)}/{len(memories)} recent memories, {len(recent_conversations)}/{len(conversations)} recent conversations (last 3 months)")
    
    # Extract from memories
    for memory in recent_memories:
        content = memory.get("content", "")
        names = extract_names_from_text(content)
        
        for name in names:
            name_lower = name.lower()
            if name_lower in user_variations:
                continue
            if name_lower not in people_dict:
                people_dict[name_lower] = {
                    "id": hashlib.md5(name_lower.encode()).hexdigest()[:16],
                    "name": name,
                    "mention_count": 0,
                    "context_snippets": []  # Store what's said about them
                }
            people_dict[name_lower]["mention_count"] += 1
            # Store context snippet (sentence containing the name)
            if len(people_dict[name_lower]["context_snippets"]) < 20:  # Limit to 20 snippets
                # Find sentences containing name
                sentences = content.replace('\n', '. ').split('.')
                for sent in sentences:
                    if name in sent and len(sent.strip()) > 10 and len(sent) < 500:
                        snippet = sent.strip()[:300]
                        if snippet not in people_dict[name_lower]["context_snippets"]:
                            people_dict[name_lower]["context_snippets"].append(snippet)
    
    # Extract from conversations
    for conv in recent_conversations:
        conv_names = set()
        
        structured = conv.get("structured", {})
        overview = structured.get("overview", "")
        title = structured.get("title", "")
        
        for text in [overview, title]:
            names = extract_names_from_text(text)
            for name in names:
                name_lower = name.lower()
                if name_lower not in user_variations:
                    conv_names.add((name_lower, name))
        
        segments = conv.get("transcript_segments", [])
        for segment in segments:
            text = segment.get("text", "")
            names = extract_names_from_text(text)
            for name in names:
                name_lower = name.lower()
                if name_lower not in user_variations:
                    conv_names.add((name_lower, name))
        
        for name_lower, name in conv_names:
            if name_lower not in people_dict:
                people_dict[name_lower] = {
                    "id": hashlib.md5(name_lower.encode()).hexdigest()[:16],
                    "name": name,
                    "mention_count": 0,
                    "context_snippets": []
                }
            people_dict[name_lower]["mention_count"] += 1
            # Store overview as context
            if overview and name in overview and len(people_dict[name_lower]["context_snippets"]) < 10:
                people_dict[name_lower]["context_snippets"].append(overview[:200])
    
    # Filter: require at least 10 mentions for reliability
    filtered = {k: v for k, v in people_dict.items() if v["mention_count"] >= 10}
    
    logger.info(f"Extracted {len(filtered)} people from content (min 5 mentions)")
    return filtered


# ============== IQ CALCULATION ==============

def calculate_iq_with_ai(people_dict: dict) -> dict:
    """Use AI to analyze context and determine IQ scores for all people."""
    if not OPENAI_API_KEY:
        logger.warning("No OpenAI key - using random IQ scores")
        return {k: calculate_iq_score_random(v) for k, v in people_dict.items()}
    
    # Prepare batch for AI analysis
    people_to_analyze = []
    for name_lower, data in people_dict.items():
        context = " | ".join(data.get("context_snippets", [])[:10])  # More snippets
        if context:
            people_to_analyze.append({
                "name": data["name"],
                "name_lower": name_lower,
                "context": context[:800]  # More context
            })
    
    if not people_to_analyze:
        return {k: calculate_iq_score_random(v) for k, v in people_dict.items()}
    
    # Batch analyze with AI (process in chunks)
    iq_scores = {}
    batch_size = 20
    
    for i in range(0, len(people_to_analyze), batch_size):
        batch = people_to_analyze[i:i + batch_size]
        
        # Create prompt
        people_list = "\n".join([f"- {p['name']}: \"{p['context']}\"" for p in batch])
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": """You analyze how people are described in conversations and assign IQ scores.

SCORING RULES:
- GENIUS (140-160): Described as brilliant, genius, incredibly smart, expert, visionary
- SMART (120-139): Smart, intelligent, knowledgeable, good ideas, sharp, insightful  
- ABOVE AVG (110-119): Competent, helpful, knows their stuff
- AVERAGE (100-109): Neutral mentions, just mentioned by name, no intelligence indicators
- BELOW AVG (85-99): Confused, made mistakes, doesn't get it, needs help
- DUMB (70-84): Stupid, dumb, clueless, bad decisions, doesn't understand, frustrating to work with

IMPORTANT:
- Look for NEGATIVE indicators: "annoying", "doesn't understand", "keeps asking", "made a mistake", "wrong", "confused"
- Look for POSITIVE indicators: "smart", "genius", "brilliant", "figured it out", "great idea", "impressive"
- If just mentioned without context → 100 IQ (average)
- Determine if each entry is a REAL HUMAN FIRST NAME (not company/place/word)

Return JSON: [{"name": "Chris", "iq": 85, "is_name": true}, ...]"""
                        },
                        {
                            "role": "user",
                            "content": f"Analyze these people and assign IQ scores (70-160) based on how they're described:\n\n{people_list}"
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result["choices"][0]["message"]["content"].strip()
                
                # Parse JSON from response
                try:
                    # Find JSON array in response
                    import re
                    json_match = re.search(r'\[.*\]', answer, re.DOTALL)
                    if json_match:
                        scores = json.loads(json_match.group())
                        for score in scores:
                            name = score.get("name", "").lower()
                            iq = score.get("iq", 100)
                            is_name = score.get("is_name", True)
                            
                            # Find matching person
                            for p in batch:
                                if p["name"].lower() == name or p["name_lower"] == name:
                                    iq_scores[p["name_lower"]] = {
                                        "iq": max(70, min(160, int(iq))),
                                        "is_name": is_name
                                    }
                                    break
                except Exception as e:
                    logger.error(f"Error parsing AI response: {e}")
            else:
                logger.error(f"OpenAI API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}")
        
        # Small delay between batches
        time.sleep(0.5)
    
    # Fill in missing scores with random
    for name_lower, data in people_dict.items():
        if name_lower not in iq_scores:
            iq_scores[name_lower] = {
                "iq": calculate_iq_score_random(data),
                "is_name": True  # Assume it's a name if we couldn't verify
            }
    
    logger.info(f"AI analyzed {len(iq_scores)} people")
    return iq_scores


def calculate_iq_score_random(person: dict) -> int:
    """Fallback: Calculate random IQ score based on name hash."""
    person_id = person.get("id", "")
    seed = int(hashlib.md5(person_id.encode()).hexdigest()[:8], 16)
    random.seed(seed)
    
    base_iq = 100
    mention_count = person.get("mention_count", 0)
    mention_bonus = min(mention_count * 2, 30)
    random_factor = random.randint(-25, 25)
    
    iq = base_iq + mention_bonus + random_factor
    iq = max(70, min(160, int(iq)))
    
    return iq


def calculate_iq_score(person: dict) -> int:
    """Calculate IQ score for a person (legacy fallback)."""
    return calculate_iq_score_random(person)


def get_iq_category(iq: int) -> tuple:
    """Get category and emoji for IQ score."""
    if iq >= 140:
        return ("Genius", "🧠", "#22c55e")
    elif iq >= 120:
        return ("Very Superior", "✨", "#3b82f6")
    elif iq >= 110:
        return ("Superior", "⭐", "#60a5fa")
    elif iq >= 90:
        return ("Average", "👤", "#94a3b8")
    elif iq >= 80:
        return ("Below Average", "😐", "#f59e0b")
    else:
        return ("Low", "🤔", "#ef4444")


# ============== CACHE & LOADING ==============

def get_cached_people(uid: str) -> Optional[List[dict]]:
    """Get cached people data for a user."""
    if uid in _cache:
        return _cache[uid]
    return None


def set_cached_people(uid: str, people: List[dict]):
    """Cache people data for a user."""
    _cache[uid] = people
    logger.info(f"Cached {len(people)} people for uid {uid[:8]}...")


def is_loading(uid: str) -> bool:
    """Check if data is currently being loaded."""
    return uid in _cache_loading


def set_loading(uid: str, loading: bool):
    """Set loading state for a user."""
    if loading:
        _cache_loading.add(uid)
    else:
        _cache_loading.discard(uid)


def load_and_process_user_data(uid: str) -> List[dict]:
    """Load all data for a user, process it, and store permanently."""
    set_loading(uid, True)
    try:
        logger.info(f"Loading data for uid {uid[:8]}...")
        
        # Check if we have stored raw data
        if has_user_data(uid):
            logger.info("Using stored raw data from database")
            memories, conversations = get_raw_data(uid)
        else:
            # Fetch fresh data from API (only once!)
            logger.info("Fetching fresh data from OMI API...")
            memories = fetch_all_memories(uid)
            conversations = fetch_all_conversations(uid)
            
            # Store raw data permanently
            store_raw_data(uid, memories, conversations)
        
        logger.info(f"Got {len(memories)} memories and {len(conversations)} conversations")
        
        if not memories and not conversations:
            set_cached_people(uid, [])
            return []
        
        # Detect user's name to exclude
        user_variations = get_user_name_variations(memories, conversations)
        
        # Extract people (raw list)
        people_dict = extract_people_from_content(memories, conversations, user_variations)
        
        if not people_dict:
            set_cached_people(uid, [])
            return []
        
        # Use OpenAI to filter out non-names
        all_names = [data["name"] for data in people_dict.values()]
        valid_names = filter_names_with_openai(all_names)
        valid_names_lower = {n.lower() for n in valid_names}
        
        # Filter to only AI-validated names (if AI key present)
        if OPENAI_API_KEY and valid_names:
            filtered_people = {k: v for k, v in people_dict.items() if v["name"].lower() in valid_names_lower}
            logger.info(f"After AI filtering: {len(filtered_people)} people (from {len(people_dict)})")
        else:
            filtered_people = people_dict
        
        if not filtered_people:
            set_cached_people(uid, [])
            return []
        
        # Calculate IQ scores using AI (analyzes context about each person)
        logger.info(f"Analyzing {len(filtered_people)} people with AI...")
        iq_results = calculate_iq_with_ai(filtered_people)
        
        # Filter out non-names identified by AI
        people_with_iq = []
        for person_key, person_data in filtered_people.items():
            iq_data = iq_results.get(person_key, {"iq": 100, "is_name": True})
            
            # Skip if AI says it's not a name
            if not iq_data.get("is_name", True):
                logger.info(f"AI filtered out non-name: {person_data['name']}")
                continue
            
            iq = iq_data.get("iq", 100)
            category, emoji, color = get_iq_category(iq)
            
            people_with_iq.append({
                "id": person_data["id"],
                "name": person_data["name"],
                "iq": iq,
                "category": category,
                "category_emoji": emoji,
                "category_color": color,
                "memory_count": person_data["mention_count"]
            })
        
        # Sort by IQ
        people_with_iq.sort(key=lambda x: x["iq"], reverse=True)
        
        # Store in database permanently
        store_people(uid, people_with_iq)
        
        # Cache for quick access
        set_cached_people(uid, people_with_iq)
        
        return people_with_iq
    finally:
        set_loading(uid, False)


def get_people_for_user(uid: str) -> Optional[List[dict]]:
    """Get people for a user - from cache, DB, or trigger loading."""
    # Check memory cache first
    cached = get_cached_people(uid)
    if cached is not None:
        return cached
    
    # Check database
    if has_people_in_db(uid):
        people = get_people_from_db(uid, include_hidden=False)
        set_cached_people(uid, people)
        return people
    
    return None


# ============== HTML TEMPLATES ==============

IQ_RATING_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤡 Who's the Dumbest?</title>
    <meta property="og:title" content="Who's the Dumbest Person I've Met?">
    <meta property="og:description" content="I ranked everyone I know by IQ... you won't believe #1 😭">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #000;
            min-height: 100vh;
            padding: 16px;
            color: #fff;
        }}
        
        .container {{ max-width: 500px; margin: 0 auto; }}
        
        .header {{ text-align: center; margin-bottom: 24px; padding-top: 16px; }}
        .header h1 {{ 
            font-size: 28px; 
            font-weight: 700; 
            background: linear-gradient(135deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }}
        .header p {{ font-size: 14px; color: #888; }}
        
        .controls {{ display: flex; gap: 8px; margin-bottom: 20px; justify-content: center; }}
        
        .sort-btn {{
            padding: 10px 20px;
            border: none;
            background: #1a1a1a;
            border-radius: 20px;
            color: #888;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-family: inherit;
        }}
        
        .sort-btn:hover {{ background: #2a2a2a; color: #fff; }}
        .sort-btn.active {{ background: #ff4757; color: #fff; }}
        .sort-btn.active.smart {{ background: #2ed573; }}
        
        .people-list {{ display: flex; flex-direction: column; gap: 12px; }}
        
        .person-card {{
            background: #111;
            border-radius: 16px;
            padding: 16px 20px;
            border: 1px solid #222;
            transition: all 0.2s;
            position: relative;
            overflow: hidden;
        }}
        
        .person-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--card-color, #333);
        }}
        
        .person-card:hover {{ 
            transform: scale(1.02); 
            border-color: #333;
        }}
        
        .person-header {{ display: flex; align-items: center; justify-content: space-between; }}
        
        .person-rank {{
            font-size: 48px;
            font-weight: 700;
            color: #333;
            margin-right: 16px;
            min-width: 60px;
        }}
        
        .person-info {{ flex: 1; }}
        
        .person-name {{ 
            font-size: 20px; 
            font-weight: 700; 
            margin-bottom: 4px;
        }}
        
        .person-mentions {{
            font-size: 12px;
            color: #666;
        }}
        
        .person-iq {{ 
            font-size: 32px; 
            font-weight: 700; 
            color: var(--iq-color, #fff);
        }}
        
        .iq-label {{
            font-size: 10px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .hide-btn {{
            position: absolute;
            top: 8px;
            right: 8px;
            background: transparent;
            border: none;
            color: #444;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 10px;
            opacity: 0;
            transition: all 0.2s;
        }}
        
        .person-card:hover .hide-btn {{ opacity: 1; }}
        .hide-btn:hover {{ color: #ff4757; background: rgba(255,71,87,0.1); }}
        
        .iq-adjust {{
            display: flex;
            flex-direction: column;
            gap: 2px;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        
        .person-card:hover .iq-adjust {{ opacity: 1; }}
        
        .adj-btn {{
            background: #222;
            border: 1px solid #333;
            color: #888;
            width: 24px;
            height: 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.2s;
        }}
        
        .adj-btn:hover {{ background: #333; color: #fff; border-color: #444; }}
        
        /* Special styles for top 3 */
        .person-card.rank-1 {{ 
            background: linear-gradient(135deg, #1a0505 0%, #2d0a0a 100%);
            border-color: #ff4757;
        }}
        .person-card.rank-1::before {{ background: #ff4757; height: 4px; }}
        .person-card.rank-1 .person-rank {{ color: #ff4757; }}
        
        .person-card.rank-2 {{ 
            background: linear-gradient(135deg, #1a1005 0%, #2d1a0a 100%);
            border-color: #ffa502;
        }}
        .person-card.rank-2::before {{ background: #ffa502; }}
        .person-card.rank-2 .person-rank {{ color: #ffa502; }}
        
        .person-card.rank-3 {{ 
            background: linear-gradient(135deg, #0a1a1a 0%, #0f2d2d 100%);
            border-color: #2ed573;
        }}
        .person-card.rank-3::before {{ background: #2ed573; }}
        .person-card.rank-3 .person-rank {{ color: #2ed573; }}
        
        .empty-state {{
            text-align: center;
            padding: 60px 24px;
            background: #111;
            border-radius: 20px;
            border: 1px solid #222;
        }}
        
        .empty-state-icon {{ font-size: 64px; margin-bottom: 16px; }}
        .empty-state h2 {{ font-size: 20px; margin-bottom: 8px; }}
        .empty-state p {{ font-size: 14px; color: #666; }}
        
        .footer {{ 
            text-align: center; 
            margin-top: 32px; 
            padding: 20px;
            font-size: 12px; 
            color: #444;
        }}
        .footer a {{ color: #ff4757; text-decoration: none; }}
        
        .share-btn {{
            display: inline-block;
            padding: 12px 24px;
            background: linear-gradient(135deg, #ff4757, #ff6b81);
            color: #fff;
            border-radius: 25px;
            font-weight: 600;
            font-size: 14px;
            text-decoration: none;
            margin-top: 16px;
        }}
        
        @media (max-width: 640px) {{
            .person-rank {{ font-size: 36px; min-width: 50px; }}
            .person-name {{ font-size: 18px; }}
            .person-iq {{ font-size: 28px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤡 WHO'S THE DUMBEST?</h1>
            <p>I ranked everyone I know by IQ</p>
        </div>
        {content}
    </div>
</body>
</html>
"""

PEOPLE_LIST_CONTENT = """
<div class="controls">
    <button class="sort-btn active" onclick="sortBy('dumbest')" id="btn-dumbest">🤡 Dumbest</button>
    <button class="sort-btn smart" onclick="sortBy('smartest')" id="btn-smartest">🧠 Smartest</button>
</div>

<div class="people-list" id="people-list"></div>

<div class="footer">
    <p>Based on {total_people} people from your conversations</p>
    <a href="#" class="share-btn" onclick="shareResults()">📱 Share Results</a>
</div>

<script>
    const uid = '{uid}';
    let peopleData = {people_data_json};
    let currentSort = 'dumbest';
    
    function getIqColor(iq) {{
        if (iq >= 130) return '#2ed573';
        if (iq >= 110) return '#7bed9f';
        if (iq >= 90) return '#ffa502';
        if (iq >= 80) return '#ff6348';
        return '#ff4757';
    }}
    
    function sortBy(sortType) {{
        currentSort = sortType;
        const btnDumbest = document.getElementById('btn-dumbest');
        const btnSmartest = document.getElementById('btn-smartest');
        
        btnDumbest.classList.toggle('active', sortType === 'dumbest');
        btnSmartest.classList.toggle('active', sortType === 'smartest');
        btnSmartest.classList.toggle('smart', sortType === 'smartest');
        
        const sorted = [...peopleData].sort((a, b) => sortType === 'smartest' ? b.iq - a.iq : a.iq - b.iq);
        renderPeople(sorted);
    }}
    
    async function hidePerson(e, personId, personName) {{
        e.stopPropagation();
        if (!confirm(`Remove "${{personName}}" from the list?`)) return;
        
        try {{
            const response = await fetch(`/iq-rating/iq/hide?uid=${{uid}}&person_id=${{personId}}`, {{ method: 'POST' }});
            if (response.ok) {{
                peopleData = peopleData.filter(p => p.id !== personId);
                sortBy(currentSort);
            }}
        }} catch (e) {{
            console.error('Error hiding person:', e);
        }}
    }}
    
    function shareResults() {{
        const text = `I ranked everyone I know by IQ... the dumbest person is ${{peopleData[peopleData.length-1]?.name || 'unknown'}} with ${{peopleData[peopleData.length-1]?.iq || '??'}} IQ 😭`;
        if (navigator.share) {{
            navigator.share({{ title: "Who's the Dumbest?", text: text, url: window.location.href }});
        }} else {{
            navigator.clipboard.writeText(text + ' ' + window.location.href);
            alert('Copied to clipboard!');
        }}
    }}
    
    async function adjustIq(e, personId, delta) {{
        e.stopPropagation();
        try {{
            const response = await fetch(`/iq-rating/iq/adjust?uid=${{uid}}&person_id=${{personId}}&delta=${{delta}}`, {{ method: 'POST' }});
            const data = await response.json();
            if (data.success) {{
                // Update local data
                const person = peopleData.find(p => p.id === personId);
                if (person) {{
                    person.iq = data.new_iq;
                    sortBy(currentSort);
                }}
            }}
        }} catch (err) {{
            console.error('Error adjusting IQ:', err);
        }}
    }}
    
    function renderPeople(people) {{
        const list = document.getElementById('people-list');
        list.innerHTML = people.slice(0, 50).map((person, index) => {{
            const rank = index + 1;
            const iqColor = getIqColor(person.iq);
            const rankClass = rank <= 3 ? `rank-${{rank}}` : '';
            const trophy = rank === 1 ? '🏆' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : '';
            
            return `
                <div class="person-card ${{rankClass}}" style="--card-color: ${{iqColor}}; --iq-color: ${{iqColor}}">
                    <button class="hide-btn" onclick="hidePerson(event, '${{person.id}}', '${{person.name}}')">✕ remove</button>
                    <div class="person-header">
                        <div class="person-rank">${{trophy || '#' + rank}}</div>
                        <div class="person-info">
                            <div class="person-name">${{person.name}}</div>
                            <div class="person-mentions">${{person.memory_count}} conversations</div>
                        </div>
                        <div style="text-align: right; display: flex; align-items: center; gap: 8px;">
                            <div class="iq-adjust">
                                <button class="adj-btn" onclick="adjustIq(event, '${{person.id}}', -10)">−</button>
                                <button class="adj-btn" onclick="adjustIq(event, '${{person.id}}', 10)">+</button>
                            </div>
                            <div>
                                <div class="person-iq">${{person.iq}}</div>
                                <div class="iq-label">IQ</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }}).join('');
    }}
    
    // Default to dumbest first - more viral!
    sortBy('dumbest');
</script>
"""

LOADING_HTML = """
<div class="empty-state">
    <div class="empty-state-icon">⏳</div>
    <h2>Loading Your Data...</h2>
    <p>Fetching your memories and conversations.<br>This page will auto-refresh in 10 seconds.</p>
</div>
<script>setTimeout(() => location.reload(), 10000);</script>
"""

EMPTY_STATE = """
<div class="empty-state">
    <div class="empty-state-icon">🤷</div>
    <h2>No People Found</h2>
    <p>Start meeting people and having conversations to build your IQ rating list!</p>
</div>
"""


# ============== API ROUTES ==============

@router.get("/", response_class=HTMLResponse)
async def root():
    """Root page."""
    html = IQ_RATING_HTML.format(content=EMPTY_STATE.replace("No People Found", "IQ Rating").replace("Start meeting people", "Add ?uid=YOUR_ID to see ratings"))
    return HTMLResponse(content=html)


@router.get("/iq", response_class=HTMLResponse)
async def iq_rating_page(uid: Optional[str] = Query(None, description="User ID")):
    """IQ Rating page."""
    if not uid:
        html = IQ_RATING_HTML.format(
            content=EMPTY_STATE.replace("No People Found", "IQ Rating").replace("Start meeting people", "Add ?uid=YOUR_ID to see ratings")
        )
        return HTMLResponse(content=html)
    
    try:
        logger.info(f"IQ rating request for uid: {uid[:8]}...")
        
        # Try to get people
        people_with_iq = get_people_for_user(uid)
        
        if people_with_iq is None:
            # Not available - check if loading
            if is_loading(uid):
                html = IQ_RATING_HTML.format(content=LOADING_HTML)
                return HTMLResponse(content=html)
            
            # Start background loading
            thread = threading.Thread(target=load_and_process_user_data, args=(uid,))
            thread.start()
            
            html = IQ_RATING_HTML.format(content=LOADING_HTML)
            return HTMLResponse(content=html)
        
        if not people_with_iq:
            html = IQ_RATING_HTML.format(content=EMPTY_STATE.replace("Start meeting people", "No names found in your memories yet"))
            return HTMLResponse(content=html)
        
        # Generate page with people data
        people_json = json.dumps(people_with_iq)
        content = PEOPLE_LIST_CONTENT.format(uid=uid, people_data_json=people_json, total_people=len(people_with_iq))
        html = IQ_RATING_HTML.format(content=content)
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Error generating IQ ratings: {e}")
        error_content = f'<div class="empty-state"><h2>Error</h2><p>{str(e)}</p></div>'
        html = IQ_RATING_HTML.format(content=error_content)
        return HTMLResponse(content=html)


@router.get("/iq/api")
async def iq_rating_api(uid: str = Query(..., description="User ID")):
    """API endpoint to get IQ ratings as JSON."""
    try:
        people_with_iq = get_people_for_user(uid)
        
        if people_with_iq is None:
            if is_loading(uid):
                return JSONResponse(content={"uid": uid, "status": "loading", "message": "Data is being loaded"})
            
            thread = threading.Thread(target=load_and_process_user_data, args=(uid,))
            thread.start()
            
            return JSONResponse(content={"uid": uid, "status": "loading", "message": "Loading started"})
        
        return JSONResponse(content={
            "uid": uid,
            "status": "ready",
            "total_people": len(people_with_iq),
            "people": people_with_iq
        })
        
    except Exception as e:
        logger.error(f"Error getting IQ ratings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iq/hide")
async def hide_person_route(uid: str = Query(...), person_id: str = Query(...)):
    """Hide a person from the list (not a real name)."""
    success = hide_person(uid, person_id)
    return {"success": success, "person_id": person_id}


@router.post("/iq/unhide")
async def unhide_person_route(uid: str = Query(...), person_id: str = Query(...)):
    """Unhide a person."""
    success = unhide_person(uid, person_id)
    return {"success": success, "person_id": person_id}


@router.post("/iq/adjust")
async def adjust_iq_route(uid: str = Query(...), person_id: str = Query(...), delta: int = Query(...)):
    """Adjust a person's IQ score. delta can be positive or negative."""
    new_iq = adjust_iq(uid, person_id, delta)
    if new_iq is not None:
        return {"success": True, "person_id": person_id, "new_iq": new_iq}
    return {"success": False, "error": "Person not found"}


@router.get("/iq/preload")
async def preload_data(uid: str = Query(..., description="User ID")):
    """Preload data for a user in background."""
    if get_people_for_user(uid) is not None:
        return {"status": "already_loaded", "uid": uid}
    
    if is_loading(uid):
        return {"status": "loading", "uid": uid}
    
    thread = threading.Thread(target=load_and_process_user_data, args=(uid,))
    thread.start()
    
    return {"status": "loading_started", "uid": uid}


@router.get("/iq/refresh")
async def refresh_data(uid: str = Query(..., description="User ID")):
    """Force refresh data for a user (re-fetch from API)."""
    # Clear existing data
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM user_raw_data WHERE uid = ?', (uid,))
    c.execute('DELETE FROM people WHERE uid = ?', (uid,))
    conn.commit()
    conn.close()
    
    # Clear cache
    if uid in _cache:
        del _cache[uid]
    
    # Start fresh load
    thread = threading.Thread(target=load_and_process_user_data, args=(uid,))
    thread.start()
    
    return {"status": "refresh_started", "uid": uid}


@router.get("/iq/setup-status")
async def setup_status():
    """Setup status endpoint required by OMI."""
    return {"is_setup_completed": True}


# Create app for deployment (Railway, etc.)
from fastapi import FastAPI as StandaloneApp
app = StandaloneApp(title="IQ Rating", version="1.0.0")
app.include_router(router)


# Standalone runner for local development
if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 8765))
    uvicorn.run(app, host='0.0.0.0', port=port)
