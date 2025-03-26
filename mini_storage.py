import sqlite3
from pathlib import Path
import os
from typing import Optional

# Backward compatible default DB path
DEFAULT_DB = Path(__file__).parent / "miniatures.db"

def get_db_path(guild_id: Optional[int] = None) -> Path:
    """Get appropriate database path (maintains backward compatibility)"""
    if guild_id is None:
        # Use legacy single-database mode
        return DEFAULT_DB
    
    # Multi-server mode
    db_dir = Path("server_databases")
    db_dir.mkdir(exist_ok=True)
    return db_dir / f"guild_{guild_id}.db"

def init_db(guild_id: Optional[int] = None):
    """Initialize database (works for both single and multi-server)"""
    db_path = get_db_path(guild_id)
    print(f"Using database file: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS miniatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                image_url TEXT NOT NULL,
                image_hash TEXT UNIQUE,
                stl_name TEXT NOT NULL,
                bundle_name TEXT NOT NULL,
                tags TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    print(f"✅ Database initialized at: {db_path}")

def store_submission(
    user_id: int,
    message_id: int,
    image_url: str,
    stl_name: str,
    bundle_name: str,
    tags: Optional[str] = None,
    guild_id: Optional[int] = None,
    image_hash: Optional[str] = None
):
    """Store submission with backward compatibility"""
    db_path = get_db_path(guild_id)
    print(f"Storing in: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
            INSERT INTO miniatures 
            (user_id, message_id, image_url, image_hash, stl_name, bundle_name, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, message_id, image_url, image_hash, stl_name, bundle_name, tags))
    
    print(f"✅ Stored: {stl_name} (Message: {message_id})")

# Maintain all existing functions with guild_id parameter
def is_duplicate(image_hash: str, guild_id: Optional[int] = None) -> bool:
    db_path = get_db_path(guild_id)
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            'SELECT 1 FROM miniatures WHERE image_hash = ?', 
            (image_hash,)
        ).fetchone() is not None

def check_table_schema(guild_id: Optional[int] = None):
    db_path = get_db_path(guild_id)
    with sqlite3.connect(db_path) as conn:
        print(f"Schema for {db_path}:")
        for column in conn.execute("PRAGMA table_info(miniatures);"):
            print(column)

# Backward compatibility - initialize default DB if run directly
if __name__ == "__main__":
    init_db()  # Legacy single-database initialization
    store_submission(
        user_id=123, 
        message_id=999, 
        image_url="http://test.com/img.jpg", 
        stl_name="Test Model", 
        bundle_name="Test Bundle"
    )
    check_table_schema()