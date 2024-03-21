import discord
import shutil
import os
import geopy
from geopy.distance import geodesic
from staticmap import StaticMap, CircleMarker
from math import pi, log, tan, cos
from PIL import Image, ImageDraw
from io import BytesIO
from numpy import random
from typing import Optional, Literal
import json
import time
from random import randint

# check if there is a token and a cards file
if not os.path.exists("TOKEN"):
    print("Please enter the bot token in the file named 'TOKEN'")
    exit()
    
with open("TOKEN", "r") as file:
    TOKEN = file.read()
    
if TOKEN == "":
    print("Please enter the bot token in the file named 'TOKEN'")
    exit()

if not os.path.exists("cards.json"):
    print("The cards.json file does not exist. Please download it.")
    exit()

# set the global variables
global players, Double_IsActive, Card_IsActive, Veto_IsActive, Current_Card, Veto_EndTime, FullRoundDone
Double_IsActive = False
Card_IsActive = False
Veto_IsActive = False
Current_Card = None
Veto_EndTime = 0
FullRoundDone = False

# set up the discord bot
intents = discord.Intents.all()
intents.message_content = True

# took this from https://github.com/TheExplainthis/ChatGPT-Discord-Bot/blob/main/src/discordBot.py and edited it a bit, though it is quite generic
class DiscordClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.synced = False
        self.added = False
        self.tree = discord.app_commands.CommandTree(self)
        self.activity = discord.Activity(type=discord.ActivityType.playing, name="Jet Lag The Game!")

    async def on_ready(self):
        await self.wait_until_ready()
        print("Syncing")
        if not self.synced:
            await self.tree.sync()
            self.synced = True
        if not self.added:
            self.added = True
        print(f"Synced, {self.user} is running!")
        # check if there is a main channel
        if not any([channel.name == "main" for channel in self.get_all_channels()]):
            print("""There is no "main" channel. Please create one.""")
            exit()
        
client = DiscordClient()

def get_coords(city):
    """Get the lat and lon of a location"""
    geolocator = geopy.Nominatim(user_agent="jetlag")
    location = geolocator.geocode(city)
    return {'lat': location.latitude, 'lon': location.longitude}

def download_map_with_points(points):
    """Download a map with the given points and areas on it. The first point is the center, the second is red, the third is green and the fourth is yellow."""
    width, height = 1600, 1200
    static_map = StaticMap(width, height)

    def point_to_coords(point):
        """Took this from the static map library and edited it down. Converts the lat and lon to the x and y coords on the map image."""
        if not (-180 <= point['lon'] <= 180):
            point['lon'] = (point['lon'] + 180) % 360 - 180
        x = ((point['lon'] + 180.) / 360) * pow(2, static_map.zoom)
        px = int(round((x - static_map.x_center) * static_map.tile_size + static_map.width / 2))
        
        if not (-90 <= point['lat'] <= 90):
            point['lat'] = (point['lat'] + 90) % 180 - 90
        y = (1-log(tan(point['lat']*pi/180) + 1/cos(point['lat']*pi/180))/pi)/2*pow(2, static_map.zoom)
        py = int(round((y - static_map.y_center) * static_map.tile_size + static_map.height / 2))
        
        return px, py
    
    for num, point in enumerate(points):
        static_map.add_marker(CircleMarker((point['lon'], point['lat']), ["black", "red", "green", "yellow"][num], 20))
    
    image = static_map.render()

    
    center, red, green, yellow = [point_to_coords(point) for point in points]
    # win areas
    rw1 = (center[0]-(center[0]-(red[0] + yellow[0]) / 2)*250, center[1]-(center[1]-(red[1] + yellow[1]) / 2)*250)
    rw2 = (center[0]-(center[0]-(red[0] + green[0]) / 2)*250, center[1]-(center[1]-(red[1] + green[1]) / 2)*250)
    gw1 = (center[0]-(center[0]-(green[0] + yellow[0]) / 2)*250, center[1]-(center[1]-(green[1] + yellow[1]) / 2)*250)
    gw2 = (center[0]-(center[0]-(green[0] + red[0]) / 2)*250, center[1]-(center[1]-(green[1] + red[1]) / 2)*250)
    yw1 = (center[0]-(center[0]-(red[0] + yellow[0]) / 2)*250, center[1]-(center[1]-(red[1] + yellow[1]) / 2)*250)
    yw2 = (center[0]-(center[0]-(green[0] + yellow[0]) / 2)*250, center[1]-(center[1]-(green[1] + yellow[1]) / 2)*250)
    
    # overlay the area between center, green and gw with green at a 50% opacity
    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon([center, rw1, rw2], fill=(150, 0, 0, 100))
    draw.polygon([center, gw1, gw2], fill=(0, 150, 0, 100))
    draw.polygon([center, yw1, yw2], fill=(150, 150, 0, 100))
    image = Image.alpha_composite(image.convert('RGBA'), overlay)
    return image

