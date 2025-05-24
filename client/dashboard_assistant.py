import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
import os
from datetime import datetime

from .integration_manager import IntegrationManager
from .workflow_engine import WorkflowEngine, WorkflowDefinition, WorkflowStatus
from .context_analyzer import ContextAnalyzer, InsightType, SeverityLevel

logger = logging.getLogger(__name__)

class DashboardAssistant:
    """Main class for the Twitch Dashboard Assistant"""

    def __init__(self):
        # Set up integration manager
        self.integration_manager = IntegrationManager()
        
        # Set up workflow engine
        self.workflow_engine = WorkflowEngine(self.integration_manager)
        
        # Set up context analyzer
        self.context_analyzer = ContextAnalyzer(self.integration_manager)
        
        # Initialization flag
        self._initialized = False
    
    async def initialize(self):
        """Initialize the dashboard assistant"""
        if self._initialized:
            logger.info("Dashboard assistant already initialized")
            return
        
        logger.info("Initializing dashboard assistant")
        
        # Initialize integration manager
        await self.integration_manager.initialize()
        
        # Load workflows
        workflow_dir = os.path.join(os.path.dirname(__file__), "../workflows")
        if os.path.exists(workflow_dir):
            self.workflow_engine.load_workflows_from_directory(workflow_dir)
            logger.info(f"Loaded workflows from {workflow_dir}")
        
        # Flag as initialized
        self._initialized = True
        
        logger.info("Dashboard assistant initialization complete")
    
    async def start(self):
        """Start the assistant services"""
        if not self._initialized:
            await self.initialize()
        
        logger.info("Starting dashboard assistant services")
        
        # Connect to enabled integrations
        await self.integration_manager.connect_all()
        
        # Start context analyzer collection
        await self.context_analyzer.start_collection()
        
        logger.info("Dashboard assistant services started")
    
    async def stop(self):
        """Stop the assistant services"""
        logger.info("Stopping dashboard assistant services")
        
        # Stop context analyzer
        await self.context_analyzer.stop_collection()
        
        # Disconnect from integrations
        await self.integration_manager.disconnect_all()
        
        logger.info("Dashboard assistant services stopped")
    
    async def close(self):
        """Stop services and clean up resources"""
        await self.stop()
        
        # Close context analyzer
        await self.context_analyzer.close()
        
        # Close integration manager
        await self.integration_manager.close()
        
        logger.info("Dashboard assistant closed")
    
    # Integration management methods
    async def connect_integration(self, name: str, **params) -> Dict[str, Any]:
        """Connect to an integration
        
        Args:
            name: Name of the integration
            **params: Connection parameters
            
        Returns:
            Dict[str, Any]: Connection result
        """
        result = await self.integration_manager.connect_integration(name, **params)
        return result
    
    async def disconnect_integration(self, name: str) -> Dict[str, Any]:
        """Disconnect from an integration
        
        Args:
            name: Name of the integration
            
        Returns:
            Dict[str, Any]: Disconnection result
        """
        result = await self.integration_manager.disconnect_integration(name)
        return result
    
    def get_integration_status(self, name: Optional[str] = None):
        """Get status of integrations
        
        Args:
            name: Optional specific integration name
            
        Returns:
            Union[Dict[str, Any], List[Dict[str, Any]]]: Integration status(es)
        """
        return self.integration_manager.get_integration_status(name)
    
    async def execute_action(self, integration_name: str, action: str, **params) -> Dict[str, Any]:
        """Execute an action on an integration
        
        Args:
            integration_name: Name of the integration
            action: Action to execute
            **params: Action parameters
            
        Returns:
            Dict[str, Any]: Action result
        """
        result = await self.integration_manager.execute_action(integration_name, action, **params)
        return result
    
    # Workflow methods
    def register_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Register a workflow from a dictionary definition
        
        Args:
            workflow: Workflow definition as a dictionary
            
        Returns:
            Dict[str, Any]: Registration result
        """
        try:
            # Convert dict to workflow definition
            workflow_obj = WorkflowDefinition.model_validate(workflow)
            
            # Ensure timestamps are set
            if not workflow_obj.created_at:
                workflow_obj.created_at = datetime.now()
            workflow_obj.updated_at = datetime.now()
            
            success = self.workflow_engine.register_workflow(workflow_obj)
            
            if success:
                return {
                    "success": True,
                    "workflow_id": workflow_obj.id,
                    "message": f"Workflow '{workflow_obj.name}' registered successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to register workflow (duplicate ID)"
                }
        
        except Exception as e:
            logger.error(f"Error registering workflow: {str(e)}")
            return {
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all registered workflows
        
        Returns:
            List[Dict[str, Any]]: List of workflow information
        """
        return self.workflow_engine.list_workflows()
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get a workflow definition
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Optional[Dict[str, Any]]: Workflow definition or None
        """
        workflow = self.workflow_engine.get_workflow(workflow_id)
        if workflow:
            return workflow.model_dump()
        return None
    
    async def start_workflow(self, workflow_id: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start a workflow execution
        
        Args:
            workflow_id: Workflow ID
            variables: Optional initial variables
            
        Returns:
            Dict[str, Any]: Start result
        """
        execution_id = await self.workflow_engine.start_workflow(
            workflow_id, variables=variables or {}
        )
        
        if execution_id:
            return {
                "success": True,
                "execution_id": execution_id,
                "message": f"Workflow '{workflow_id}' started"
            }
        else:
            return {
                "success": False,
                "message": f"Failed to start workflow '{workflow_id}'"
            }
    
    async def trigger_event(self, event_name: str, event_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Trigger an event that may start workflows
        
        Args:
            event_name: Event name
            event_data: Optional event data
            
        Returns:
            Dict[str, Any]: Trigger result
        """
        execution_ids = await self.workflow_engine.trigger_event(event_name, event_data or {})
        
        return {
            "success": True,
            "event": event_name,
            "executions": execution_ids,
            "count": len(execution_ids)
        }
    
    def get_workflow_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a workflow execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Optional[Dict[str, Any]]: Status information
        """
        return self.workflow_engine.get_workflow_status(execution_id)
    
    def list_executions(self, workflow_id: Optional[str] = None, 
                      status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List workflow executions
        
        Args:
            workflow_id: Optional workflow ID filter
            status: Optional status filter
            
        Returns:
            List[Dict[str, Any]]: Execution information
        """
        # Convert string status to enum if provided
        status_enum = WorkflowStatus(status) if status else None
        
        return self.workflow_engine.list_executions(workflow_id, status_enum)
    
    # Context analyzer methods
    def get_insights(self, insight_type: Optional[str] = None, 
                    severity: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get insights from context analyzer
        
        Args:
            insight_type: Optional insight type filter
            severity: Optional minimum severity filter
            limit: Maximum number of insights to return
            
        Returns:
            List[Dict[str, Any]]: Filtered insights
        """
        # Convert string parameters to enums if provided
        type_enum = InsightType(insight_type) if insight_type else None
        severity_enum = SeverityLevel(severity) if severity else None
        
        return self.context_analyzer.get_insights(type_enum, severity_enum, limit)
    
    def get_metric_history(self, metric_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get historical values for a metric
        
        Args:
            metric_name: Metric name
            limit: Maximum points to return
            
        Returns:
            List[Dict[str, Any]]: Metric history
        """
        return self.context_analyzer.get_metric_history(metric_name, limit)
    
    def get_stream_context(self) -> Dict[str, Any]:
        """Get the current stream context
        
        Returns:
            Dict[str, Any]: Current context data
        """
        return self.context_analyzer.get_current_context()
    
    # Utility methods
    def get_status(self) -> Dict[str, Any]:
        """Get overall assistant status
        
        Returns:
            Dict[str, Any]: Status information
        """
        # Get integration statuses
        integrations = self.integration_manager.get_integration_status()
        integration_statuses = {}
        
        if isinstance(integrations, list):
            for integration in integrations:
                integration_statuses[integration.name] = {
                    "status": integration.status,
                    "error": integration.error
                }
        
        # Get workflow stats
        workflow_count = len(self.workflow_engine.workflow_registry)
        executions = self.workflow_engine.list_executions()
        active_executions = [e for e in executions 
                           if e["status"] in [WorkflowStatus.RUNNING, WorkflowStatus.PAUSED]]
        
        # Get insight stats
        insights = self.context_analyzer.get_insights(limit=100)
        critical_insights = [i for i in insights if i["severity"] in ["high", "critical"]]
        
        return {
            "initialized": self._initialized,
            "integrations": integration_statuses,
            "workflows": {
                "count": workflow_count,
                "active_executions": len(active_executions)
            },
            "insights": {
                "count": len(insights),
                "critical_count": len(critical_insights)
            },
            "stream_active": self.context_analyzer.get_current_context().get("streaming", False)
        }