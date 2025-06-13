import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from datetime import datetime
import logging
import asyncio
from typing import Optional
from discord.ext.commands import Bot
# Load environment variables first
from mysql.connector import Error
# Remove: import sqlite3
from mini_storage import mysql_storage
import aiomysql
import base64
import re
import binascii
import json

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

#async def get_guild_id(ctx: commands.Context) -> Optional[int]:
    """Safely retrieves the guild ID with proper typing and error handling."""
    if not ctx.guild:  # Check if in DMs
        await ctx.send("❌ This command only works in servers!")
        return False
    return ctx.guild.id

#async def get_guild_name(ctx: commands.Context) -> Optional[str]:
    """Safely retrieves the guild name with proper typing and error handling."""
    if not ctx.guild:
        await ctx.send("❌ This command only works in servers!")
        return False
    return ctx.guild.name

#@bot.command()
#async def test_guild_info(ctx):
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

#@bot.command()
#async def test_dm(ctx):
    """Verify DM handling"""
    await ctx.send(f"In DMs: ID={await get_guild_id(ctx)}, Name={await get_guild_name(ctx)}")

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
        
        # Find required channels with more flexible search
        submit_chan = discord.utils.find(lambda c: (
            c.name.lower() == DEFAULTS['submissions_chan'].lower() and 
            isinstance(c, discord.TextChannel)
        ), guild.channels)
        
        gallery_chan = discord.utils.find(lambda c: (
            c.name.lower() == DEFAULTS['gallery_chan'].lower() and 
            isinstance(c, discord.TextChannel)
        ), guild.channels)
        
        if submit_chan and gallery_chan:
            bot.channels[guild.id] = {
                'submit': submit_chan,
                'gallery': gallery_chan,
                'configured': True
            }
            print(f"✅ Found channels in {guild.name} (ID: {guild.id})")
            
            # Verify database schema
            async with mysql_storage.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        SELECT COLUMN_NAME 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME = 'miniatures' 
                        AND COLUMN_NAME = 'gallery_message_id'
                    """)
                    if not await cursor.fetchone():
                        print(f"⚠️ Adding gallery_message_id column for {guild.name}")
                        await cursor.execute("""
                            ALTER TABLE miniatures
                            ADD COLUMN gallery_message_id VARCHAR(20)
                        """)
                        await conn.commit()
        else:
            bot.channels[guild.id] = {'configured': False}
            missing = []
            if not submit_chan: missing.append(DEFAULTS['submissions_chan'])
            if not gallery_chan: missing.append(DEFAULTS['gallery_chan'])
            
            print(f"⚠️ Missing channels in {guild.name}: {', '.join(missing)}")

    print(f"\nBot fully initialized in {len([g for g in bot.channels.values() if g.get('configured')])}/{len(bot.guilds)} servers")
    print("Servers with proper setup:", ', '.join([str(gid) for gid, ch in bot.channels.items() if ch.get('configured')]))
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

        # Handle image submissions
        if message.guild.id in bot.channels:  # Check if guild has configured channels
            submit_channel = bot.channels[message.guild.id].get('submit')
        
        if submit_channel and message.channel == submit_channel:
            if message.attachments and any(
                att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))
                for att in message.attachments
            ):
                print("Bot recognises message in submit_chan")
                await process_submission(message)
    except Exception as e:
        logging.error(f"Error: {str(e)}", exc_info=True)    

@bot.command(name='guide')
async def get_help(ctx):
    """Display help information about bot commands"""
    embed = discord.Embed(
        title="Miniature Gallery Bot Help",
        description="Here are all the available commands:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="!setup",
        value="Admin only. Configures the submission and gallery channels for this server.",
        inline=False
    )
    
    embed.add_field(
        name="!store",
        value=(
            "Reply to a submission with this command, then include:\n"
            "```STL: ModelName (required)\n"
            "Bundle: BundleName (optional)\n"
            "Tags: tag1,tag2 (optional)```\n"
            "Each field should be on a new line."
        ),
        inline=False
    )
    
    embed.add_field(
        name="!show [search]",
        value=(
            "Search for miniatures in the gallery channel. Examples:\n"
            "• `!show Dragon` - Finds dragon miniatures\n"
            "• `!show Bundle: BundleName` - Shows bundle contents\n"
            "• `!show tags:fantasy` - Finds fantasy-tagged miniatures"
        ),
        inline=False
    )
    embed.add_field(
        name="!edit [STL:/Bundle:/Tags:]",
        value=(
            "Reply to a message and use command with above format.\n"
            "• `!edit STL: (new name)`\n"
            "• `!edit Bundle: (new bundle name)`\n"
            "• `!edit tags: (new tags)`"
        ),
        inline=False
    )

    embed.add_field(
        name="!del",
        value="Reply to a gallery post with this command to delete your submission (authors and admins only).",
        inline=False
    )
    
    embed.set_footer(text="Bot created by kiann.ardalan")
    
    await ctx.send(embed=embed)

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
            'image_url': json.dumps([a.url for a in submission.attachments]),
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

class AlbumView(View):
    def __init__(self, image_url):
        super().__init__(timeout=180)
        self.image_urls = image_url
        self.index = 0

    async def update_embed(self, interaction):
        embed = discord.Embed(title=f"Image {self.index+1} of {len(self.image_urls)}")
        embed.set_image(url=self.image_urls[self.index])
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.index = (self.index - 1) % len(self.image_urls)
        await self.update_embed(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        self.index = (self.index + 1) % len(self.image_urls)
        await self.update_embed(interaction)

@bot.command(name='del')
async def delete_submission(ctx):
    """Delete a submission by replying to its gallery post"""
    try:
        # Verify reply exists
        if not ctx.message.reference:
            await ctx.send("❌ Please reply to the gallery post you want to delete", delete_after=15)
            await ctx.message.delete()
            return
            
        # Get replied message
        replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        # Extract and validate embed
        if not replied_msg.embeds or not replied_msg.embeds[0].footer:
            await ctx.send("❌ Replied message is not a valid gallery post", delete_after=15)
            await ctx.message.delete()
            return
            
        # Extract and decode deletion ID
        embed = replied_msg.embeds[0]
        footer = embed.footer.text
        
        # More robust ID extraction
        match = re.search(r'DELETION_ID:([^\s:]+)', footer)
        if not match:
            await ctx.send("❌ Could not find valid deletion ID", delete_after=15)
            await ctx.message.delete()
            return
            
        encoded_id = match.group(1)
        
        try:
            # Fix padding and decode
            encoded_id = fix_base64_padding(encoded_id)
            decoded_id = base64.b64decode(encoded_id).decode('utf-8')
            
            # Split into components (assuming format "message_id:guild_id")
            deletion_parts = decoded_id.split(':')
            if len(deletion_parts) != 2:
                raise ValueError("Invalid ID format")
                
            message_id, guild_id = deletion_parts
            
        except (binascii.Error, ValueError) as e:
            await ctx.send(f"❌ Invalid ID format: {str(e)}", delete_after=15)
            await ctx.message.delete()
            return
        # Verify permissions and delete
        async with mysql_storage.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Just verify permission and existence - we already have the IDs we need
                await cursor.execute('''
                    SELECT 1 FROM miniatures 
                    WHERE message_id = %s 
                    AND guild_id = %s
                    AND (user_id = %s OR %s)
                ''', (
                    message_id,  # From earlier extraction
                    guild_id,   # From earlier extraction
                    str(ctx.author.id),
                    ctx.author.guild_permissions.manage_messages
                ))
                
                if not await cursor.fetchone():
                    await ctx.send("❌ Entry not found or no permission", delete_after=15)
                    await ctx.message.delete()
                    return

                # Delete gallery post if exists (using known IDs)
                await cursor.execute('''
                    SELECT gallery_message_id FROM miniatures
                    WHERE message_id = %s AND guild_id = %s
                ''', (message_id, guild_id))
                
                if gallery_msg_id := (await cursor.fetchone())[0]:
                    try:
                        gallery_channel = bot.channels[ctx.guild.id]['gallery']
                        gallery_msg = await gallery_channel.fetch_message(int(gallery_msg_id))
                        await gallery_msg.delete()
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        await ctx.send("❌ Bot lacks permissions to delete gallery message", delete_after=15)
                        return

                # Delete the database record
                await cursor.execute('''
                    DELETE FROM miniatures
                    WHERE message_id = %s AND guild_id = %s
                ''', (message_id, guild_id))
                
                await conn.commit()        

        
    except Exception as e:
        logging.error(f"Delete error: {str(e)}", exc_info=True)
    try:
        await ctx.message.add_reaction('❌')
        # DON'T delete here - let unified cleanup handle it
    except:
        pass

# Unified cleanup (runs whether success or error)
    try:
        if 'replied_msg' in locals() and replied_msg:  # Safer existence check
            await replied_msg.delete()
    except discord.NotFound:
        pass

    try:
    # Only add reaction if we didn't already add ❌
        if not isinstance(e, Exception):  # Only on success
            await ctx.message.add_reaction('🗑️')
    except:
        pass

    try:
        await ctx.message.delete(delay=2)
    except discord.NotFound:
        pass
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# async def clear_pending_submission(submission_id, timeout):
#     await asyncio.sleep(timeout)
#     if submission_id in bot.pending_subs:
#         del bot.pending_subs[submission_id]
#         logging.info(f"Cleared timed out submission {submission_id}")

@bot.command(name='store')
async def store_miniature(ctx):
    """Store a miniature from a replied-to message with metadata"""
    # Check if message is a reply
    if not ctx.message.reference:
        await ctx.send("❌ Please reply to an image message first", delete_after=10)
        await ctx.message.delete()
        return

    try:
        # Get original message
        original_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        # Verify image exists
        if not original_msg.attachments:
            await ctx.send("❌ Replied message has no image attachment", delete_after=10)
            await ctx.message.delete()
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
            await ctx.send("❌ STL name is required (format: `STL: ModelName`)", delete_after = 15)
            return

        # Prepare submission data
        submission_data = {
            'guild_id': str(ctx.guild.id),
            'user_id': str(ctx.author.id),
            'message_id': str(original_msg.id),
            'author': str(original_msg.author),
            'image_url': json.dumps([a.url for a in original_msg.attachments]),
            'channel_id': str(ctx.channel.id),
            'stl_name': metadata['stl_name'],
            'bundle_name': metadata['bundle_name'],
            'tags': metadata['tags']
        }

        # Debug output
        print(f"Storing submission: {submission_data}")

        # Store in database
        success = await mysql_storage.store_submission(**submission_data)
        
        try:
            if success:
                # Add checkmark reaction to the command message
                await ctx.message.add_reaction('✅')
                await original_msg.add_reaction('✅')
                # Send confirmation (will auto-delete)
                confirmation = await ctx.send(f"✅ Saved {metadata['stl_name']}!", delete_after=10)
                
                # Delete the original command message after 3 seconds
                await asyncio.sleep(3)
                await ctx.message.delete()
                
                # Optional: Delete the confirmation after it auto-deletes
                await confirmation.delete(delay=7)  # Matches the 10s total
            else:
                await ctx.message.add_reaction('❌')
                error_msg = await ctx.send("❌ Failed to store - please try again")
                await asyncio.sleep(5)
                await error_msg.delete()
                await ctx.message.delete()

        except discord.Forbidden:
            logging.warning(f"Missing permissions in {ctx.guild.id}")
        except discord.HTTPException as e:
            logging.error(f"Message cleanup failed: {e}")

    except Exception as e:
        logging.error(f"Store error: {e}")
        await ctx.send("❌ An error occurred - check your format and try again")

def fix_base64_padding(encoded_str):
    return encoded_str + "=" * ((4 - len(encoded_str) % 4) % 4)

@bot.command(name='show')
async def show_miniature(ctx, *, search_query: str = None):
    """Display 5 random miniatures in gallery channel"""
    try:
        # Verify gallery channel exists
        if ctx.guild.id not in bot.channels or 'gallery' not in bot.channels[ctx.guild.id]:
            await ctx.send("❌ Gallery channel not configured! Ask an admin to set one up.")
            return
            
        gallery_channel = bot.channels[ctx.guild.id]['gallery']
        
        # Determine search mode
        is_collection_search = search_query and search_query.startswith("Bundle:")
        is_tag_search = search_query and search_query.startswith("tags:")
        
        async with ctx.typing():
            async with mysql_storage.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    if is_collection_search:
                        bundle_name = search_query.split(":", 1)[1].strip() if ":" in search_query else None
                        if bundle_name:
                            await cursor.execute('''
                                SELECT * FROM miniatures
                                WHERE guild_id = %s
                                AND bundle_name LIKE %s
                                ORDER BY RAND()
                                LIMIT 5
                            ''', (str(ctx.guild.id), f'%{bundle_name}%'))
                        else:
                            await cursor.execute('''
                                SELECT * FROM miniatures
                                WHERE guild_id = %s
                                AND bundle_name IS NOT NULL
                                ORDER BY RAND()
                                LIMIT 5
                            ''', (str(ctx.guild.id),))
                            
                    elif is_tag_search:
                        tag_input = search_query.split(":", 1)[1].strip()
                        tags = [t.strip().lower() for t in tag_input.split(",") if t.strip()]
                        
                        # Build dynamic OR conditions for tags
                        conditions = []
                        params = [str(ctx.guild.id)]
                        for tag in tags:
                            conditions.append("(FIND_IN_SET(%s, tags) OR tags LIKE %s")
                            params.extend([tag, f'%{tag}%'])
                        
                        await cursor.execute(f'''
                            SELECT * FROM miniatures
                            WHERE guild_id = %s
                            AND ({' OR '.join(conditions)})
                            ORDER BY RAND()
                            LIMIT 5
                        ''', params)
                        
                    else:  # Default STL name search
                        search_term = search_query or ""
                        await cursor.execute('''
                            SELECT * FROM miniatures
                            WHERE guild_id = %s
                            AND (stl_name LIKE %s OR tags LIKE %s)
                            ORDER BY RAND()
                            LIMIT 5
                        ''', (str(ctx.guild.id), f'%{search_term}%', f'%{search_term}%'))

                    submissions = await cursor.fetchall()
                    if not submissions:
                        await ctx.message.delete()
                        await ctx.send(f"❌ No miniatures found{f' matching: {search_query}' if search_query else ''}", delete_after = 10)
                        return

                    # Send results to gallery channel
                    for sub in submissions:
                        embed = discord.Embed(
                            title=f"STL: {sub['stl_name']}",
                            description=f"Bundle: {sub['bundle_name'] or 'None'}",
                            color=discord.Color.blue()
                        )
                        image_urls = json.loads(sub['image_url'])  # This is now a list of URLs
                        embed.set_image(url=image_urls[0])  # Show the first image by default
                        encoded_id = base64.b64encode(f"{sub['message_id']}:{sub['guild_id']}".encode()).decode()
                        encoded_id = fix_base64_padding(encoded_id)
                        embed.set_footer(text=f"DELETION_ID:{encoded_id}\nBy: {sub['author']} | Tags: {sub['tags'] or 'None'}")
                        
                        view = AlbumView(image_urls)
                        msg = await gallery_channel.send(embed=embed, view=view)
                        # Update gallery_message_id in database
                        await cursor.execute('''
                            UPDATE miniatures
                            SET gallery_message_id = %s
                            WHERE message_id = %s AND guild_id = %s
                        ''', (str(msg.id), sub['message_id'], str(ctx.guild.id)))
                    
                    await conn.commit()
                    await ctx.send(f"✅ Displayed {len(submissions)} results in {gallery_channel.mention}",delete_after = 10)
                    await ctx.message.delete(delay=5)  # Delete command message after 5 seconds
    except Exception as e:
        logging.error(f"Show error: {e}", exc_info=True)
        await ctx.send("❌ Error searching miniatures", delete_after=15)
        await ctx.message.delete()

def fix_base64_padding(encoded_str):
    """Ensure base64 string has correct padding"""
    padding = len(encoded_str) % 4
    if padding:
        encoded_str += '=' * (4 - padding)
    return encoded_str

@bot.command(name='edit')
async def edit_submission(ctx):
    """Edit a submission's metadata"""
    try:
        # Validate command format
        if not ctx.message.content.strip()[5:]:  # 5 = len("!edit")
            await ctx.send("❌ Please include edit parameters (STL:/Bundle:/Tags:)", delete_after=15)
            await ctx.message.delete()
            return

        # Validate reply exists
        if not ctx.message.reference:
            await ctx.send("❌ Please reply to the gallery post you want to edit", delete_after=15)
            await ctx.message.delete()
            return

        # Get replied message
        replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        # Extract and decode deletion ID
        embed = replied_msg.embeds[0]
        footer = embed.footer.text
        
        # More robust ID extraction
        match = re.search(r'DELETION_ID:([^\s:]+)', footer)
        if not match:
            await ctx.send("❌ Could not find valid deletion ID", delete_after=15)
            await ctx.message.delete()
            return
            
        encoded_id = match.group(1)
        
        try:
            # Fix padding and decode
            encoded_id = fix_base64_padding(encoded_id)
            decoded_id = base64.b64decode(encoded_id).decode('utf-8')
            
            # Split into components (assuming format "message_id:guild_id")
            deletion_parts = decoded_id.split(':')
            if len(deletion_parts) != 2:
                raise ValueError("Invalid ID format")
                
            message_id, guild_id = deletion_parts
            
        except (binascii.Error, ValueError) as e:
            await ctx.send(f"❌ Invalid ID format: {str(e)}", delete_after=15)
            await ctx.message.delete()
            return

        # Parse edit parameters
        args = ctx.message.content.strip()[5:].strip()
        metadata = {
            'stl_name': None,
            'bundle_name': None,
            'tags': None
        }
        
        for line in args.split('\n'):
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

        # Validate at least one field is being updated
        if not any(metadata.values()):
            await ctx.send("❌ Provide at least one field to update (STL:/Bundle:/Tags:)", delete_after=15)
            await ctx.message.delete()
            return

        # Update database
        async with mysql_storage.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Verify permissions and update
                await cursor.execute('''
                    UPDATE miniatures
                    SET
                        stl_name = COALESCE(%s, stl_name),
                        bundle_name = COALESCE(%s, bundle_name),
                        tags = COALESCE(%s, tags)
                    WHERE message_id = %s 
                    AND guild_id = %s
                    AND (user_id = %s OR %s)
                ''', (
                    metadata['stl_name'],
                    metadata['bundle_name'],
                    metadata['tags'],
                    message_id,
                    guild_id,
                    str(ctx.author.id),
                    ctx.author.guild_permissions.manage_messages
                ))
                
                if cursor.rowcount == 0:
                    await ctx.send("❌ Submission not found or no permission", delete_after=10)
                    await ctx.message.delete()
                    return
                    
                await conn.commit()
        
        # Update gallery embed
        new_embed = discord.Embed(
            title=f"STL: {metadata['stl_name'] or embed.title.split(':')[1].strip()}",
            description=f"Bundle: {metadata['bundle_name'] or embed.description.split(':')[1].strip()}",
            color=embed.color
        )
        new_embed.set_image(url=embed.image.url)
        new_embed.set_footer(text=embed.footer.text)
        await replied_msg.edit(embed=new_embed)
        
        await ctx.message.add_reaction('✏️')
        await ctx.message.delete(delay=2)
        
    except Exception as e:
        logging.error(f"Edit error: {e}", exc_info=True)
        await ctx.message.add_reaction('❌')

@bot.command(name="opt out")
async def opt_out(ctx):
    """User opts out of having their submission stored"""
    pass

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

