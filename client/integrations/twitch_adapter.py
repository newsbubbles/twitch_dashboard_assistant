import logging
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime
from pydantic import BaseModel, Field

from twitchAPI.twitch import Twitch
from twitchAPI.eventsub import EventSub
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, EventSubSubscriptionError

from .base_adapter import IntegrationAdapter, ConnectionStatus, IntegrationCapability

logger = logging.getLogger(__name__)

class TwitchUserInfo(BaseModel):
    """Model representing Twitch user information"""
    id: str = Field(..., description="Twitch user ID")
    login: str = Field(..., description="Twitch username (login)")
    display_name: str = Field(..., description="Display name")
    profile_image_url: Optional[str] = Field(None, description="Profile image URL")
    offline_image_url: Optional[str] = Field(None, description="Offline image URL")
    broadcaster_type: Optional[str] = Field(None, description="Broadcaster type")
    description: Optional[str] = Field(None, description="Channel description")
    created_at: Optional[datetime] = Field(None, description="Account creation date")

class TwitchStreamInfo(BaseModel):
    """Model representing a Twitch stream"""
    id: str = Field(..., description="Stream ID")
    user_id: str = Field(..., description="Broadcaster ID")
    user_name: str = Field(..., description="Broadcaster username")
    game_id: str = Field(..., description="Game/category ID")
    game_name: str = Field(..., description="Game/category name")
    type: str = Field(..., description="Stream type")
    title: str = Field(..., description="Stream title")
    viewer_count: int = Field(..., description="Current viewer count")
    started_at: datetime = Field(..., description="Stream start time")
    language: str = Field(..., description="Stream language")
    thumbnail_url: str = Field(..., description="Thumbnail URL")
    tags: List[str] = Field(default_factory=list, description="Stream tags")
    is_mature: Optional[bool] = Field(None, description="Whether stream is marked as mature")

class TwitchChatSettings(BaseModel):
    """Model representing Twitch chat settings"""
    emote_mode: bool = Field(..., description="Emote-only mode")
    follower_mode: bool = Field(..., description="Follower-only mode")
    follower_mode_duration: Optional[int] = Field(
        None, description="Required follow time in minutes"
    )
    slow_mode: bool = Field(..., description="Slow mode")
    slow_mode_delay: Optional[int] = Field(None, description="Slow mode delay in seconds")
    subscriber_mode: bool = Field(..., description="Subscriber-only mode")
    unique_chat_mode: bool = Field(..., description="Unique chat mode (no duplicate messages)")

class TwitchChannelInfo(BaseModel):
    """Model representing Twitch channel information"""
    broadcaster_id: str = Field(..., description="Broadcaster ID")
    broadcaster_login: str = Field(..., description="Broadcaster login")
    broadcaster_name: str = Field(..., description="Broadcaster display name")
    broadcaster_language: str = Field(..., description="Broadcaster language")
    title: str = Field(..., description="Stream title")
    category_id: str = Field(..., description="Category ID")
    category_name: str = Field(..., description="Category name")
    is_mature: bool = Field(False, description="Whether channel is marked as mature")

