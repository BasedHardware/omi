import os
import sqlite3
from contextlib import contextmanager
import json

# Database setup
DB_PATH = os.getenv("DB_PATH", "plugins/composio/data/composio.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Context manager for database connections
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Create the necessary tables
def create_db_tables():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Table for user credentials (Notion tokens)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_credentials (
            uid TEXT PRIMARY KEY,
            notion_access_token TEXT,
            notion_workspace_id TEXT,
            notion_workspace_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Table for extracted memories/facts
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS extracted_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            source TEXT,
            memory_text TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uid) REFERENCES user_credentials(uid)
        )
        ''')
        
        conn.commit()

# Functions for Notion credentials management
def store_notion_credentials(uid, access_token, workspace_id, workspace_name):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE INTO user_credentials (uid, notion_access_token, notion_workspace_id, notion_workspace_name, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (uid, access_token, workspace_id, workspace_name))
        conn.commit()

def get_notion_credentials(uid):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_credentials WHERE uid = ?', (uid,))
        result = cursor.fetchone()
        return dict(result) if result else None

# Functions for memory management
def store_memory(uid, source, memory_text):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO extracted_memories (uid, source, memory_text)
        VALUES (?, ?, ?)
        ''', (uid, source, memory_text))
        conn.commit()
        return cursor.lastrowid

def update_memory_status(memory_id, status):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE extracted_memories
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (status, memory_id))
        conn.commit()

def get_pending_memories(uid, limit=100):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM extracted_memories
        WHERE uid = ? AND status = 'pending'
        ORDER BY created_at ASC
        LIMIT ?
        ''', (uid, limit))
        results = cursor.fetchall()
        return [dict(row) for row in results]

def get_all_memories(uid, limit=100, offset=0):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM extracted_memories
        WHERE uid = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        ''', (uid, limit, offset))
        results = cursor.fetchall()
        return [dict(row) for row in results] 