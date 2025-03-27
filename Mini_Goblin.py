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

def get_guild_info(guild) -> Optional[dict]:
    """Safely extract guild information without GuildManager"""
    try:
        return {
            'id': str(guild.id),  # Convert to string for MySQL compatibility
            'name': guild.name,
            'channel': guild.system_channel.id if guild.system_channel else None,
            'member_count': guild.member_count
        }
    except AttributeError as e:
        print(f"⚠️ Failed to get guild info: {e}")
        return None
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


@bot.event
async def on_guild_join(guild):
    """Auto-initialize for new guilds"""
    try:
        db_path = mysql_storage.store_guild_info(guild)
        print(f"Initialized DB for {guild.id}")
        
        # Optional welcome message
        if guild.system_channel:
            await guild.system_channel.send(
        "Little Goblin is ready to steal your pics! Start with a !setup_Chan command!"
        )    
    except Exception as e:
        print(f"Failed to init DB for new guild: {str(e)}")
    
    # Optional: Send welcome message to system channel
    if guild.system_channel:
        await guild.system_channel.send(
            "Thanks for adding me! Use `!setup_DB` to configure submission channels."
        )
@bot.command()
async def check_db(ctx):
    """Verify database is working"""
    guild_id = ctx.guild_id
    db_path = mysql_storage.init_db()
    await ctx.send(f"✅ Guild database active at: `{db_path}`")
@bot.event
async def on_ready():
    """Bot startup initialization"""
    print(f'{bot.user.name} online in {len(bot.guilds)} guilds!')
    bot.pending_subs = {}  # Reset pending submissions
    
    # Initialize databases for all current guilds
    for guild in bot.guilds:
        mysql_storage.init_db()
        
    # Find existing channels (first guild with both channels wins)
    for guild in bot.guilds:
        bot.submit_chan = discord.utils.get(guild.channels, name=DEFAULTS['submissions_chan'])
        bot.gallery_chan = discord.utils.get(guild.channels, name=DEFAULTS['gallery_chan'])
        if bot.submit_chan and bot.gallery_chan:
            print(f"Found channels in {guild.name}")
            break
    else:
        print("Warning: No submission/gallery channels found")

@bot.command(name='setup')
@commands.has_permissions(administrator=True)
async def setup_Channel(ctx, cleanup_mins: int = DEFAULTS['cleanup_mins']):
    """Initializes bot channels"""
    print ('in setup')
    mysql_storage.init_db(ctx.guild_id)
    # Check if the bot has the necessary permissions
    bot_member = ctx.guild.get_member(bot.user.id)
    if not bot_member.guild_permissions.manage_channels:
        await ctx.send("❌ I need the 'Manage Channels' permission to set up channels.")
        return

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("Please enter the name of the submissions channel (or type 'default' to create a new one):")
    try:
        submit_response = await bot.wait_for('message', check=check, timeout=60)
        submit_channel_name = submit_response.content.strip()
    except asyncio.TimeoutError:
        await ctx.send("❌ Setup timed out. Please try again.")
        return

    # Handle submissions and gallery channels (existing logic remains unchanged)
    if submit_channel_name.lower() == 'default':
        bot.submit_chan = await ctx.guild.create_text_channel(
            DEFAULTS['submissions_chan'],
            topic="Post your painted miniatures here"
        )
    else:
        bot.submit_chan = discord.utils.get(ctx.guild.channels, name=submit_channel_name)
        if not bot.submit_chan:
            await ctx.send(f"❌ Channel '{submit_channel_name}' not found. Please try again.")
            return

    # Handle gallery channel
    bot.gallery_chan = await ctx.guild.create_text_channel(
        DEFAULTS['gallery_chan'],
        topic="Bot-generated painting examples"
        )

    # Set permissions
    await bot.submit_chan.set_permissions(ctx.guild.default_role, send_messages=True)
    await bot.gallery_chan.set_permissions(ctx.guild.default_role, send_messages=False)

    await ctx.send(
        f"✅ Setup complete!\n"
        f"- Submissions: {bot.submit_chan.mention}\n"
        f"- Gallery: {bot.gallery_chan.mention}\n"
        f"- Auto-cleanup: {cleanup_mins} minutes"
    )

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.event
async def on_message(message):
    try:
        if message.author == bot.user:
            return

        # Allow commands like !setup to bypass the channel restriction
        if message.content.startswith('!'):
            await bot.process_commands(message)
            return

        # Ensure the message is in the submissions channel
        if bot.submit_chan and message.channel != bot.submit_chan:
            return

        # Handle image submissions
        if message.attachments and any(
            att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))
            for att in message.attachments
        ):
            await process_image_submission(message)

        # Handle metadata replies
        elif message.reference:
            await handle_metadata_reply(message)

    except Exception as e:
        logging.error(f"Error: {str(e)}", exc_info=True)
