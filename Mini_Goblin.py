import discord
from discord.ext import commands
import os
import hashlib
from datetime import datetime
import logging
import asyncio
from typing import Optional
from discord.ext.commands import Bot
# Load environment variables first
import mysql.connector
from mysql.connector import Error
# Remove: import sqlite3
from mini_storage import mysql_storage
import aiomysql

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
intents = discord.Intents.default()
intents.message_content = True
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

# In your database configuration (e.g., config.py or main bot file)
DB_CONFIG = {
    'host': 'your_mysql_host',  # Replace with actual host
    'user': 'your_username',
    'password': 'your_password',
    'db': 'your_database_name',
    'port': 3306  # Default MySQL port
}

# Runtime storage
intents=discord.Intents.all()
intents.message_content = True
intents.messages = True  # Needed to read messages

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
        return False
    return ctx.guild.id

async def get_guild_name(ctx: commands.Context) -> Optional[str]:
    """Safely retrieves the guild name with proper typing and error handling."""
    if not ctx.guild:
        await ctx.send("❌ This command only works in servers!")
        return False
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

async def get_db_connection():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = await aiomysql.connect(
                host=DB_CONFIG['host'],
                port=DB_CONFIG['port'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                db=DB_CONFIG['db'],
                cursorclass=aiomysql.DictCursor
            )
            return conn
        except Exception as e:
            logging.error(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1)

@bot.event
async def on_ready():
    # Initialize storage
    bot.channels = {}  # Now stores channels for ALL servers
    bot.pending_subs = {}  # Reset pending submissions
    
    print(f'{bot.user.name} online in {len(bot.guilds)} servers!')
    
    # Scan all servers
    for guild in bot.guilds:
        # Initialize database (if needed per server)
        await mysql_storage.init_db()
        
        # Find required channels
        submit_chan = discord.utils.get(guild.channels, name=DEFAULTS['submissions_chan'])
        gallery_chan = discord.utils.get(guild.channels, name=DEFAULTS['gallery_chan'])
        
        if submit_chan and gallery_chan:
            bot.channels[guild.id] = {
                'submit': submit_chan,
                'gallery': gallery_chan
            }
            print(f"✅ Found channels in {guild.name} (ID: {guild.id})")
        else:
            print(f"⚠️ Missing channels in {guild.name} - need both:")
            print(f"    - {DEFAULTS['submissions_chan']}")
            print(f"    - {DEFAULTS['gallery_chan']}")

    print(f"\nBot fully initialized in {len(bot.channels)}/{len(bot.guilds)} servers")
    print("Servers with proper setup:", ', '.join([str(gid) for gid in bot.channels.keys()]))
@bot.command(name='setup')
@commands.has_permissions(administrator=True)
async def setup_Channel(ctx, cleanup_mins: int = DEFAULTS['cleanup_mins']):
    """Initializes bot channels"""
    print ('in setup')
 
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
async def on_message(message):
    # Let commands process first
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
        if message.guild.id in bot.channels:
            if message.channel == bot.channels[message.guild.id]['submit']:    
            
                if message.attachments and any(
                att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))
                for att in message.attachments
        ):
                    print ("Bot recognises message in submit_chan")
                    await process_submission(message)
    except Exception as e:
        logging.error(f"Error: {str(e)}", exc_info=True)    

