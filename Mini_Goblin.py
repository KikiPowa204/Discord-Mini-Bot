import discord
from discord.ext import commands
import os
import hashlib
from datetime import datetime
from pathlib import Path
import sqlite3
from mini_storage import store_submission, is_duplicate
import logging

# Initialize global variables
pending_submissions = {}  # Format: {prompt_message_id: original_message_data}
DB_FILE = "miniatures.db"  # Database file path
print(f"Using database file: {DB_FILE}")
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
# Custom database module
import mini_storage  # Your database operations file


# Default settings
DEFAULTS = {
    'cleanup_mins': 10,
    'max_examples': 5,
    'submissions_chan': 'miniature-submissions',
    'gallery_chan': 'miniature-gallery'
}

# Runtime storage
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True  # Needed for message history

bot = commands.Bot(command_prefix='!', intents=intents)
bot.pending_subs = {}  # Single source for pending submissions
@bot.event
async def on_ready():
    bot.pending_subs = {}
    print(f'{bot.user.name} online!')
    # Initialize database
    mini_storage.init_db()
    
    # Find existing channels
    for guild in bot.guilds:
        bot.submit_chan = discord.utils.get(guild.channels, name=DEFAULTS['submissions_chan'])
        bot.gallery_chan = discord.utils.get(guild.channels, name=DEFAULTS['gallery_chan'])
        if bot.submit_chan and bot.gallery_chan:
            break

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx, cleanup_mins: int = DEFAULTS['cleanup_mins']):
    """Initializes bot channels"""
    # Create channels
    bot.submit_chan = await ctx.guild.create_text_channel(
        DEFAULTS['submissions_chan'],
        topic="Post your painted miniatures here"
    )
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
            
        # Handle image submissions
        if message.attachments and any(
            att.filename.lower().endswith(('.png','.jpg','.jpeg','.gif'))
            for att in message.attachments
        ):
            await process_image_submission(message)
        
        # Handle metadata replies
        elif message.reference:
            await handle_metadata_reply(message)
            
        await bot.process_commands(message)
        
    except Exception as e:
        logging.error(f"Error: {str(e)}", exc_info=True)
async def handle_metadata_reply(message):
    if not message.reference:
        logging.error("No message reference found")
        return
    
    try:
        # Log the current pending submissions
        logging.info(f"Pending submissions before processing: {bot.pending_subs}")
        
        # Get the pending submission from bot.pending_subs
        submission = bot.pending_subs.get(message.reference.message_id)
        if not submission:
            logging.error(f"No submission found for message {message.reference.message_id}")
            await message.channel.send("❌ Submission not found. Please post a new image.", delete_after=10)
            return
                
        # Parse metadata
        stl_name = None
        bundle_name = None
        tags = None
        
        for line in message.content.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'stl':
                    stl_name = value
                elif key == 'bundle':
                    bundle_name = value
                elif key == 'tags':
                    tags = value
        
        # Validate required fields
        if not stl_name:
            await message.channel.send("❌ Missing STL name (use 'STL: ModelName')", delete_after=10)
            return
            
        if not bundle_name:
            await message.channel.send("❌ Missing Bundle name (use 'Bundle: BundleName')", delete_after=10)
            return
        
        # Store submission
        mini_storage.store_submission(
            user_id=submission['user_id'],
            message_id=submission['original_msg_id'],
            image_url=submission['image_url'],
            stl_name=stl_name,
            bundle_name=bundle_name,
            tags=tags
        )
        
        # Cleanup
        try:
            await message.delete()
            if 'original_msg_id' in submission:
                original_msg = await message.channel.fetch_message(submission['original_msg_id'])
                pass  # No action needed for message deletion
            if 'prompt_id' in submission:
                prompt_msg = await message.channel.fetch_message(submission['prompt_id'])
                await prompt_msg.delete()
        except discord.NotFound:
            pass
            
        # Remove from pending submissions
        if message.reference.message_id in bot.pending_subs:
            del bot.pending_subs[message.reference.message_id]
            
        # Send confirmation
        await message.channel.send(
            f"✅ {stl_name} from {bundle_name} has been cataloged!" + 
            (f"\nTags: {tags}" if tags else ""),
            delete_after=15
        )
        
    except Exception as e:
        logging.error(f"Metadata processing failed: {str(e)}", exc_info=True)
        await message.channel.send(
            "❌ Failed to process your submission. Please use:\n"
            "STL: ModelName\nBundle: BundleName\nTags: optional",
            delete_after=15
        )
