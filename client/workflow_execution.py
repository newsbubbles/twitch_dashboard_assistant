import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
import uuid

from .workflow_engine import WorkflowDefinition, WorkflowContext, WorkflowStatus, WorkflowState

logger = logging.getLogger(__name__) 

class ExecutionResult(Enum):
    """Enum representing execution result types"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CONDITIONAL = "conditional"

class WorkflowExecutor:
    """Helper class for workflow execution"""
    
    @classmethod
    async def execute_workflow_step(cls, 
                                   state: WorkflowState, 
                                   context: WorkflowContext, 
                                   integration_manager: Any) -> Dict[str, Any]:
        """Execute a single workflow step
        
        Args:
            state: Current state to execute
            context: Workflow execution context
            integration_manager: Integration manager for executing actions
            
        Returns:
            Dict[str, Any]: Execution result with next state information
        """
        action = state.action
        logger.info(f"Executing workflow action '{action.method}' on service '{action.service}'")
        
        # Process variables in the parameters
        processed_params = cls._process_parameters(action.params, context.variables, context.results)
        
        try:
            # Execute the action based on service type
            if action.service == "internal":
                result = await cls._execute_internal_action(action.method, processed_params, context)
            else:
                # Execute through integration manager
                result = await integration_manager.execute_action(
                    action.service, action.method, **processed_params
                )
            
            # Store the result in the context
            context.results[state.name] = result
            
            # Handle conditional returns from internal actions
            if isinstance(result, dict) and "event" in result:
                return {
                    "result_type": ExecutionResult.CONDITIONAL,
                    "event": result["event"],
                    "result": result
                }
            
            # Check for error results
            if isinstance(result, dict) and "error" in result:
                return {
                    "result_type": ExecutionResult.ERROR,
                    "error": result["error"],
                    "result": result
                }
            
            # Success case
            return {
                "result_type": ExecutionResult.SUCCESS,
                "result": result
            }
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout executing action '{action.method}' on '{action.service}'")
            return {
                "result_type": ExecutionResult.TIMEOUT,
                "error": f"Timeout executing action '{action.method}'"
            }
            
        except Exception as e:
            logger.error(f"Error executing action '{action.method}' on '{action.service}': {str(e)}")
            return {
                "result_type": ExecutionResult.ERROR,
                "error": str(e)
            }
    
    @classmethod
    def _process_parameters(cls, params: Dict[str, Any], variables: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
        """Process variables in parameters
        
        Args:
            params: Raw parameters with variable references
            variables: Workflow variables
            results: Results from previous states
            
        Returns:
            Dict[str, Any]: Processed parameters with variables substituted
        """
        import json
        import re
        
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
            elif parts[0] == 'uuid':
                return str(uuid.uuid4())
            
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
    
    @classmethod
    async def _execute_internal_action(cls, method: str, params: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        """Execute an internal action
        
        Args:
            method: Method name
            params: Method parameters
            context: Workflow context
            
        Returns:
            Dict[str, Any]: Action result
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
                if key != "method" and key != "service":  # Skip these reserved keys
                    context.variables[key] = value
            return {"variables_set": list(params.keys())}
        
        elif method == "conditional":
            # Evaluate a condition and return an event
            condition = params.get("condition")
            true_event = params.get("true_event", "condition_true")
            false_event = params.get("false_event", "condition_false")
            
            try:
                # For simple conditions in string format
                if isinstance(condition, str):
                    # Very limited eval for conditional expressions
                    # In real code, use a safer approach
                    result = eval(condition, {"__builtins__": {}}, context.variables)
                else:
                    result = bool(condition)
                    
                return {"event": true_event if result else false_event, "condition_result": result}
            except Exception as e:
                return {"error": f"Error evaluating condition: {str(e)}"}
        
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
            
            return {"logged": message, "level": level}
        
        elif method == "merge_variables":
            # Merge dictionaries into a variable
            target_var = params.get("target", "merged_result")
            sources = params.get("sources", [])
            merged = {}
            
            for source in sources:
                # Source can be a variable name or a direct dictionary
                if isinstance(source, str) and source in context.variables:
                    source_data = context.variables[source]
                    if isinstance(source_data, dict):
                        merged.update(source_data)
                elif isinstance(source, dict):
                    merged.update(source)
            
            context.variables[target_var] = merged
            return {"merged_to": target_var, "source_count": len(sources)}
            
        else:
            return {"error": f"Unknown internal method: {method}"}
            
