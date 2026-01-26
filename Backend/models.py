"""
Database models and initialization for user authentication and chat history.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB", "market-intelligence.db"))

def get_db_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_chat_tables():
    """Initialize the users and chat tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Chat sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
            updated_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Chat messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            execution_time REAL,
            created_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    ''')
    
    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id)')
    
    conn.commit()
    conn.close()
    print("Chat tables initialized successfully.")

# User CRUD operations
def create_user(email: str, password_hash: str, display_name: str = None) -> int:
    """Create a new user and return the user ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)',
        (email, password_hash, display_name)
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id

def get_user_by_email(email: str) -> dict:
    """Get user by email."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> dict:
    """Get user by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, email, display_name, created_at FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# Chat session CRUD operations
def create_chat_session(user_id: int, title: str = "New Chat") -> int:
    """Create a new chat session and return the session ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        'INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)',
        (user_id, title, now, now)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def get_user_chat_sessions(user_id: int) -> list:
    """Get all chat sessions for a user, ordered by most recent."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, created_at, updated_at 
        FROM chat_sessions 
        WHERE user_id = ? 
        ORDER BY updated_at DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_chat_session(session_id: int, user_id: int) -> dict:
    """Get a specific chat session (with ownership check)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?',
        (session_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_chat_session_title(session_id: int, user_id: int, title: str) -> bool:
    """Update chat session title."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        'UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?',
        (title, now, session_id, user_id)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def delete_chat_session(session_id: int, user_id: int) -> bool:
    """Delete a chat session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM chat_sessions WHERE id = ? AND user_id = ?',
        (session_id, user_id)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# Chat message CRUD operations
def add_chat_message(session_id: int, role: str, content: str, execution_time: float = None) -> int:
    """Add a message to a chat session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        'INSERT INTO chat_messages (session_id, role, content, execution_time, created_at) VALUES (?, ?, ?, ?, ?)',
        (session_id, role, content, execution_time, now)
    )
    message_id = cursor.lastrowid
    
    # Update session's updated_at timestamp
    cursor.execute(
        'UPDATE chat_sessions SET updated_at = ? WHERE id = ?',
        (now, session_id)
    )
    
    conn.commit()
    conn.close()
    return message_id

def get_chat_messages(session_id: int) -> list:
    """Get all messages for a chat session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, role, content, execution_time, created_at 
        FROM chat_messages 
        WHERE session_id = ? 
        ORDER BY created_at ASC
    ''', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

if __name__ == "__main__":
    init_chat_tables()
