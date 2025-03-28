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
    """Initializes bot channels with comprehensive error handling"""
    try:
        print(f'Setup initiated in {ctx.guild.name} by {ctx.author}')

        # 1. Verify bot permissions
        if not ctx.guild.me.guild_permissions.manage_channels:
            raise commands.BotMissingPermissions(['manage_channels'])

        # 2. Initialize database
        if not mysql_storage.init_db(str(ctx.guild.id)):
            raise Exception("Database initialization failed")

        # 3. Channel setup with interactive prompts
        await ctx.send("🛠️ Starting setup process...")
        
        # Create channels with proper permissions
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                send_messages=True,  # Allow submissions
                read_message_history=True
            ),
            ctx.guild.me: discord.PermissionOverwrite(
                manage_messages=True,
                embed_links=True
            )
        }

        submissions_channel = await ctx.guild.create_text_channel(
            name=DEFAULTS['submissions_chan'],
            topic="Post your miniature submissions here",
            overwrites=overwrites,
            position=0  # Top position
        )

        gallery_overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                send_messages=False,  # Read-only
                read_messages=True
            )
        }

        gallery_channel = await ctx.guild.create_text_channel(
            name=DEFAULTS['gallery_chan'],
            topic="Approved miniature gallery",
            overwrites=gallery_overwrites,
            position=1  # Below submissions
        )

        # 4. Store configuration
        mysql_storage.store_guild_info(
            guild_id=str(ctx.guild.id),
            guild_name=ctx.guild.name,
            system_channel=str(ctx.guild.system_channel.id) if ctx.guild.system_channel else None,
            submissions_channel=str(submissions_channel.id),
            gallery_channel=str(gallery_channel.id),
            cleanup_mins=cleanup_mins
        )

        # 5. Final confirmation
        embed = discord.Embed(
            title="✅ Setup Complete",
            color=0x00ff00
        )
        embed.add_field(
            name="Submissions Channel",
            value=submissions_channel.mention,
            inline=False
        )
        embed.add_field(
            name="Gallery Channel",
            value=gallery_channel.mention,
            inline=False
        )
        embed.set_footer(text=f"Auto-cleanup: {cleanup_mins} minutes")
        
        await ctx.send(embed=embed)

    except commands.BotMissingPermissions as e:
        await ctx.send(f"❌ Missing required permissions: {', '.join(e.missing_permissions)}")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Setup timed out. Please restart the process.")
    except mysql.connector.Error as e:
        await ctx.send("🔴 Database error during setup. Check logs.")
        logging.error(f"Database error: {e}")
    except Exception as e:
        await ctx.send(f"⚠️ Unexpected error: {str(e)}")
        logging.exception("Setup failed:")
@bot.event
async def on_message(message):
    # Let commands process first
    if message.content.startswith('!'):
            await bot.process_commands(message)
            return
    # Handle metadata replies
    if (message.reference and 
        message.reference.message_id in 
        [v['prompt_msg_id'] for v in bot.pending_subs.values()]):
        await handle_metadata_reply(message)

async def handle_metadata_reply(message: discord.Message):
    """Process metadata replies with proper context handling"""
    
    # Validate guild context
    if not message.guild:
        await message.channel.send("❌ This only works in servers", delete_after=10)
        return

    guild_id = message.guild.id
    submission_id, submission = next(
        ((k, v) for k, v in bot.pending_subs.items() 
         if v.get('prompt_msg_id') == message.reference.message_id),
        (None, None)
    )

    if not submission:
        await message.channel.send("❌ Submission expired", delete_after=10)
        return

    # Parse metadata
    metadata = {
        'guild_id': str(guild_id),
        'user_id': str(submission['user_id']),
        'message_id': str(submission['original_msg_id']),
        'image_url': submission['image_url'],
        **parse_metadata_lines(message.content)  # New helper function
    }

    # Store to database
    if await store_submission(metadata):
        await message.add_reaction('✅')
        del bot.pending_subs[submission_id]
    else:
        await message.channel.send("❌ Failed to save", delete_after=10)

        
# Helper functions
async def parse_metadata_lines(content: str) -> dict:
    """Extract STL, bundle, and tags from message content"""
    result = {'stl_name': None, 'bundle_name': None, 'tags': ''}
    for line in content.split('\n'):
        line = line.strip().lower()
        if line.startswith('stl:'): 
            result['stl_name'] = line[4:].strip()
        elif line.startswith('bundle:'):
            result['bundle_name'] = line[7:].strip()
        elif line.startswith('tags:'):
            result['tags'] = line[5:].strip()
    return result

async def store_submission(data: dict) -> bool:
    """Database storage with connection handling"""
    query = """
        INSERT INTO miniatures 
        (guild_id, user_id, message_id, image_url, stl_name, bundle_name, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        async with mysql_storage.init_db() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (
                    data['guild_id'],
                    data['user_id'],
                    data['message_id'],
                    data['image_url'],
                    data['stl_name'],
                    data['bundle_name'],
                    data['tags']
                ))
            return True
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return False
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

async def process_image_submission(message):
    if not message.attachments:
        await message.channel.send("❌ No attachments found", delete_after=10)
        return

    for attachment in message.attachments:
        try:
            if not attachment.filename.lower().endswith(('.png','.jpg','.jpeg','.webp')):
                continue

            submission_id = f"{message.id}-{message.author.id}-{attachment.id}"
            
            # Store pending submission
            bot.pending_subs[submission_id] = {
                'user_id': message.author.id,
                'guild_id': str(message.guild.id),
                'channel_id': message.channel.id,
                'image_url': attachment.url,
                'original_msg_id': message.id,
                'attachment_id': attachment.id
            }

            # First ensure guild exists
            if not mysql_storage.store_guild_info(
                guild_id=str(message.guild.id),
                guild_name=message.guild.name,
                system_channel=message.guild.system_channel.id if message.guild.system_channel else None
            ):
                raise Exception("Failed to store guild info")

            # Send metadata prompt
            prompt_msg = await message.channel.send(
                f"{message.author.mention} Please reply with:\n"
                "`STL: ModelName`\n"
                "`Bundle: BundleName`\n"
                "`Tags: optional,tags`",
                delete_after=900
            )
            
            bot.pending_subs[submission_id]['prompt_msg_id'] = prompt_msg.id
            asyncio.create_task(clear_pending_submission(submission_id, timeout=900))

        except mysql.connector.Error as e:
            logging.error(f"Database error processing {attachment.filename}: {e}")
            await message.channel.send("❌ Database error - please try again later", delete_after=10)
        except Exception as e:
            logging.error(f"Failed to process {attachment.filename}: {e}")
            await message.channel.send(f"❌ Failed to process {attachment.filename}", delete_after=10)

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
       
async def handle_submission(message: discord.Message):
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