async def process_image_submission(message):
    try:
        image = message.attachments[0]
        image_url = image.url
        
        prompt = await message.channel.send(
            f"{message.author.mention} **Tag your miniature:**\n"
            "Reply to THIS message with:\n"
            "`STL: Model Name`\n"
            "`Bundle: Bundle Name`\n"
            "`Tags: tag1, tag2` (optional)",
            reference=message
        )
        
        # Store in bot.pending_subs
        bot.pending_subs[prompt.id] = {
            'user_id': message.author.id,
            'image_url': image_url,
            'original_msg_id': message.id,
            'prompt_id': prompt.id,
            'channel_id': message.channel.id
        }
        
        # Log the pending submissions
        logging.info(f"Pending submissions updated: {bot.pending_subs}")
        
    except Exception as e:
        logging.error(f"Image processing error: {e}")
        await message.channel.send("❌ Failed to process image", delete_after=5)    
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
        # Find the submission in bot.pending_subs
        submission = next(
            (v for k,v in bot.pending_subs.items() 
            if v['prompt_id'] == interaction.message.id),
            None
    )
    
        if not submission:
            await interaction.response.send_message("Submission expired", ephemeral=True)
            return
        
        store_submission(
        user_id=submission['user_id'],
        message_id=submission['original_msg_id'],
        image_url=submission['image_url'],
        stl_name=self.children[0].value,
        bundle_name=self.children[1].value,
        tags=self.children[2].value if self.children[2].value else None
    )
    
        await interaction.response.send_message("✅ Tagged successfully!", ephemeral=True)
    
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
        if not message.attachments:
            await message.channel.send("❌ Please attach an image!")
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
            
        # Store in database
        store_submission(
            user_id=message.author.id,
            message_id=message.id,
            image_url=image_url,
            stl_name=stl_name,
            bundle_name=bundle_name,
        )
        
        await message.add_reaction('✅')
        
    except sqlite3.Error as e:
        await message.channel.send("❌ Database error - please try again later")
        print(f"Database error: {e}")  # Log for debugging
        
    except Exception as e:
        await message.channel.send("❌ Something went wrong - please check your input")
        print(f"Unexpected error: {e}")  # Log for debugging

@bot.command(name='show')
async def show_examples(ctx, *, search_query: str):
    """Display miniatures matching the search term"""
    try:
        # Parse query (allow optional count like "lucian 3")
        parts = search_query.split()
        name = ' '.join(parts[:-1]) if len(parts) > 1 and parts[-1].isdigit() else search_query
        count = int(parts[-1]) if len(parts) > 1 and parts[-1].isdigit() else 5
        count = min(count, 10)  # Limit to 10 results max

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT image_url, stl_name, bundle_name 
                FROM miniatures
                WHERE stl_name LIKE ?
                ORDER BY RANDOM()
                LIMIT ?
            ''', (f'%{name}%', count))
            
            results = c.fetchall()

        if not results:
            return await ctx.send(f"No examples found for '{name}'", delete_after=15)

        for image_url, stl_name, bundle_name in results:
            try:
                embed = discord.Embed(
                    title=f"{stl_name}",
                    description=f"From {bundle_name}" if bundle_name else "",
                    color=0x3498db
                )
                embed.set_image(url=image_url)
                await ctx.send(embed=embed)
                
            except Exception as e:
                print(f"Error showing {stl_name}: {e}")
                await ctx.send(f"🖼️ **{stl_name}** (Image unavailable)")

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}", delete_after=10)
        logging.error(f"Show command failed: {str(e)}")
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log'),
        logging.StreamHandler()
    ]
)
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
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = c.fetchall()
        c.execute("SELECT COUNT(*) FROM miniatures")
        count = c.fetchone()[0]
        
    await ctx.send(
        f"Database status:\n"
        f"Tables: {', '.join(t[0] for t in tables)}\n"
        f"Submissions: {count}\n"
        f"Pending: {len(pending_submissions)}"
    )
if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))

# Last updated 03/25/2025 14:17:34
