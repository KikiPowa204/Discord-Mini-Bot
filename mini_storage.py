import sqlite3
from pathlib import Path
from datetime import datetime
import hashlib
import os
# mini_storage.py
import sqlite3
from datetime import datetime

import sqlite3
from pathlib import Path
from datetime import datetime
import hashlib

DB_FILE = Path(__file__).parent / "miniatures.db"

def init_db():
    """Initialize database with verification"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''
        CREATE TABLE IF NOT EXISTS miniatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_id INTEGER,
            image_url TEXT NOT NULL,
            image_hash TEXT UNIQUE NOT NULL,
            stl_name TEXT NOT NULL,
            bundle_name TEXT,
            timestamp DATETIME NOT NULL
        )''')
        
        conn.commit()
        print(f"✅ Database initialized at: {DB_FILE}")
        
        # Verify table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='miniatures'")
        if not c.fetchone():
            raise RuntimeError("Table creation failed!")
            
    except Exception as e:
        print(f"🚨 Database error: {e}")
        raise
    finally:
        if conn: conn.close()

def store_submission(user_id: int, message_id: int, image_url: str, stl_name: str, bundle_name: str):
    """Store submission with full validation"""
    conn = None
    try:
        image_hash = hashlib.md5(image_url.encode()).hexdigest()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''
        INSERT INTO miniatures 
        (user_id, message_id, image_url, image_hash, stl_name, bundle_name, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, message_id, image_url, image_hash, stl_name, bundle_name, datetime.now()))
        
        conn.commit()
        print(f"✅ Stored submission: {stl_name} ({message_id})")
        
        # Verify insertion
        c.execute("SELECT 1 FROM miniatures WHERE message_id=?", (message_id,))
        if not c.fetchone():
            raise RuntimeError("Insertion verification failed!")
            
    except sqlite3.IntegrityError:
        print("⚠️ Duplicate image detected (hash already exists)")
    except Exception as e:
        print(f"🚨 Storage error: {e}")
        raise
    finally:
        if conn: conn.close()

def is_duplicate(image_hash):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('SELECT 1 FROM miniatures WHERE image_hash = ?', (image_hash,))
        return c.fetchone() is not None

# Test when run directly
if __name__ == "__main__":
    init_db()
    # Test insertion
    store_submission(123, 999, "http://test.com/img.jpg", "Test Model", "Test Bundle")
# Test immediately when module loads
print(f"🔍 Database location VERIFIED: {os.path.exists(DB_FILE)}")
init_db()
