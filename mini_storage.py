from pathlib import Path
from datetime import datetime
import hashlib
import os
from typing import Dict, Optional  # Add this importS
import mysql.connector
# Remove: import sqlite3
from mysql.connector import connect, Error  # Import MySQL connector


connection = mysql.connector.connect(
    host="gondola.proxy.rlwy.net",
    user="root",
    password="VFPUYdKKzWeFagKmSOPyINxNqFUnwIRt",
    port=19512,
    database="railway"
)

# Use the connection to execute queries
cursor = connection.cursor()
cursor.execute("SELECT * FROM your_table")
result = cursor.fetchall()
print(result)

# Don't forget to close the connection when you're done
cursor.close()
connection.close()

# Example: Querying the database
cursor.execute("SELECT * FROM submissions;")
rows = cursor.fetchall()
for row in rows:
    print(row)

#new version of mini_storage.py to upload

class GuildManager:
    def __init__(self, host, user, password, database):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.connection = None  # To store the connection to MySQL
    
    def connect(self):
        """ Establish MySQL connection """
        if not self.connection:
            try:
                self.connection = connect(
                    host=self.host,
                    user=self.user,
                    password=self.password,
                    database=self.database
                )
                print("✅ MySQL connected successfully")
            except Error as e:
                print(f"❌ MySQL connection failed: {e}")
    
    def close_connection(self):
        """ Close MySQL connection """
        if self.connection:
            self.connection.close()
            print("✅ MySQL connection closed.")
    
    def get_connection(self):
        """ Returns the active connection """
        if not self.connection:
            self.connect()  # Connect if not already connected
        return self.connection
class MiniStorage:
    def __init__(self, guild_manager):
        self.guild_manager = guild_manager  # MySQL connection manager
    
    def init_db(self):
        """ Initialize the database tables (only once) """
        connection = self.guild_manager.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS miniatures (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id INT NOT NULL,
                    user_id INT NOT NULL,
                    message_id INT NOT NULL,
                    image_url TEXT NOT NULL,
                    image_hash TEXT UNIQUE,
                    stl_name TEXT NOT NULL,
                    bundle_name TEXT NOT NULL,
                    tags TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            connection.commit()  # Commit changes
            print("✅ Database initialized (MySQL)")
        except Error as e:
            print(f"❌ Error initializing database: {e}")
    
    def store_submission(self, guild_id: int, **kwargs):
        """ Store submission in the MySQL database """
        connection = self.guild_manager.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute('''
                INSERT INTO miniatures 
                (guild_id, user_id, message_id, image_url, image_hash, stl_name, bundle_name, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            connection.commit()  # Commit changes
            print(f"✅ Stored: {kwargs['stl_name']} (Guild: {guild_id})")
            return True
        except Error as e:
            print(f"❌ Error storing submission: {e}")
            return False

    def is_duplicate(self, guild_id: int, image_hash: str) -> bool:
        """ Check for duplicate image in the MySQL database """
        connection = self.guild_manager.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute('''
                SELECT 1 FROM miniatures WHERE image_hash = %s
            ''', (image_hash,))
            result = cursor.fetchone()
            return result is not None
        except Error as e:
            print(f"❌ Error checking duplicates: {e}")
            return False
# MySQL connection details
host = "your-mysql-host"
user = "your-mysql-user"
password = "your-mysql-password"
database = "your-mysql-database"

# Initialize GuildManager and MiniStorage
guild_manager = GuildManager(host, user, password, database)
mini_storager = MiniStorage(guild_manager)

# Initialize the database (creating tables if necessary)
mini_storager.init_db()

# Store and check for duplicates
TEST_GUILD = 12345
test_data = {
    'user_id': 123,
    'message_id': 999,
    'image_url': "http://test.com/img.jpg",
    'image_hash': "abc123",
    'stl_name': "Test Model",
    'bundle_name': "Test Bundle",
    'tags': "test,demo"
}

if mini_storager.store_submission(TEST_GUILD, **test_data):
    print("✅ Test storage successful")

# Verify duplicate check
if mini_storager.is_duplicate(TEST_GUILD, "abc123"):
    print("✅ Duplicate check working")

