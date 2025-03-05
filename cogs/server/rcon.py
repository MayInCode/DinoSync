import nextcord
from nextcord.ext import commands
from gamercon_async import EvrimaRCON
from util.config import RCON_HOST, RCON_PORT, RCON_PASS
import logging

class EvrimaRcon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rcon_host = RCON_HOST
        self.rcon_password = RCON_PASS
        self.rcon_port = RCON_PORT

    @nextcord.slash_command(
        description="Evrima RCON Commands",
        default_member_permissions=nextcord.Permissions(administrator=True),
        dm_permission=False
    )
    async def rcon(self, _interaction: nextcord.Interaction):
        pass

    @rcon.subcommand(description="Save the current state of the server.")
    async def saveserver(self, interaction: nextcord.Interaction):
        await interaction.response.send_message("Saving server...", ephemeral=True)
        command = b'\x02' + b'\x50' + b'\x00'
        response = await self.run_rcon(command)
        await interaction.followup.send(f"RCON response: {response}", ephemeral=True)

    @rcon.subcommand(description="Make an announcement on the server.")
    async def announce(self, interaction: nextcord.Interaction, message: str):
        command = b'\x02' + b'\x10' + message.encode() + b'\x00'
        response = await self.run_rcon(command)
        await interaction.response.send_message(f"RCON response: {response}", ephemeral=True)

    # Does not seem to be working as intended.
    # Will look into this further.
    @rcon.subcommand(description="Ban a player from the server.")
    async def banplayer(self, interaction: nextcord.Interaction, user_id: str, reason: str, ban_length: int):
        try:
            await interaction.response.send_message(f"Banning player with User ID {user_id} for {ban_length} hours.\nReason: {reason}", ephemeral=True)
            formatted_command = f"{user_id},{reason},{ban_length}"
            command = b'\x02' + b'\x20' + formatted_command.encode() + b'\x00'
            response = await self.run_rcon(command)
            await interaction.followup.send(f"RCON response: {response}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @rcon.subcommand(description="Kick a player from the server.")
    async def kickplayer(self, interaction: nextcord.Interaction, user_id: str, reason: str):
        await interaction.response.send_message(f"Kicking player with User ID {user_id}\nReason: {reason}", ephemeral=True)
        formatted_command = f"{user_id},{reason}"
        command = b'\x02' + b'\x30' + formatted_command.encode() + b'\x00'
        response = await self.run_rcon(command)
        await interaction.followup.send(f"RCON response: {response}", ephemeral=True)
    
    @rcon.subcommand(description="Display a list of players on the server.")
    async def playerlist(self, interaction: nextcord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            command = b'\x02' + b'\x40' + b'\x00'
            response = await self.run_rcon(command)
            await interaction.followup.send(f"RCON response: {response}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @rcon.subcommand(description="Update list of allowed playables.")
    async def updateplayables(self, interaction: nextcord.Interaction, message: str):
        command = b'\x02' + b'\x15' + message.encode() + b'\x00'
        response = await self.run_rcon(command)
        await interaction.response.send_message(f"RCON response: {response}", ephemeral=True)
        
    @rcon.subcommand(description="Get details about the server.")
    async def serverinfo(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)
        try:
            # Get server info
            command = b'\x02' + b'\x12' + b'\x00'
            response = await self.run_rcon(command)
            
            # Log raw response for debugging
            print(f"Raw server response: {response}")
            logging.info(f"Server info raw response: {response}")
            
            # Create a basic embed with the server info
            embed = nextcord.Embed(
                title="Server Information",
                description="Details about the game server",
                color=nextcord.Color.blue()
            )
            
            # Add the raw response to the embed in a code block
            if response:
                # Parse response to find server name
                server_name = "Unknown Server"
                if "ServerName:" in response:
                    name_part = response.split("ServerName:", 1)[1]
                    if "," in name_part:
                        server_name = name_part.split(",", 1)[0].strip()
                
                embed.add_field(
                    name="Server Name", 
                    value=server_name,
                    inline=False
                )
                    
                # Format the rest of the response
                formatted_response = response.replace(", ", "\n• ")
                formatted_response = "• " + formatted_response
                
                if len(formatted_response) > 1024:
                    # If response is too long, split it
                    parts = [formatted_response[i:i+1024] for i in range(0, len(formatted_response), 1024)]
                    for i, part in enumerate(parts):
                        embed.add_field(
                            name=f"Server Details (Part {i+1})" if i > 0 else "Server Details",
                            value=part,
                            inline=False
                        )
                else:
                    embed.add_field(name="Server Details", value=formatted_response, inline=False)
            else:
                embed.add_field(name="Error", value="No response from server", inline=False)
            
            # Add a thumbnail
            embed.set_thumbnail(url="https://raw.githubusercontent.com/dkoz/evrima-bot/refs/heads/main/assets/isle.png")
            
            # Add timestamp
            embed.timestamp = nextcord.utils.utcnow()
            
            # Send the embed
            await interaction.followup.send(embed=embed)
            print("Embed sent successfully")
            
        except Exception as e:
            # Log the error
            error_msg = f"Error in serverinfo command: {str(e)}"
            print(error_msg)
            logging.error(error_msg)
            import traceback
            traceback.print_exc()
            
            # Send error message
            try:
                await interaction.followup.send(f"An error occurred: {str(e)}\n\nRaw response: ```{response if 'response' in locals() else 'No response received'}```")
            except:
                try:
                    await interaction.followup.send("An error occurred while processing server information.")
                except:
                    pass

    @rcon.subcommand(description="Get details about a player.")
    async def playerinfo(self, interaction: nextcord.Interaction, user_id: str):
        await interaction.response.defer(ephemeral=True)
        command = b'\x02' + b'\x77' + user_id.encode() + b'\x00'
        response = await self.run_rcon(command)
        await interaction.followup.send(f"RCON response: {response}", ephemeral=True)

    @rcon.subcommand(description="Wipe all corpses from the server.")
    async def wipecorpses(self, interaction: nextcord.Interaction):
        command = b'\x02' + b'\x13' + b'\x00'
        response = await self.run_rcon(command)
        await interaction.response.send_message(f"RCON response: {response}", ephemeral=True)

    async def run_rcon(self, command):
        try:
            rcon = EvrimaRCON(self.rcon_host, self.rcon_port, self.rcon_password)
            await rcon.connect()
            return await rcon.send_command(command)
        except Exception as e:
            logging.error(f"Error running RCON command: {e}")
            return None

def setup(bot):
    cog = EvrimaRcon(bot)
    bot.add_cog(cog)
    if not hasattr(bot, 'all_slash_commands'):
        bot.all_slash_commands = []
    bot.all_slash_commands.extend([
        cog.rcon
    ])