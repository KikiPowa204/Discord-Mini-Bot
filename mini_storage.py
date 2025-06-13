from pathlib import Path
from datetime import datetime, timezone
import os
from mysql.connector import connect, Error  # Import MySQL connector
import os
from typing import Optional
from mysql.connector import Error
import aiomysql
from urllib.parse import urlparse
import logging
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
                minsize=5,
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
                        author VARCHAR(255) NOT NULL,
                        image_url TEXT NOT NULL,
                        channel_id VARCHAR(255),
                        stl_name VARCHAR(255),
                        bundle_name VARCHAR(255),
                        tags TEXT,
                        INDEX idx_guild (guild_id),
                        INDEX idx_stl_name (stl_name),
                        FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
                    )
                ''')
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS exclude (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id VARCHAR(255) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
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
        """Store submission using connection pool"""
        required_fields = {'guild_id', 'user_id', 'message_id', 'image_url', 'stl_name'}
        if missing := required_fields - kwargs.keys():
            logging.error(f"Missing required fields: {missing}")
            return False

        defaults = {
            'bundle_name': None,
            'tags': None,
            'author': 'Unknown',
            'channel_id': None
        }
        submission_data = {**defaults, **kwargs}

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # Upsert guild (simplified version)
                    await cursor.execute('''
                        INSERT INTO guilds (guild_id, guild_name, last_seen)
                        VALUES (%s, %s, NOW())
                        ON DUPLICATE KEY UPDATE last_seen=NOW()
                    ''', (
                        str(submission_data['guild_id']),
                        f"Guild-{submission_data['guild_id']}"
                    ))

                    # Fixed INSERT statement - removed trailing comma
                    await cursor.execute('''
                        INSERT INTO miniatures (
                            guild_id, user_id, message_id, author,
                            image_url, channel_id, stl_name,
                            bundle_name, tags
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        str(submission_data['guild_id']),
                        str(submission_data['user_id']),
                        str(submission_data['message_id']),
                        str(submission_data['author']),
                        submission_data['image_url'],
                        str(submission_data['channel_id']) if submission_data['channel_id'] else None,
                        submission_data['stl_name'],
                        submission_data['bundle_name'],
                        submission_data['tags']
                    ))
                    
                    await conn.commit()
                    return True
        except Exception as e:
            logging.error(f"Database error: {e}")
            return False
            

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