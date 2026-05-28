import sys
import os
import sqlite3
import argparse

# Add parent directory to sys.path to allow importing models/auth
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from auth import hash_password

def main():
    parser = argparse.ArgumentParser(description="Create or promote a user to Admin in the SQLite DB.")
    parser.add_argument("--email", required=True, help="User's email address")
    parser.add_argument("--password", required=True, help="User's password")
    parser.add_argument("--name", default="Admin User", help="User's display name")
    args = parser.parse_args()

    db_path = os.getenv("DATABASE_PATH") or os.path.join(parent_dir, "DB", "market-intelligence.db")
    print(f"Using database path: {db_path}")
    
    if not os.path.exists(db_path):
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        print(f"Creating new SQLite database file at: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure users table exists (in case running on a completely clean DB)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'analyst' CHECK(role IN ('admin', 'analyst', 'viewer')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Check if user already exists
    cursor.execute("SELECT id, role FROM users WHERE email = ?", (args.email,))
    existing = cursor.fetchone()

    hashed = hash_password(args.password)

    if existing:
        user_id = existing[0]
        print(f"User {args.email} already exists with ID {user_id}. Promoting to admin and updating password...")
        cursor.execute(
            "UPDATE users SET role = 'admin', password_hash = ?, display_name = ? WHERE id = ?",
            (hashed, args.name, user_id)
        )
    else:
        print(f"Creating new admin user {args.email}...")
        cursor.execute(
            "INSERT INTO users (email, password_hash, display_name, role) VALUES (?, ?, ?, 'admin')",
            (args.email, hashed, args.name)
        )

    conn.commit()
    conn.close()
    print("Success! Admin user is ready.")

if __name__ == "__main__":
    main()
