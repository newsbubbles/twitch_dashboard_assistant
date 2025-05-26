import logging
import asyncio
from typing import Dict, List, Optional, Any, Union, Literal
import os
from contextlib import asynccontextmanager
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from mcp.server.fastmcp import FastMCP, Context

from client.dashboard_assistant import DashboardAssistant
from client.workflow_engine import WorkflowDefinition
from client.context_analyzer import InsightType, SeverityLevel

# Load environment variables from .env file if present
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("dashboard_assistant.log")
    ]
)

logger = logging.getLogger("dashboard_assistant_mcp")

# Request/Response Models
class ConnectIntegrationRequest(BaseModel):
    """Request to connect to an integration"""
    integration_name: str = Field(..., description="Name of the integration to connect to")
    connection_params: Dict[str, Any] = Field(
        default_factory=dict, description="Connection parameters"
    )

class ConnectIntegrationResponse(BaseModel):
    """Response from connect_integration"""
    success: bool = Field(..., description="Whether the connection was successful")
    message: Optional[str] = Field(None, description="Additional information or error message")

class DisconnectIntegrationRequest(BaseModel):
    """Request to disconnect from an integration"""
    integration_name: str = Field(..., description="Name of the integration to disconnect from")

class DisconnectIntegrationResponse(BaseModel):
    """Response from disconnect_integration"""
    success: bool = Field(..., description="Whether the disconnection was successful")
    message: Optional[str] = Field(None, description="Additional information or error message")

class ExecuteActionRequest(BaseModel):
    """Request to execute an action on an integration"""
    integration_name: str = Field(..., description="Name of the integration")
    action_name: str = Field(..., description="Name of the action to execute")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")

class ExecuteActionResponse(BaseModel):
    """Response from execute_action"""
    success: bool = Field(..., description="Whether the action executed successfully")
    result: Any = Field(None, description="Result of the action")

class StartWorkflowRequest(BaseModel):
    """Request to start a workflow"""
    workflow_id: str = Field(..., description="ID of the workflow to start")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Initial variables")

class StartWorkflowResponse(BaseModel):
    """Response from start_workflow"""
    success: bool = Field(..., description="Whether the workflow started successfully")
    execution_id: Optional[str] = Field(None, description="Execution ID if successful")
    message: Optional[str] = Field(None, description="Additional information or error message")

class TriggerEventRequest(BaseModel):
    """Request to trigger an event"""
    event_name: str = Field(..., description="Name of the event to trigger")
    event_data: Dict[str, Any] = Field(default_factory=dict, description="Event data")

class TriggerEventResponse(BaseModel):
    """Response from trigger_event"""
    success: bool = Field(..., description="Whether the event was triggered successfully")
    executions: List[str] = Field(default_factory=list, description="Started execution IDs")
    count: int = Field(0, description="Number of executions started")

class CancelWorkflowRequest(BaseModel):
    """Request to cancel a workflow execution"""
    execution_id: str = Field(..., description="ID of the workflow execution to cancel")

class CancelWorkflowResponse(BaseModel):
    """Response from cancel_workflow"""
    success: bool = Field(..., description="Whether the workflow was cancelled successfully")
    message: Optional[str] = Field(None, description="Additional information or error message")

class PauseWorkflowRequest(BaseModel):
    """Request to pause a workflow execution"""
    execution_id: str = Field(..., description="ID of the workflow execution to pause")

class PauseWorkflowResponse(BaseModel):
    """Response from pause_workflow"""
    success: bool = Field(..., description="Whether the workflow was paused successfully")
    message: Optional[str] = Field(None, description="Additional information or error message")

class ResumeWorkflowRequest(BaseModel):
    """Request to resume a workflow execution"""
    execution_id: str = Field(..., description="ID of the workflow execution to resume")

class ResumeWorkflowResponse(BaseModel):
    """Response from resume_workflow"""
    success: bool = Field(..., description="Whether the workflow was resumed successfully")
    message: Optional[str] = Field(None, description="Additional information or error message")

class ExecuteWorkflowStepRequest(BaseModel):
    """Request to execute a single workflow step"""
    execution_id: str = Field(..., description="ID of the workflow execution")

