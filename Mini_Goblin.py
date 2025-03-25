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

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
# Custom database module
import mini_storage  # Your database operations file

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Default settings
DEFAULTS = {
    'cleanup_mins': 10,
    'max_examples': 5,
    'submissions_chan': 'miniature-submissions',
    'gallery_chan': 'miniature-gallery'
}

# Runtime storage
bot.pending_subs = {}
bot.submit_chan = None
bot.gallery_chan = None

@bot.event
async def on_ready():
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
        return
    
    submission = pending_submissions.get(message.reference.message_id)
    if not submission:
        return
    
    try:
        lines = [line.strip() for line in message.content.split('\n') if line.strip()]
        stl_name = next((line[4:].strip() for line in lines if line.lower().startswith('stl:')), None)
        bundle_name = next((line[7:].strip() for line in lines if line.lower().startswith('bundle:')), None)
        
        if not stl_name or not bundle_name:
            await message.channel.send("❌ Must include both STL and Bundle!", delete_after=10)
            return
            
        store_submission(
            user_id=submission['user_id'],
            message_id=submission['original_msg_id'],
            image_url=submission['image_url'],
            stl_name=stl_name,
            bundle_name=bundle_name
        )
        
        # Cleanup
        try:
            await message.delete()
            await message.channel.delete_messages([
                discord.Object(id=submission['prompt_id']),
                discord.Object(id=submission['original_msg_id'])
            ])
        except discord.NotFound:
            pass
            
        del pending_submissions[message.reference.message_id]
        
    except Exception as e:
        logging.error(f"Metadata error: {e}")
        await message.channel.send("❌ Failed to save tags", delete_after=5)
async def process_image_submission(message):
    try:
        if not message.attachments:
            return
            
        image = message.attachments[0]
        if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            return
            
        image_url = image.url
        image_hash = hashlib.md5(image_url.encode()).hexdigest()
        
        if is_duplicate(image_hash):
            await message.channel.send("🛑 This image was already submitted!", delete_after=5)
            return
            
        prompt = await message.channel.send(
            f"{message.author.mention} **Tag your miniature:**\n"
            "Reply to THIS message with:\n"
            "`STL: Model Name`\n"
            "`Bundle: Bundle Name`\n"
            "`Tags: tag1, tag2`",
            reference=message
        )
        
        pending_submissions[prompt.id] = {
            'user_id': message.author.id,
            'image_url': image_url,
            'original_msg_id': message.id,
            'prompt_id': prompt.id
        }
        
    except Exception as e:
        logging.error(f"Error in process_image_submission: {str(e)}", exc_info=True)
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
        # Get the original submission
        original_id = next((k for k,v in pending_submissions.items() if v['prompt_id'] == interaction.message.id), None)
        if not original_id:
            await interaction.response.send_message("Submission expired. Please post a new image.", ephemeral=True)
            return
            
        submission = pending_submissions[original_id]
        
        # Store in database
        store_submission(
            user_id=submission['user_id'],
            message_id=submission['original_msg_id'],
            image_url=submission['image_url'],
            stl_name=self.children[0].value,
            bundle_name=self.children[1].value,
            tags=self.children[2].value
        )
        
        await interaction.response.send_message("✅ Miniature tagged successfully!", ephemeral=True)
       
async def handle_submission(message):
    try:
        # Validate input
        if not message.attachments:
            await message.channel.send("❌ Please attach an image!")
            return
            
        image_url = message.attachments[0].url
        
        # Parse metadata
        lines = [line.strip() for line in message.content.split('\n') if line.strip()]
        stl_name = next((line[4:].strip() for line in lines if line.lower().startswith('stl:')), None)
        bundle_name = next((line[7:].strip() for line in lines if line.lower().startswith('bundle:')), None)
        
        if not stl_name:
            await message.channel.send("❌ Missing STL name (use 'STL: Model Name')")
            return
            
        # Store in database
        store_submission(
            user_id=message.author.id,
            message_id=message.id,
            image_url=image_url,
            stl_name=stl_name,
            bundle_name=bundle_name
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
    """Search for examples with proper image display"""
    try:
        # Parse query
        parts = search_query.rsplit(maxsplit=1)
        model_name = parts[0] if len(parts) == 1 else ' '.join(parts[:-1])
        count = min(int(parts[-1]), 10) if len(parts) > 1 and parts[-1].isdigit() else 5

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT message_id, stl_name, bundle_name 
                FROM miniatures
                WHERE stl_name LIKE ?
                ORDER BY RANDOM()
                LIMIT ?
            ''', (f'%{model_name}%', count))
            
            results = c.fetchall()

        if not results:
            return await ctx.send(f"No examples found for '{model_name}'", delete_after=15)

        for msg_id, stl_name, bundle_name in results:
            try:
                # Fetch original message
                original_msg = await ctx.channel.fetch_message(msg_id)
                if original_msg.attachments:
                    # Re-upload the image properly
                    file = await original_msg.attachments[0].to_file()
                    embed = discord.Embed(
                        title=f"{stl_name}",
                        description=f"From {bundle_name}",
                        color=0x3498db
                    )
                    embed.set_image(url=f"attachment://{file.filename}")
                    await ctx.send(embed=embed, file=file)
                else:
                    # Fallback to URL if attachment missing
                    await ctx.send(f"🖼️ **{stl_name}**\n{original_msg.content}")
                    
            except discord.NotFound:
                # Message was deleted but DB record remains
                continue

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
    for msg_id, data in pending_submissions.items():
        output.append(f"- {msg_id}: {data.get('stl_name', 'Untagged')}")
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
