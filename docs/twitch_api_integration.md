# Twitch API Integration Guide

## Overview

The Twitch Dashboard Assistant provides comprehensive integration with the Twitch API, enabling streamers to manage their channels, interact with viewers, and automate streaming-related tasks through natural language commands.

This integration is built on top of the `twitchAPI` Python package, providing a streamlined interface that handles authentication, error handling, rate limiting, and other complexities of working with the Twitch API.

## Features

The Twitch integration supports the following key functionality:

### Authentication & Connection

- App authentication for basic API functionalities
- User authentication for streamer-specific actions
- EventSub support for real-time events and notifications
- Automatic token refresh and session management

### Channel Management

- Get and update channel information (title, category, language)
- Retrieve stream information and statistics
- Manage stream tags
- Create stream markers for highlighting important moments
- Create clips programmatically

### Viewer Engagement

- Get follower information
- Manage channel rewards and redemptions
- Configure and update chat settings
- Send chat announcements
- Start and cancel channel raids

### Analytics & Insights

- Retrieve viewer counts and other stream metrics
- Access to clips, followers, and stream markers

## Setup Requirements

To use the Twitch integration, you'll need the following:

1. A Twitch account
2. A registered Twitch application with a Client ID and Client Secret
   - Register at [Twitch Developer Console](https://dev.twitch.tv/console)
   - Set the OAuth Redirect URL to `http://localhost:17563`
3. Environment variables in your `.env` file:
   ```
   TWITCH_CLIENT_ID=your_client_id
   TWITCH_CLIENT_SECRET=your_client_secret
   TWITCH_CALLBACK_URL=your_callback_url_for_eventsub (optional)
   ```

## Usage Examples

### Connecting to Twitch

```
Connect to Twitch using my credentials so I can manage my channel.
```

### Channel Management

```
Update my stream title to "Learning Python with Chat!"
```

```
Change my stream category to "Just Chatting"
```

```
What is my current viewer count?
```

```
Create a stream marker for this awesome moment
```

### Chat Management

```
Enable subscriber-only mode in my chat
```

```
Set slow mode with a 5-second delay
```

```
Get my current chat settings
```

### Viewer Interaction

```
Show me my recent followers
```

```
Send an announcement to chat that we're starting a giveaway in 5 minutes
```

```
Start a raid to channel "friendlystreamer"
```

### Clip Management

```
Create a clip of what just happened
```

```
Show me my most popular clips from the past week
```

## Using in Workflows

The Twitch integration can be incorporated into automated workflows, allowing you to create complex sequences combining OBS, Twitch, and other tools. For example:

- Stream start workflow that sets up OBS scenes and updates Twitch title/category
- Ad break workflow that plays a scene in OBS and sends a chat announcement
- Raid workflow that thanks viewers, plays an outro, and raids another channel

Example workflow snippet:

```json
{
  "name": "Stream Start",
  "description": "Prepare OBS and update Twitch for a new stream",
  "trigger": {
    "type": "manual"
  },
  "steps": [
    {
      "name": "Switch to Starting Soon scene",
      "action": {
        "integration": "obs",
        "operation": "set_current_scene",
        "parameters": {
          "scene_name": "Starting Soon"
        }
      }
    },
    {
      "name": "Update stream title",
      "action": {
        "integration": "twitch",
        "operation": "update_channel",
        "parameters": {
          "title": "{{stream_title}}",
          "category_id": "{{category_id}}"
        }
      }
    },
    {
      "name": "Start streaming",
      "action": {
        "integration": "obs",
        "operation": "start_streaming",
        "parameters": {}
      }
    },
    {
      "name": "Wait 2 minutes",
      "action": {
        "operation": "wait",
        "parameters": {
          "duration": 120
        }
      }
    },
    {
      "name": "Switch to Main scene",
      "action": {
        "integration": "obs",
        "operation": "set_current_scene",
        "parameters": {
          "scene_name": "Main"
        }
      }
    },
    {
      "name": "Send welcome announcement",
      "action": {
        "integration": "twitch",
        "operation": "send_chat_announcement",
        "parameters": {
          "message": "Welcome to today's stream! Don't forget to follow for notifications.",
          "color": "purple"
        }
      }
    }
  ]
}
```

## EventSub for Real-time Events

The Twitch integration supports EventSub to receive real-time notifications for various events like:

- New followers and subscribers
- Stream online/offline events
- Channel point redemptions
- Raid notifications
- Chat events

To use EventSub, you need a publicly accessible callback URL (specified in the `TWITCH_CALLBACK_URL` environment variable). This can be set up using a service like ngrok for development or a proper web server for production.

## Error Handling

The Twitch integration includes robust error handling for common issues:

- Authentication errors (invalid credentials, expired tokens)
- API rate limiting
- Network connectivity issues
- Invalid parameters or requests

All errors are logged and returned with descriptive messages to help with troubleshooting.

## Advanced Configuration

For advanced users, the Twitch integration can be customized through the integration manager:

```python
# Example custom configuration
twitch_config = {
    "connection_params": {
        "client_id": "your_client_id",
        "client_secret": "your_client_secret",
        "callback_url": "your_callback_url",
        "auto_reconnect": True
    }
}

# Update integration config
assistant.update_integration_config("twitch", twitch_config)
```

## Available Scopes

When authenticating with user credentials, you might want to request specific scopes depending on your needs. The most commonly used scopes include:

- `channel:manage:broadcast` - Update channel information and create stream markers
- `channel:read:subscriptions` - View subscribers
- `channel:manage:redemptions` - Manage channel points rewards
- `chat:edit` - Send chat messages
- `chat:read` - Read chat messages
- `clips:edit` - Create clips
- `moderator:manage:banned_users` - Ban/unban users

The full list of scopes is available in the [Twitch API documentation](https://dev.twitch.tv/docs/authentication/scopes/).

## Troubleshooting

Common issues and their solutions:

1. **Authentication failures**: Ensure your client ID and secret are correct and that you've set up the redirect URL properly in your Twitch Developer Console.

2. **Missing permissions**: If certain actions fail, you might need additional scopes during authentication.

3. **Rate limiting**: The Twitch API has rate limits. The integration handles these automatically, but excessive requests may still cause temporary blocks.

4. **EventSub issues**: Ensure your callback URL is publicly accessible and properly handles the verification challenge.

For more help, check the logs or contact support.
