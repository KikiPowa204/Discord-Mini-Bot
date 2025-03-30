from pathlib import Path
from datetime import datetime
import os
from mysql.connector import connect, Error  # Import MySQL connector
import os
from typing import Optional
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import aiomysql
import re
from urllib.parse import urlparse
class MySQLStorage:
    def __init__(self):
        self.pool = None
    
    def _parse_public_url(self):
        """Extract connection details from MYSQL_PUBLIC_URL"""
        url = os.getenv('MYSQL_PUBLIC_URL')
        if not url:
            raise ValueError("❌ MYSQL_PUBLIC_URL not found in environment")
        
        try:
            # Parse the URL (e.g. "mysql://user:pass@host:port/db")
            parsed = urlparse(url)
            return {
                'host': parsed.hostname,
                'port': parsed.port or 3306,  # Default MySQL port
                'user': parsed.username,
                'password': parsed.password,
                'db': parsed.path[1:]  # Remove leading '/'
            }
        except Exception as e:
            raise ValueError(f"❌ Failed to parse MYSQL_PUBLIC_URL: {e}")

    async def initialize(self):
        """Initialize database for a specific guild"""
        """Call this once at setup"""
        await self._create_connection()
        print(f'Pool autocommit status: {self.pool.autocommit[0].autocommit}')
    
    async def _create_connection(self):
        """Create and return MySQL connection"""
        try:
            config = self._parse_public_url()
            
            self.pool = await aiomysql.create_pool(
                host=config['host'],
                port=config['port'],
                user=config['user'],
                password=config['password'],
                db=config['db'],
                minsize=1,
                maxsize=10,
                connect_timeout=10,
                autocommit=False
            )
            print(f"✅ Connected to MySQL at {config['host']}:{config['port']}")
        except Exception as e:
            print(f"❌ Connection failed. Verify:")
            print(f"- MYSQL_PUBLIC_URL is correct")
            print(f"- MySQL service is running (not paused)")
            print(f"- Error details: {e}")
            raise

    async def execute_query(self, query, args=None):
        """Generic query executor"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args or ())
                await conn.commit()
                return cursor

    async def init_db(self):
        """Initialize database tables"""
        if not self.pool:
            await self._create_connection()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS guilds (
                        guild_id VARCHAR(255) PRIMARY KEY,
                        guild_name VARCHAR(255) NOT NULL,
                        system_channel BIGINT NULL,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_last_seen (last_seen)
                    )
                ''')
                # Create miniatures table if not exists
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS miniatures (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id VARCHAR(255) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        message_id VARCHAR(255) NOT NULL,
                        image_url TEXT NOT NULL,
                        stl_name VARCHAR(255) NOT NULL,
                        bundle_name VARCHAR(255) NOT NULL,
                        tags TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_guild (guild_id),
                        INDEX idx_stl_name (stl_name),
                        UNIQUE KEY unique_image (image_hash),
                        FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
                    )
                ''')
                await conn.commit()
        return True
    
    async def store_guild_info(self, guild_id: str, guild_name: str, system_channel: Optional[int] = None):
        """Store basic guild information"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                    INSERT INTO guilds 
                    (guild_id, guild_name, system_channel, last_seen)
                    VALUES (%s, %s, %s, NOW()) AS new
                    ON DUPLICATE KEY UPDATE
                        guild_name = VALUES(guild_name),
                        system_channel = VALUES(system_channel),
                        last_seen = VALUES(last_seen)
                ''', (guild_id, guild_name, system_channel))
                await conn.commit()
                return True
        except Error as e:
            print(f"❌ Failed to store guild info: {e}")
            return False

    async def store_submission(self, **kwargs):
        """Store submission with all required fields"""
        required_fields = {'guild_id', 'user_id', 'message_id', 'image_url', 'stl_name'}
        if missing := required_fields - kwargs.keys():
            print(f"❌ Missing required fields: {missing}")
            return False
        
        defaults = {
        'bundle_name': '',
        'tags': '',
        'approval_status': 'pending',  # New field example
        'submitted_at': datetime.utcnow(),
        'prompt_id': None
    }
        submission_data = {**defaults, **kwargs}

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await conn.begin()
                    await cursor.execute('''
                    INSERT INTO guilds (guild_id, guild_name, last_seen)
                    VALUES (%s, NOW())
                    ON DUPLICATE KEY UPDATE last_seen=NOW()
                ''', (submission_data['guild_id'], 
                     f"Guild-{submission_data['guild_id']}"))
                # Then insert the submission
                await cursor.execute('''
                    INSERT INTO miniatures (
                        guild_id, user_id, message_id,
                        image_url, stl_name, bundle_name,
                        tags, approval_status, submitted_at,
                        prompt_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    str(submission_data['guild_id']),
                    str(submission_data['user_id']),
                    str(submission_data['message_id']),
                    str(submission_data['author_name']),
                    submission_data['image_url'],
                    submission_data['channel_id'],
                    submission_data['stl_name'],
                    submission_data['bundle_name'],
                    submission_data['tags']
                ))
                await conn.commit()
                return True
        except Error as e:
            print(f"❌Database error: {e}")
            return False
        except Exception as e:
            print(f"❌Unexpected Error: {e}")
        
    async def get_submissions(self, guild_id: str, search_query: str = "", limit: int = 5):
        """Retrieve submissions with search"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                    SELECT m.*, g.guild_name 
                    FROM miniatures m
                    JOIN guilds g ON m.guild_id = g.guild_id
                    WHERE m.guild_id = %s
                    AND (m.stl_name LIKE %s OR m.bundle_name LIKE %s OR m.tags LIKE %s)
                    ORDER BY m.created_at DESC
                    LIMIT %s
                ''', (
                    str(guild_id),
                    f'%{search_query}%',
                    f'%{search_query}%',
                    f'%{search_query}%',
                    limit
                ))
                return cursor.fetchall()
        except Error as e:
            print(f"❌ Query failed: {e}")
            

# Singleton instance
mysql_storage = MySQLStorage()

if __name__ == "__main__":
    # Test guild info storage
    mysql_storage.store_guild_info(
        guild_id="12345",
        guild_name="Test Guild",
        system_channel=67890
    )
    # Test retrieval
    results = mysql_storage.get_submissions("12345", "Test")
    print(f"Test results: {results}")   