class ExecuteWorkflowStepResponse(BaseModel):
    """Response from execute_workflow_step"""
    success: bool = Field(..., description="Whether the step was executed successfully")
    execution_id: str = Field(..., description="ID of the workflow execution")
    state: Optional[str] = Field(None, description="Current workflow state")
    result: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    error: Optional[str] = Field(None, description="Error message if execution failed")

class GetInsightsRequest(BaseModel):
    """Request to get insights"""
    insight_type: Optional[str] = Field(None, description="Type of insights to filter by")
    severity: Optional[str] = Field(None, description="Minimum severity level")
    limit: int = Field(10, description="Maximum number of insights to return")
    
    @field_validator("insight_type")
    @classmethod
    def validate_insight_type(cls, value):
        if value and value not in [t.value for t in InsightType]:
            valid_types = ", ".join([t.value for t in InsightType])
            raise ValueError(f"Invalid insight type. Valid values are: {valid_types}")
        return value
    
    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value):
        if value and value not in [s.value for s in SeverityLevel]:
            valid_levels = ", ".join([s.value for s in SeverityLevel])
            raise ValueError(f"Invalid severity level. Valid values are: {valid_levels}")
        return value

class RegisterWorkflowRequest(BaseModel):
    """Request to register a workflow"""
    workflow: Dict[str, Any] = Field(..., description="Workflow definition")

class RegisterWorkflowResponse(BaseModel):
    """Response from register_workflow"""
    success: bool = Field(..., description="Whether the workflow was registered successfully")
    workflow_id: Optional[str] = Field(None, description="Workflow ID if successful")
    message: Optional[str] = Field(None, description="Additional information or error message")

class GetMetricHistoryRequest(BaseModel):
    """Request to get metric history"""
    metric_name: str = Field(..., description="Name of the metric")
    limit: int = Field(50, description="Maximum number of points to return")

class UpdateChatSettingsRequest(BaseModel):
    """Request to update Twitch chat settings"""
    broadcaster_id: Optional[str] = Field(None, description="Broadcaster ID (will use authenticated user if not provided)")
    moderator_id: Optional[str] = Field(None, description="Moderator ID (will use authenticated user if not provided)")
    emote_mode: Optional[bool] = Field(None, description="Set emote-only mode")
    follower_mode: Optional[bool] = Field(None, description="Set follower-only mode")
    follower_mode_duration: Optional[int] = Field(None, description="Required follow time in minutes")
    slow_mode: Optional[bool] = Field(None, description="Set slow mode")
    slow_mode_delay: Optional[int] = Field(None, description="Slow mode delay in seconds")
    subscriber_mode: Optional[bool] = Field(None, description="Set subscriber-only mode")
    unique_chat_mode: Optional[bool] = Field(None, description="Set unique chat mode")

# Set up FastMCP server
mcp = FastMCP(
    "Twitch Dashboard Assistant",
    dependencies=[
        "twitchAPI", "httpx", "pydantic", "asyncio", "obs-websocket-py",
        "discord.py", "python-dotenv"
    ]
)

# Lifespan setup for DashboardAssistant
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Initialize and manage the DashboardAssistant lifecycle"""
    logger.info("Initializing Dashboard Assistant")
    assistant = DashboardAssistant()
    await assistant.initialize()
    
    try:
        # Start the assistant services
        await assistant.start()
        
        yield {"assistant": assistant}
    finally:
        # Clean up
        logger.info("Shutting down Dashboard Assistant")
        await assistant.close()

# Set up the lifespan
mcp = FastMCP("Twitch Dashboard Assistant", lifespan=app_lifespan)

# MCP Tools

@mcp.tool()
async def get_status(ctx: Context) -> Dict[str, Any]:
    """Get the overall status of the Dashboard Assistant"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    return assistant.get_status()

# Integration Management Tools

@mcp.tool()
async def list_integrations(ctx: Context) -> List[Dict[str, Any]]:
    """List all available integrations and their status"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    integrations = assistant.get_integration_status()
    return [i.model_dump() if hasattr(i, 'model_dump') else i for i in integrations]

@mcp.tool()
async def get_integration_status(integration_name: str, ctx: Context) -> Dict[str, Any]:
    """Get detailed status of an integration
    
    Args:
        integration_name: Name of the integration
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    status = assistant.get_integration_status(integration_name)
    if isinstance(status, dict) and "error" in status:
        return status
    return status.model_dump() if hasattr(status, 'model_dump') else status