class TwitchAdapter(IntegrationAdapter):
    """Adapter for Twitch API"""

    def __init__(self):
        super().__init__("Twitch")
        self._capabilities = [
            IntegrationCapability.CHAT_INTERACTION,
            IntegrationCapability.ANALYTICS,
            IntegrationCapability.EVENT_SUBSCRIPTION,
        ]
        self._twitch: Optional[Twitch] = None
        self._eventsub: Optional[EventSub] = None
        self._app_authenticated: bool = False
        self._user_authenticated: bool = False
        self._auth_scopes: List[AuthScope] = []
        self._client_id: str = ""
        self._client_secret: str = ""
        self._user_id: Optional[str] = None
        self._user_login: Optional[str] = None
        self._user_display_name: Optional[str] = None
        self._event_callbacks: Dict[str, List[Callable]] = {}
        self._active_subscriptions: Dict[str, str] = {}
        self._callback_url: Optional[str] = None

    async def connect(self, client_id: str, client_secret: str, **kwargs) -> bool:
        """Connect to Twitch API using app credentials
        
        Args:
            client_id: Twitch API client ID
            client_secret: Twitch API client secret
            **kwargs: Additional connection parameters
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        self._update_status(ConnectionStatus.CONNECTING)
        
        self._client_id = client_id
        self._client_secret = client_secret
        
        try:
            # Initialize Twitch API client
            self._twitch = await Twitch(client_id, client_secret)
            self._app_authenticated = True
            
            # Set up EventSub if callback URL provided
            callback_url = kwargs.get('callback_url')
            if callback_url:
                self._callback_url = callback_url
                if self._user_authenticated:  # EventSub requires user authentication
                    await self._setup_eventsub()
            
            self._update_status(ConnectionStatus.CONNECTED)
            return True
        except Exception as e:
            error_message = f"Failed to authenticate with Twitch API: {str(e)}"
            self._update_status(ConnectionStatus.ERROR, error_message)
            logger.error(error_message)
            return False

    async def authenticate_user(self, scopes: List[str]) -> Dict[str, Any]:
        """Authenticate with Twitch API using user authentication
        
        Args:
            scopes: List of OAuth scope strings
            
        Returns:
            Dict[str, Any]: Result containing tokens or error
        """
        if not self._app_authenticated or not self._twitch:
            return {"error": "Must connect with app credentials first"}
        
        try:
            # Convert scope strings to AuthScope enum values
            auth_scopes = [getattr(AuthScope, scope) for scope in scopes if hasattr(AuthScope, scope)]
            
            # Initialize authenticator
            auth = UserAuthenticator(self._twitch, auth_scopes)
            
            # Authenticate (this will open a browser)
            token, refresh_token = await auth.authenticate()
            
            # Set authentication in Twitch client
            self._auth_scopes = auth_scopes
            await self._twitch.set_user_authentication(token, auth_scopes, refresh_token)
            
            # Get authenticated user info
            user_info = await self._get_authenticated_user_info()
            
            # Set up EventSub if callback URL was provided
            if self._callback_url:
                await self._setup_eventsub()
            
            self._user_authenticated = True
            return {
                "success": True,
                "token": token,
                "refresh_token": refresh_token,
                "user_id": self._user_id,
                "user_login": self._user_login,
                "user_display_name": self._user_display_name
            }
        except Exception as e:
            error_message = f"User authentication failed: {str(e)}"
            logger.error(error_message)
            return {"error": error_message}

    async def _get_authenticated_user_info(self) -> bool:
        """Get information about the authenticated user
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._twitch:
            return False
        
        try:
            # Get authenticated user's info
            user_info = await self._twitch.get_users()
            if not user_info.data:
                return False
            
            user = user_info.data[0]
            self._user_id = user.id
            self._user_login = user.login
            self._user_display_name = user.display_name
            
            return True
        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            return False

    async def _setup_eventsub(self) -> bool:
        """Set up EventSub for real-time events
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._twitch or not self._callback_url or not self._user_id:
            logger.error("Cannot set up EventSub: missing Twitch client, callback URL, or user ID")
            return False
        
        try:
            # Initialize EventSub
            self._eventsub = EventSub(self._callback_url, self._twitch)
            await self._eventsub.start()
            logger.info(f"EventSub initialized with callback URL: {self._callback_url}")
            
            # Restore any active subscriptions
            if self._active_subscriptions:
                for event_type, condition in self._active_subscriptions.items():
                    await self._create_subscription(event_type, condition)
            
            return True
        except Exception as e:
            logger.error(f"Failed to set up EventSub: {str(e)}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Twitch API
        
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        try:
            # Stop EventSub
            if self._eventsub:
                await self._eventsub.stop()
                self._eventsub = None
            
            # Close Twitch client
            if self._twitch:
                await self._twitch.close()
                self._twitch = None
            
            self._app_authenticated = False
            self._user_authenticated = False
            self._update_status(ConnectionStatus.DISCONNECTED)
            return True
        except Exception as e:
            error_message = f"Error disconnecting from Twitch API: {str(e)}"
            self._update_status(ConnectionStatus.ERROR, error_message)
            logger.error(error_message)
            return False

    async def subscribe_to_event(self, event_type: str, **condition) -> Dict[str, Any]:
        """Subscribe to a Twitch event
        
        Args:
            event_type: Event type to subscribe to (e.g., 'channel_follow')
            **condition: Parameters for the subscription
            
        Returns:
            Dict[str, Any]: Result containing subscription ID or error
        """
        if not self._user_authenticated or not self._eventsub:
            return {"error": "Not authenticated or EventSub not initialized"}
        
        try:
            # Create the subscription
            subscription_id = await self._create_subscription(event_type, condition)
            
            return {
                "success": True,
                "subscription_id": subscription_id,
                "event_type": event_type
            }
        except EventSubSubscriptionError as e:
            return {"error": f"Failed to subscribe to event: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    async def _create_subscription(self, event_type: str, condition: Dict[str, Any]) -> str:
        """Create an EventSub subscription
        
        Args:
            event_type: Event type to subscribe to
            condition: Parameters for the subscription
            
        Returns:
            str: Subscription ID if successful
        """
        if not self._eventsub or not self._user_id:
            raise ValueError("EventSub not initialized or user ID not available")
        
        # Format event type for method name (replace dots with underscores)
        method_name = f"listen_{event_type.replace('.', '_')}"
        
        if hasattr(self._eventsub, method_name):
            method = getattr(self._eventsub, method_name)
            
            # Add broadcaster_user_id if not already in condition
            if "broadcaster_user_id" not in condition and "broadcaster_id" not in condition:
                condition["broadcaster_user_id"] = self._user_id
            
            # Create subscription
            subscription_id = await method(**condition, callback=self._event_callback)
            self._active_subscriptions[event_type] = subscription_id
            
            logger.info(f"Subscribed to {event_type} events, ID: {subscription_id}")
            return subscription_id
        
        raise ValueError(f"Unsupported event type: {event_type}")

    async def _event_callback(self, uuid: str, data: dict) -> None:
        """Handle EventSub callback
        
        Args:
            uuid: Subscription UUID
            data: Event data
        """
        try:
            event_type = data.get('subscription', {}).get('type', '')
            logger.debug(f"Received {event_type} event: {data}")
            
            # Call any registered callbacks for this event type
            if event_type in self._event_callbacks:
                for callback in self._event_callbacks[event_type]:
                    try:
                        await callback(data)
                    except Exception as e:
                        logger.error(f"Error in event callback: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing event: {str(e)}")

    async def unsubscribe_from_event(self, event_type: str) -> Dict[str, Any]:
        """Unsubscribe from a Twitch event
        
        Args:
            event_type: Event type to unsubscribe from
            
        Returns:
            Dict[str, Any]: Result of the unsubscription
        """
        if not self._eventsub:
            return {"error": "EventSub not initialized"}
        
        if event_type not in self._active_subscriptions:
            return {"error": f"No active subscription for {event_type}"}
        
        try:
            subscription_id = self._active_subscriptions[event_type]
            await self._eventsub.delete_subscription(subscription_id)
            del self._active_subscriptions[event_type]
            
            logger.info(f"Unsubscribed from {event_type} events")
            return {"success": True}
        except Exception as e:
            return {"error": f"Error unsubscribing: {str(e)}"}

    def register_event_callback(self, event_type: str, callback: Callable):
        """Register a callback for an event type
        
        Args:
            event_type: Event type to listen for
            callback: Async function to call when event occurs
        """
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        
        self._event_callbacks[event_type].append(callback)
        logger.debug(f"Registered callback for {event_type} events")

    def unregister_event_callback(self, event_type: str, callback: Callable) -> bool:
        """Unregister an event callback
        
        Args:
            event_type: Event type
            callback: Callback to remove
            
        Returns:
            bool: True if callback was removed, False if not found
        """
        if event_type in self._event_callbacks and callback in self._event_callbacks[event_type]:
            self._event_callbacks[event_type].remove(callback)
            return True
        return False

    async def execute_action(self, action: str, **params) -> Dict[str, Any]:
        """Execute a Twitch action
        
        Args:
            action: The name of the action to execute
            **params: Parameters for the action
            
        Returns:
            Dict[str, Any]: Result of the action
        """
        if not self._twitch:
            return {"error": "Not connected to Twitch API"}
        
        try:
            # Map action names to methods
            action_map = {
                "get_user": self._get_user,
                "get_users": self._get_users,
                "get_channel": self._get_channel,
                "update_channel": self._update_channel,
                "get_stream": self._get_stream,
                "get_streams": self._get_streams,
                "get_followers": self._get_followers,
                "get_followed_channels": self._get_followed_channels,
                "get_channel_info": self._get_channel_info,
                "get_chat_settings": self._get_chat_settings,
                "update_chat_settings": self._update_chat_settings,
                "create_clip": self._create_clip,
                "get_clips": self._get_clips,
                "start_commercial": self._start_commercial,
                "get_channel_emotes": self._get_channel_emotes,
                "get_global_emotes": self._get_global_emotes,
                "send_chat_announcement": self._send_chat_announcement,
                "send_chat_message": self._send_chat_message,
                "delete_chat_message": self._delete_chat_message,
                "ban_user": self._ban_user,
                "unban_user": self._unban_user,
                "get_moderators": self._get_moderators,
                "add_moderator": self._add_moderator,
                "remove_moderator": self._remove_moderator,
                "get_vips": self._get_vips,
                "add_vip": self._add_vip,
                "remove_vip": self._remove_vip,
                "create_stream_marker": self._create_stream_marker,
                "get_stream_markers": self._get_stream_markers,
                "raid_channel": self._raid_channel,
                "cancel_raid": self._cancel_raid,
                "get_polls": self._get_polls,
                "create_poll": self._create_poll,
                "end_poll": self._end_poll,
                "get_predictions": self._get_predictions,
                "create_prediction": self._create_prediction,
                "end_prediction": self._end_prediction,
                "get_channel_rewards": self._get_channel_rewards,
                "create_channel_reward": self._create_channel_reward,
                "delete_channel_reward": self._delete_channel_reward,
                "get_channel_reward_redemptions": self._get_channel_reward_redemptions,
                "update_redemption_status": self._update_redemption_status,
                "get_hype_train": self._get_hype_train,
                "get_stream_tags": self._get_stream_tags,
                "replace_stream_tags": self._replace_stream_tags
            }
            
            if action not in action_map:
                return {"error": f"Unknown action: {action}"}
            
            # Execute the action
            result = await action_map[action](**params)
            return result
        
        except Exception as e:
            logger.error(f"Error executing Twitch action '{action}': {str(e)}")
            return {"error": str(e)}

    async def _get_user(self, user_id: Optional[str] = None, login: Optional[str] = None) -> Dict[str, Any]:
        """Get user information by ID or login"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not user_id and not login:
            # If neither is provided, return authenticated user
            if not self._user_authenticated:
                raise ValueError("No user ID or login provided, and no authenticated user")
            user_id = self._user_id
        
        response = await self._twitch.get_users(user_ids=[user_id] if user_id else None, 
                                           logins=[login] if login else None)
        
        if not response.data:
            return {"error": "User not found"}
        
        user = response.data[0]
        return TwitchUserInfo(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            profile_image_url=user.profile_image_url,
            offline_image_url=user.offline_image_url,
            broadcaster_type=user.broadcaster_type,
            description=user.description,
            created_at=user.created_at
        ).model_dump()

    async def _get_users(self, user_ids: Optional[List[str]] = None, 
                     logins: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get multiple users by IDs or logins"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not user_ids and not logins:
            return {"users": []}
        
        response = await self._twitch.get_users(user_ids=user_ids, logins=logins)
        
        users = []
        for user in response.data:
            users.append(TwitchUserInfo(
                id=user.id,
                login=user.login,
                display_name=user.display_name,
                profile_image_url=user.profile_image_url,
                offline_image_url=user.offline_image_url,
                broadcaster_type=user.broadcaster_type,
                description=user.description,
                created_at=user.created_at
            ).model_dump())
        
        return {"users": users}

    async def _get_channel(self, broadcaster_id: Optional[str] = None) -> Dict[str, Any]:
        """Get channel information"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not broadcaster_id:
            if not self._user_authenticated:
                raise ValueError("No broadcaster ID provided, and no authenticated user")
            broadcaster_id = self._user_id
        
        response = await self._twitch.get_channel_information(broadcaster_id=broadcaster_id)
        
        if not response.data:
            return {"error": "Channel not found"}
        
        channel = response.data[0]
        return TwitchChannelInfo(
            broadcaster_id=channel.broadcaster_id,
            broadcaster_login=channel.broadcaster_login,
            broadcaster_name=channel.broadcaster_name,
            broadcaster_language=channel.broadcaster_language,
            title=channel.title,
            category_id=channel.game_id,
            category_name=channel.game_name,
            is_mature=channel.is_mature
        ).model_dump()

    # More Twitch API methods would be implemented here
    # For brevity, we'll skip the implementation details of all methods
    # and just list placeholders for them

    async def _update_channel(self, **params) -> Dict[str, Any]:
        # Implementation for updating channel
        return {"success": True}

    async def _get_stream(self, **params) -> Dict[str, Any]:
        # Implementation for getting stream
        return {"stream": {}}

    async def _get_streams(self, **params) -> Dict[str, Any]:
        # Implementation for getting multiple streams
        return {"streams": []}

    async def _get_followers(self, **params) -> Dict[str, Any]:
        # Implementation for getting followers
        return {"followers": []}

    async def _get_followed_channels(self, **params) -> Dict[str, Any]:
        # Implementation for getting followed channels
        return {"followed_channels": []}

    async def _get_channel_info(self, **params) -> Dict[str, Any]:
        # Implementation for getting channel info
        return {"channel_info": {}}

    async def _get_chat_settings(self, **params) -> Dict[str, Any]:
        # Implementation for getting chat settings
        return {"chat_settings": {}}

    async def _update_chat_settings(self, **params) -> Dict[str, Any]:
        # Implementation for updating chat settings
        return {"success": True}

    async def _create_clip(self, **params) -> Dict[str, Any]:
        # Implementation for creating a clip
        return {"clip": {}}

    async def _get_clips(self, **params) -> Dict[str, Any]:
        # Implementation for getting clips
        return {"clips": []}

    async def _start_commercial(self, **params) -> Dict[str, Any]:
        # Implementation for starting a commercial
        return {"success": True}

    async def _get_channel_emotes(self, **params) -> Dict[str, Any]:
        # Implementation for getting channel emotes
        return {"emotes": []}

    async def _get_global_emotes(self, **params) -> Dict[str, Any]:
        # Implementation for getting global emotes
        return {"emotes": []}

    async def _send_chat_announcement(self, **params) -> Dict[str, Any]:
        # Implementation for sending chat announcement
        return {"success": True}

    async def _send_chat_message(self, **params) -> Dict[str, Any]:
        # Implementation for sending chat message
        return {"success": True}

    async def _delete_chat_message(self, **params) -> Dict[str, Any]:
        # Implementation for deleting chat message
        return {"success": True}

    async def _ban_user(self, **params) -> Dict[str, Any]:
        # Implementation for banning a user
        return {"success": True}

    async def _unban_user(self, **params) -> Dict[str, Any]:
        # Implementation for unbanning a user
        return {"success": True}

    async def _get_moderators(self, **params) -> Dict[str, Any]:
        # Implementation for getting moderators
        return {"moderators": []}

    async def _add_moderator(self, **params) -> Dict[str, Any]:
        # Implementation for adding a moderator
        return {"success": True}

    async def _remove_moderator(self, **params) -> Dict[str, Any]:
        # Implementation for removing a moderator
        return {"success": True}

    async def _get_vips(self, **params) -> Dict[str, Any]:
        # Implementation for getting VIPs
        return {"vips": []}

    async def _add_vip(self, **params) -> Dict[str, Any]:
        # Implementation for adding a VIP
        return {"success": True}

    async def _remove_vip(self, **params) -> Dict[str, Any]:
        # Implementation for removing a VIP
        return {"success": True}

    async def _create_stream_marker(self, **params) -> Dict[str, Any]:
        # Implementation for creating a stream marker
        return {"marker": {}}

    async def _get_stream_markers(self, **params) -> Dict[str, Any]:
        # Implementation for getting stream markers
        return {"markers": []}

    async def _raid_channel(self, **params) -> Dict[str, Any]:
        # Implementation for raiding a channel
        return {"success": True}

    async def _cancel_raid(self, **params) -> Dict[str, Any]:
        # Implementation for canceling a raid
        return {"success": True}

    async def _get_polls(self, **params) -> Dict[str, Any]:
        # Implementation for getting polls
        return {"polls": []}

    async def _create_poll(self, **params) -> Dict[str, Any]:
        # Implementation for creating a poll
        return {"poll": {}}

    async def _end_poll(self, **params) -> Dict[str, Any]:
        # Implementation for ending a poll
        return {"success": True}

    async def _get_predictions(self, **params) -> Dict[str, Any]:
        # Implementation for getting predictions
        return {"predictions": []}

    async def _create_prediction(self, **params) -> Dict[str, Any]:
        # Implementation for creating a prediction
        return {"prediction": {}}

    async def _end_prediction(self, **params) -> Dict[str, Any]:
        # Implementation for ending a prediction
        return {"success": True}

    async def _get_channel_rewards(self, **params) -> Dict[str, Any]:
        # Implementation for getting channel rewards
        return {"rewards": []}

    async def _create_channel_reward(self, **params) -> Dict[str, Any]:
        # Implementation for creating a channel reward
        return {"reward": {}}

    async def _delete_channel_reward(self, **params) -> Dict[str, Any]:
        # Implementation for deleting a channel reward
        return {"success": True}

    async def _get_channel_reward_redemptions(self, **params) -> Dict[str, Any]:
        # Implementation for getting reward redemptions
        return {"redemptions": []}

    async def _update_redemption_status(self, **params) -> Dict[str, Any]:
        # Implementation for updating redemption status
        return {"success": True}

    async def _get_hype_train(self, **params) -> Dict[str, Any]:
        # Implementation for getting hype train info
        return {"hype_train": {}}

    async def _get_stream_tags(self, **params) -> Dict[str, Any]:
        # Implementation for getting stream tags
        return {"tags": []}

    async def _replace_stream_tags(self, **params) -> Dict[str, Any]:
        # Implementation for replacing stream tags
        return {"success": True}

    async def get_status(self) -> Dict[str, Any]:
        """Get detailed status information
        
        Returns:
            Dict[str, Any]: A dictionary with status information
        """
        result = {
            "connection_status": self._status,
            "app_authenticated": self._app_authenticated,
            "user_authenticated": self._user_authenticated,
            "capabilities": self._capabilities,
            "event_sub_enabled": self._eventsub is not None
        }
        
        if self._user_authenticated and self._user_id:
            result.update({
                "user_id": self._user_id,
                "user_login": self._user_login,
                "user_display_name": self._user_display_name,
                "auth_scopes": [scope.name for scope in self._auth_scopes]
            })
        
        if self._eventsub and self._active_subscriptions:
            result["active_subscriptions"] = list(self._active_subscriptions.keys())
        
        return result
