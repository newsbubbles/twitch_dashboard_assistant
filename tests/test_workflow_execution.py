import asyncio
import logging
import sys
import os
import json
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from client.dashboard_assistant import DashboardAssistant
from client.workflow_execution import WorkflowExecutionEnhancer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("workflow_execution_test")

async def test_workflow_execution():
    """Test workflow execution functionality"""
    logger.info("Initializing Dashboard Assistant for testing...")
    
    # Initialize dashboard assistant
    assistant = DashboardAssistant()
    await assistant.initialize()
    
    try:
        # Connect to integrations
        # Note: This is a test, so we'll just log what would happen
        logger.info("In a real environment, we'd connect to OBS and Twitch here")
        
        # List available workflows
        workflows = assistant.list_workflows()
        logger.info(f"Found {len(workflows)} workflows:")
        for workflow in workflows:
            logger.info(f"  - {workflow['name']} (ID: {workflow['id']})")
        
        if not workflows:
            logger.warning("No workflows found, creating a test workflow")
            
            # Create test workflow
            test_workflow = {
                "id": "test_workflow",
                "name": "Test Workflow",
                "description": "A simple test workflow",
                "initial_state": "start",
                "states": [
                    {
                        "name": "start",
                        "description": "Start state",
                        "action": {
                            "service": "internal",
                            "method": "log",
                            "params": {
                                "message": "Starting test workflow",
                                "level": "info"
                            }
                        },
                        "transitions": {
                            "success": "wait"
                        }
                    },
                    {
                        "name": "wait",
                        "description": "Wait a bit",
                        "action": {
                            "service": "internal",
                            "method": "wait",
                            "params": {
                                "seconds": 1
                            }
                        },
                        "transitions": {
                            "success": "set_variables"
                        }
                    },
                    {
                        "name": "set_variables",
                        "description": "Set some variables",
                        "action": {
                            "service": "internal",
                            "method": "set_variables",
                            "params": {
                                "test_value": "Hello, world!",
                                "timestamp": "${timestamp}"
                            }
                        },
                        "transitions": {
                            "success": "conditional"
                        }
                    },
                    {
                        "name": "conditional",
                        "description": "Test conditional",
                        "action": {
                            "service": "internal",
                            "method": "conditional",
                            "params": {
                                "condition": True,
                                "true_event": "path_a",
                                "false_event": "path_b"
                            }
                        },
                        "transitions": {
                            "path_a": "end_success",
                            "path_b": "end_failure"
                        }
                    },
                    {
                        "name": "end_success",
                        "description": "Success end state",
                        "action": {
                            "service": "internal",
                            "method": "log",
                            "params": {
                                "message": "Test workflow completed successfully",
                                "level": "info"
                            }
                        },
                        "transitions": {}
                    },
                    {
                        "name": "end_failure",
                        "description": "Failure end state",
                        "action": {
                            "service": "internal",
                            "method": "log",
                            "params": {
                                "message": "Test workflow failed",
                                "level": "error"
                            }
                        },
                        "transitions": {}
                    }
                ],
                "triggers": ["test"],
                "version": "1.0",
                "tags": ["test"]
            }
            
            result = assistant.register_workflow(test_workflow)
            if result.get("success", False):
                logger.info(f"Registered test workflow: {result['workflow_id']}")
            else:
                logger.error(f"Failed to register test workflow: {result['message']}")
                return
        
        # Choose a workflow to execute
        test_workflow_id = workflows[0]['id'] if workflows else "test_workflow"
        
        # Start the workflow
        logger.info(f"Starting workflow {test_workflow_id}...")
        start_result = await assistant.start_workflow(test_workflow_id, {"test": True})
        
        if not start_result.get("success", False):
            logger.error(f"Failed to start workflow: {start_result.get('message')}")
            return
            
        execution_id = start_result["execution_id"]
        logger.info(f"Workflow started with execution ID: {execution_id}")
        
        # Monitor execution until completion
        completed = False
        iterations = 0
        max_iterations = 10  # Prevent infinite loop
        
        while not completed and iterations < max_iterations:
            status = assistant.get_workflow_status(execution_id)
            
            if status:
                logger.info(f"Execution status: {status['status']} - State: {status['current_state']}")
                
                if status["status"] in ["completed", "failed", "cancelled"]:
                    completed = True
                    logger.info(f"Workflow execution {status['status']}")
                    
                    # Show the state history
                    logger.info(f"State transitions: {' -> '.join(status['state_history'])}")
                    
                    # Show execution time
                    if status.get("start_time") and status.get("end_time"):
                        start = datetime.fromisoformat(status["start_time"])
                        end = datetime.fromisoformat(status["end_time"])
                        duration = (end - start).total_seconds()
                        logger.info(f"Execution time: {duration:.2f} seconds")
            else:
                logger.error(f"Could not get execution status for {execution_id}")
                break
            
            iterations += 1
            await asyncio.sleep(0.5)
        
        if not completed:
            logger.warning("Execution did not complete within expected time")
            
            # Try cancelling it
            cancel_result = await assistant.cancel_workflow(execution_id)
            logger.info(f"Cancelled workflow: {cancel_result}")
    
    finally:
        # Clean up
        try:
            logger.info("Closing Dashboard Assistant...")
            await assistant.close()
            logger.info("Test completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(test_workflow_execution())