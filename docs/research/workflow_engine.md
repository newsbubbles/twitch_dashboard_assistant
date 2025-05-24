# Workflow Engine Research

This document outlines our research into workflow engine architectures and implementation strategies for the Twitch Dashboard Assistant.

## Requirements

A workflow engine for our project needs to support:

1. **Sequence Definition**: Clear way to define multi-step operations
2. **Execution Control**: Start, stop, pause workflows
3. **State Management**: Track progress and maintain state
4. **Error Handling**: Recover from or bypass errors
5. **Condition Branching**: Decision making based on results
6. **Persistence**: Save and load workflow definitions
7. **Triggers**: Event-based or scheduled execution
8. **Integration**: Connect with our service adapters

## Workflow Engine Architectures

### 1. Event-Driven Workflow

#### Overview
An event-driven workflow system is based on a pub/sub (publish/subscribe) pattern. Components emit events that trigger actions in other components.

#### Strengths
- Highly responsive to real-time events
- Good for asynchronous operations
- Naturally distributed
- Loose coupling between components

#### Weaknesses
- Can be complex to debug
- State management can be challenging
- Event sequence tracking is difficult
- May lead to "spaghetti" workflows for complex processes

#### Implementation Pattern
```python
class EventBus:
    def __init__(self):
        self.subscribers = {}
    
    def subscribe(self, event_type, callback):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
    
    async def publish(self, event_type, data):
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                await callback(data)

class WorkflowManager:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.workflows = {}
        # Set up event handlers
        self.event_bus.subscribe("stream_started", self.on_stream_start)
    
    async def on_stream_start(self, data):
        # Execute "stream start" workflow
        workflow_id = "stream_start_sequence"
        if workflow_id in self.workflows:
            await self.execute_workflow(workflow_id, data)
    
    async def execute_workflow(self, workflow_id, context):
        workflow = self.workflows[workflow_id]
        for step in workflow["steps"]:
            try:
                result = await self.execute_step(step, context)
                # Update context with result
                context.update(result)
            except Exception as e:
                # Handle error based on workflow policy
                if workflow["error_policy"] == "continue":
                    continue
                else:
                    break
```

### 2. Directed Acyclic Graph (DAG) Workflow

#### Overview
DAG-based workflow engines organize tasks in a graph structure where each node is a task, and edges represent dependencies between tasks.

#### Strengths
- Clear visualization of complex dependencies
- Parallel execution support
- Efficient for complex workflows
- Good for batch processing

#### Weaknesses
- More complex implementation
- Requires explicit dependency definition
- Can be overkill for simple workflows
- More challenging to modify dynamically

#### Implementation Pattern
```python
class Task:
    def __init__(self, name, func):
        self.name = name
        self.func = func
        self.upstream_tasks = []
        self.downstream_tasks = []
    
    def set_upstream(self, task):
        self.upstream_tasks.append(task)
        task.downstream_tasks.append(self)
    
    async def execute(self, context):
        return await self.func(context)

class DAGWorkflow:
    def __init__(self, name):
        self.name = name
        self.tasks = {}
        
    def add_task(self, task):
        self.tasks[task.name] = task
    
    async def execute(self):
        # Topological sort of tasks
        execution_order = self._get_execution_order()
        context = {}
        
        for task_name in execution_order:
            task = self.tasks[task_name]
            # Check if all upstream tasks completed
            if all(upstream.name in context for upstream in task.upstream_tasks):
                try:
                    result = await task.execute(context)
                    context[task.name] = result
                except Exception as e:
                    context[task.name] = {"error": str(e)}
        
        return context
    
    def _get_execution_order(self):
        # Implementation of topological sort
        # Returns list of task names in execution order
        pass
```

### 3. State Machine Workflow

#### Overview
State machine workflows model processes as a series of states and transitions between those states based on events or conditions.

#### Strengths
- Conceptually simple to understand
- Natural representation of many processes
- Clear visualization
- Good for processes with distinct states

#### Weaknesses
- Can become complex for highly branched workflows
- Less efficient for parallel processing
- May require more boilerplate code
- State explosion for complex processes

#### Implementation Pattern
```python
class State:
    def __init__(self, name, handler):
        self.name = name
        self.handler = handler
        self.transitions = {}
    
    def add_transition(self, event, target_state):
        self.transitions[event] = target_state
    
    async def execute(self, context):
        result = await self.handler(context)
        # Determine next state based on result
        next_event = result.get("event")
        if next_event in self.transitions:
            return self.transitions[next_event]
        return None

class StateMachineWorkflow:
    def __init__(self, name):
        self.name = name
        self.states = {}
        self.current_state = None
        self.initial_state = None
    
    def add_state(self, state, is_initial=False):
        self.states[state.name] = state
        if is_initial:
            self.initial_state = state.name
    
    async def execute(self, context={}):
        if not self.initial_state:
            raise ValueError("No initial state defined")
        
        self.current_state = self.states[self.initial_state]
        execution_history = []
        
        while self.current_state is not None:
            execution_history.append(self.current_state.name)
            next_state_name = await self.current_state.execute(context)
            
            if next_state_name is None:
                # Workflow complete
                break
            
            if next_state_name not in self.states:
                raise ValueError(f"Invalid state transition: {next_state_name}")
                
            self.current_state = self.states[next_state_name]
        
        return {
            "history": execution_history,
            "context": context
        }
```

## Workflow Definition Format