@mcp.tool()
async def connect_integration(request: ConnectIntegrationRequest, ctx: Context) -> ConnectIntegrationResponse:
    """Connect to an integration
    
    Args:
        request: Connection details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.connect_integration(
        request.integration_name, **request.connection_params
    )
    
    success = "success" in result and result["success"]
    message = result.get("message", result.get("error", None))
    
    return ConnectIntegrationResponse(success=success, message=message)

@mcp.tool()
async def disconnect_integration(request: DisconnectIntegrationRequest, ctx: Context) -> DisconnectIntegrationResponse:
    """Disconnect from an integration
    
    Args:
        request: Disconnection details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.disconnect_integration(request.integration_name)
    
    success = "success" in result and result["success"]
    message = result.get("message", result.get("error", None))
    
    return DisconnectIntegrationResponse(success=success, message=message)

@mcp.tool()
async def execute_integration_action(request: ExecuteActionRequest, ctx: Context) -> ExecuteActionResponse:
    """Execute an action on an integration
    
    Args:
        request: Action details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.execute_action(
        request.integration_name, request.action_name, **request.params
    )
    
    success = "error" not in result
    
    return ExecuteActionResponse(success=success, result=result)

# Workflow Management Tools

@mcp.tool()
async def list_workflows(ctx: Context) -> List[Dict[str, Any]]:
    """List all registered workflows"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    return assistant.list_workflows()

@mcp.tool()
async def get_workflow(workflow_id: str, ctx: Context) -> Dict[str, Any]:
    """Get a workflow definition
    
    Args:
        workflow_id: ID of the workflow
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    workflow = assistant.get_workflow(workflow_id)
    if not workflow:
        return {"error": f"Workflow '{workflow_id}' not found"}
    return workflow

@mcp.tool()
async def register_workflow(request: RegisterWorkflowRequest, ctx: Context) -> RegisterWorkflowResponse:
    """Register a new workflow
    
    Args:
        request: Workflow definition
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = assistant.register_workflow(request.workflow)
    
    return RegisterWorkflowResponse(
        success=result.get("success", False),
        workflow_id=result.get("workflow_id"),
        message=result.get("message")
    )

@mcp.tool()
async def start_workflow(request: StartWorkflowRequest, ctx: Context) -> StartWorkflowResponse:
    """Start a workflow execution
    
    Args:
        request: Workflow start details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.start_workflow(request.workflow_id, request.variables)
    
    return StartWorkflowResponse(
        success=result.get("success", False),
        execution_id=result.get("execution_id"),
        message=result.get("message")
    )

@mcp.tool()
async def execute_workflow_step(request: ExecuteWorkflowStepRequest, ctx: Context) -> ExecuteWorkflowStepResponse:
    """Execute a single step of a workflow
    
    Args:
        request: Step execution details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.execute_workflow_step(request.execution_id)
    
    if "error" in result:
        return ExecuteWorkflowStepResponse(
            success=False,
            execution_id=request.execution_id,
            error=result["error"]
        )
    
    return ExecuteWorkflowStepResponse(
        success=True,
        execution_id=result["execution_id"],
        state=result["state"],
        result=result["result"]
    )

@mcp.tool()
async def cancel_workflow(request: CancelWorkflowRequest, ctx: Context) -> CancelWorkflowResponse:
    """Cancel a workflow execution
    
    Args:
        request: Cancel details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.cancel_workflow(request.execution_id)
    
    return CancelWorkflowResponse(
        success=result.get("success", False),
        message=result.get("message")
    )

@mcp.tool()
async def pause_workflow(request: PauseWorkflowRequest, ctx: Context) -> PauseWorkflowResponse:
    """Pause a workflow execution
    
    Args:
        request: Pause details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.pause_workflow(request.execution_id)
    
    return PauseWorkflowResponse(
        success=result.get("success", False),
        message=result.get("message")
    )

