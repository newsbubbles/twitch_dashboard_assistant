import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Add parent directory to the path so we can import client modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.integrations.obs_adapter_enhanced import OBSAdapter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_obs_connection')

async def test_connection():
    # Load environment variables
    load_dotenv()
    
    # Create OBS adapter
    obs = OBSAdapter()
    
    # Get connection details from environment or use defaults
    host = os.getenv('OBS_WEBSOCKET_HOST', 'localhost')
    port = int(os.getenv('OBS_WEBSOCKET_PORT', '4455'))
    password = os.getenv('OBS_WEBSOCKET_PASSWORD', '')
    
    logger.info(f"Connecting to OBS at {host}:{port}")
    
    # Try to connect
    connected = await obs.connect(host=host, port=port, password=password)
    
    if connected:
        logger.info("Successfully connected to OBS!")
        
        # Get status
        status = await obs.get_status()
        logger.info(f"OBS Version: {status.get('obs_version', 'Unknown')}")
        logger.info(f"WebSocket Version: {status.get('websocket_version', 'Unknown')}")
        logger.info(f"Current Scene: {status.get('current_scene', 'Unknown')}")
        logger.info(f"Streaming: {status.get('streaming', False)}")
        logger.info(f"Recording: {status.get('recording', False)}")
        
        # Get scenes
        scenes_result = await obs.execute_action('get_scene_list')
        scenes = scenes_result.get('scenes', [])
        logger.info(f"Available scenes: {[scene['name'] for scene in scenes]}")
        
        # Disconnect
        await obs.disconnect()
        logger.info("Disconnected from OBS")
    else:
        logger.error(f"Failed to connect to OBS: {obs.error_message}")

if __name__ == "__main__":
    asyncio.run(test_connection())