def defer(func):
    """apply "await interaction.response.defer()" to function using decorator. (this should only be done once (but then sometimes twice???). I have no idea how the heck this works but it does so fine i guess.)"""
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        await interaction.response.defer()
        await func(interaction, *args, **kwargs)
    return wrapper

class Checks:
    """Checking decorators for the commands. Class based for easy use."""
    def admin_only(func):
        """Check if user has admin permissions"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send(f"You don't have permission to use this command, {interaction.user.mention}")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def main_channel_only(func):
        """Check if the command is used in the main channel"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not interaction.channel.name == "main":
                await interaction.followup.send(f"You can't use this command here, {interaction.user.mention}")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def runners_channel_only(func):
        """Check if the command is used in the runners-only channel"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not interaction.channel.name == "runners-only":
                await interaction.followup.send(f"You can't use this command here, {interaction.user.mention}")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def enough_players(func):
        """Check if there are enough players to start the game"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if len([member for member in interaction.guild.members if not member.bot and not member.guild_permissions.administrator]) != 3:
                await interaction.followup.send(f"Not the right amount of players to start the game. There need to be exactly 3 players, excluding bots and admins.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def isnt_running(func):
        """Makes sure the game isn't running"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if any([any(role.name in ["Runner", "Chaser"] for role in member.roles) for member in interaction.guild.members]):
                await interaction.followup.send(f"A game is already running. Please stop the game before running this command.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def is_running(func):
        """Makes sure the game is running"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not any([any(role.name in ["Runner", "Chaser"] for role in member.roles) for member in interaction.guild.members]):
                await interaction.followup.send(f"No game is currently running, go start one first.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def players_exist(func):
        """Check if players exist. This happens if the program restarts in the middle of a game."""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not 'players' in globals() and not 'players' in locals():
                await interaction.followup.send(f"No players are currently in the game. The program may have restarted.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def no_card_active(func):
        """Checks that no card is active"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if Card_IsActive:
                await interaction.followup.send(f"A card is currently active. Please finish that one before drawing a new one.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def card_active(func):
        """Checks that a card is active"""
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not Card_IsActive:
                await interaction.followup.send(f"No card is currently active. Please draw a card first.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    
    def no_veto_active(func):
        """Checks that no veto is active"""
        global Veto_IsActive, Veto_EndTime
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            global Veto_IsActive, Veto_EndTime
            if int(time.time()) < Veto_EndTime:
                await interaction.followup.send(f"A veto is currently active. Please wait for it to finish before drawing a new card.")
                return
            await func(interaction, *args, **kwargs)
        return wrapper

def confirm(func):
    """Roughly based uppon the reaction from "Just a random coder" on:
    https://stackoverflow.com/questions/76299397/how-to-add-accept-deny-button-to-a-submission-bot-discord-py/76302606#76302606"
    
    This decorator adds a confirm and cancel button to the command, and only runs the command if the confirm button is pressed by the same user who used the command.
    Made for safety."""
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        
        iu = interaction.user
        b1 = discord.ui.Button(label='Confirm', style=discord.ButtonStyle.success)
        b2 = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.danger)
        view = discord.ui.View()
        view.add_item(b1)
        view.add_item(b2)
        async def b1_callback(interaction:discord.Interaction):
            if interaction.user != iu:
                await interaction.response.send_message(f"{interaction.user.mention}You can't confirm this command, as it was run by {iu.mention}.", ephemeral=True)
                return
            await prevmessage.edit(content="Confirmed", view=None)
            await func(interaction, *args, **kwargs)
        async def b2_callback(interaction:discord.Interaction):
            if interaction.user != iu:
                await interaction.response.send_message(f"{interaction.user.mention}You can't cancel this command, as it was run by {iu.mention}.", ephemeral=True)
                return
            await prevmessage.edit(content="Cancelled", view=None)
        b1.callback = b1_callback
        b2.callback = b2_callback
        # sadly, this can NOT be set to only visible for the user who used the command (due to deferring), so we have to check if the user is the same as the user who used the command.
        prevmessage = await interaction.followup.send('Are you sure?', ephemeral=True, view=view)
           
    return wrapper

@client.event
async def on_message(message):
    """Save the chatlog to a file, and the attachments to a folder. This is done for all messages in all channels."""
    try:
        with open(f"chatlog/{message.channel.name}.txt", "a") as file:
            file.write(f"{message.author.name}: {message.content}\n")
        if len(message.attachments) > 0:
            for attachment in message.attachments:
                await attachment.save(f"chatlog/{message.channel.name}/{attachment.filename}")
    except (AttributeError, FileNotFoundError):
        pass

@client.tree.command(
    name="help",
    description="The help for the bot (in this channel)"
)
async def help(interaction: discord.Interaction):
    """The full help menu"""
    @defer
    async def run(interaction: discord.Interaction):
        await interaction.followup.send( \
"""The Help Menu:

- Usable Everywhere:
    - /winner place:
    shows the winner at the given place or coordinates
    - /help:
    shows this help menu
    - /wallet:
    Returns the amount of coins you have (only visible to you)
    
- Useable only in the runners-only channel:
    - /shop:
    Shows the shop
    - /travel method minutes:
    Travel with the given method for the given amount of minutes
    - /draw:
    Draw a card from the deck
    - /finished:
    Put the coins into the wallet, if the photo has been sendt.
    - /veto
    Veto the card. Blocks purchases and new card drawing within this time.
    
- Useable only by admins, in the main channel:
    - /start start end1 end2 end3:
    Starts the game with the given posistions
    - /stop: 
    Stops the game
    - /tagged:
    Switch the runners and chasers around, and give 300 coins to the new runner.
    - /manual user(tag) role(tag) coins
    Only if neccesary, manually fix roles and coins
"""
)
    await run(interaction)

@client.tree.command(
    name="clear",
    description="Clears the chat (in this channel)"
)
async def clear(interaction: discord.Interaction):
    """Clears the chat in the main channel (mostly for testing)"""
    @defer
    @Checks.admin_only
    @Checks.main_channel_only
    @Checks.isnt_running
    @confirm
    async def run(interaction: discord.Interaction):
        await interaction.channel.purge()
    await run(interaction)
        
@client.tree.command(
    name="start",
    description="Starts the game"
)
async def start(interaction: discord.Interaction, start: str, end1: str, end2: str, end3: str):
    """Start the game with the given positions. The bot will randomly assign roles and end locations to the players. The bot will also create the runners-only and chasers-only channels."""
    global players
    @defer
    @Checks.admin_only
    @Checks.main_channel_only
    @Checks.enough_players
    @Checks.isnt_running
    @confirm
    @defer
    async def run(interaction: discord.Interaction, start: str, end1: str, end2: str, end3: str):
        global players
        try:
            shutil.rmtree('chatlog')
        except FileNotFoundError:
            pass
        os.mkdir('chatlog')
        os.mkdir('chatlog/main')
        os.mkdir('chatlog/chasers-only')
        os.mkdir('chatlog/runners-only')
        await interaction.followup.send(f"Chatlog Reset!\n\nGame started with the following settings:\nStart: {start}\nEnd 1: {end1}\nEnd 2: {end2}\nEnd 3: {end3}\n\nPlease wait for about 30 seconds for the map to be generated.")
        try:
            points = [get_coords(city) for city in [start, end1, end2, end3]]
        except AttributeError:
            await interaction.followup.send("One or more of the places you entered was not found. Please try again.")
            return
        image = download_map_with_points(points)
        
        #send the image in the chat
        image_bytes = BytesIO()
        image.save(image_bytes, format="PNG")
        image_bytes.seek(0)
        await interaction.followup.send(file=discord.File(image_bytes, filename="Your_Map.png"))
        destinations = [end1, end2, end3]
        random.shuffle(destinations)
        p = [member for member in interaction.guild.members if not member.bot and not member.guild_permissions.administrator]
        random.shuffle(p)
        # set the players to their respective roles and destinations
        players = [[p[0], destinations[0], "Runner", 2000], [p[1], destinations[1], "Chaser", 2000], [p[2], destinations[2], "Chaser", 2000]]
        msg = ""
        for player, destination, role, coins in players:
            await player.add_roles(discord.utils.get(interaction.guild.roles, name=role)) 
            msg += (f"{player.mention} is a {discord.utils.get(interaction.guild.roles, name=role).mention} and is going to {destination.title()}.\n\n")
        await interaction.followup.send(msg + "The game has started!, everyone gets 2000 coins!. Good luck!")
    
        # make a private channel named "runners-only" and make it only available to the runners
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            discord.utils.get(interaction.guild.roles, name="Runner"): discord.PermissionOverwrite(read_messages=True),
        }
        await interaction.guild.create_text_channel('runners-only', overwrites=overwrites)

        # make a private channel named "chasers-only" and make it only available to the chasers
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            discord.utils.get(interaction.guild.roles, name="Chaser"): discord.PermissionOverwrite(read_messages=True),
        }
        await interaction.guild.create_text_channel('chasers-only', overwrites=overwrites)
        # get the channel named runners-only and chasers-only
        runners_channel = discord.utils.get(interaction.guild.text_channels, name="runners-only")
        chasers_channel = discord.utils.get(interaction.guild.text_channels, name="chasers-only")
        # send the destinations, roles and names in the channels
        await runners_channel.send(f"You are a {discord.utils.get(interaction.guild.roles, name='Runner').mention}, Good luck!")
        await chasers_channel.send(f"You are a {discord.utils.get(interaction.guild.roles, name='Chaser').mention}, Good luck!")
        
    await run(interaction, start, end1, end2, end3)

@client.tree.command(
    name="winner",
    description="Shows the winner at the given place or coordinates"
)
async def winner(interaction: discord.Interaction, place: str):
    """Returns who the winner would be at the given location"""
    global players
    @defer
    @Checks.is_running
    @Checks.players_exist
    async def run(interaction: discord.Interaction, place: str):
        global players
        try:
            coords = get_coords(place)
        except AttributeError:
            await interaction.followup.send("The place you entered was not found. Please try again.")
            return
        # get the coords for all the players' destinations
        destinations = [get_coords(player[1]) for player in players]
        # get the distance from the place to all the players' destinations
        distances = [geodesic((coords['lat'], coords['lon']), (destination['lat'], destination['lon'])).meters for destination in destinations]
        # get the index of the minimum distance
        winner = distances.index(min(distances))
        # get the winner
        winner = players[winner][0]
        await interaction.followup.send(f"The winner at {place.title()} would be {winner.mention}!")
        
    await run(interaction, place)
    
@client.tree.command(
    name="stop",
    description="Stops the game"
)
async def stop(interaction: discord.Interaction):
    """Stops the game and removes the roles and channels"""
    global players
    @defer
    @Checks.admin_only
    @Checks.main_channel_only
    @Checks.is_running
    @confirm
    @defer
    async def run(interaction: discord.Interaction):
        global players
        
        if 'players' in globals() or 'players' in locals():
            for player, destination, role, coins in players:
                await player.remove_roles(discord.utils.get(interaction.guild.roles, name="Runner"))
                await player.remove_roles(discord.utils.get(interaction.guild.roles, name="Chaser"))
        else:
            players = [member for member in interaction.guild.members if not member.bot and not member.guild_permissions.administrator]
            for player in players:
                await player.remove_roles(discord.utils.get(interaction.guild.roles, name="Runner"))
                await player.remove_roles(discord.utils.get(interaction.guild.roles, name="Chaser"))

        #remove the runners-only and chasers-only channels
        await discord.utils.get(interaction.guild.text_channels, name="runners-only").delete()
        await discord.utils.get(interaction.guild.text_channels, name="chasers-only").delete()
        players = []
        await interaction.followup.send("Game stopped. The roles have been revoked, the channels have been deleted and the coins have been removed.")
        
    await run(interaction)
    
@client.tree.command(
    name="wallet",
    description="Returns the amount of coins you have"
)
async def wallet(interaction: discord.Interaction, user: Optional[discord.Member]):
    """Shows the amount of coins a user has privately to them/ An admin can use this too, and see the wallets of others"""
    global players
    @defer
    @Checks.is_running
    @Checks.players_exist
    async def run(interaction: discord.Interaction, user: Optional[discord.Member]):
        global players
        await interaction.followup.send(f"Just a sec... (you will recieve a message only visible to you shortly)", ephemeral=True)
        # the optional user is only available to admins
        if user != None and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(f"You can't see the amount of coins someone else has, {interaction.user.mention}. Use this without the optional part", ephemeral=True)
            return
        
        if user == None:
            user = interaction.user
        for player in players:
            if player[0] == user:
                await interaction.followup.send(f"{user.mention} has {player[3]} coins.", ephemeral=True)
                return
        await interaction.followup.send(f"{user.mention} was not found in the players list.", ephemeral=True)
        
    await run(interaction, user)

@client.tree.command(
    name="manual",
    description="Manually fix roles and coins"
)
async def manual(interaction: discord.Interaction, user: discord.Member, role: discord.Role, coins: int):
    """In case of need, you may need to manually fix roles and coins. This is the command for that."""
    global players
    @defer
    @Checks.admin_only
    @Checks.main_channel_only
    @confirm
    @defer
    async def run(interaction: discord.Interaction, user: discord.Member, role: discord.Role, coins: int):
        global players
        # remove all roles from the user
        for player in players:
            if player[0] == user:
                await user.remove_roles(discord.utils.get(interaction.guild.roles, name="Runner"))
                await user.remove_roles(discord.utils.get(interaction.guild.roles, name="Chaser"))
                # add the new role
                await user.add_roles(role)
                # change the coins
                player[3] = coins
                await interaction.followup.send(f"{user.mention} has been set to {role.mention} and has {coins} coins.", ephemeral=True)
                return
        await interaction.followup.send(f"{user.mention} was not found in the players list.")
        
    await run(interaction, user, role, coins)

@client.tree.command(
    name="shop",
    description="Shows the shop"
)
async def shop(interaction: discord.Interaction):
    """The shop, what else!"""
    global players, Double_IsActive
    @defer
    @Checks.runners_channel_only
    @Checks.players_exist
    @Checks.no_veto_active
    async def run(interaction: discord.Interaction):
        global players, Double_IsActive
        iu = interaction.user
        b1 = discord.ui.Button(label='[250 coins] Double value & veto penalty of next challenge', style=discord.ButtonStyle.blurple)
        b2 = discord.ui.Button(label='[1500 coins] 10 minutes with your tracker off', style=discord.ButtonStyle.blurple)
        b3 = discord.ui.Button(label='[1000 coins] Find out where the chasers are', style=discord.ButtonStyle.blurple)
        b4 = discord.ui.Button(label='[2000 coins] Chasers stay still for 10 minutes', style=discord.ButtonStyle.blurple)
        b5 = discord.ui.Button(label='Exit the shop', style=discord.ButtonStyle.danger)
        
        view = discord.ui.View()
        view.add_item(b1)
        view.add_item(b2)
        view.add_item(b3)
        view.add_item(b4)
        view.add_item(b5)
        
        async def b1_callback(interaction:discord.Interaction):
            global Double_IsActive
            await prevmessage.edit(content="Bought 'Double value & veto penalty of next challenge'. It is now active", view=None)
            Double_IsActive = True
            for player in players:
                if player[0] == iu:
                    if player[3] < 250:
                        await interaction.followup.send(f"{iu.mention}, you don't have enough coins to buy this item.")
                        return
                    player[3] -= 250
                    return
            
        async def b2_callback(interaction:discord.Interaction):
            await prevmessage.edit(content=f"Bought '10 minutes with your tracker off'. The Chasers have been notified\n\nTime left: <t:{int(time.time()) + 600}:R>", view=None)
            await discord.utils.get(interaction.guild.text_channels, name="chasers-only").send(f"{iu.mention} has turned off their tracker for 10 minutes!\n\nTime left: <t:{int(time.time()) + 600}:R>")
            for player in players:
                if player[0] == iu:
                    if player[3] < 1500:
                        await interaction.followup.send(f"{iu.mention}, you don't have enough coins to buy this item.")
                        return
                    player[3] -= 1500
                    return
                
        async def b3_callback(interaction:discord.Interaction):
            await prevmessage.edit(content="Bought 'Find out where the chasers are'. The Chasers have been notified, and should send their location shortly.", view=None)
            await discord.utils.get(interaction.guild.text_channels, name="chasers-only").send(f"{iu.mention} paid to know where you guys are! Let them know!")
            for player in players:
                if player[0] == iu:
                    if player[3] < 1000:
                        await interaction.followup.send(f"{iu.mention}, you don't have enough coins to buy this item.")
                        return
                    player[3] -= 1000
                    return
            
        async def b4_callback(interaction:discord.Interaction):
            await prevmessage.edit(content=f"Bought 'Chasers stay still for 10 minutes'. The Chasers have been notified.\n\nTime left: <t:{int(time.time()) + 600}:R>", view=None)
            await discord.utils.get(interaction.guild.text_channels, name="chasers-only").send(f"{iu.mention} paid for you to stay still for 10 minutes! Send a picture now, and one in 10 minutes, so you dont cheat!\n\nTime left: <t:{int(time.time()) + 600}:R>")
            for player in players:
                if player[0] == iu:
                    if player[3] < 2000:
                        await interaction.followup.send(f"{iu.mention}, you don't have enough coins to buy this item.")
                        return
                    player[3] -= 2000
                    return
            
            
        async def b5_callback(interaction:discord.Interaction):
            await prevmessage.edit(content="Shop closed", view=None)
        
        b1.callback = b1_callback
        b2.callback = b2_callback
        b3.callback = b3_callback
        b4.callback = b4_callback
        b5.callback = b5_callback
        prevmessage = await interaction.followup.send('What item do you want to buy?', ephemeral=True, view=view)
    
    await run(interaction)

@client.tree.command(
    name="travel",
    description="Travel with the given method for the given amount of minutes (price given per minute)"
)
async def travel(interaction: discord.Interaction, method: Literal["[25 coins] high-speed rail", "[10 coins] low-speed rail", "[5 coins] local bus/tram/metro", "[100 coins] plane", "[10 coins] ferry", "[1 coin] bike/scooter"], minutes: int):
    """Travel using any of the given methods. The price is given per minute."""
    @defer
    @Checks.runners_channel_only
    @Checks.players_exist
    @Checks.no_veto_active
    async def run(interaction: discord.Interaction, method: Literal["[25 coins] high-speed rail", "[10 coins] low-speed rail", "[5 coins] local bus/tram/metro", "[100 coins] plane", "[10 coins] ferry", "[1 coin] bike/scooter"], minutes: int):
        global players
        if minutes <= 0:
            await interaction.followup.send("You can't travel back in time, silly.")
            return
        if method == "[25 coins] high-speed rail":
            cost = 25
        elif method == "[10 coins] low-speed rail":
            cost = 10
        elif method == "[5 coins] local bus/tram/metro":
            cost = 5
        elif method == "[100 coins] plane":
            cost = 100
        elif method == "[10 coins] ferry":
            cost = 10
        elif method == "[1 coin] bike/scooter":
            cost = 1
        else:
            await interaction.followup.send("That's not a valid method of travel.")
            return
        
        # subtract the cost from the player's coins
        for player in players:
            if player[0] == interaction.user:
                if player[3] < cost * minutes:
                    await interaction.followup.send(f"{interaction.user.mention}, you don't have enough coins to travel for {minutes} minutes with {method}.")
                    return
                player[3] -= cost * minutes
                await interaction.followup.send(f"{interaction.user.mention}, you can travel for {minutes} minutes with {method}. This costed you {cost * minutes} coins.")
                return
        
            
        
        
    await run(interaction, method, minutes)
    
@client.tree.command(
    name="draw",
    description="Draw a card from the deck"
)
async def draw(interaction: discord.Interaction):
    """Draw a card from the deck randomly."""
    global Card_IsActive, Current_Card
    @defer
    @Checks.runners_channel_only
    @Checks.no_card_active
    @Checks.no_veto_active
    @Checks.players_exist
    async def run(interaction: discord.Interaction):
        global Card_IsActive, Current_Card
        cardnum = randint(1, 21)
        # open the cards.json file and import it as a dictionary
        with open("cards.json", "r") as file:
            cards = json.load(file)
        
        # get the card from the dictionary
        card = cards[str(cardnum)]
        # send the card in the chat
        await interaction.followup.send(f"Card drawn: {card['Challenge']}\n\nPoints: {card['Reward']}\n\nPicture: {card['Picture']}\n\nExplanation: {card['Explanation']}\n")
        if cardnum == 14:
            await interaction.followup.send(f"Also, your random number is: {randint(1, 6)}")
        # set the card as active
        Card_IsActive = True
        Current_Card = card
    
    await run(interaction)
    
@client.tree.command(
    name="finished",
    description="Put the coins into the wallet, if the photo has been sendt"
)
async def finished(interaction: discord.Interaction, photo: discord.Attachment):
    """Finish the current card. Picture is required. Coins will be given (and doubled if powerup is active)"""
    global Current_Card, Double_IsActive, Card_IsActive
    @defer
    @Checks.runners_channel_only
    @Checks.card_active
    @Checks.no_veto_active
    @Checks.players_exist
    async def run(interaction: discord.Interaction, photo: discord.Attachment):
        global Current_Card, Double_IsActive, Card_IsActive
        # get the card from the dictionary

        await photo.save(f"chatlog/runners-only/{photo.filename}")
        with open("cards.json", "r") as file:
            cards = json.load(file)
        # get the reward from the card
        reward = int(Current_Card["Reward"])
        if Double_IsActive:
            reward *= 2
            Double_IsActive = False
        # add the reward to the player's coins
        for player in players:
            if player[0] == interaction.user:
                player[3] += reward
                break
            
        Card_IsActive = False
        Current_Card = None
        # send the photo in the chat
        await interaction.followup.send(f"Photo recieved: {photo.url}. You have recieved the coins.")
        
    
    await run(interaction, photo)

@client.tree.command(
    name="veto",
    description="Veto the card. Blocks purchases and new card drawing within this time."
)
async def veto(interaction: discord.Interaction):
    """Veto command. Blocks purchases and new card drawing within this time. (30 minutes, or 1 hour if the double powerup is active)"""
    global Veto_IsActive, Card_IsActive, Double_IsActive, Veto_EndTime
    @defer
    @Checks.runners_channel_only
    @Checks.card_active
    @Checks.no_veto_active
    @Checks.players_exist
    @confirm
    @defer
    async def run(interaction: discord.Interaction):
        global Veto_IsActive, Card_IsActive, Double_IsActive, Veto_EndTime

        if Double_IsActive:
            Veto_EndTime = int(time.time()) + 30*60*2
        else:
            Veto_EndTime = int(time.time()) + 30*60
        await interaction.followup.send(f"Veto activated. No new cards can be drawn or purchases can be made until <t:{Veto_EndTime}:R>.")

        Card_IsActive = False
        Veto_IsActive = True
        Double_IsActive = False
        
    await run(interaction)

@client.tree.command(
    name="tagged",
    description="Switch the runners and chasers around, and give 300 coins to the new runner."
)
async def tagged(interaction: discord.Interaction):
    """Switch the runners and chasers around, and give 300 coins to the new runner. (if a full round has been done)"""
    global players, Double_IsActive, Card_IsActive, Veto_IsActive, Current_Card, Veto_EndTime, FullRoundDone
    @defer
    @Checks.admin_only
    @Checks.main_channel_only
    @Checks.is_running
    @confirm
    @defer
    async def run(interaction: discord.Interaction):
        global players, Double_IsActive, Card_IsActive, Veto_IsActive, Current_Card, Veto_EndTime, FullRoundDone
        #purge the runners and chasers' channels
        try:
            await discord.utils.get(interaction.guild.text_channels, name="runners-only").purge()
            await discord.utils.get(interaction.guild.text_channels, name="chasers-only").purge()
        except AttributeError:
            pass
            
        Double_IsActive = False
        Card_IsActive = False
        Veto_IsActive = False
        Current_Card = None
        Veto_EndTime = 0
            
        if players[0][2] == "Runner":
            players[0][2] = "Chaser"
            players[1][2] = "Runner"
            if FullRoundDone:
                players[1][3] += 300
        elif players[1][2] == "Runner":
            players[1][2] = "Chaser"
            players[2][2] = "Runner"
            if FullRoundDone:
                players[2][3] += 300
        elif players[2][2] == "Runner":
            players[2][2] = "Chaser"
            players[0][2] = "Runner"
            if FullRoundDone:
                players[0][3] += 300
            else:
                FullRoundDone = True
        
        # remove all roles from the players
        for player in players:
            await player[0].remove_roles(discord.utils.get(interaction.guild.roles, name="Runner"))
            await player[0].remove_roles(discord.utils.get(interaction.guild.roles, name="Chaser"))
        
        msg = ""
        for player, destination, role, coins in players:
            await player.add_roles(discord.utils.get(interaction.guild.roles, name=role))
            msg += (f"{player.mention} is now a {discord.utils.get(interaction.guild.roles, name=role).mention} and (dont forget) they are going to {destination.title()}.\n\n")

        if FullRoundDone:
            await interaction.followup.send(msg + "Roles switched, and 300 coins given to the new runner. (a full round has been done)")
            
        else: 
            await interaction.followup.send(msg + "Roles switched.")
        
    await run(interaction)
    

client.run(TOKEN)