@mcp.tool()
async def resume_workflow(request: ResumeWorkflowRequest, ctx: Context) -> ResumeWorkflowResponse:
    """Resume a paused workflow execution
    
    Args:
        request: Resume details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.resume_workflow(request.execution_id)
    
    return ResumeWorkflowResponse(
        success=result.get("success", False),
        message=result.get("message")
    )

@mcp.tool()
async def list_workflow_executions(
    workflow_id: Optional[str] = None, 
    status: Optional[str] = None,
    ctx: Context
) -> List[Dict[str, Any]]:
    """List workflow executions
    
    Args:
        workflow_id: Optional workflow ID to filter by
        status: Optional status to filter by (not_started, running, paused, completed, failed, cancelled)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    return assistant.list_executions(workflow_id, status)

@mcp.tool()
async def get_workflow_status(execution_id: str, ctx: Context) -> Dict[str, Any]:
    """Get the status of a workflow execution
    
    Args:
        execution_id: Execution ID
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    status = assistant.get_workflow_status(execution_id)
    if not status:
        return {"error": f"Execution '{execution_id}' not found"}
    return status

@mcp.tool()
async def trigger_event(request: TriggerEventRequest, ctx: Context) -> TriggerEventResponse:
    """Trigger an event that may start workflows
    
    Args:
        request: Event details
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    result = await assistant.trigger_event(request.event_name, request.event_data)
    
    return TriggerEventResponse(
        success=result.get("success", False),
        executions=result.get("executions", []),
        count=result.get("count", 0)
    )

# Context Analysis Tools

@mcp.tool()
async def get_insights(request: GetInsightsRequest, ctx: Context) -> List[Dict[str, Any]]:
    """Get insights from the context analyzer
    
    Args:
        request: Filter parameters
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    insights = assistant.get_insights(
        request.insight_type, request.severity, request.limit
    )
    return insights

@mcp.tool()
async def get_stream_context(ctx: Context) -> Dict[str, Any]:
    """Get the current stream context"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    context = assistant.get_stream_context()
    return context

@mcp.tool()
async def get_metric_history(request: GetMetricHistoryRequest, ctx: Context) -> List[Dict[str, Any]]:
    """Get historical values for a metric
    
    Args:
        request: Metric parameters
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    history = assistant.get_metric_history(request.metric_name, request.limit)
    return history

# OBS Convenience Tools

@mcp.tool()
async def set_obs_scene(scene_name: str, ctx: Context) -> Dict[str, Any]:
    """Set the current scene in OBS
    
    Args:
        scene_name: Name of the scene to switch to
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action("obs", "set_current_scene", scene_name=scene_name)

@mcp.tool()
async def start_streaming(ctx: Context) -> Dict[str, Any]:
    """Start streaming in OBS"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action("obs", "start_streaming")

@mcp.tool()
async def stop_streaming(ctx: Context) -> Dict[str, Any]:
    """Stop streaming in OBS"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action("obs", "stop_streaming")

@mcp.tool()
async def start_recording(ctx: Context) -> Dict[str, Any]:
    """Start recording in OBS"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action("obs", "start_recording")

@mcp.tool()
async def stop_recording(ctx: Context) -> Dict[str, Any]:
    """Stop recording in OBS"""
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action("obs", "stop_recording")

@mcp.tool()
async def toggle_source_visibility(
    scene_name: str, source_name: str, visible: bool, ctx: Context
) -> Dict[str, Any]:
    """Toggle visibility of a source in a scene
    
    Args:
        scene_name: Name of the scene
        source_name: Name of the source
        visible: Whether the source should be visible
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # First get the scene items to find the item ID
    items_result = await assistant.execute_action(
        "obs", "get_scene_item_list", scene_name=scene_name
    )
    
    if "error" in items_result:
        return items_result
    
    # Find the item ID for the source
    items = items_result.get("items", [])
    source_item = next((item for item in items if item["source_name"] == source_name), None)
    
    if not source_item:
        return {"error": f"Source '{source_name}' not found in scene '{scene_name}'"}
    
    # Set the visibility
    return await assistant.execute_action(
        "obs", "set_scene_item_properties",
        scene_name=scene_name,
        item_id=source_item["id"],
        visible=visible
    )

