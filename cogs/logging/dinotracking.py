import nextcord
from nextcord.ext import commands, tasks
import paramiko
import os
import re
import asyncio
from datetime import datetime
import logging
from collections import defaultdict
from util.config import FTP_HOST, FTP_PASS, FTP_PORT, FTP_USER
from util.config import ENABLE_DINO_TRACKER, FILE_PATH, DINOTRACKER_CHANNEL

class DinoTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ftp_host = FTP_HOST
        self.ftp_port = FTP_PORT
        self.ftp_username = FTP_USER
        self.ftp_password = FTP_PASS
        self.filepath = FILE_PATH  # Same log file as chat logs
        self.dinotracker_channel_id = DINOTRACKER_CHANNEL
        self.last_position = None
        
        # Track active players and their dinos
        self.active_players = {}  # {steam_id: {"name": player_name, "dino": dino_type, "gender": gender, "growth": growth}}
        
        # Track dino counts by species
        self.dino_counts = defaultdict(int)
        
        # Message ID of the status message to update
        self.status_message_id = None

    @commands.Cog.listener()
    async def on_ready(self):
        print("DinoTracker cog is ready.")
        self.check_log.start()
        self.update_status.start()

    async def async_sftp_operation(self, operation, *args, **kwargs):
        loop = asyncio.get_event_loop()
        with paramiko.Transport((self.ftp_host, self.ftp_port)) as transport:
            transport.connect(username=self.ftp_username, password=self.ftp_password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                result = await loop.run_in_executor(None, operation, sftp, *args, **kwargs)
                return result
            finally:
                sftp.close()

    def read_file(self, sftp, filepath, last_position):
        with sftp.file(filepath, "r") as file:
            if last_position is None:
                file.seek(0, os.SEEK_END)
                last_position = file.tell()
            else:
                file.seek(last_position)
            file_content = file.read().decode()
            new_position = file.tell()
        return file_content, new_position

    def parse_join_leave_data(self, log_content):
        # Pattern for join data with existing save file
        join_pattern_existing = r"LogTheIsleJoinData.*?: (.*?) $$(\d+)$$ Joined The Server\. Save file found Dino: (.*?), Gender: (.*?), Growth: ([\d\.]+)"
        
        # Pattern for fresh spawn join
        join_pattern_fresh = r"LogTheIsleJoinData.*?: (.*?) $$(\d+)$$ Save file not found - Starting as fresh spawn. Class: (.*?), Gender: (.*?), Growth: ([\d\.]+)"
        
        # Updated pattern for leave data - make it more flexible too
        leave_pattern = r"LogTheIsleJoinData.*?: (.*?) $$(\d+)$$ Left The Server whilebeing safelogged, Was playing as: (.*?), Gender: (.*?), Growth: ([\d\.]+)"
        
        # Find all joins and leaves
        joins_existing = re.findall(join_pattern_existing, log_content)
        joins_fresh = re.findall(join_pattern_fresh, log_content)
        leaves = re.findall(leave_pattern, log_content)
        
        # Combine both types of joins
        joins = joins_existing + joins_fresh
        
        return joins, leaves

    def update_player_data(self, joins, leaves):
        changes = []
        
        # Process joins
        for join in joins:
            player_name, steam_id, dino_type, gender, growth = join
            
            # Clean up the dino type (remove BP_ prefix and _C suffix if present)
            dino_type = dino_type.replace("BP_", "").replace("_C", "")
            
            # Check if this is a new player or dino change
            if steam_id in self.active_players:
                old_dino = self.active_players[steam_id]["dino"]
                # Decrement the old dino count
                if old_dino in self.dino_counts:
                    self.dino_counts[old_dino] -= 1
                    if self.dino_counts[old_dino] <= 0:
                        del self.dino_counts[old_dino]
                
                changes.append(f"**{player_name}** changed to {dino_type} ({gender}, {float(growth):.2f} growth)")
            else:
                # Check if this is a fresh spawn based on the growth value
                if float(growth) == 0.25:  # Most fresh spawns are 0.25
                    changes.append(f"**{player_name}** joined as new {dino_type} ({gender}, fresh spawn)")
                else:
                    changes.append(f"**{player_name}** joined as {dino_type} ({gender}, {float(growth):.2f} growth)")
            
            # Update player data
            self.active_players[steam_id] = {
                "name": player_name,
                "dino": dino_type,
                "gender": gender,
                "growth": float(growth)
            }
            
            # Increment dino count
            self.dino_counts[dino_type] += 1
        
        # Process leaves - updated to handle the format with dino information
        for leave in leaves:
            player_name, steam_id, dino_type, gender, growth = leave
            
            # Clean up dino type
            dino_type = dino_type.replace("BP_", "").replace("_C", "")
            
            if steam_id in self.active_players:
                changes.append(f"**{player_name}** left (was {dino_type}, {float(growth):.2f} growth)")
                
                # Decrement dino count
                if dino_type in self.dino_counts:
                    self.dino_counts[dino_type] -= 1
                    if self.dino_counts[dino_type] <= 0:
                        del self.dino_counts[dino_type]
                
                # Remove player from active players
                del self.active_players[steam_id]
        
        return changes

    @tasks.loop(seconds=30)
    async def check_log(self):
        try:
            file_content, new_position = await self.async_sftp_operation(
                self.read_file, self.filepath, self.last_position
            )
            
            if self.last_position is not None and new_position > self.last_position:
                self.last_position = new_position
                
                # Parse the log content
                joins, leaves = self.parse_join_leave_data(file_content)
                
                # Update player data and get changes
                changes = self.update_player_data(joins, leaves)
                
                # Send changes to the channel if any
                if changes and len(changes) > 0:
                    channel = self.bot.get_channel(self.dinotracker_channel_id)
                    if channel:
                        for change in changes:
                            await channel.send(change)
            
            elif self.last_position is None:
                self.last_position = new_position
        
        except Exception as e:
            logging.error(f"Error in DinoTracker check_log: {str(e)}")
            import traceback
            traceback.print_exc()

    @tasks.loop(seconds=10)
    async def update_status(self):
        """Post or update a status message with current dino counts"""
        try:
            channel = self.bot.get_channel(self.dinotracker_channel_id)
            if not channel:
                return
            
            # Create status embed
            embed = nextcord.Embed(
                title="🦕 Active Dinosaurs 🦖",
                description=f"Total Players: {len(self.active_players)}",
                color=nextcord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            # Sort dinos by count (highest first)
            sorted_dinos = sorted(self.dino_counts.items(), key=lambda x: x[1], reverse=True)
            
            if sorted_dinos:
                dino_list = "\n".join([f"**{dino}**: {count}" for dino, count in sorted_dinos])
                embed.add_field(name="Species Distribution", value=dino_list, inline=False)
            else:
                embed.add_field(name="Species Distribution", value="No dinosaurs currently active", inline=False)
            
            # Update or send the status message
            if self.status_message_id:
                try:
                    status_message = await channel.fetch_message(self.status_message_id)
                    await status_message.edit(embed=embed)
                except (nextcord.NotFound, nextcord.HTTPException):
                    # Message was deleted or not found, send a new one
                    status_message = await channel.send(embed=embed)
                    self.status_message_id = status_message.id
            else:
                # First time sending the status message
                status_message = await channel.send(embed=embed)
                self.status_message_id = status_message.id
        
        except Exception as e:
            logging.error(f"Error updating dino status: {str(e)}")
            import traceback
            traceback.print_exc()

def setup(bot):
    from util.config import ENABLE_DINO_TRACKER
    
    if ENABLE_DINO_TRACKER:
        bot.add_cog(DinoTracker(bot))
    else:
        print("DinoTracker cog is disabled.")