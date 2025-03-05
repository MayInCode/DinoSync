import nextcord
from nextcord.ext import commands
from gamercon_async import EvrimaRCON
from util.config import RCON_HOST, RCON_PORT, RCON_PASS, ENABLE_CHAT_COMMANDS
import logging
import re

class ChatCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rcon_host = RCON_HOST
        self.rcon_password = RCON_PASS
        self.rcon_port = RCON_PORT
        logging.info("ChatCommands cog initialized")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from bots to prevent potential loops
        if message.author.bot:
            return
            
        # Check if this is a chat message forwarded from the game
        # The pattern matches messages formatted like "**PlayerName**: Message"
        pattern = r"\*\*(.*?)\*\*: (.*)"
        match = re.match(pattern, message.content)
        
        if match:
            player_name = match.group(1)
            chat_message = match.group(2)
            
            # Process !slay command
            if chat_message.strip().lower() == "!slay":
                logging.info(f"Player {player_name} used !slay command")
                await self.process_slay_command(player_name, message.channel)
    
    async def process_slay_command(self, player_name, response_channel):
        try:
            # First get the player list to find their ID
            player_id = await self.find_player_id(player_name)
            
            if player_id:
                # Execute the kill command via RCON
                result = await self.kill_player(player_id)
                await response_channel.send(f"Processed !slay command for {player_name} (ID: {player_id}). Result: {result}")
            else:
                await response_channel.send(f"Could not find player ID for {player_name}")
        except Exception as e:
            logging.error(f"Error processing !slay: {str(e)}")
            await response_channel.send(f"Error processing !slay command: {str(e)}")
    
    async def find_player_id(self, player_name):
        """Get player ID from player name using RCON playerlist command"""
        command = b'\x02' + b'\x40' + b'\x00'  # playerlist command
        response = await self.run_rcon(command)
        
        if not response:
            return None
            
        # Parse the player list to find the player ID
        # The format varies, but usually includes name and ID pairs
        # Example: PlayerName(ID: 12345678)
        player_pattern = re.compile(rf"{re.escape(player_name)}\s*$ID:\s*(\d+)$")
        matches = player_pattern.findall(response)
        
        if matches:
            return matches[0]  # Return the first matching ID
        return None
    
    async def kill_player(self, player_id):
        """Execute the kill player command via RCON"""
        # The exact command may vary based on your game server
        # For The Isle/Evrima, we assume this format:
        # Note: Verify the correct RCON command format for killing a player in your game
        command = b'\x02' + b'\x11' + f"{player_id}".encode() + b'\x00'
        return await self.run_rcon(command)
    
    async def run_rcon(self, command):
        try:
            rcon = EvrimaRCON(self.rcon_host, self.rcon_port, self.rcon_password)
            await rcon.connect()
            return await rcon.send_command(command)
        except Exception as e:
            logging.error(f"Error running RCON command: {e}")
            return None

def setup(bot):
    # Import the configuration directly
    from util.config import ENABLE_CHAT_COMMANDS
    
    if ENABLE_CHAT_COMMANDS:
        bot.add_cog(ChatCommands(bot))
    else:
        print("ChatCommands cog is disabled.")