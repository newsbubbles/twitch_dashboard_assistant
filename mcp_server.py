import logging
import asyncio
from typing import Dict, List, Optional, Any, Union, Literal
import os
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
    category_name: str, ctx: Context
) -> Dict[str, Any]:
    """Update the stream category on Twitch
    
    Args:
        category_name: Name of the game/category
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    
    # Get broadcaster ID
    channel_info = await assistant.execute_action("twitch", "get_channel")
    if "error" in channel_info:
        return channel_info
    
    broadcaster_id = channel_info["broadcaster_id"]
    
    # Need to search for the game ID first
    # This would be a separate API call, but we'll simplify for now
    # In a full implementation, we would search for the game ID using the Twitch API
    
    return await assistant.execute_action(
        "twitch", "update_channel",
        broadcaster_id=broadcaster_id,
        game_name=category_name
    )

@mcp.tool()
async def create_stream_marker(
    description: str, ctx: Context
) -> Dict[str, Any]:
    """Create a stream marker on Twitch
    
    Args:
        description: Marker description
    """
    assistant = ctx.request_context.lifespan_context["assistant"]
    return await assistant.execute_action(
        "twitch", "create_stream_marker",
        description=description
    )

# Main function
def main():
    mcp.run()
    
if __name__ == "__main__":
    main()