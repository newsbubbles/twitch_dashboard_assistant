import logging
import asyncio
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Callable, Set
import json
from datetime import datetime
import os
import re
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

class WorkflowStatus(str, Enum):
    """Enum representing the status of a workflow"""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class StateTransition(BaseModel):
    """Model representing a transition between states"""
    event: str = Field(..., description="Event that triggers this transition")
    target_state: str = Field(..., description="Target state name")

class StateAction(BaseModel):
    """Model representing an action to be performed in a state"""
    service: str = Field(..., description="Service to use for this action")
    method: str = Field(..., description="Method to call on the service")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the method call")

class WorkflowState(BaseModel):
    """Model representing a state in the workflow"""
    name: str = Field(..., description="Name of the state")
    description: Optional[str] = Field(None, description="Description of this state")
    action: StateAction = Field(..., description="Action to perform in this state")
    transitions: Dict[str, str] = Field(
        default_factory=dict, description="Map of event names to target state names"
    )
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds for this state")
    on_timeout: Optional[str] = Field(
        None, description="Target state on timeout, or empty to fail the workflow"
    )
    # Additional fields for advanced functionality
    retry_count: int = Field(0, description="Number of retries for this state")
    retry_delay_seconds: int = Field(1, description="Delay between retries in seconds")
    max_retries: int = Field(0, description="Maximum number of retries")

class WorkflowDefinition(BaseModel):
    """Model representing a complete workflow definition"""
    id: str = Field(..., description="Unique identifier for the workflow")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Description of the workflow")
    initial_state: str = Field(..., description="Name of the initial state")
    states: List[WorkflowState] = Field(..., description="List of states in this workflow")
    version: str = Field("1.0", description="Version of this workflow definition")
    author: Optional[str] = Field(None, description="Author of this workflow")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    tags: List[str] = Field(default_factory=list, description="Tags for categorizing this workflow")
    triggers: List[str] = Field(default_factory=list, description="Events that trigger this workflow")
    
    @field_validator("states")
    @classmethod
    def validate_states(cls, states: List[WorkflowState], values: Dict[str, Any]) -> List[WorkflowState]:
        """Validate that all state transitions reference valid states"""
        if not states:
            raise ValueError("Workflow must have at least one state")
        
        state_names = {state.name for state in states}
        initial_state = values.get("initial_state")
        
        # Check if initial state exists
        if initial_state and initial_state not in state_names:
            raise ValueError(f"Initial state '{initial_state}' does not exist in the workflow")
        
        # Check all transitions
        for state in states:
            for event, target in state.transitions.items():
                if target and target not in state_names:
                    raise ValueError(
                        f"State '{state.name}' has transition to non-existent state '{target}'"
                    )
            
            # Check timeout transition
            if state.on_timeout and state.on_timeout not in state_names:
                raise ValueError(
                    f"State '{state.name}' has timeout transition to non-existent state '{state.on_timeout}'"
                )
        
        return states

class WorkflowContext(BaseModel):
    """Model representing the context of a workflow execution"""
    workflow_id: str = Field(..., description="ID of the workflow")
    execution_id: str = Field(..., description="Unique execution ID")
    trigger: Optional[str] = Field(None, description="Event that triggered this execution")
    status: WorkflowStatus = Field(WorkflowStatus.NOT_STARTED, description="Current status")
    current_state: Optional[str] = Field(None, description="Current state name")
    state_history: List[str] = Field(default_factory=list, description="History of state transitions")
    start_time: Optional[datetime] = Field(None, description="Start time of execution")
    end_time: Optional[datetime] = Field(None, description="End time of execution")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Execution variables")
    results: Dict[str, Any] = Field(default_factory=dict, description="Results from state actions")
    error: Optional[str] = Field(None, description="Error message if failed")
    
    class Config:
        arbitrary_types_allowed = True

