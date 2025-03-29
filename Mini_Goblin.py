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

# Use the connection to execute querie
cursor = connection.cursor()
cursor.execute("SELECT * FROM miniatures")
result = cursor.fetchall()  # Close cursor after fetching data
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
intents.messages = True  # Needed

def fetch_miniatures(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM miniatures")
    result = cursor.fetchall()
    cursor.close()  # Close cursor after fetching data
    return result

#works. Don't touch.
@bot.command(name='setup_DB')
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

@bot.event
async def on_ready():
    
    await mysql_storage.init_db()
    
    """Bot startup initialization"""
    print(f'{bot.user.name} online in {len(bot.guilds)} guilds!')
    bot.pending_subs = {}  # Reset pending submissions
    
    # Initialize databases for all current guilds
    for guild in bot.guilds:
        await mysql_storage.init_db()
        
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
    guild_id = await get_guild_id(ctx)
    await mysql_storage.init_db(guild_id)
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
    except Error as e:
        await ctx.send(f"❌ Error: {e} Submitted name couldn't be used")
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
@bot.event
async def message_organiser(message: discord.Message):
    # Let commands process first
    if message.content.startswith('!'):
        await bot.process_commands(message)
        return

    # Ensure the message is in the submissions channel and not from a bot
    if not bot.submit_chan or message.channel != bot.submit_chan or message.author.bot:
        return

    # Check if the message contains attachments
    if not message.attachments:
        await message.channel.send("❌ Please attach an image to your submission.", delete_after=30)
        return

    # Process the first valid attachment
    for attachment in message.attachments:
        if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            await process_submission(message)  # Use await for the async function
            return

    # If no valid attachment is found
    await message.channel.send("❌ Only image files (.png, .jpg, .jpeg, .gif) are allowed.", delete_after=30)
        

async def get_SBT(message: discord.Message):
    try:
        submission_data = {
            'user_id': message.author.id,
            'image_url': message.attachments[0].url if message.attachments else None,
            'guild_id': message.guild.id,
            'original_msg_id': message.id,
            'prompt_id': None,
            'channel_id': message.channel.id,
            'stl_name': None,
            'bundle_name': None,
            'tags': None
        }
        
        prompt = await message.channel.reply(
                f"{message.author.mention} Please reply with:\n"
                "`STL: ModelName`\n"
                "`Bundle: BundleName`\n"
                "`Tags: optional,tags`",
                delete_after=900
            )
        submission_data['prompt_id'] = prompt.id
        
        # Parse user input to fill the metadata
        def check(reply):
            return reply.author == message.author and reply.channel == message.channel
        
        try:
            user_reply = await bot.wait_for('message', timeout=300, check=check)  # Wait for 5 minutes
        except asyncio.TimeoutError:
            await message.channel.send("❌ You took too long to reply. Please try again.")
            return
        # Process the user's reply
        for line in user_reply.content.split('\n'):
            line = line.strip().lower()
            if line.startswith('stl:'):
                bot.pending_subs[prompt.id]['stl_name'] = line[4:].strip()
            elif line.startswith('bundle:'):
                bot.pending_subs[prompt.id]['bundle_name'] = line[7:].strip()
            elif line.startswith('tags:'):
                bot.pending_subs[prompt.id]['tags'] = line[5:].strip()
        
        # Confirm the submission
        await message.channel.send("✅ Submission updated with your input!", delete_after= 30)

        return submission_data
    except Exception as e:
        await message.channel.send(f"❌ An error occurred: {e}")
        
async def process_submission(self, submission: discord.Message):
    try:
        submission_data = await get_SBT(submission)
        
        submission_id = hashlib.md5(f"{submission.id}{submission.attachments[0].url}".encode()).hexdigest()

        if not submission_data:
            logging.error("Submission data is empty or invalid")
            return
    
        stl_name = submission_data.get('stl_name')
        bundle_name = submission_data.get('bundle_name')
        tags = submission_data.get('tags')
    
        #Store the submission in db
        await mysql_storage.store_submission(
        guild_id=submission_data['guild_id'],
            user_id=submission_data['user_id'],
            message_id=str(submission_data['original_msg_id']),
            author=submission.author.name,
            image_url=submission_data['image_url'],
            stl_name=stl_name,
            bundle_name=bundle_name,
            tags=tags
            )
        await connection.commit()
        
       # Start a timer to clear the pending submission after 10 minutes
        asyncio.create_task(clear_pending_submission(submission_id, 600))
    
    except Exception as e:
        logging.error(f"Error processing submission: {e}")
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

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
            await connection.commit()
            logging.info(f"Stored submission: {submission['stl_name']}")
            if success:
                await interaction.response.send_message("✅ Saved to database!", ephemeral=True)
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

