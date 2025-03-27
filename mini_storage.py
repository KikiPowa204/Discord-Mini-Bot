import sqlite3
from pathlib import Path
from datetime import datetime
import hashlib
import os
# mini_storage.py
from typing import Dict, Optional  # Add this import
import guild_manager
#new version of mini_storage.py to upload

class MiniStorage:
    def __init__(self):
        self.guild_manager = guild_manager

    def store_submission(self, guild_id: int, **kwargs):
        """Store submission with proper guild handling"""
        db_path = self.guild_manager.get_guild_db(guild_id)
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute('''
                    INSERT INTO miniatures 
                    (guild_id, user_id, message_id, image_url, stl_name, bundle_name, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    guild_id,
                    kwargs['user_id'],
                    kwargs['message_id'],
                    kwargs['image_url'],
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
    # Initialize test guild DB
    TEST_GUILD = 12345
    guild_manager.get_guild_db(TEST_GUILD)
    
    # Test storage
    test_data = {
        'user_id': 123,
        'message_id': 999,
        'image_url': "http://test.com/img.jpg",
        'stl_name': "Test Model",
        'bundle_name': "Test Bundle",
        'tags': "test,demo"
    }
    
    if mini_storage.store_submission(TEST_GUILD, **test_data):
        print("✅ Test storage successful")
    
    # Test duplicate check
    test_hash = "abc123"  # Replace with actual hash
    if mini_storage.is_duplicate(TEST_GUILD, test_hash):
        print("⚠️ Test duplicate found")
    else:
        print("✅ No duplicates found")
