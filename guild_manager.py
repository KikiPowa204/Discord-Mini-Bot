from pathlib import Path
import sqlite3
from typing import Dict, Optional

class GuildManager:
    def __init__(self):
        self.guild_dbs: Dict[int, str] = {}  # {guild_id: db_path}
        
    def get_guild_db(self, guild_id: int) -> str:
        """Get or create database path for a guild"""
        if guild_id not in self.guild_dbs:
            db_path = f"server_dbs/guild_{guild_id}.db"
            Path("server_dbs").mkdir(exist_ok=True)
            self._init_db(guild_id, db_path)
            self.guild_dbs[guild_id] = db_path
        return self.guild_dbs[guild_id]
    
    def _init_db(self, guild_id: int, db_path: str):
        """Initialize a new guild database"""
        with sqlite3.connect(db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS miniatures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    image_url TEXT NOT NULL,
                    stl_name TEXT NOT NULL,
                    bundle_name TEXT NOT NULL,
                    tags TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        print(f"Initialized DB for guild {guild_id} at {db_path}")

# Singleton instance
guild_manager = GuildManager()