import asyncio
import os
import logging
from dotenv import load_dotenv
from pprint import pprint

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("twitch_test")

# Ensure we can import from parent directory
import sys
sys.path.append("..")
from client.integrations.twitch_adapter import TwitchAdapter

async def test_twitch_adapter():
    """Test the Twitch adapter functionality."""
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    callback_url = os.getenv("TWITCH_CALLBACK_URL")
    
    if not client_id or not client_secret:
        logger.error("Missing Twitch API credentials in .env file")
        return False
    
    logger.info("Initializing Twitch adapter")
    adapter = TwitchAdapter()
    
    try:
        # Connect with app authentication
        logger.info("Connecting to Twitch API")
        connection_params = {
            "client_id": client_id,
            "client_secret": client_secret
        }
        if callback_url:
            connection_params["callback_url"] = callback_url
            
        success = await adapter.connect(**connection_params)
        
        if not success:
            logger.error(f"Failed to connect to Twitch API: {adapter.error_message}")
            return False
        
        logger.info("Successfully connected to Twitch API with app authentication")
        
        # Test user authentication (this will open a browser)
        proceed = input("Do you want to test user authentication? (y/n): ")
        if proceed.lower() == "y":
            logger.info("Starting user authentication...")
            scopes = [
                "CHANNEL_READ_STREAM_KEY",
                "CHANNEL_MANAGE_BROADCAST",
                "CHANNEL_READ_SUBSCRIPTIONS",
                "CHANNEL_READ_REDEMPTIONS",
                "CLIPS_EDIT",
                "USER_EDIT_BROADCAST",
                "USER_READ_BROADCAST",
                "CHAT_EDIT",
                "CHAT_READ"
            ]
            auth_result = await adapter.authenticate_user(scopes)
            
            if "error" in auth_result:
                logger.error(f"User authentication failed: {auth_result['error']}")
                return False
                
            logger.info("Successfully authenticated as user")
            logger.info(f"Authenticated as: {auth_result.get('user_display_name')}")
        
        # Run some test actions
        await test_actions(adapter)
        
        # Disconnect
        logger.info("Disconnecting from Twitch API")
        await adapter.disconnect()
        logger.info("Disconnected")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during Twitch adapter test: {str(e)}")
        return False

async def test_actions(adapter):
    """Test various Twitch API actions."""
    # Get authenticated user
    logger.info("\nGetting user information:")
    user_info = await adapter.execute_action("get_user")
    pprint(user_info)
    
    # Only run these tests if user is authenticated
    if adapter._user_authenticated:
        # Get channel information
        logger.info("\nGetting channel information:")
        channel_info = await adapter.execute_action("get_channel")
        pprint(channel_info)
        
        # Get stream information if broadcaster is live
        logger.info("\nGetting stream information:")
        stream_info = await adapter.execute_action("get_stream")
        pprint(stream_info)
        
        # Get chat settings
        logger.info("\nGetting chat settings:")
        chat_settings = await adapter.execute_action("get_chat_settings")
        pprint(chat_settings)
        
        # Get followers (if scopes allow)
        logger.info("\nGetting followers:")
        followers = await adapter.execute_action("get_followers", first=5)
        pprint(followers)
        
        # Get channel tags
        logger.info("\nGetting stream tags:")
        tags = await adapter.execute_action("get_stream_tags")
        pprint(tags)
    else:
        logger.info("Skipping authenticated user tests (no user authentication)")

if __name__ == "__main__":
    asyncio.run(test_twitch_adapter())