async def handle_metadata_reply(message):
    guild_id = message.guild.id
    if not message.reference:
        logging.error("No message reference found")
        return
    
    try:
        if not message.reference:
            return
            
        # Find the original submission
        submission_id = next(
            (k for k,v in bot.pending_subs.items() 
             if v.get('prompt_msg_id') == message.reference.message_id),
            None
        )
        
        if not submission_id:
            return await message.channel.send("❌ No active submission found", delete_after=10)
            
        submission = bot.pending_subs[submission_id]
        
        metadata = {
        # From message object
        'guild_id': str(message.guild.id),
        'user_id': str(message.author.id),
        'message_id': str(message.id),
        'image_urls': [str(a.url) for a in message.attachments],
    
        # From user input
        'stl_name': None,
        'bundle_name': None,
        'tags': None,
    
        # Generated/optional
        'image_hash': None  # Could be generated later
        }
        
        for line in message.content.split('\n'):
            line = line.strip().lower()
            if line.startswith('stl:'):
                metadata['stl_name'] = line[4:].strip()
            elif line.startswith('bundle:'):
                metadata['bundle_name'] = line[7:].strip()
            elif line.startswith('tags:'):
                metadata['tags'] = line[5:].strip()
        
        # Validate required fields
        if not metadata['stl_name']:
            return await message.channel.send("❌ STL name is required", delete_after=300)
        if not metadata['bundle_name']:
            return await message.channel.send("❌ Bundle name is required", delete_after=300)
        
        # Store in MySQL
        success = mysql_storage.store_submission(
            guild_id=submission['guild_id'],
            user_id=submission['user_id'],
            message_id=submission['original_msg_id'],
            image_url=submission['image_url'],
            **metadata
        )
        
        if success:
            await message.add_reaction('✅')
            del bot.pending_subs[submission_id]  # Clean up
        else:
            await message.channel.send("❌ Failed to save submission", delete_after=10)
            
    except Exception as e:
        logging.error(f"Metadata handling error: {e}")
        await message.channel.send("❌ Processing failed", delete_after=10)

async def process_image_submission(message):
    # Add guild_id but make it optional
    if not message.attachments:
        await message.channel.send("❌ No attachments found", delete_after=10)
        return

    for attachment in message.attachments:  # Direct iteration
        try:
            if not attachment.filename.lower().endswith(('.png','.jpg','.jpeg','.webp')):
                continue  # Skip non-image files

            submission_id = f"{message.id}-{message.author.id}-{attachment.id}"
            
            bot.pending_subs[submission_id] = {
                'user_id': message.author.id,
                'guild_id': str(message.guild.id),
                'channel_id': message.channel.id,
                'image_url': attachment.url,
                'original_msg_id': message.id,
                'attachment_id': attachment.id
            }

            # Process each attachment individually
            await handle_attachment(attachment)

        except Exception as e:
            logging.error(f"Failed to process attachment {attachment.filename}: {e}")

    await message.channel.send(f"✅ Processed {len(message.attachments)} attachment(s)", delete_after=10)
async def clear_pending_submission(submission_id, timeout):
    await asyncio.sleep(timeout)
    if submission_id in bot.pending_subs:
        del bot.pending_subs[submission_id]
        logging.info(f"Cleared timed out submission {submission_id}")
  
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

@bot.command(name='del')
@commands.has_permissions(administrator=True)
async def delete_entry(ctx):
    """Remove an entry from the database by replying to the post"""
    if not ctx.message.reference:
        await ctx.send("❌ Please reply to the message you want to delete.", delete_after=10)
        return

    # Get the referenced message
    if ctx.message.reference:
        # If the command is a reply to a message, fetch the referenced message
        referenced_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        message_id = referenced_message.id
            
    if referenced_message.author == bot.user and referenced_message.embeds:
        embed = referenced_message.embeds[0]
    if embed.image and embed.image.url:
        image_url = embed.image.url
        try:
            with mysql.connector.connect(
                host="your_host",
                user="your_username",
                password="your_password",
                database="your_database"
            ) as conn:
                c = conn.cursor()
                c.execute("SELECT message_id FROM miniatures WHERE image_url = %s", (image_url,))
                result = c.fetchone()
                if result:
                    message_id = result[0]
                else:
                    await ctx.send("❌ No entry found for the referenced image.", delete_after=10)
                    return
        except mysql.connector.Error as e:
            await ctx.send(f"❌ Error accessing the database: {e}", delete_after=10)
            return            
        else:
            # If not a reply, assume the user provides the message ID directly
            if not ctx.message.content.strip().split(" ")[1:]:
                await ctx.send("❌ Please provide a message ID or reply to a message.", delete_after=10)
                return
        with connection.connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM miniatures WHERE message_id = ?", (message_id,))
            if c.rowcount == 0:
                await ctx.send(f"❌ No entry found for the referenced message.", delete_after=10)
                return
            conn.commit()

        await ctx.send(f"✅ Entry for the referenced message has been removed.", delete_after=10)
        
@bot.command(name='show')
async def show_examples(ctx, *, search_query: str = ""):
    """Display examples from MySQL"""
    submissions = mysql_storage.get_submissions(
        guild_id=str(ctx.guild.id),
        search_query=search_query.strip()
    )
    
    if not submissions:
        return await ctx.send(f"No results for '{search_query}'")
    
    for sub in submissions:
        embed = discord.Embed(
            title=sub['stl_name'],
            description=f"From {sub['bundle_name']}",
            color=0x3498db
        )
        embed.set_image(url=sub['image_url'])
        await ctx.send(embed=embed)
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
def gallery_janitor():
    async def cleanup_gallery():
        if not bot.gallery_chan:  # Ensure the gallery channel exists
            return
        try:
            async for message in bot.gallery_chan.history(limit=200):
                if message.author == bot.user:
                    await message.delete(delay=600)  # Deletes the bot's message after 10 minutes
                else:
                    await message.delete(delay=3600)  # Deletes other messages after 1 hour
        except Exception as e:
            logging.error(f"Gallery cleanup error: {e}")
        return cleanup_gallery
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

