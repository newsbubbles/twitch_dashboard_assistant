# Twitch Dashboard Assistant

A powerful integration layer that connects and automates popular streaming tools through natural language commands. This AI-powered assistant helps streamers manage their tech stack, automate workflows, and get smart recommendations.

## Project Vision

Unlike yet another overlay or bot system, the Twitch Dashboard Assistant serves as an intelligent integration hub that:

1. **Connects existing tools** rather than replacing them
2. **Automates common workflows** across multiple platforms
3. **Provides AI-powered suggestions** based on stream context
4. **Simplifies management** of streaming tech stack

## Integrations

### Current Integrations
- **OBS/Streamlabs OBS**: Scene switching, source control, streaming management
- **Twitch API**: Channel data, stream metrics, viewer analytics
- **Discord**: Community announcements, server management
- **StreamElements/Streamlabs**: Alert customization, widget management
- **Nightbot/Streamlabs Chatbot**: Command management, automated responses

## Key Features

### Integration Management
- Connect and authenticate with multiple streaming services
- Manage connection status and health
- Securely store credentials and tokens

### Workflow Automation
- Create multi-step workflows across different tools
- Trigger workflows manually or based on events
- Define custom conditions and variable substitution

### Context-Aware Assistance
- Real-time stream health monitoring
- Viewer engagement analysis
- Chat sentiment and patterns detection
- Performance optimization recommendations

### Smart Suggestions
- Content ideas based on current trends
- Engagement tactics based on audience behavior
- Technical improvements for stream quality
- Scheduling recommendations based on historical data

## Architecture

### Core Components

1. **Integration Adapters**: Connect with third-party services
2. **Workflow Engine**: Execute automation sequences
3. **Context Analyzer**: Understand stream state and metrics
4. **Recommendation Engine**: Generate smart suggestions
5. **MCP Server**: Natural language interface to all functionality

### Technical Stack

- **Python**: Core language for backend services
- **PyTwitchAPI**: Twitch API integration
- **OBSWebSocket**: OBS remote control
- **discord.py**: Discord bot functionality
- **asyncio**: Asynchronous operation handling
- **httpx**: Modern HTTP client
- **pydantic**: Data validation and settings management
- **MCP (Model Context Protocol)**: Natural language interface

## Getting Started

### Prerequisites

- Python 3.7+
- OBS with WebSocket plugin
- Twitch API credentials
- Discord bot token (optional)
- StreamElements/Streamlabs API keys (optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/twitch-dashboard-assistant.git
cd twitch-dashboard-assistant

# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```
# Required
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
OBS_WEBSOCKET_PASSWORD=your_obs_websocket_password

# Optional
DISCORD_BOT_TOKEN=your_discord_bot_token
STREAMLABS_TOKEN=your_streamlabs_token
STREAMELEMENTS_JWT=your_streamelements_jwt
```

### Running the Assistant

```bash
python assistant.py
```

## Usage Examples

### Stream Setup Automation

```
"Set up my Just Chatting layout with webcam, chat overlay, and alerts"
"Switch to my Valorant setup and post a Discord notification that I'm playing"
"Start my stream with a 5-minute countdown, then switch to main scene"
```

### Cross-Platform Actions

```
"Announce that I'm live on Discord with my current stream title"
"Create a poll about what game to play next and share it to chat"
"Save the last 30 seconds as a clip and post it to Discord"
```

### Stream Management

```
"Check my current viewer count and chat engagement"
"Show me my best performing stream times over the last month"
"What category should I play to maximize viewers right now?"
```

## Roadmap

### Phase 1: Core Integration Framework
- [x] Project pivot and vision redefinition
- [x] Research on integration targets and APIs
- [x] Workflow engine design
- [ ] OBS WebSocket integration
- [ ] Twitch API integration

### Phase 2: Workflow Automation
- [ ] State machine workflow implementation
- [ ] Workflow persistence and loading
- [ ] Event-based triggers
- [ ] Discord integration

### Phase 3: Context Analyzer
- [ ] Stream metrics collection
- [ ] Chat analysis
- [ ] Recommendation engine
- [ ] Data visualization

### Phase 4: Advanced Features
- [ ] Mobile companion app
- [ ] Stream deck integration
- [ ] Multi-channel management
- [ ] Content calendar planning

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [OBS Project](https://obsproject.com/)
- [Twitch API](https://dev.twitch.tv/docs/api/)
- [Discord.py](https://discordpy.readthedocs.io/)
- [MCP SDK](https://modelcontextprotocol.io/)