async def process_submission(submission: discord.Message):
    """Process a submission from the submissions channel"""
    try:
        # Validate message has attachments
        if not submission.attachments:
            await submission.channel.send("❌ Please include an image attachment", delete_after=10)
            return False

        submission_id = f"{submission.id}-{submission.author.id}"
        submission_data = {
            'guild_id': str(submission.guild.id),
            'user_id': str(submission.author.id),
            'message_id': str(submission.id),
            'author': str(submission.author),
            'image_url': submission.attachments[0].url,
            'channel_id': str(submission.channel.id),
            'stl_name': None,
            'bundle_name': None,
            'tags': None
        }
        bot.pending_subs[submission_id] = submission_data

        # Send prompt for metadata (don't auto-delete this one)
        prompt_msg = await submission.channel.send(
            f"{submission.author.mention} Please reply with:\n"
            "`STL: ModelName` (required)\n"
            "`Bundle: BundleName`\n"
            "`Tags: tag1,tag2`\n"
        )

        bot.pending_subs[submission_id]['prompt_id'] = prompt_msg.id

        def check(m):
            return (m.author == submission.author and 
                    m.channel == submission.channel and
                    m.reference and 
                    m.reference.message_id == prompt_msg.id)

        try:
            reply = await bot.wait_for('message', check=check, timeout=300)
            
            # Parse reply
            for line in reply.content.split('\n'):
                line = line.strip().lower()
                if line.startswith('stl:'):
                    bot.pending_subs[submission_id]['stl_name'] = line[4:].strip()
                elif line.startswith('bundle:'):
                    bot.pending_subs[submission_id]['bundle_name'] = line[7:].strip()
                elif line.startswith('tags:'):
                    bot.pending_subs[submission_id]['tags'] = line[5:].strip()

            # Validate required STL name
            if not bot.pending_subs[submission_id]['stl_name']:
                await prompt_msg.delete()
                await reply.delete()
                await submission.channel.send("❌ STL name is required", delete_after=15)
                del bot.pending_subs[submission_id]
                return False

            # Store in database
            success = await mysql_storage.store_submission(**{
                k: bot.pending_subs[submission_id][k] 
                for k in [
                    'guild_id', 'user_id', 'message_id', 'author',
                    'image_url', 'channel_id', 'stl_name',
                    'bundle_name', 'tags'
                ]
            })

            if success:
                # Cleanup messages
                try:
                    await prompt_msg.delete()
                    await reply.delete()
                except discord.NotFound:
                    pass  # Messages already deleted
                
                await submission.add_reaction('✅')
                return True
            else:
                await submission.channel.send("❌ Failed to store submission", delete_after=15)
                return False

        except asyncio.TimeoutError:
            try:
                await prompt_msg.delete()
            except discord.NotFound:
                pass
            await submission.channel.send("❌ Timed out waiting for details", delete_after=15)
            del bot.pending_subs[submission_id]
            return False

    except Exception as e:
        logging.error(f"Submission processing error: {e}")
        if submission_id in bot.pending_subs:
            try:
                if 'prompt_id' in bot.pending_subs[submission_id]:
                    prompt_msg = await submission.channel.fetch_message(
                        bot.pending_subs[submission_id]['prompt_id']
                    )
                    await prompt_msg.delete()
            except:
                pass
            del bot.pending_subs[submission_id]
        await submission.channel.send("❌ Error processing submission", delete_after=15)
        return False

    except Exception as e:
        logging.error(f"Submission processing error: {e}")
        if submission_id in bot.pending_subs:
            del bot.pending_subs[submission_id]
        await submission.channel.send("❌ Error processing submission", delete_after=15)
        return False
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

async def clear_pending_submission(submission_id, timeout):
    await asyncio.sleep(timeout)
    if submission_id in bot.pending_subs:
        del bot.pending_subs[submission_id]
        logging.info(f"Cleared timed out submission {submission_id}")

async def clear_pending_submission(
    submission_id: str, 
    timeout: float,
    bot_instance: Optional[Bot] = None
) -> None:
    """Safely clear submission after timeout with cancellation support."""
    try:
        await asyncio.sleep(timeout)
        
        if not hasattr(bot_instance, 'pending_subs'):
            logging.warning("No pending_subs dictionary found")
            return

        if submission_id in bot_instance.pending_subs:
            del bot_instance.pending_subs[submission_id]
            logging.info(f"Cleared submission {submission_id}")
            
    except asyncio.CancelledError:
        logging.debug(f"Submission {submission_id} completed early")
    except Exception as e:
        logging.error(f"Failed to clear submission {submission_id}: {str(e)}")

