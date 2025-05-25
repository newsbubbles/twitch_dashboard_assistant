# Setting Up OBS WebSocket Integration

## Overview

The OBS WebSocket integration allows the Twitch Dashboard Assistant to control OBS Studio remotely. This includes changing scenes, starting/stopping streams, adjusting audio sources, and more.

## Requirements

- **OBS Studio** (version 28.0.0 or later recommended)
- **OBS WebSocket** (included in OBS Studio 28.0.0+, otherwise install as a plugin)

## Setup Instructions

### 1. Enable WebSocket Server in OBS

1. Open OBS Studio
2. Go to **Tools** > **WebSocket Server Settings**
3. Check **Enable WebSocket Server**
4. Configure the server:
   - **Server Port**: 4455 (default)
   - **Enable Authentication**: Recommended for security
   - **Password**: Create a strong password

### 2. Configure Dashboard Assistant

1. Create a `.env` file in the root directory of the project (if not already present)
2. Add the following environment variable:

```
OBS_WEBSOCKET_PASSWORD=your_password_here
```

3. If you're not using the default host (localhost) or port (4455), add these variables:

```
OBS_WEBSOCKET_HOST=your_host
OBS_WEBSOCKET_PORT=your_port
```

### 3. Test the Connection

You can test the connection using the Dashboard Assistant with the following command:

```
connect_integration obs
```

If successful, you should see a confirmation message that the connection was established.

## Troubleshooting

### Connection Issues

- **WebSocket Server Not Responding**:
  - Ensure OBS is running
  - Verify the WebSocket server is enabled in OBS settings
  - Check that the port matches your configuration
  - Make sure no firewall is blocking the connection
  
- **Authentication Failed**:
  - Confirm the password in your .env file matches the one in OBS
  - Try regenerating the password in OBS and updating your .env file

- **Version Compatibility**:
  - Different versions of OBS WebSocket have different APIs
  - This implementation targets OBS WebSocket v5.x (OBS 28.0.0+)
  - If using an older version, you might need an adapter for your version

## Available Actions

Once connected, you can perform the following actions:

- **Scene Management**:
  - List all scenes: `execute_integration_action obs get_scene_list`
  - Get current scene: `execute_integration_action obs get_current_scene`
  - Set current scene: `execute_integration_action obs set_current_scene scene_name="Your Scene Name"`

- **Stream Control**:
  - Start streaming: `execute_integration_action obs start_streaming`
  - Stop streaming: `execute_integration_action obs stop_streaming`
  - Start recording: `execute_integration_action obs start_recording`
  - Stop recording: `execute_integration_action obs stop_recording`
  - Get streaming status: `execute_integration_action obs get_streaming_status`

- **Source Control**:
  - Get scene items: `execute_integration_action obs get_scene_item_list scene_name="Your Scene Name"`
  - Toggle source visibility: `execute_integration_action obs set_scene_item_properties scene_name="Your Scene Name" item_id=1 visible=true`

- **Audio Control**:
  - Get audio sources: `execute_integration_action obs get_audio_sources`
  - Mute/unmute source: `execute_integration_action obs set_mute source_name="Mic/Aux" muted=true`
  - Adjust volume: `execute_integration_action obs set_volume source_name="Mic/Aux" volume=-20 volume_type="db"`

- **Statistics**:
  - Get OBS stats: `execute_integration_action obs get_stats`

## Convenience Tools

The Dashboard Assistant also provides these shortcut tools for common OBS actions:

- `set_obs_scene "Your Scene Name"` - Switch to a specific scene
- `start_streaming` - Begin streaming
- `stop_streaming` - End streaming
- `start_recording` - Begin recording
- `stop_recording` - End recording
- `toggle_source_visibility "Scene Name" "Source Name" true/false` - Show/hide a specific source
