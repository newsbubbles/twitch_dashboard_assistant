# Workflow Engine Notes

## Overview

The workflow engine is a state machine-based system that allows streamers to automate complex sequences of actions across different streaming tools and services. It's designed to be flexible, event-driven, and to handle errors gracefully.

## Key Concepts

### State Machine

The core of the workflow engine is a state machine where:
- Each workflow has multiple states representing discrete steps
- States contain actions to execute (either on integrations or internal)
- Transitions between states can be conditional based on action results
- Error handling and timeouts are handled at the state level

### Event-Driven

Workflows can be triggered by:
- Manual execution via the API
- Events from integrations (e.g., new followers, subscriptions)
- Time-based scheduling (planned)
- Other workflows (via event emission)

### Variable System

- Workflows maintain a context with variables
- Variables can be initialized when starting a workflow
- Actions can use variables via `${variable}` syntax
- Results from actions are stored and available to later states
- Special variables like `${date}` and `${time}` are available

## Current Status

- Basic workflow definition structure is complete
- State machine model is defined with Pydantic
- Registration, listing, and basic workflow operations work
- Basic execution functionality is partially implemented
- Advanced features like event triggers are planned but not fully implemented

## Implementation Details

### WorkflowDefinition

The main model that defines a workflow:
- `id`: Unique identifier
- `name`: Human-readable name
- `description`: Optional description
- `initial_state`: Starting state name
- `states`: List of state definitions
- `triggers`: Events that can start this workflow

### WorkflowState

Defines a single state in the workflow:
- `name`: State name
- `action`: The action to perform
- `transitions`: Map of events to target states
- `timeout_seconds`: Optional timeout
- `retry` settings: Configurable retry behavior

### StateAction

Defines what to do in a state:
- `service`: Integration name (or "internal")
- `method`: Method to call on the service
- `params`: Parameters for the method

## Example Workflow

A stream start workflow might look like:

```json
{
  "id": "stream_start",
  "name": "Stream Start Sequence",
  "description": "Automated sequence for starting a stream",
  "initial_state": "switch_to_starting_scene",
  "states": [
    {
      "name": "switch_to_starting_scene",
      "action": {
        "service": "obs",
        "method": "set_current_scene",
        "params": {
          "scene_name": "Starting Soon"
        }
      },
      "transitions": {
        "success": "send_discord_notification",
        "error": "handle_error"
      }
    },
    {
      "name": "send_discord_notification",
      "action": {
        "service": "discord",
        "method": "send_message",
        "params": {
          "channel_id": "${discord.announcement_channel}",
          "message": "🔴 Stream going live in 5 minutes!"
        }
      },
      "transitions": {
        "success": "wait_for_viewers",
        "error": "wait_for_viewers"  // Continue even if Discord fails
      }
    },
    {
      "name": "wait_for_viewers",
      "action": {
        "service": "internal",
        "method": "wait",
        "params": {
          "seconds": 300
        }
      },
      "transitions": {
        "success": "update_stream_info"
      }
    },
    {
      "name": "update_stream_info",
      "action": {
        "service": "twitch",
        "method": "update_channel",
        "params": {
          "title": "${stream.title}",
          "game_name": "${stream.category}"
        }
      },
      "transitions": {
        "success": "switch_to_main_scene",
        "error": "switch_to_main_scene"  // Continue even if update fails
      }
    },
    {
      "name": "switch_to_main_scene",
      "action": {
        "service": "obs",
        "method": "set_current_scene",
        "params": {
          "scene_name": "Main"
        }
      },
      "transitions": {}
    },
    {
      "name": "handle_error",
      "action": {
        "service": "internal",
        "method": "log",
        "params": {
          "message": "Error in stream start workflow",
          "level": "error"
        }
      },
      "transitions": {}
    }
  ],
  "triggers": ["manual", "scheduled.stream_start"],
  "version": "1.0",
  "tags": ["stream", "automation"]
}
```

## Future Improvements

- Complete the implementation of event-based triggers
- Add condition evaluation for complex branching workflows 
- Implement workflow persistence to survive restarts
- Add visual workflow builder interface
- Add scheduling capabilities for time-based execution
- Implement workflow templates for common scenarios
- Add export/import functionality for sharing workflows