@bot.command(name='store')
async def store_miniature(ctx):
    """Store a miniature from a replied-to message with metadata"""
    # Check if message is a reply
    if not ctx.message.reference:
        await ctx.send("❌ Please reply to an image message first")
        return

    try:
        # Get original message
        original_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        # Verify image exists
        if not original_msg.attachments:
            await ctx.send("❌ Replied message has no image attachment")
            return

        # Parse command content
        lines = [line.strip() for line in ctx.message.content.split('\n') if line.strip()]
        metadata = {
            'stl_name': None,
            'bundle_name': None,
            'tags': None
        }

        for line in lines[1:]:  # Skip first line (!store)
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                if key == 'stl':
                    metadata['stl_name'] = value
                elif key == 'bundle':
                    metadata['bundle_name'] = value
                elif key == 'tags':
                    metadata['tags'] = value

        # Validate required fields
        if not metadata['stl_name']:
            await ctx.send("❌ STL name is required (format: `STL: ModelName`)")
            return

        # Prepare submission data
        submission_data = {
            'guild_id': str(ctx.guild.id),
            'user_id': str(ctx.author.id),
            'message_id': str(original_msg.id),
            'author': str(original_msg.author),
            'image_url': original_msg.attachments[0].url,
            'channel_id': str(ctx.channel.id),
            'stl_name': metadata['stl_name'],
            'bundle_name': metadata['bundle_name'],
            'tags': metadata['tags']
        }

        # Debug output
        print(f"Storing submission: {submission_data}")

        # Store in database
        success = await mysql_storage.store_submission(**submission_data)
        if success:
            await ctx.message.add_reaction('✅')
            await ctx.send(f"✅ Saved {metadata['stl_name']}!", delete_after=10)
        else:
            await ctx.send("❌ Failed to store - please try again")

    except Exception as e:
        logging.error(f"Store error: {e}")
        await ctx.send("❌ An error occurred - check your format and try again")

@bot.command(name='show')
async def show_miniature(ctx, stl_name: str):
    """Display a specific miniature with deletion metadata"""
    try:
        async with ctx.typing():
            # Search database
            async with mysql_storage.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute('''
                        SELECT * FROM miniatures
                        WHERE guild_id = %s
                        AND stl_name LIKE %s
                        LIMIT 1
                    ''', (str(ctx.guild.id), f'%{stl_name}%'))
                    submission = await cursor.fetchone()

            if not submission:
                await ctx.send(f"❌ No miniature found matching '{stl_name}'")
                return

            embed = discord.Embed(
    title=f"STL: {submission['stl_name']}",
    description=f"From bundle: {submission['bundle_name'] or 'No bundle specified'}",
    color=discord.Color.blue()
)
            
            # Add visible fields
            embed.set_author(name=f"Painted by {submission['author']}")
            embed.set_image(url=submission['image_url'])
            
            # Add hidden metadata for deletion
            embed.set_footer(text=f"DELETION_ID:{submission['message_id']}:{submission['guild_id']}")

            if submission['tags']:
                embed.add_field(name="Tags", value=submission['tags'], inline=False)
            
            await ctx.send(embed=embed)

    except Exception as e:
        logging.error(f"Error showing miniature: {e}")
        await ctx.send("❌ An error occurred while fetching this miniature")
        
    try:
        async with ctx.typing():
            # Determine search mode
            is_collection_search = stl_name and stl_name.startswith("collection:")
            bundle_name = stl_name.split(":", 1)[1] if is_collection_search and ":" in stl_name else None

            async with mysql_storage.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    if is_collection_search:
                        # Collection/bundle search
                        if bundle_name:
                            await cursor.execute('''
                                SELECT * FROM miniatures
                                WHERE guild_id = %s
                                AND bundle_name LIKE %s
                                ORDER BY stl_name
                                LIMIT 25
                            ''', (str(ctx.guild.id), f'%{bundle_name}%'))
                        else:
                            await cursor.execute('''
                                SELECT * FROM miniatures
                                WHERE guild_id = %s
                                AND bundle_name IS NOT NULL
                                ORDER BY bundle_name, stl_name
                                LIMIT 25
                            ''', (str(ctx.guild.id),))
                    else:
                        # Normal STL name search
                        search_term = stl_name or ""
                        await cursor.execute('''
                            SELECT * FROM miniatures
                            WHERE guild_id = %s
                            AND (stl_name LIKE %s OR tags LIKE %s)
                            ORDER BY stl_name
                            LIMIT 25
                        ''', (str(ctx.guild.id), f'%{search_term}%', f'%{search_term}%'))

                    submissions = await cursor.fetchall()

            if not submissions:
                await ctx.send(f"❌ No miniatures found{f' in bundle {bundle_name}' if is_collection_search and bundle_name else ''}")
                return

            # Format results
            for i in range(0, len(submissions), 5):  # 5 results per embed
                embed = discord.Embed(
                    title=f"Bundle: {bundle_name}" if is_collection_search and bundle_name 
                          else "All Bundled Miniatures" if is_collection_search
                          else f"Results for: {stl_name}" if stl_name
                          else "Recent Miniatures",
                    color=discord.Color.blue()
                )

                for sub in submissions[i:i+5]:
                    embed.add_field(
                        name=f"{sub['stl_name']}",
                        value=f"Bundle: {sub['bundle_name'] or 'None'}\n"
                              f"By: {sub['author']}\n"
                              f"[Image]({sub['image_url']}) | "
                              f"`ID: {sub['message_id']}`",
                        inline=False
                    )

                await ctx.send(embed=embed)

    except Exception as e:
        logging.error(f"Show error: {e}")
        await ctx.send("❌ Error searching miniatures")
