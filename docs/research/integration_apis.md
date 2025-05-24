# Integration APIs Research

This document contains detailed research on the APIs for each service we plan to integrate with in the Twitch Dashboard Assistant.

## 1. OBS WebSocket

### Overview
OBS WebSocket is a plugin for OBS Studio that allows external applications to control OBS via a WebSocket connection.

### API Details
- **Version**: 5.0
- **Protocol**: WebSocket
- **Documentation**: [OBS WebSocket Protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
- **Python Library**: [obs-websocket-py](https://github.com/Elektordi/obs-websocket-py)
- **Authentication**: Password or token-based authentication

### Key Endpoints/Functions

#### Connection
```python
from obswebsocket import obsws, requests

ws = obsws("localhost", 4455, "password")
ws.connect()
```

#### Scene Management
```python
# Get current scene
scene_info = ws.call(requests.GetCurrentProgramScene())
print(f"Current scene: {scene_info.datain['currentProgramSceneName']}")

# Switch scenes
ws.call(requests.SetCurrentProgramScene(sceneName="Scene 2"))

# List all scenes
scenes = ws.call(requests.GetSceneList())
for scene in scenes.datain['scenes']:
    print(scene['sceneName'])
```

#### Source Control
```python
# Toggle source visibility
ws.call(requests.SetSceneItemEnabled(
    sceneName="Main Scene", 
    sceneItemId=5, 
    sceneItemEnabled=True
))

# Get source settings
settings = ws.call(requests.GetInputSettings(inputName="Webcam"))
print(settings.datain)

# Set source settings
ws.call(requests.SetInputSettings(
    inputName="Webcam", 
    inputSettings={"width": 1280, "height": 720}
))
```

#### Streaming/Recording
```python
# Start streaming
ws.call(requests.StartStream())

# Stop streaming
ws.call(requests.StopStream())

# Start recording
ws.call(requests.StartRecord())

# Stop recording
record_info = ws.call(requests.StopRecord())
print(f"Recording saved to: {record_info.datain['outputPath']}")
```

#### Audio Control
```python
# Mute an audio source
ws.call(requests.SetInputMute(inputName="Mic/Aux", inputMuted=True))

# Get audio levels
audio_info = ws.call(requests.GetInputVolume(inputName="Desktop Audio"))
print(f"Volume: {audio_info.datain['inputVolumeDb']} dB")

# Set volume (0.0-1.0 scale)
ws.call(requests.SetInputVolume(inputName="Desktop Audio", inputVolumeMul=0.5))
```

### Implementation Notes
- Requires OBS WebSocket plugin to be installed and enabled
- WebSocket server must be configured in OBS (Tools > WebSocket Server Settings)
- Event subscription allows for reacting to OBS state changes
- Connection can drop if OBS is closed/reopened

## 2. Streamlabs API

### Overview
The Streamlabs API allows integration with Streamlabs alert box, donation processing, and other widgets.

### API Details
- **Base URL**: https://streamlabs.com/api/v1.0/
- **Protocol**: REST
- **Authentication**: OAuth2
- **Documentation**: [Streamlabs API Documentation](https://dev.streamlabs.com/)
- **Rate Limits**: 300 requests per 5 minutes

### Key Endpoints/Functions

#### Authentication
```python
import requests

# OAuth2 flow
auth_url = "https://streamlabs.com/api/v1.0/authorize"
token_url = "https://streamlabs.com/api/v1.0/token"
redirect_uri = "http://localhost:3000/callback"
client_id = "YOUR_CLIENT_ID"
client_secret = "YOUR_CLIENT_SECRET"

auth_params = {
    "client_id": client_id,
    "redirect_uri": redirect_uri,
    "response_type": "code",
    "scope": "donations.read donations.create alerts.create"
}

# After redirect and code acquisition
token_params = {
    "client_id": client_id,
    "client_secret": client_secret,
    "code": "AUTHORIZATION_CODE",
    "grant_type": "authorization_code",
    "redirect_uri": redirect_uri
}

response = requests.post(token_url, data=token_params)
token_data = response.json()
access_token = token_data["access_token"]
```

#### Alert Box
```python
# Test alert
headers = {"Authorization": f"Bearer {access_token}"}

# Follow alert
alert_data = {
    "type": "follow",
    "message": "Test follow alert",
    "user_message": "Thanks for following!"
}
requests.post(
    "https://streamlabs.com/api/v1.0/alerts", 
    headers=headers, 
    data=alert_data
)

# Donation alert
donate_data = {
    "name": "TestDonator",
    "message": "Great stream!",
    "identifier": "123456",
    "amount": 5,
    "currency": "USD"
}
requests.post(
    "https://streamlabs.com/api/v1.0/donations", 
    headers=headers, 
    data=donate_data
)
```

#### Alert Settings
```python
# Get alert box settings
response = requests.get(
    "https://streamlabs.com/api/v1.0/alertbox/settings",
    headers=headers
)
settings = response.json()

# Update alert settings
settings_data = {
    "type": "donation",
    "image_href": "https://example.com/image.gif",
    "sound_href": "https://example.com/sound.mp3",
    "duration": 5000,  # milliseconds
    "enable_custom_messages": True
}
requests.put(
    "https://streamlabs.com/api/v1.0/alertbox/settings", 
    headers=headers, 
    data=settings_data
)
```

#### Widget Themes
```python
# Get available themes
response = requests.get(
    "https://streamlabs.com/api/v1.0/alertbox/themes",
    headers=headers
)
themes = response.json()

# Set theme
theme_data = {"theme_id": "theme123"}
requests.put(
    "https://streamlabs.com/api/v1.0/alertbox/theme", 
    headers=headers, 
    data=theme_data
)
```

### Implementation Notes
- OAuth2 flow requires redirecting user to authorize the application
- Access tokens expire after 90 days
- Rate limits must be respected (300 requests per 5 minutes)
- Most alert box customization requires the alerts.create scope

## 3. StreamElements API

### Overview
The StreamElements API allows integration with StreamElements overlays, chat bot, and loyalty systems.

### API Details
- **Base URL**: https://api.streamelements.com/kappa/v2/
- **Protocol**: REST
- **Authentication**: JWT token
- **Documentation**: [StreamElements API Documentation](https://dev.streamelements.com/)

### Key Endpoints/Functions

#### Authentication
```python
import requests

# JWT token is obtained from StreamElements dashboard
jwt_token = "YOUR_JWT_TOKEN"
headers = {"Authorization": f"Bearer {jwt_token}"}
```

#### Channel Information
```python
# Get channel info
response = requests.get(
    "https://api.streamelements.com/kappa/v2/channels/me",
    headers=headers
)
channel_data = response.json()
print(f"Channel ID: {channel_data['_id']}")
```

#### Overlays
```python
# Get all overlays
response = requests.get(
    "https://api.streamelements.com/kappa/v2/overlays",
    headers=headers
)
overlays = response.json()

# Get specific overlay
overlay_id = overlays[0]["_id"]
response = requests.get(
    f"https://api.streamelements.com/kappa/v2/overlays/{overlay_id}",
    headers=headers
)
overlay_data = response.json()
```

#### Bot Commands
```python
# Get all commands
response = requests.get(
    "https://api.streamelements.com/kappa/v2/bot/commands",
    headers=headers
)
commands = response.json()

# Create a command
command_data = {
    "command": "!hello",
    "reply": "Hello, $(user)!",
    "enabled": True,
    "cost": 0,
    "cooldown": {"global": 5, "user": 15}
}
requests.post(
    "https://api.streamelements.com/kappa/v2/bot/commands",
    headers=headers,
    json=command_data
)
```

#### Alerts/Events
```python
# Trigger test alert
event_data = {
    "_id": "follow",  # Event type
    "providerId": "twitch" 
}
requests.post(
    "https://api.streamelements.com/kappa/v2/bot/testwave",
    headers=headers,
    json=event_data
)
```

#### Activities Feed
```python
# Get recent activities
response = requests.get(
    "https://api.streamelements.com/kappa/v2/activities",
    headers=headers,
    params={"limit": 20}
)
activities = response.json()
```

### Implementation Notes
- JWT token must be generated in the StreamElements dashboard
- Token has full account access, so security is critical
- Some features like alerts require creating overlay first
- API structure is subject to change

## 4. Nightbot API

### Overview
The Nightbot API allows management of Nightbot commands, timers, and channel settings.

### API Details
- **Base URL**: https://api.nightbot.tv/1/
- **Protocol**: REST
- **Authentication**: OAuth2
- **Documentation**: [Nightbot API Documentation](https://api-docs.nightbot.tv/)

### Key Endpoints/Functions

#### Authentication
```python
import requests

# OAuth2 flow
auth_url = "https://api.nightbot.tv/oauth2/authorize"
token_url = "https://api.nightbot.tv/oauth2/token"
redirect_uri = "http://localhost:3000/callback"
client_id = "YOUR_CLIENT_ID"
client_secret = "YOUR_CLIENT_SECRET"

auth_params = {
    "client_id": client_id,
    "redirect_uri": redirect_uri,
    "response_type": "code",
    "scope": "commands timers channel"
}

# After redirect and code acquisition
token_params = {
    "client_id": client_id,
    "client_secret": client_secret,
    "code": "AUTHORIZATION_CODE",
    "grant_type": "authorization_code",
    "redirect_uri": redirect_uri
}

response = requests.post(token_url, data=token_params)
token_data = response.json()
access_token = token_data["access_token"]
headers = {"Authorization": f"Bearer {access_token}"}
```

#### Commands
```python
# Get all commands
response = requests.get(
    "https://api.nightbot.tv/1/commands",
    headers=headers
)
commands = response.json()

# Add a command
command_data = {
    "name": "!hello",
    "message": "Hello, $(user)!",
    "userLevel": "everyone",
    "coolDown": 30
}
requests.post(
    "https://api.nightbot.tv/1/commands",
    headers=headers,
    json=command_data
)

# Update a command
command_id = "command_id_here"
update_data = {"coolDown": 60}
requests.put(
    f"https://api.nightbot.tv/1/commands/{command_id}",
    headers=headers,
    json=update_data
)
```

#### Timers
```python
# Get all timers
response = requests.get(
    "https://api.nightbot.tv/1/timers",
    headers=headers
)
timers = response.json()

# Add a timer
timer_data = {
    "name": "Reminder",
    "message": "Don't forget to follow the channel!",
    "interval": 15,  # minutes
    "lines": 5,      # chat lines before trigger
    "enabled": True
}
requests.post(
    "https://api.nightbot.tv/1/timers",
    headers=headers,
    json=timer_data
)
```

#### Channel
```python
# Get channel info
response = requests.get(
    "https://api.nightbot.tv/1/channel",
    headers=headers
)
channel_data = response.json()

# Update channel settings
settings_data = {"chatters": True}  # Enable chatter list
requests.put(
    "https://api.nightbot.tv/1/channel",
    headers=headers,
    json=settings_data
)
```

### Implementation Notes
- OAuth2 flow requires redirecting user to authorize the application
- Limited API functionality compared to web dashboard
- Some features may require additional scopes
- Rate limits are not clearly documented but should be respected

## 5. Discord API

### Overview
The Discord API allows bot integration with Discord servers, enabling automated announcements and server management.

### API Details
- **Base URL**: https://discord.com/api/v10
- **Protocol**: REST + WebSocket
- **Authentication**: Bot token
- **Documentation**: [Discord Developer Documentation](https://discord.com/developers/docs/intro)
- **Python Library**: [discord.py](https://discordpy.readthedocs.io/)

### Key Endpoints/Functions

#### Bot Setup
```python
import discord
from discord.ext import commands

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

bot.run("YOUR_BOT_TOKEN")
```

#### Message Sending
```python
# Send message to a channel
@bot.command()
async def announce(ctx, *, message):
    channel = bot.get_channel(CHANNEL_ID)  # Replace with target channel ID
    await channel.send(message)

# Send direct message
@bot.command()
async def dm(ctx, member: discord.Member, *, message):
    await member.send(message)

# Send embedded message (rich content)
@bot.command()
async def stream_live(ctx):
    embed = discord.Embed(
        title="Stream is Live!",
        description="Come join us at https://twitch.tv/username",
        color=0x6441A4  # Twitch purple
    )
    embed.set_image(url="https://example.com/thumbnail.jpg")
    embed.add_field(name="Game", value="Valorant", inline=True)
    embed.add_field(name="Title", value="Ranked Grind!", inline=True)
    
    channel = bot.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
    await channel.send(embed=embed)
```

#### Role Management
```python
# Assign role to member
@bot.command()
async def add_role(ctx, member: discord.Member, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if role:
        await member.add_roles(role)
        await ctx.send(f"Added {role_name} to {member.display_name}")

# Create role
@bot.command()
async def create_role(ctx, role_name, color_hex="#000000"):
    # Convert hex to discord.Color
    color = discord.Color(int(color_hex.lstrip('#'), 16))
    await ctx.guild.create_role(name=role_name, color=color)
    await ctx.send(f"Created role {role_name}")
```

#### Channel Management
```python
# Create text channel
@bot.command()
async def create_channel(ctx, channel_name, category_name=None):
    guild = ctx.guild
    category = None
    if category_name:
        category = discord.utils.get(guild.categories, name=category_name)
        
    await guild.create_text_channel(channel_name, category=category)
    await ctx.send(f"Created channel #{channel_name}")

# Send message to specific channel
automate_channel = bot.get_channel(CHANNEL_ID)
await automate_channel.send("Your stream is scheduled in 30 minutes!")
```

#### Event Handling
```python
# React to new members
@bot.event
async def on_member_join(member):
    welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
    await welcome_channel.send(f"Welcome to the server, {member.mention}!")
    
    # Add default role
    role = discord.utils.get(member.guild.roles, name="Viewer")
    if role:
        await member.add_roles(role)

# React to reactions (for role assignment)
@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id == ROLES_MESSAGE_ID:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        
        # Map emoji to roles
        if payload.emoji.name == "🎮":
            role = discord.utils.get(guild.roles, name="Gamer")
            await member.add_roles(role)
```

### Implementation Notes
- Requires creating a Discord application and bot in the Discord Developer Portal
- Bot needs to be invited to server with proper permissions
- Intents must be enabled in both the code and Developer Portal
- WebSocket connection maintains real-time updates
- Rate limits are strictly enforced

## Implementation Priorities

Based on the research, here's a recommended order of implementation:

1. **OBS WebSocket** - Highest immediate value for streamers, relatively simple API
2. **Twitch API** - Already partially implemented in our existing code
3. **Discord API** - Strong community management value, good Python library support
4. **StreamElements/Streamlabs** - Alert system integration, more complex OAuth flow
5. **Nightbot** - Command management, lower priority due to limited API scope

## Common Integration Challenges

### Authentication Management
- Storing tokens securely
- Handling token refresh
- Managing multiple service authentications

### Connection Stability
- Reconnecting after disconnections
- Handling rate limits
- Managing WebSocket connections

### Data Synchronization
- Keeping local state in sync with services
- Handling conflicting updates
- Maintaining consistency across platforms

### Error Handling
- API-specific error responses
- Network failures
- Service outages