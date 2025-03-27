import sqlite3
from pathlib import Path
from datetime import datetime
import hashlib
import os
from typing import Dict, Optional  # Add this import
#new version of mini_storage.py to upload

# First define the GuildManager (was missing)
class GuildManager:
    def __init__(self):
        self.server_dbs = Path("server_databases")
        self.server_dbs.mkdir(exist_ok=True)
    
    def get_guild_db(self, guild_id=None):
        return self.server_dbs / f"guild_{guild_id}.db" if guild_id else Path("miniatures.db")

# Initialize the manager singleton
guild_manager = GuildManager()

class MiniStorage:
    def __init__(self):
        self.guild_manager = guild_manager  # Make sure guild_manager is imported/defined
    
    def init_db(self, guild_id=None):
        db_path = self.guild_manager.get_guild_db(guild_id)
        print(f"Using database file: {db_path}")
        
        with sqlite3.connect(db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS miniatures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    image_hash TEXT UNIQUE,  # Added for duplicate checking
                    stl_name TEXT NOT NULL,
                    bundle_name TEXT NOT NULL,
                    tags TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        print(f"✅ Database initialized at: {db_path}")
        return db_path
    
    def store_submission(self, guild_id: int, **kwargs):
        """Store submission with proper guild handling"""
        db_path = self.guild_manager.get_guild_db(guild_id)
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute('''
                    INSERT INTO miniatures 
                    (guild_id, user_id, message_id, image_url, image_hash, stl_name, bundle_name, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    guild_id,
                    kwargs['user_id'],
                    kwargs['message_id'],
                    kwargs['image_url'],
                    kwargs.get('image_hash'), 
                    kwargs['stl_name'],
                    kwargs['bundle_name'],
                    kwargs.get('tags')
                ))
            print(f"✅ Stored: {kwargs['stl_name']} (Guild: {guild_id})")
            return True
        except Exception as e:
            print(f"❌ Storage failed: {e}")
            return False

    def is_duplicate(self, guild_id: int, image_hash: str) -> bool:
        """Check for duplicate image in guild-specific DB"""
        db_path = self.guild_manager.get_guild_db(guild_id)
        try:
            with sqlite3.connect(db_path) as conn:
                return conn.execute(
                    'SELECT 1 FROM miniatures WHERE image_hash = ?',
                    (image_hash,)
                ).fetchone() is not None
        except Exception as e:
            print(f"❌ Duplicate check failed: {e}")
            return False

# Singleton instance for easy import
mini_storage = MiniStorage()

# Test when run directly
if __name__ == "__main__":
    mini_storage.init_db()
    
    # Test guild DB
    TEST_GUILD = 12345
    db_path = mini_storage.init_db(TEST_GUILD)
    
    # Test storage
    test_data = {
        'user_id': 123,
        'message_id': 999,
        'image_url': "http://test.com/img.jpg",
        'image_hash': "abc123",
        'stl_name': "Test Model",
        'bundle_name': "Test Bundle",
        'tags': "test,demo"
    }
    
    if mini_storage.store_submission(TEST_GUILD, **test_data):
        print("✅ Test storage successful")
    
    # Verify duplicate check
    if mini_storage.is_duplicate(TEST_GUILD, "abc123"):
        print("✅ Duplicate check working")