class WorkflowExecutionEnhancer:
    """Enhances workflow execution with improved state machine processing"""
    
    def __init__(self, workflow_engine, integration_manager):
        self.workflow_engine = workflow_engine
        self.integration_manager = integration_manager
        self.active_executions = {}
    
    async def execute_workflow(self, execution_id: str) -> Dict[str, Any]:
        """Execute a workflow to completion
        
        Args:
            execution_id: Execution ID
        
        Returns:
            Dict[str, Any]: Execution result
        """
        if execution_id not in self.workflow_engine.active_workflows:
            return {"error": f"Workflow execution '{execution_id}' not found"}
        
        context = self.workflow_engine.active_workflows[execution_id]
        workflow_id = context.workflow_id
        
        if workflow_id not in self.workflow_engine.workflow_registry:
            return {"error": f"Workflow definition '{workflow_id}' not found"}
        
        workflow = self.workflow_engine.workflow_registry[workflow_id]
        
        # Initialize if not started
        if context.status == WorkflowStatus.NOT_STARTED:
            context.status = WorkflowStatus.RUNNING
            context.current_state = workflow.initial_state
            context.state_history = [workflow.initial_state]
            context.start_time = datetime.now()
            
            logger.info(f"Starting workflow execution '{execution_id}' in state '{workflow.initial_state}'")
        
        # Execute until completion or failure
        execution_result = await self._execute_workflow_steps(execution_id, workflow, context)
        
        return execution_result
    
    async def _execute_workflow_steps(self, execution_id: str, workflow: WorkflowDefinition, context: WorkflowContext) -> Dict[str, Any]:
        """Execute workflow steps until completion
        
        Args:
            execution_id: Execution ID
            workflow: Workflow definition
            context: Workflow context
            
        Returns:
            Dict[str, Any]: Execution result
        """
        max_steps = 100  # Safety limit to prevent infinite loops
        step_count = 0
        
        while context.status == WorkflowStatus.RUNNING and step_count < max_steps:
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
            
            logger.info(f"Executing state '{current_state_name}' in workflow '{workflow.id}'")
            
            # Execute the state with retry logic
            retry_count = 0
            execute_success = False
            execution_result = None
            
            while not execute_success and retry_count <= current_state.max_retries:
                try:
                    # Execute the action
                    execution_result = await WorkflowExecutor.execute_workflow_step(
                        current_state, context, self.integration_manager
                    )
                    
                    execute_success = True
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count <= current_state.max_retries:
                        logger.warning(
                            f"Retry {retry_count}/{current_state.max_retries} for state '{current_state_name}': {str(e)}"
                        )
                        await asyncio.sleep(current_state.retry_delay_seconds)
                    else:
                        execution_result = {
                            "result_type": ExecutionResult.ERROR,
                            "error": f"State execution failed after {retry_count} attempts: {str(e)}"
                        }
                        execute_success = True  # Exit retry loop
            
            # Handle execution result
            if execution_result["result_type"] == ExecutionResult.ERROR:
                # Check if there's an error transition
                if "error" in current_state.transitions:
                    next_state = current_state.transitions["error"]
                    context.current_state = next_state
                    context.state_history.append(next_state)
                else:
                    # No error handler, mark as failed
                    self._mark_execution_failed(
                        execution_id, execution_result["error"]
                    )
                    break
                    
            elif execution_result["result_type"] == ExecutionResult.TIMEOUT:
                # Handle timeout
                if current_state.on_timeout:
                    next_state = current_state.on_timeout
                    context.current_state = next_state
                    context.state_history.append(next_state)
                else:
                    # No timeout handler, mark as failed
                    self._mark_execution_failed(
                        execution_id, "State execution timed out"
                    )
                    break
                    
            elif execution_result["result_type"] == ExecutionResult.CONDITIONAL:
                # Handle conditional result
                event = execution_result["event"]
                if event in current_state.transitions:
                    next_state = current_state.transitions[event]
                    context.current_state = next_state
                    context.state_history.append(next_state)
                else:
                    # No matching transition, check for default
                    if "default" in current_state.transitions:
                        next_state = current_state.transitions["default"]
                        context.current_state = next_state
                        context.state_history.append(next_state)
                    elif "success" in current_state.transitions:
                        # Fall back to success transition
                        next_state = current_state.transitions["success"]
                        context.current_state = next_state 
                        context.state_history.append(next_state)
                    else:
                        # No transition defined, we're done
                        self._mark_execution_completed(execution_id)
                        break
            
            else:  # SUCCESS
                # Check for success transition
                if "success" in current_state.transitions:
                    next_state = current_state.transitions["success"]
                    context.current_state = next_state
                    context.state_history.append(next_state)
                else:
                    # No more transitions, we're done
                    self._mark_execution_completed(execution_id)
                    break
            
            step_count += 1
            
            # Check if we hit the step limit
            if step_count >= max_steps:
                self._mark_execution_failed(
                    execution_id, f"Workflow execution exceeded maximum steps ({max_steps})"
                )
                break
        
        return {
            "execution_id": execution_id,
            "workflow_id": workflow.id,
            "status": context.status,
            "steps_executed": step_count,
            "state_history": context.state_history,
            "variables": context.variables,
            "results": context.results,
            "error": context.error
        }
    
    def _mark_execution_failed(self, execution_id: str, error_message: str) -> None:
        """Mark a workflow execution as failed
        
        Args:
            execution_id: Execution ID
            error_message: Error message
        """
        if execution_id not in self.workflow_engine.active_workflows:
            return
        
        context = self.workflow_engine.active_workflows[execution_id]
        context.status = WorkflowStatus.FAILED
        context.error = error_message
        context.end_time = datetime.now()
        
        logger.error(f"Workflow execution '{execution_id}' failed: {error_message}")
    
    def _mark_execution_completed(self, execution_id: str) -> None:
        """Mark a workflow execution as completed
        
        Args:
            execution_id: Execution ID
        """
        if execution_id not in self.workflow_engine.active_workflows:
            return
        
        context = self.workflow_engine.active_workflows[execution_id]
        context.status = WorkflowStatus.COMPLETED
        context.end_time = datetime.now()
        
        logger.info(f"Workflow execution '{execution_id}' completed successfully")