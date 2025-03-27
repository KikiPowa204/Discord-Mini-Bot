from pathlib import Path
from datetime import datetime
import os
from mysql.connector import connect, Error  # Import MySQL connector
import os
from typing import Optional
import mysql.connector
from mysql.connector import Error
from datetime import datetime

class MySQLStorage:
    def __init__(self):
        self.connection = self._create_connection()
        self.init_db()  # Initialize tables on startup
        print(f"Autocommit status: {self.connection.autocommit}")

    def _create_connection(self):
        """Create and return MySQL connection"""
        try:
            connection = mysql.connector.connect(
                host="gondola.proxy.rlwy.net",
                user="root",
                password="VFPUYdKKzWeFagKmSOPyINxNqFUnwIRt",
                port=19512,
                database="railway"
            )
            print("✅ MySQL connection successful!")
            return connection
        except Error as e:
            print(f"❌ MySQL connection failed: {e}")
            exit(1)

    def init_db(self):
        """Initialize database tables"""
        try:
            with self.connection.cursor() as cursor:
                # Create guilds table if not exists
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS guilds (
                        guild_id VARCHAR(255) PRIMARY KEY,
                        guild_name VARCHAR(255) NOT NULL,
                        system_channel BIGINT NULL,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_last_seen (last_seen)
                    )
                ''')
                
                # Create miniatures table if not exists
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS miniatures (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id VARCHAR(255) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        message_id VARCHAR(255) NOT NULL,
                        image_url TEXT NOT NULL,
                        stl_name VARCHAR(255) NOT NULL,
                        bundle_name VARCHAR(255) NOT NULL,
                        tags TEXT,
                        image_hash VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_guild (guild_id),
                        INDEX idx_stl_name (stl_name),
                        UNIQUE KEY unique_image (image_hash),
                        FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
                    )
                ''')
                
            self.connection.commit()
            print("✅ Database tables initialized")
        except Error as e:
            print(f"❌ Table creation failed: {e}")
            raise

    def store_guild_info(self, guild_id: str, guild_name: str, system_channel: Optional[int] = None):
        """Store basic guild information"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO guilds 
                    (guild_id, guild_name, system_channel, last_seen)
                    VALUES (%s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        guild_name = VALUES(guild_name),
                        system_channel = VALUES(system_channel),
                        last_seen = VALUES(last_seen)
                ''', (guild_id, guild_name, system_channel))
            self.connection.commit()
            return True
        except Error as e:
            print(f"❌ Failed to store guild info: {e}")
            return False

    def store_submission(self, guild_id: str, **kwargs):
        print("\n=== STORING SUBMISSION ===")
        print(f"Guild ID: {guild_id}")
        print("Submission data:", kwargs)

        """Store submission with all required fields"""
        required = ['guild_id', 'user_id', 'message_id', 'image_url', 'stl_name', 'bundle_name']
        if any(kwargs.get(k) is None for k in required):
            print(f"Missing required fields: {required}")
            return False

        try:
            with self.connection.cursor() as cursor:
            # 1. Ensure guild exists
                cursor.execute('''
                INSERT INTO guilds (guild_id, guild_name, last_seen)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE last_seen=NOW()
            ''', (guild_id, kwargs.get('guild_name', f"Guild-{guild_id}")))
            print(f"✓ Guild {guild_id} ensured")

            # 2. Prepare miniature data
            miniature_data = (
                guild_id,
                str(kwargs['user_id']),
                str(kwargs['message_id']),
                kwargs['image_url'],
                kwargs['stl_name'],
                kwargs['bundle_name'],
                kwargs.get('tags', ''),
                kwargs.get('image_hash', None)  # Handle optional field
            )
            print("Miniature data prepared:", miniature_data)

            # 3. Insert miniature
            cursor.execute('''
                INSERT INTO miniatures (
                    guild_id, user_id, message_id,
                    image_url, stl_name, bundle_name, tags, image_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', miniature_data)
            print(f"✓ Miniature inserted (ID: {cursor.lastrowid})")

            self.connection.commit()
            print("✓ Transaction committed")
            return True

        except mysql.connector.Error as e:
            print(f"✗ Database error: {e}")
            self.connection.rollback()
            return False
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return False    
    def get_submissions(self, guild_id: str, search_query: str = "", limit: int = 5):
        """Retrieve submissions with search"""
        try:
            with self.connection.cursor(dictionary=True) as cursor:
                cursor.execute('''
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
            return []

def check_table_structure():
    with mysql_storage.connection.cursor(dictionary=True) as cursor:
        cursor.execute("DESCRIBE miniatures")
        print("Miniatures table structure:")
        for column in cursor.fetchall():
            print(f"{column['Field']}: {column['Type']} {'NULL' if column['Null'] == 'YES' else 'NOT NULL'}")

# Singleton instance
mysql_storage = MySQLStorage()

if __name__ == "__main__":
    # Test guild info storage
    mysql_storage.store_guild_info(
        guild_id="12345",
        guild_name="Test Guild",
        system_channel=67890
    )
    
    # Test submission storage
    test_data = {
        'user_id': 123,
        'message_id': 999,
        'image_url': "http://test.com/img.jpg",
        'stl_name': "Test Model",
        'bundle_name': "Test Bundle",
        'tags': "test,demo",
        'image_hash': "abc123",
        'guild_name': "Test Guild"
    }
    
    if mysql_storage.store_submission("12345", **test_data):
        print("✅ Test storage successful")
    
    # Test retrieval
    results = mysql_storage.get_submissions("12345", "Test")
    print(f"Test results: {results}")