@bot.command(name='show tag')
async def show_by_tag(ctx, *, tag_query: str = None):
    """Show random miniatures matching tags
    
    Examples:
    !show tag fantasy
    !show tag fantasy,creature
    !show tag       (shows completely random)
    """
    try:
        async with ctx.typing():
            async with mysql_storage.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    if tag_query:
                        # Search by specific tags
                        tags = [tag.strip() for tag in tag_query.split(",")]
                        await cursor.execute('''
                            SELECT * FROM miniatures
                            WHERE guild_id = %s
                            AND tags REGEXP %s
                            ORDER BY RAND()
                            LIMIT 5
                        ''', (str(ctx.guild.id), "|".join(tags)))
                    else:
                        # Show completely random if no tag specified
                        await cursor.execute('''
                            SELECT * FROM miniatures
                            WHERE guild_id = %s
                            ORDER BY RAND()
                            LIMIT 5
                        ''', (str(ctx.guild.id),))

                    submissions = await cursor.fetchall()

            if not submissions:
                await ctx.send(f"❌ No miniatures found{f' with tags: {tag_query}' if tag_query else ''}")
                return

            # Display each result as its own embed
            for sub in submissions:
                embed = discord.Embed(
                    title=f"{sub['stl_name']}",
                    description=f"From bundle: {sub['bundle_name'] or 'No bundle'}",
                    color=discord.Color.blue()
                )
                embed.set_image(url=sub['image_url'])
                
                if sub['tags']:
                    embed.add_field(name="Tags", value=sub['tags'], inline=False)
                
                embed.set_footer(text=f"ID: {sub['message_id']} | Found via tag search")
                await ctx.send(embed=embed)

    except Exception as e:
        logging.error(f"Tag search error: {e}")
        await ctx.send("❌ Error searching by tags")
@bot.command(name='del')
async def delete_submission(ctx):
    if not ctx.message.reference:
        await ctx.send("❌ Please reply to a !show result")
        return

    try:
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ Permission denied")
            return

        show_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        if show_message.author != bot.user or not show_message.embeds:
            await ctx.send("❌ Invalid target message")
            return

        # Extract hidden metadata from footer
        footer_text = show_message.embeds[0].footer.text
        if not footer_text.startswith("DELETION_ID:"):
            await ctx.send("❌ Not a deletable submission")
            return

        _, message_id, guild_id = footer_text.split(":")
        
        if guild_id != str(ctx.guild.id):
            await ctx.send("❌ Cross-server deletion not allowed")
            return

        # Database deletion
        async with mysql_storage.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    DELETE FROM miniatures 
                    WHERE message_id = %s AND guild_id = %s
                ''', (message_id, guild_id))
                await conn.commit()

        # Cleanup messages
        try:
            await ctx.channel.fetch_message(message_id).delete()
        except:
            pass
            
        await ctx.message.delete()
        await show_message.delete()
        await ctx.send("✅ Deleted", delete_after=2)

    except Exception as e:
        logging.error(f"Delete error: {e}")
        await ctx.send("❌ Deletion failed", delete_after=5)
        

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