For our implementation, we need a clear, serializable way to define workflows. JSON is a natural choice for this.

### Event-Driven Workflow Definition Example
```json
{
  "id": "stream_start_sequence",
  "name": "Stream Start Sequence",
  "trigger": "stream_started",
  "error_policy": "stop_on_error",
  "steps": [
    {
      "id": "switch_scene",
      "service": "obs",
      "action": "set_current_scene",
      "params": {
        "scene_name": "Starting Soon"
      }
    },
    {
      "id": "send_discord_notification",
      "service": "discord",
      "action": "send_channel_message",
      "params": {
        "channel_id": "${config.discord_channel_id}",
        "message": "Stream starting soon!"
      }
    },
    {
      "id": "start_countdown",
      "service": "internal",
      "action": "wait",
      "params": {
        "seconds": 300
      }
    },
    {
      "id": "switch_to_main",
      "service": "obs",
      "action": "set_current_scene",
      "params": {
        "scene_name": "Main"
      }
    }
  ]
}
```

### DAG Workflow Definition Example
```json
{
  "id": "stream_end_processing",
  "name": "Stream End Processing",
  "nodes": [
    {
      "id": "end_stream",
      "service": "obs",
      "action": "stop_streaming",
      "params": {}
    },
    {
      "id": "save_vod",
      "service": "obs",
      "action": "save_replay_buffer",
      "params": {
        "filename": "stream_${date}_${time}.mp4"
      },
      "depends_on": ["end_stream"]
    },
    {
      "id": "update_discord",
      "service": "discord",
      "action": "send_channel_message",
      "params": {
        "channel_id": "${config.discord_channel_id}",
        "message": "Stream ended! VOD processing."
      },
      "depends_on": ["end_stream"]
    },
    {
      "id": "create_highlight",
      "service": "twitch",
      "action": "create_clip",
      "params": {
        "title": "Stream Highlight - ${date}"
      },
      "depends_on": ["end_stream"]
    },
    {
      "id": "share_highlight",
      "service": "discord",
      "action": "send_channel_message",
      "params": {
        "channel_id": "${config.discord_channel_id}",
        "message": "Check out this highlight: ${create_highlight.url}"
      },
      "depends_on": ["create_highlight"]
    }
  ]
}
```

### State Machine Workflow Definition Example
```json
{
  "id": "raid_workflow",
  "name": "Channel Raid Workflow",
  "initial_state": "prepare_raid",
  "states": [
    {
      "name": "prepare_raid",
      "action": {
        "service": "obs",
        "method": "set_current_scene",
        "params": {
          "scene_name": "Raid Screen"
        }
      },
      "transitions": {
        "success": "announce_raid",
        "error": "end_stream"
      }
    },
    {
      "name": "announce_raid",
      "action": {
        "service": "twitch",
        "method": "send_chat_message",
        "params": {
          "message": "We're raiding ${raid_target} in 30 seconds! Get ready!"
        }
      },
      "transitions": {
        "success": "wait_for_raid",
        "error": "end_stream"
      }
    },
    {
      "name": "wait_for_raid",
      "action": {
        "service": "internal",
        "method": "wait",
        "params": {
          "seconds": 30
        }
      },
      "transitions": {
        "success": "execute_raid",
        "cancel": "end_stream"
      }
    },
    {
      "name": "execute_raid",
      "action": {
        "service": "twitch",
        "method": "raid_channel",
        "params": {
          "target_channel": "${raid_target}"
        }
      },
      "transitions": {
        "success": "end_stream",
        "error": "end_stream"
      }
    },
    {
      "name": "end_stream",
      "action": {
        "service": "obs",
        "method": "stop_streaming",
        "params": {}
      },
      "transitions": {}
    }
  ]
}
```

## Architecture Decision

Based on our research, we recommend implementing a **State Machine Workflow** architecture for the following reasons:

1. **Intuitive Model**: State machines are easy to understand for non-technical users
2. **Simple Visualization**: Can be represented as a flowchart
3. **Good UI Potential**: Easy to build a visual editor for state machines
4. **Stream-Appropriate**: Streaming workflows often have clear states (starting, live, ending, etc.)
5. **Error Recovery**: Built-in support for error handling via state transitions

This decision is aligned with our goal of creating an intuitive system that streamers can easily customize.

## Implementation Plan

### Core Components

1. **WorkflowDefinition**: Class representing a workflow definition with states and transitions
2. **WorkflowState**: Class representing a single state with actions and transitions
3. **WorkflowEngine**: Runtime execution engine that progresses through states
4. **WorkflowRegistry**: Storage and retrieval of workflow definitions
5. **WorkflowTrigger**: System to initiate workflows based on events or schedules

### Phase 1: Basic Implementation

1. Create core workflow engine classes
2. Implement JSON serialization/deserialization
3. Develop simple state execution with basic actions
4. Add support for manual workflow triggering

### Phase 2: Integration

1. Connect workflow engine to service adapters
2. Implement variable substitution and context passing
3. Add error handling and recovery mechanisms
4. Create workflow persistence layer

### Phase 3: Advanced Features

1. Add conditional branching based on service results
2. Implement event-based workflow triggers
3. Create scheduling system for timed workflows
4. Develop parallel execution support for independent actions

### Phase 4: User Interface

1. Create workflow listing and management commands
2. Implement workflow editing through natural language
3. Develop saved workflow templates
4. Add support for sharing workflows