class WorkflowEngine:
    """Engine for executing state machine workflows"""

    def __init__(self, integration_manager):
        self.integration_manager = integration_manager
        self.workflow_registry: Dict[str, WorkflowDefinition] = {}
        self.active_workflows: Dict[str, WorkflowContext] = {}
        self.event_subscriptions: Dict[str, Set[str]] = {}
        self._timeout_tasks: Dict[str, asyncio.Task] = {}
    
    def register_workflow(self, workflow: WorkflowDefinition) -> bool:
        """Register a workflow definition
        
        Args:
            workflow: The workflow definition to register
            
        Returns:
            bool: True if registration was successful, False if ID already exists
        """
        if workflow.id in self.workflow_registry:
            logger.warning(f"Workflow with ID '{workflow.id}' already exists, overwriting")
        
        # Initialize empty set for each trigger
        for trigger in workflow.triggers:
            if trigger not in self.event_subscriptions:
                self.event_subscriptions[trigger] = set()
            self.event_subscriptions[trigger].add(workflow.id)
        
        self.workflow_registry[workflow.id] = workflow
        logger.info(f"Registered workflow '{workflow.name}' with ID '{workflow.id}'")
        return True
    
    def unregister_workflow(self, workflow_id: str) -> bool:
        """Unregister a workflow definition
        
        Args:
            workflow_id: ID of the workflow to unregister
            
        Returns:
            bool: True if unregistration was successful, False if not found
        """
        if workflow_id not in self.workflow_registry:
            logger.warning(f"Workflow with ID '{workflow_id}' not found")
            return False
        
        workflow = self.workflow_registry[workflow_id]
        
        # Remove from event subscriptions
        for trigger in workflow.triggers:
            if trigger in self.event_subscriptions and workflow_id in self.event_subscriptions[trigger]:
                self.event_subscriptions[trigger].remove(workflow_id)
        
        del self.workflow_registry[workflow_id]
        logger.info(f"Unregistered workflow '{workflow_id}'")
        return True
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get a workflow definition by ID
        
        Args:
            workflow_id: ID of the workflow
            
        Returns:
            Optional[WorkflowDefinition]: The workflow definition if found, None otherwise
        """
        return self.workflow_registry.get(workflow_id)
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all registered workflows
        
        Returns:
            List[Dict[str, Any]]: List of workflow information
        """
        return [
            {
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "version": workflow.version,
                "author": workflow.author,
                "tags": workflow.tags,
                "triggers": workflow.triggers,
                "state_count": len(workflow.states)
            }
            for workflow in self.workflow_registry.values()
        ]
    
    async def trigger_event(self, event_name: str, event_data: Dict[str, Any] = None) -> List[str]:
        """Trigger workflows subscribed to an event
        
        Args:
            event_name: Name of the event
            event_data: Event data to pass to the workflows
            
        Returns:
            List[str]: Execution IDs of the started workflows
        """
        if event_name not in self.event_subscriptions:
            return []
        
        started_executions = []
        
        for workflow_id in self.event_subscriptions[event_name]:
            execution_id = await self.start_workflow(
                workflow_id, trigger=event_name, variables=event_data or {}
            )
            if execution_id:
                started_executions.append(execution_id)
        
        return started_executions
    
    async def start_workflow(
        self, workflow_id: str, execution_id: Optional[str] = None, 
        trigger: Optional[str] = None, variables: Dict[str, Any] = None
    ) -> Optional[str]:
        """Start a workflow execution
        
        Args:
            workflow_id: ID of the workflow to start
            execution_id: Optional custom execution ID
            trigger: Optional trigger event name
            variables: Optional initial variables
            
        Returns:
            Optional[str]: Execution ID if started successfully, None otherwise
        """
        if workflow_id not in self.workflow_registry:
            logger.error(f"Workflow '{workflow_id}' not found")
            return None
        
        workflow = self.workflow_registry[workflow_id]
        
        # Generate execution ID if not provided
        if not execution_id:
            execution_id = f"{workflow_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        # Create context
        context = WorkflowContext(
            workflow_id=workflow_id,
            execution_id=execution_id,
            trigger=trigger,
            status=WorkflowStatus.NOT_STARTED,
            current_state=None,
            start_time=datetime.now(),
            variables=variables or {}
        )
        
        self.active_workflows[execution_id] = context
        logger.info(f"Created workflow execution '{execution_id}' for workflow '{workflow_id}'")
        
        # Start the execution
        asyncio.create_task(self._execute_workflow(execution_id))
        
        return execution_id
    
    async def _execute_workflow(self, execution_id: str) -> None:
        """Execute a workflow
        
        Args:
            execution_id: Execution ID of the workflow to execute
        """
        if execution_id not in self.active_workflows:
            logger.error(f"Workflow execution '{execution_id}' not found")
            return
        
        context = self.active_workflows[execution_id]
        workflow_id = context.workflow_id
        
        if workflow_id not in self.workflow_registry:
            logger.error(f"Workflow definition '{workflow_id}' not found")
            self._mark_execution_failed(execution_id, "Workflow definition not found")
            return
        
        workflow = self.workflow_registry[workflow_id]
        
        # Initialize execution
        context.status = WorkflowStatus.RUNNING
        context.current_state = workflow.initial_state
        context.state_history = [workflow.initial_state]
        
        logger.info(f"Starting workflow execution '{execution_id}' in state '{workflow.initial_state}'")
        
        # Execute states until completion or failure
        while context.status == WorkflowStatus.RUNNING:
            current_state_name = context.current_state
            
            # Find the current state
            current_state = next(
                (s for s in workflow.states if s.name == current_state_name), None
            )
            
            if not current_state:
                self._mark_execution_failed(
                    execution_id, f"State '{current_state_name}' not found in workflow"
                )
                break
            
            logger.debug(f"Executing state '{current_state_name}' in workflow '{workflow_id}'")
            
            # Execute the state
            next_state = await self._execute_state(execution_id, current_state)
            
            # If execution was cancelled, paused, or failed during state execution
            if context.status != WorkflowStatus.RUNNING:
                break
            
            # If no next state, we're done
            if not next_state:
                self._mark_execution_completed(execution_id)
                break
            
            # Transition to the next state
            context.current_state = next_state
            context.state_history.append(next_state)
        
        logger.info(
            f"Workflow execution '{execution_id}' ended with status '{context.status}'"
        )
    
    async def _execute_state(self, execution_id: str, state: WorkflowState) -> Optional[str]:
        """Execute a single workflow state
        
        Args:
            execution_id: Execution ID
            state: The state to execute
            
        Returns:
            Optional[str]: Name of the next state, or None if no transition
        """
        context = self.active_workflows[execution_id]
        
        # Set up timeout if specified
        timeout_task = None
        if state.timeout_seconds:
            timeout_task = asyncio.create_task(
                self._handle_state_timeout(execution_id, state)
            )
            self._timeout_tasks[execution_id] = timeout_task
        
        try:
            # Execute the action with retry logic
            result = await self._execute_action_with_retry(execution_id, state)
            
            # Cancel timeout task if it was created
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
                self._timeout_tasks.pop(execution_id, None)
            
            # Handle error result
            if isinstance(result, dict) and result.get("error"):
                error_msg = result["error"]
                if "error" in state.transitions:
                    # Transition to error state
                    return state.transitions["error"]
                else:
                    # Mark execution as failed
                    self._mark_execution_failed(execution_id, error_msg)
                    return None
            
            # Store the result in context
            context.results[state.name] = result
            
            # Determine next state based on result
            if "success" in state.transitions:
                return state.transitions["success"]
            
            # Default: no transition
            return None
        
        except asyncio.CancelledError:
            # Handle cancellation (e.g., due to timeout)
            if execution_id in self._timeout_tasks:
                self._timeout_tasks.pop(execution_id, None)
            
            # If we were cancelled due to timeout, handle timeout transition
            if context.status == WorkflowStatus.RUNNING and state.on_timeout:
                return state.on_timeout
            
            return None
        
        except Exception as e:
            # Handle unexpected exception
            error_msg = f"Error executing state '{state.name}': {str(e)}"
            logger.error(error_msg)
            
            # Cancel timeout task if it exists
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
                self._timeout_tasks.pop(execution_id, None)
            
            if "error" in state.transitions:
                # Transition to error state
                return state.transitions["error"]
            else:
                # Mark execution as failed
                self._mark_execution_failed(execution_id, error_msg)
                return None
    
    async def _execute_action_with_retry(self, execution_id: str, state: WorkflowState) -> Any:
        """Execute a state action with retry logic
        
        Args:
            execution_id: Execution ID
            state: The state containing the action
            
        Returns:
            Any: Result of the action
        """
        context = self.active_workflows[execution_id]
        action = state.action
        
        # Process variable substitution in params
        processed_params = self._process_variables(action.params, context.variables, context.results)
        
        # Check if this is an internal action
        if action.service == "internal":
            return await self._execute_internal_action(action.method, processed_params, context)
        
        # Execute the action on the specified service
        retry_count = 0
        while True:
            try:
                result = await self.integration_manager.execute_action(
                    action.service, action.method, **processed_params
                )
                return result
            
            except Exception as e:
                retry_count += 1
                if retry_count <= state.max_retries:
                    logger.warning(
                        f"Retry {retry_count}/{state.max_retries} for action '{action.method}' "
                        f"on '{action.service}': {str(e)}"
                    )
                    await asyncio.sleep(state.retry_delay_seconds)
                else:
                    return {"error": f"Action failed after {retry_count} attempts: {str(e)}"}
    
    async def _handle_state_timeout(self, execution_id: str, state: WorkflowState) -> None:
        """Handle timeout for a state
        
        Args:
            execution_id: Execution ID
            state: The state that has a timeout
        """
        try:
            await asyncio.sleep(state.timeout_seconds)
            context = self.active_workflows.get(execution_id)
            
            if context and context.status == WorkflowStatus.RUNNING and context.current_state == state.name:
                logger.warning(
                    f"State '{state.name}' timed out after {state.timeout_seconds} seconds"
                )
                
                if state.on_timeout:
                    # Let the execution continue to the timeout state
                    return
                else:
                    # Mark the execution as failed
                    self._mark_execution_failed(
                        execution_id, f"State '{state.name}' timed out"
                    )
        
        except asyncio.CancelledError:
            # Timeout was cancelled (normal operation)
            pass
        
        except Exception as e:
            logger.error(f"Error in timeout handler: {str(e)}")
    
    def _process_variables(self, params: Dict[str, Any], 
                         variables: Dict[str, Any], 
                         results: Dict[str, Any]) -> Dict[str, Any]:
        """Process variable substitutions in parameters
        
        Args:
            params: Parameters to process
            variables: Workflow variables
            results: Results from previous states
            
        Returns:
            Dict[str, Any]: Processed parameters with variables substituted
        """
        if not params:
            return {}
        
        # Convert to JSON and back to handle nested structures
        params_json = json.dumps(params)
        
        # Substitute variables ${var}
        variable_pattern = r'\${([\w\.]+)}'
        
        def replace_variable(match):
            var_path = match.group(1)
            parts = var_path.split('.')
            
            # Handle special variables
            if parts[0] == 'date':
                return datetime.now().strftime('%Y-%m-%d')
            elif parts[0] == 'time':
                return datetime.now().strftime('%H:%M:%S')
            elif parts[0] == 'timestamp':
                return datetime.now().isoformat()
            
            # Try to find in variables first
            if parts[0] in variables:
                value = variables[parts[0]]
                for part in parts[1:]:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return match.group(0)  # Return original if path doesn't exist
                return json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            
            # Then check in results
            if parts[0] in results:
                value = results[parts[0]]
                for part in parts[1:]:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return match.group(0)  # Return original if path doesn't exist
                return json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            
            # No match found, return original
            return match.group(0)
        
        processed_json = re.sub(variable_pattern, replace_variable, params_json)
        processed_params = json.loads(processed_json)
        
        return processed_params
    
    async def _execute_internal_action(self, method: str, params: Dict[str, Any], 
                                   context: WorkflowContext) -> Any:
        """Execute an internal action
        
        Args:
            method: Internal method name
            params: Method parameters
            context: Workflow context
            
        Returns:
            Any: Result of the action
        """
        if method == "wait":
            # Wait for specified seconds
            seconds = params.get("seconds", 0)
            if seconds > 0:
                await asyncio.sleep(seconds)
            return {"waited": seconds}
        
        elif method == "set_variables":
            # Set workflow variables
            for key, value in params.items():
                context.variables[key] = value
            return {"variables_set": list(params.keys())}
        
        elif method == "conditional":
            # Evaluate a condition and return an event
            condition = params.get("condition")
            true_event = params.get("true_event", "condition_true")
            false_event = params.get("false_event", "condition_false")
            
            if condition:
                return {"event": true_event}
            else:
                return {"event": false_event}
        
        elif method == "log":
            # Log a message
            message = params.get("message", "")
            level = params.get("level", "info").lower()
            
            if level == "debug":
                logger.debug(message)
            elif level == "info":
                logger.info(message)
            elif level == "warning":
                logger.warning(message)
            elif level == "error":
                logger.error(message)
            
            return {"logged": message}
        
        else:
            return {"error": f"Unknown internal method: {method}"}
    
    def _mark_execution_failed(self, execution_id: str, error_message: str) -> None:
        """Mark a workflow execution as failed
        
        Args:
            execution_id: Execution ID
            error_message: Error message
        """
        if execution_id not in self.active_workflows:
            return
        
        context = self.active_workflows[execution_id]
        context.status = WorkflowStatus.FAILED
        context.error = error_message
        context.end_time = datetime.now()
        
        logger.error(f"Workflow execution '{execution_id}' failed: {error_message}")
        
        # Cancel any timeout task
        if execution_id in self._timeout_tasks:
            self._timeout_tasks[execution_id].cancel()
            self._timeout_tasks.pop(execution_id)
    
    def _mark_execution_completed(self, execution_id: str) -> None:
        """Mark a workflow execution as completed
        
        Args:
            execution_id: Execution ID
        """
        if execution_id not in self.active_workflows:
            return
        
        context = self.active_workflows[execution_id]
        context.status = WorkflowStatus.COMPLETED
        context.end_time = datetime.now()
        
        logger.info(f"Workflow execution '{execution_id}' completed successfully")
    
    async def cancel_workflow(self, execution_id: str) -> bool:
        """Cancel a running workflow execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            bool: True if cancelled, False if not found or not running
        """
        if execution_id not in self.active_workflows:
            return False
        
        context = self.active_workflows[execution_id]
        if context.status not in [WorkflowStatus.RUNNING, WorkflowStatus.PAUSED]:
            return False
        
        context.status = WorkflowStatus.CANCELLED
        context.end_time = datetime.now()
        
        # Cancel any timeout task
        if execution_id in self._timeout_tasks:
            self._timeout_tasks[execution_id].cancel()
            self._timeout_tasks.pop(execution_id)
        
        logger.info(f"Workflow execution '{execution_id}' cancelled")
        return True
    
    async def pause_workflow(self, execution_id: str) -> bool:
        """Pause a running workflow execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            bool: True if paused, False if not found or not running
        """
        # Note: Pausing is complex in this model and depends on
        # the current state implementation supporting pause/resume
        # This is a simplified version
        
        if execution_id not in self.active_workflows:
            return False
        
        context = self.active_workflows[execution_id]
        if context.status != WorkflowStatus.RUNNING:
            return False
        
        context.status = WorkflowStatus.PAUSED
        
        # Cancel any timeout task
        if execution_id in self._timeout_tasks:
            self._timeout_tasks[execution_id].cancel()
            self._timeout_tasks.pop(execution_id)
        
        logger.info(f"Workflow execution '{execution_id}' paused")
        return True
    
    async def resume_workflow(self, execution_id: str) -> bool:
        """Resume a paused workflow execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            bool: True if resumed, False if not found or not paused
        """
        if execution_id not in self.active_workflows:
            return False
        
        context = self.active_workflows[execution_id]
        if context.status != WorkflowStatus.PAUSED:
            return False
        
        context.status = WorkflowStatus.RUNNING
        
        # Create new execution task
        asyncio.create_task(self._execute_workflow(execution_id))
        
        logger.info(f"Workflow execution '{execution_id}' resumed")
        return True
    
    def get_workflow_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a workflow execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Optional[Dict[str, Any]]: Status information or None if not found
        """
        if execution_id not in self.active_workflows:
            return None
        
        context = self.active_workflows[execution_id]
        return {
            "execution_id": context.execution_id,
            "workflow_id": context.workflow_id,
            "status": context.status,
            "current_state": context.current_state,
            "state_history": context.state_history,
            "start_time": context.start_time.isoformat() if context.start_time else None,
            "end_time": context.end_time.isoformat() if context.end_time else None,
            "error": context.error,
            "trigger": context.trigger
        }
    
    def list_executions(self, workflow_id: Optional[str] = None, 
                      status: Optional[WorkflowStatus] = None) -> List[Dict[str, Any]]:
        """List workflow executions with optional filtering
        
        Args:
            workflow_id: Optional workflow ID to filter by
            status: Optional status to filter by
            
        Returns:
            List[Dict[str, Any]]: List of execution information
        """
        executions = []
        
        for execution_id, context in self.active_workflows.items():
            # Apply filters
            if workflow_id and context.workflow_id != workflow_id:
                continue
            if status and context.status != status:
                continue
            
            executions.append({
                "execution_id": context.execution_id,
                "workflow_id": context.workflow_id,
                "status": context.status,
                "current_state": context.current_state,
                "start_time": context.start_time.isoformat() if context.start_time else None,
                "end_time": context.end_time.isoformat() if context.end_time else None,
                "state_count": len(context.state_history)
            })
        
        return executions
    
    def load_workflow_from_file(self, file_path: str) -> Optional[str]:
        """Load a workflow definition from a JSON file
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            Optional[str]: Workflow ID if loaded successfully, None otherwise
        """
        try:
            with open(file_path, "r") as f:
                workflow_data = json.load(f)
            
            workflow = WorkflowDefinition.model_validate(workflow_data)
            if self.register_workflow(workflow):
                return workflow.id
            return None
        
        except Exception as e:
            logger.error(f"Error loading workflow from '{file_path}': {str(e)}")
            return None
    
    def save_workflow_to_file(self, workflow_id: str, file_path: str) -> bool:
        """Save a workflow definition to a JSON file
        
        Args:
            workflow_id: ID of the workflow to save
            file_path: Path to the output JSON file
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        if workflow_id not in self.workflow_registry:
            logger.error(f"Workflow '{workflow_id}' not found")
            return False
        
        workflow = self.workflow_registry[workflow_id]
        
        try:
            with open(file_path, "w") as f:
                f.write(workflow.model_dump_json(indent=2))
            
            logger.info(f"Saved workflow '{workflow_id}' to '{file_path}'")
            return True
        
        except Exception as e:
            logger.error(f"Error saving workflow to '{file_path}': {str(e)}")
            return False
    
    def load_workflows_from_directory(self, directory_path: str) -> List[str]:
        """Load all workflow definitions from a directory
        
        Args:
            directory_path: Path to the directory containing workflow JSON files
            
        Returns:
            List[str]: List of successfully loaded workflow IDs
        """
        if not os.path.isdir(directory_path):
            logger.error(f"Directory '{directory_path}' not found")
            return []
        
        loaded_ids = []
        
        for filename in os.listdir(directory_path):
            if not filename.endswith(".json"):
                continue
            
            file_path = os.path.join(directory_path, filename)
            workflow_id = self.load_workflow_from_file(file_path)
            
            if workflow_id:
                loaded_ids.append(workflow_id)
        
        logger.info(f"Loaded {len(loaded_ids)} workflows from '{directory_path}'")
        return loaded_ids