# Twitch Convenience Tools

@mcp.tool()
async def get_twitch_user(user_id: Optional[str] = None, login: Optional[str] = None, ctx: Context) -> Dict[str, Any]:
    """Get information about a Twitch user
    
    Args:
        user_id: Twitch user ID (optional)
        login: Twitch username/login (optional)
    
    Note: If neither user_id nor login is provided, returns information about the authenticated user
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # Build the parameters
    params = {}
    if user_id:
        params["user_id"] = user_id
    if login:
        params["login"] = login
    
    return await assistant.execute_action("twitch", "get_user", **params)

@mcp.tool()
async def get_twitch_channel(broadcaster_id: Optional[str] = None, ctx: Context) -> Dict[str, Any]:
    """Get information about a Twitch channel
    
    Args:
        broadcaster_id: Broadcaster ID (optional, uses authenticated user if not provided)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # Build the parameters
    params = {}
    if broadcaster_id:
        params["broadcaster_id"] = broadcaster_id
    
    return await assistant.execute_action("twitch", "get_channel", **params)

@mcp.tool()
async def update_stream_title(title: str, ctx: Context) -> Dict[str, Any]:
    """Update the stream title on Twitch
    
    Args:
        title: New stream title
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # Get broadcaster ID if not provided
    channel_info = await assistant.execute_action("twitch", "get_channel")
    if "error" in channel_info:
        return channel_info
    
    broadcaster_id = channel_info["broadcaster_id"]
    
    return await assistant.execute_action(
        "twitch", "update_channel",
        broadcaster_id=broadcaster_id,
        title=title
    )

@mcp.tool()
async def update_stream_category(
    category_id: Optional[str] = None, 
    category_name: Optional[str] = None, 
    ctx: Context
) -> Dict[str, Any]:
    """Update the stream category on Twitch
    
    Args:
        category_id: ID of the game/category (preferred if you know it)
        category_name: Name of the game/category (if category_id is not provided)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # Get broadcaster ID
    channel_info = await assistant.execute_action("twitch", "get_channel")
    if "error" in channel_info:
        return channel_info
    
    broadcaster_id = channel_info["broadcaster_id"]
    
    # Build parameters for the update
    params = {"broadcaster_id": broadcaster_id}
    
    if category_id:
        params["category_id"] = category_id
    elif category_name:
        # In a real implementation, we would search for the game ID using the Twitch API
        # For simplicity, we'll use the category_name directly
        params["category_id"] = category_name
    else:
        return {"error": "Either category_id or category_name must be provided"}
    
    return await assistant.execute_action("twitch", "update_channel", **params)

@mcp.tool()
async def create_stream_marker(
    description: Optional[str] = None, ctx: Context
) -> Dict[str, Any]:
    """Create a stream marker on Twitch
    
    Args:
        description: Marker description (optional)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {}
    if description:
        params["description"] = description
    
    return await assistant.execute_action("twitch", "create_stream_marker", **params)

@mcp.tool()
async def get_stream_info(broadcaster_id: Optional[str] = None, ctx: Context) -> Dict[str, Any]:
    """Get the current stream information for a broadcaster
    
    Args:
        broadcaster_id: Broadcaster ID (optional, uses authenticated user if not provided)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {}
    if broadcaster_id:
        params["broadcaster_id"] = broadcaster_id
    
    return await assistant.execute_action("twitch", "get_stream", **params)

@mcp.tool()
async def get_followers(broadcaster_id: Optional[str] = None, first: int = 20, ctx: Context) -> Dict[str, Any]:
    """Get followers for a broadcaster
    
    Args:
        broadcaster_id: Broadcaster ID (optional, uses authenticated user if not provided)
        first: Maximum number of followers to return
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {"first": first}
    if broadcaster_id:
        params["broadcaster_id"] = broadcaster_id
    
    return await assistant.execute_action("twitch", "get_followers", **params)

@mcp.tool()
async def create_clip(has_delay: bool = False, ctx: Context) -> Dict[str, Any]:
    """Create a clip of the current broadcast
    
    Args:
        has_delay: Whether to add a delay before the clip is captured
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action("twitch", "create_clip", has_delay=has_delay)

