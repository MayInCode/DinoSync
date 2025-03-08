import nextcord
from nextcord.ext import commands, tasks
import asyncio
from datetime import datetime
import re
import logging
from collections import defaultdict
from util.config import RCON_HOST, RCON_PORT, RCON_PASS
from util.config import ENABLE_DINO_TRACKER, DINOTRACKER_CHANNEL
from gamercon_async import EvrimaRCON

class DinoTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rcon_host = RCON_HOST
        self.rcon_port = RCON_PORT
        self.rcon_password = RCON_PASS
        self.dinotracker_channel_id = DINOTRACKER_CHANNEL
        
        # Debug info
        print(f"DinoTracker initialized with:")
        print(f"RCON Host: {self.rcon_host}")
        print(f"RCON Port: {self.rcon_port}")
        print(f"Channel ID: {self.dinotracker_channel_id}")
        
        # Track active players and their dinos
        self.active_players = {}  # {steam_id: {"name": player_name, "dino": dino_type, "gender": None, "growth": growth}}
        # Track dino counts by species
        self.dino_counts = defaultdict(int)
        # Message ID of the status message to update
        self.status_message_id = None
        
        # Known dinosaur species for categorization
        self.carnivores = [
            'Omniraptor',
            'Carnotaurus', 
            'Ceratosaurus',
            'Dilophosaurus',
            'Herrerasaurus',
            'Troodon',
            'Deinosuchus',
            'Pteranodon'  # Moved from flyers
        ]
        
        self.herbivores = [
            'Stegosaurus',
            'Dryosaurus',
            'Tenontosaurus',
            'Hypsilophodon',
            'Pachycephalosaurus',
            'Maiasaura',
            'Diabloceratops'
        ]
        
        self.omnivores = [  # New group
            'Gallimimus',
            'Beipiaosaurus'
        ]
        
        # Common name mappings (BP_Carno_C might show up instead of Carnotaurus)
        self.name_mappings = {
            # General prefixes/suffixes to clean
            'BP_': '',
            '_C': '',
            # Direct mappings
            'Utah': 'Omniraptor',
            'Utahraptor': 'Omniraptor',
            'Carno': 'Carnotaurus',
            'Cerato': 'Ceratosaurus', 
            'Dilo': 'Dilophosaurus',
            'Herrera': 'Herrerasaurus',
            'Deino': 'Deinosuchus',
            'Ptera': 'Pteranodon',
            'Stego': 'Stegosaurus',
            'Dryo': 'Dryosaurus',
            'Teno': 'Tenontosaurus',
            'Hypsi': 'Hypsilophodon',
            'Pachy': 'Pachycephalosaurus',
            'Maia': 'Maiasaura',
            'Diablo': 'Diabloceratops',
            'Beipi': 'Beipiaosaurus',
            'Galli': 'Gallimimus'
        }

    @commands.Cog.listener()
    async def on_ready(self):
        print("DinoTracker cog is ready.")
        self.update_player_info.start()
        self.update_status.start()
    
    def normalize_dino_name(self, dino_type):
        """Normalize dinosaur names to their full proper names"""
        if not dino_type:
            return "Unknown"
            
        print(f"Normalizing dino name: {dino_type}")
        
        # First remove BP_ prefix and _C suffix
        cleaned_name = dino_type.replace("BP_", "").replace("_C", "")
        print(f"  After removing prefixes/suffixes: {cleaned_name}")
        
        # Check direct mappings
        if cleaned_name in self.name_mappings:
            result = self.name_mappings[cleaned_name]
            print(f"  Found mapping: {cleaned_name} -> {result}")
            return result
            
        # Return the cleaned name if no mapping found
        print(f"  No mapping found, using: {cleaned_name}")
        return cleaned_name

    async def get_player_list(self):
        """Get the list of players currently on the server using RCON"""
        print("Getting player list...")
        try:
            rcon = EvrimaRCON(self.rcon_host, self.rcon_port, self.rcon_password)
            print("Connecting to RCON...")
            await rcon.connect()
            print("RCON connected successfully")
            
            # Use the RCON_GETPLAYERLIST opcode (0x40)
            command = b'\x02' + b'\x40' + b'\x00'
            print("Sending GETPLAYERLIST command (0x40)")
            response = await rcon.send_command(command)
            print(f"RCON response: {response}")
            
            # Parse the response with the actual format
            player_data = []
            
            if "PlayerList" in response:
                # Split the response into lines
                lines = response.strip().split('\n')
                if len(lines) > 1:
                    # Skip the first line which is "PlayerList"
                    # The remaining lines should come in pairs: SteamID, then Name
                    for i in range(1, len(lines) - 1, 2):
                        if i + 1 < len(lines):  # Make sure we have both ID and name
                            steam_id = lines[i].strip().replace(',', '')
                            player_name = lines[i + 1].strip().replace(',', '')
                            
                            print(f"  Player: {player_name}, Steam ID: {steam_id}")
                            player_data.append({
                                "name": player_name,
                                "steam_id": steam_id
                            })
            
            print(f"Found {len(player_data)} players in response")
            return player_data
        except Exception as e:
            print(f"Error getting player list: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    async def get_player_info(self, player_name):
        """Get detailed information about a specific player"""
        print(f"Getting info for player: {player_name}")
        try:
            rcon = EvrimaRCON(self.rcon_host, self.rcon_port, self.rcon_password)
            await rcon.connect()
            
            # Use the RCON_GETPLAYERDATA opcode (0x77) followed by player name
            # We need to encode the player name and properly format the binary command
            player_name_bytes = player_name.encode('utf-8')
            command = b'\x02' + b'\x77' + player_name_bytes
            
            print(f"Sending GETPLAYERDATA command (0x77) for {player_name}")
            response = await rcon.send_command(command)
            print(f"RCON response: {response}")
            
            # Parse the response to extract player information
            pattern = r"PlayerDataName: (.*?), PlayerID: (\d+), Location: .*?, Class: (.*?), Growth: ([\d\.]+), Health: ([\d\.]+), Stamina: ([\d\.]+), Hunger: ([\d\.]+), Thirst: ([\d\.]+)"
            match = re.search(pattern, response)
            
            if match:
                name, steam_id, dino_class, growth, health, stamina, hunger, thirst = match.groups()
                normalized_dino = self.normalize_dino_name(dino_class)
                
                player_info = {
                    "name": name,
                    "steam_id": steam_id,
                    "dino": normalized_dino,
                    "growth": float(growth),
                    "health": float(health),
                    "stamina": float(stamina),
                    "hunger": float(hunger),
                    "thirst": float(thirst)
                }
                
                print(f"Player info extracted: {player_info}")
                return player_info
            else:
                print(f"Failed to match pattern in response for {player_name}")
                print(f"Response was: {response}")
                return None
        except Exception as e:
            print(f"Error getting player info for {player_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    @tasks.loop(minutes=1)  # Changed to 1 minute interval
    async def update_player_info(self):
        """Update player information using RCON commands"""
        print("\n--- Updating player info ---")
        try:
            # Get list of current players
            current_players = await self.get_player_list()
            current_steam_ids = {player['steam_id'] for player in current_players}
            
            print(f"Current players: {len(current_players)}")
            print(f"Previously tracked players: {len(self.active_players)}")
            
            # Find players who left
            for steam_id in list(self.active_players.keys()):
                if steam_id not in current_steam_ids:
                    # Player left
                    left_player = self.active_players[steam_id]
                    dino_type = left_player.get('dino')
                    print(f"Player left: {left_player['name']} (Steam ID: {steam_id}) as {dino_type}")
                    
                    if dino_type and dino_type in self.dino_counts:
                        self.dino_counts[dino_type] -= 1
                        print(f"  Decreased count for {dino_type} to {self.dino_counts[dino_type]}")
                        if self.dino_counts[dino_type] <= 0:
                            print(f"  Removed {dino_type} from counts (zero players)")
                    
                    # Remove from active players
                    del self.active_players[steam_id]
            
            # Get info for current players
            for player in current_players:
                steam_id = player['steam_id']
                player_name = player['name']
                
                print(f"Getting detailed info for player: {player_name}")
                # Get detailed info
                player_info = await self.get_player_info(player_name)
                if player_info:
                    dino_type = player_info['dino']
                    growth = player_info['growth']
                    
                    # Check if player is new or changed dinos
                    if steam_id not in self.active_players:
                        # New player
                        print(f"New player joined: {player_name} as {dino_type}")
                        self.active_players[steam_id] = player_info
                        self.dino_counts[dino_type] += 1
                        print(f"  Increased count for {dino_type} to {self.dino_counts[dino_type]}")
                    else:
                        # Existing player - check if they changed dinos
                        old_dino = self.active_players[steam_id].get('dino')
                        if old_dino != dino_type:
                            # Changed dinos
                            print(f"Player changed dinos: {player_name} from {old_dino} to {dino_type}")
                            
                            if old_dino:
                                self.dino_counts[old_dino] -= 1
                                print(f"  Decreased count for {old_dino} to {self.dino_counts[old_dino]}")
                            
                            self.dino_counts[dino_type] += 1
                            print(f"  Increased count for {dino_type} to {self.dino_counts[dino_type]}")
                        else:
                            print(f"Player still active: {player_name} as {dino_type}")
                        
                        # Update player info
                        self.active_players[steam_id] = player_info
                else:
                    print(f"Could not get detailed info for player: {player_name}")
            
            print(f"Current dino counts: {dict(self.dino_counts)}")
            print(f"Active players: {len(self.active_players)}")
        
        except Exception as e:
            print(f"Error updating player info: {str(e)}")
            import traceback
            traceback.print_exc()
    
    @update_player_info.before_loop
    async def before_update_player_info(self):
        await self.bot.wait_until_ready()
        print("Bot is ready, starting player info updates")
    
    @tasks.loop(minutes=1)  # Changed to 1 minute interval
    async def update_status(self):
        """Post or update a status message with current dino counts"""
        print("\n--- Updating status message ---")
        try:
            channel = self.bot.get_channel(self.dinotracker_channel_id)
            if not channel:
                print(f"Channel not found: {self.dinotracker_channel_id}")
                return
                
            # Get local time and format it
            local_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            
            # Create status embed without timestamp
            embed = nextcord.Embed(
                title="🦕 Active Dinosaurs 🦖",
                description=f"Total Players: {len(self.active_players)}",
                color=nextcord.Color.green()
            )
            
            # Always show all dinosaurs, even if count is 0
            print("Creating embed with all dinosaur types")
            
            # Add carnivores section
            carnivore_text = ""
            for dino in self.carnivores:
                count = self.dino_counts.get(dino, 0)
                carnivore_text += f"**{dino}**: {count}\n"
            
            if carnivore_text:
                print(f"Adding carnivores section")
                embed.add_field(name="🍖 Carnivores", value=carnivore_text, inline=False)
            
            # Add herbivores section
            herbivore_text = ""
            for dino in self.herbivores:
                count = self.dino_counts.get(dino, 0)
                herbivore_text += f"**{dino}**: {count}\n"
            
            if herbivore_text:
                print(f"Adding herbivores section")
                embed.add_field(name="🌿 Herbivores", value=herbivore_text, inline=False)
            
            # Add omnivores section
            omnivore_text = ""
            for dino in self.omnivores:
                count = self.dino_counts.get(dino, 0)
                omnivore_text += f"**{dino}**: {count}\n"
            
            if omnivore_text:
                print(f"Adding omnivores section")
                embed.add_field(name="🍽️ Omnivores", value=omnivore_text, inline=False)
            
            # Add uncategorized section for any dinosaurs not in our lists
            uncategorized_text = ""
            for dino, count in self.dino_counts.items():
                if (dino not in self.carnivores and 
                    dino not in self.herbivores and 
                    dino not in self.omnivores):
                    uncategorized_text += f"**{dino}**: {count}\n"
            
            if uncategorized_text:
                print(f"Adding uncategorized section")
                embed.add_field(name="🦖 Other", value=uncategorized_text, inline=False)
            
            # Custom footer with local time
            embed.set_footer(text=f"Last updated: {local_time}")
            
            # Update or send the status message
            if self.status_message_id:
                try:
                    print(f"Attempting to update existing message: {self.status_message_id}")
                    status_message = await channel.fetch_message(self.status_message_id)
                    await status_message.edit(embed=embed)
                    print("Status message updated successfully")
                except nextcord.NotFound:
                    # Message was deleted or not found, fetch the most recent message
                    print("Status message not found, fetching the most recent message")
                    async for message in channel.history(limit=1):
                        if message.author == self.bot.user:
                            self.status_message_id = message.id
                            await message.edit(embed=embed)
                            print("Most recent message updated successfully")
                            return
                    # If no message found, send a new one
                    print("No previous message found, sending new one")
                    status_message = await channel.send(embed=embed)
                    self.status_message_id = status_message.id
                    print(f"New status message ID: {self.status_message_id}")
            else:
                # First time sending the status message
                print("First time sending status message")
                async for message in channel.history(limit=1):
                    if message.author == self.bot.user:
                        self.status_message_id = message.id
                        await message.edit(embed=embed)
                        print("Most recent message updated successfully")
                        return
                # If no message found, send a new one
                status_message = await channel.send(embed=embed)
                self.status_message_id = status_message.id
                print(f"New status message ID: {self.status_message_id}")
        except Exception as e:
            print(f"Error updating dino status: {str(e)}")
            import traceback
            traceback.print_exc()

    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()
        print("Bot is ready, starting status updates")
    
    def cog_unload(self):
        print("DinoTracker cog unloading")
        self.update_player_info.cancel()
        self.update_status.cancel()

def setup(bot):
    from util.config import ENABLE_DINO_TRACKER
    if ENABLE_DINO_TRACKER:
        bot.add_cog(DinoTracker(bot))
        print("DinoTracker cog loaded and enabled")
    else:
        print("DinoTracker cog is disabled.")