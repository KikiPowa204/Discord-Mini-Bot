import discord
from discord.ext import commands
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import logging
import asyncio
from typing import Optional
# Load environment variables first
import mysql.connector
from mysql.connector import Error
# Remove: import sqlite3
from mini_storage import mysql_storage

connection = mysql.connector.connect(
    host="gondola.proxy.rlwy.net",
    user="root",
    password="VFPUYdKKzWeFagKmSOPyINxNqFUnwIRt",
    port=19512,
    database="railway"
)

# Use the connection to execute queries
cursor = connection.cursor()
cursor.execute("SELECT * FROM miniatures")
result = cursor.fetchall()
print(result)

# Initialize global variables
pending_submissions = {}  # Format: {prompt_message_id: original_message_data}
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
# Custom database module
#Update this bitch

# Default settings
DEFAULTS = {
    'cleanup_mins': 10,
    'max_examples': 5,
    'submissions_chan': 'miniature-submissions',
    'gallery_chan': 'miniature-gallery'
}

# Runtime storage
intents=discord.Intents.all()
intents.message_content = True
intents.messages = True  # Needed for message history

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_DB(ctx):
    """Initialize database for this server (explicit admin command)"""
    guild_id = ctx.guild.id
    guild_name = ctx.guild.name
    system_channel = ctx.guild.system_channel.id if ctx.guild.system_channel else None

    # Initialize the database for the server
    mysql_storage.store_guild_info(guild_id, guild_name, system_channel)

    # Send confirmation message
    await ctx.send(f"✅ Server database initialized for **{guild_name}**!")
from discord.ext import commands
from typing import Optional

async def get_guild_id(ctx: commands.Context) -> Optional[int]:
    """Safely retrieves the guild ID with proper typing and error handling."""
    if not ctx.guild:  # Check if in DMs
        await ctx.send("❌ This command only works in servers!")
        return None
    return ctx.guild.id

async def get_guild_name(ctx: commands.Context) -> Optional[str]:
    """Safely retrieves the guild name with proper typing and error handling."""
    if not ctx.guild:
        await ctx.send("❌ This command only works in servers!")
        return None
    return ctx.guild.name
@bot.command()
async def test_guild_info(ctx):
    """Test both functions in one command"""
    guild_id = await get_guild_id(ctx)
    guild_name = await get_guild_name(ctx)
    
    if None in (guild_id, guild_name):
        return  # Errors already handled
    
    embed = discord.Embed(title="Guild Info Test")
    embed.add_field(name="ID", value=f"`{guild_id}`", inline=False)
    embed.add_field(name="Name", value=guild_name, inline=False)
    embed.set_footer(text=f"Tested at {datetime.now().isoformat()}")
    
    await ctx.send(embed=embed)

@bot.command()
async def test_dm(ctx):
    """Verify DM handling"""
    await ctx.send(f"In DMs: ID={await get_guild_id(ctx)}, Name={await get_guild_name(ctx)}")
class SubmissionButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=3600)  # 1 hour timeout
    
    @discord.ui.button(label="Add Tags", style=discord.ButtonStyle.blurple)
    async def add_tags(self, interaction, button):
        await interaction.response.send_modal(TaggingModal())

class TaggingModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Tag This Miniature")
        self.add_item(discord.ui.TextInput(label="STL Name", placeholder="Lucian the Paladin", required=True))
        self.add_item(discord.ui.TextInput(label="Bundle Name", placeholder="Fantasy Heroes Vol. 3", required=True))
        self.add_item(discord.ui.TextInput(label="Tags (optional)", placeholder="NMM, OSL, freehand", required=False))
    
    async def on_submit(self, interaction):
        submission = next(
            (v for k,v in bot.pending_subs.items() 
            if v['prompt_id'] == interaction.message.id),
            None
            )
    
        if not submission:
            return await interaction.response.send_message("❌ Submission expired", ephemeral=True)
    
        try:
            success = mysql_storage.store_submission(
                guild_id=submission['guild_id'],
                user_id=submission['user_id'],
                message_id=submission['original_msg_id'],
                image_url=submission['image_url'],
                stl_name=self.children[0].value,  # From STL input
                bundle_name=self.children[1].value,  # From Bundle input
                tags=self.children[2].value  # From Tags input
        )
        
            if success:
                await interaction.response.send_message("✅ Saved to database!", ephemeral=True)
                await interaction.message.add_reaction('✅')
            else:
                await interaction.response.send_message("❌ Failed to save", ephemeral=True)
            
        except Exception as e:
            logging.error(f"Storage failed: {e}")
            await interaction.response.send_message("⚠️ Database error occurred", ephemeral=True)
    
    # Cleanup
        try:
            pass  # No action needed for message deletion
            channel = bot.get_channel(submission['channel_id'])
            if channel:
                msg = await channel.fetch_message(submission['original_msg_id'])
        except Exception as e:
            logging.error(f"Cleanup error: {e}")
       
async def handle_submission(message):
    print (message)
    try:
        # Validate input
        if not message.attachments or not any(
            message.attachments[0].filename.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif')
        ):
            await message.channel.send("❌ Please attach a valid image file (jpg, jpeg, png, gif)!")
            return
            
        stl_name = None
        bundle_name = None
        tags = None

        for line in message.content.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith('stl:'):
                stl_name = line[4:].strip()
            elif line.lower().startswith('bundle:'):
                bundle_name = line[7:].strip()
            elif line.lower().startswith('tags:'):
                tags = line[5:].strip()

        if not stl_name:
            await message.channel.send("❌ Missing STL name (use 'STL: Model Name')")
            return
        
        await message.add_reaction('✅')
        
    except connection.Error as e:
        await message.channel.send("❌ Database error - please try again later")
        print(f"Database error: {e}")  # Log for debugging
        
    except Exception as e:
        await message.channel.send("❌ Something went wrong - please check your input")
        print(f"Unexpected error: {e}")  # Log for debugging


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log'),
        logging.StreamHandler()
    ]
)
# to always keep the gallery channel empty

@bot.command()
async def debug_pending(ctx):
    """Show current pending submissions"""
    output = ["Current pending submissions:"]
    for msg_id, data in bot.pending_subs.items():
        output.append(f"- Prompt ID: {msg_id}, Data: {data}")
    await ctx.send('\n'.join(output)[:2000])
@bot.command()
async def debug_db(ctx):
    """Show database status"""
    try:
        # Get the MySQL connection from mysql_storage
        with mysql_storage.connection.cursor() as c:
            # Show list of tables
            c.execute("SHOW TABLES")
            tables = c.fetchall()

            # Get the count of records in the miniatures table
            c.execute("SELECT COUNT(*) FROM miniatures")
            count = c.fetchone()[0]

        # Send the result back to Discord
        await ctx.send(f"Tables in database: {tables}\nCount of miniatures: {count}")

        await ctx.send(
        f"Database status:\n"
        f"Tables: {', '.join(t[0] for t in tables)}\n"
        f"Submissions: {count}\n"
        f"Pending: {len(pending_submissions)}"
    )
    except Error as e:
        await ctx.send(f"❌ Database error: {e}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
    
# Last updated 03/25/2025 14:17:34