@mcp.tool()
async def get_chat_settings(broadcaster_id: Optional[str] = None, ctx: Context) -> Dict[str, Any]:
    """Get chat settings for a channel
    
    Args:
        broadcaster_id: Broadcaster ID (optional, uses authenticated user if not provided)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {}
    if broadcaster_id:
        params["broadcaster_id"] = broadcaster_id
    
    return await assistant.execute_action("twitch", "get_chat_settings", **params)

@mcp.tool()
async def update_chat_settings(request: UpdateChatSettingsRequest, ctx: Context) -> Dict[str, Any]:
    """Update chat settings for a channel
    
    Args:
        request: Chat settings to update
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # Convert the request to a dictionary and remove None values
    params = {k: v for k, v in request.model_dump().items() if v is not None}
    
    return await assistant.execute_action("twitch", "update_chat_settings", **params)

@mcp.tool()
async def send_channel_announcement(
    broadcaster_id: str, 
    moderator_id: str, 
    message: str, 
    color: Optional[str] = None, 
    ctx: Context
) -> Dict[str, Any]:
    """Send an announcement message to a Twitch channel's chat
    
    Args:
        broadcaster_id: ID of the broadcaster's channel
        moderator_id: ID of the moderator sending the announcement
        message: The announcement message
        color: Color of the announcement (blue, green, orange, purple, or None)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {
        "broadcaster_id": broadcaster_id,
        "moderator_id": moderator_id,
        "message": message
    }
    
    if color:
        params["color"] = color
    
    return await assistant.execute_action("twitch", "send_chat_announcement", **params)

@mcp.tool()
async def raid_channel(
    from_broadcaster_id: str, 
    to_broadcaster_id: str, 
    ctx: Context
) -> Dict[str, Any]:
    """Start a raid from one channel to another
    
    Args:
        from_broadcaster_id: ID of the broadcaster starting the raid
        to_broadcaster_id: ID of the broadcaster to raid
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    return await assistant.execute_action(
        "twitch", "raid_channel",
        from_broadcaster_id=from_broadcaster_id,
        to_broadcaster_id=to_broadcaster_id
    )

@mcp.tool()
async def cancel_raid(broadcaster_id: str, ctx: Context) -> Dict[str, Any]:
    """Cancel a pending raid
    
    Args:
        broadcaster_id: ID of the broadcaster canceling the raid
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    return await assistant.execute_action("twitch", "cancel_raid", broadcaster_id=broadcaster_id)

@mcp.tool()
async def get_channel_rewards(broadcaster_id: Optional[str] = None, only_manageable_rewards: bool = False, ctx: Context) -> Dict[str, Any]:
    """Get custom channel point rewards for a channel
    
    Args:
        broadcaster_id: Broadcaster ID (optional, uses authenticated user if not provided)
        only_manageable_rewards: Whether to only return rewards that can be managed
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {"only_manageable_rewards": only_manageable_rewards}
    if broadcaster_id:
        params["broadcaster_id"] = broadcaster_id
    
    return await assistant.execute_action("twitch", "get_channel_rewards", **params)

@mcp.tool()
async def get_stream_tags(broadcaster_id: Optional[str] = None, ctx: Context) -> Dict[str, Any]:
    """Get stream tags for a channel
    
    Args:
        broadcaster_id: Broadcaster ID (optional, uses authenticated user if not provided)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {}
    if broadcaster_id:
        params["broadcaster_id"] = broadcaster_id
    
    return await assistant.execute_action("twitch", "get_stream_tags", **params)

@mcp.tool()
async def replace_stream_tags(
    broadcaster_id: str, 
    tag_ids: Optional[List[str]] = None, 
    ctx: Context
) -> Dict[str, Any]:
    """Replace all stream tags for a channel
    
    Args:
        broadcaster_id: Broadcaster ID
        tag_ids: List of tag IDs to set (empty list to clear all tags)
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    params = {"broadcaster_id": broadcaster_id}
    if tag_ids is not None:
        params["tag_ids"] = tag_ids
    
    return await assistant.execute_action("twitch", "replace_stream_tags", **params)

# Main function
def main():
    mcp.run()
    
if __name__ == "__main__":
    main()