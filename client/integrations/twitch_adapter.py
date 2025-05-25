import logging
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime
from pydantic import BaseModel, Field

from twitchAPI.twitch import Twitch
from twitchAPI.eventsub import EventSub
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, EventSubSubscriptionError
from twitchAPI.helper import first

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

class TwitchFollower(BaseModel):
    """Model representing a Twitch follower"""
    user_id: str = Field(..., description="ID of the user following the broadcaster")
    user_login: str = Field(..., description="Login of the user following the broadcaster")
    user_name: str = Field(..., description="Display name of the user following the broadcaster")
    followed_at: datetime = Field(..., description="Date and time when the user started following the broadcaster")

class TwitchClip(BaseModel):
    """Model representing a Twitch clip"""
    id: str = Field(..., description="ID of the clip")
    url: str = Field(..., description="URL of the clip")
    embed_url: str = Field(..., description="Embed URL of the clip")
    broadcaster_id: str = Field(..., description="ID of the broadcaster")
    broadcaster_name: str = Field(..., description="Display name of the broadcaster")
    creator_id: str = Field(..., description="ID of the user who created the clip")
    creator_name: str = Field(..., description="Display name of the user who created the clip")
    video_id: str = Field(..., description="ID of the video the clip was created from")
    game_id: str = Field(..., description="ID of the game assigned to the stream when the clip was created")
    language: str = Field(..., description="Language of the stream when the clip was created")
    title: str = Field(..., description="Title of the clip")
    view_count: int = Field(..., description="Number of views of the clip")
    created_at: datetime = Field(..., description="Date and time when the clip was created")
    thumbnail_url: str = Field(..., description="URL of the clip's thumbnail")
    duration: float = Field(..., description="Duration of the clip in seconds")

class TwitchStreamMarker(BaseModel):
    """Model representing a Twitch stream marker"""
    id: str = Field(..., description="ID of the marker")
    created_at: datetime = Field(..., description="Date and time when the marker was created")
    description: Optional[str] = Field(None, description="Description of the marker")
    position_seconds: int = Field(..., description="Position in the stream (in seconds) where the marker was created")

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

    async def _update_channel(self, broadcaster_id: Optional[str] = None, title: Optional[str] = None, 
                          category_id: Optional[str] = None, broadcaster_language: Optional[str] = None) -> Dict[str, Any]:
        """Update channel information"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not broadcaster_id:
            broadcaster_id = self._user_id
            if not broadcaster_id:
                return {"error": "No broadcaster ID provided"}
        
        try:
            # Need at least one parameter to update
            if not any([title, category_id, broadcaster_language]):
                return {"error": "At least one update parameter required"}
            
            # Build parameters dict with only the values to update
            params = {}
            if title is not None:
                params['title'] = title
            if category_id is not None:
                params['game_id'] = category_id
            if broadcaster_language is not None:
                params['broadcaster_language'] = broadcaster_language
            
            await self._twitch.modify_channel_information(broadcaster_id=broadcaster_id, **params)
            
            # Get updated channel information
            return await self._get_channel(broadcaster_id)
        except Exception as e:
            return {"error": str(e)}

    async def _get_stream(self, broadcaster_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current stream information for a broadcaster"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not broadcaster_id:
            if not self._user_authenticated or not self._user_id:
                return {"error": "No broadcaster ID provided"}
            broadcaster_id = self._user_id
        
        try:
            response = await self._twitch.get_streams(user_id=broadcaster_id)
            
            if not response.data:
                return {"stream": None, "is_live": False}
            
            stream = response.data[0]
            stream_info = TwitchStreamInfo(
                id=stream.id,
                user_id=stream.user_id,
                user_name=stream.user_name,
                game_id=stream.game_id,
                game_name=stream.game_name,
                type=stream.type,
                title=stream.title,
                viewer_count=stream.viewer_count,
                started_at=stream.started_at,
                language=stream.language,
                thumbnail_url=stream.thumbnail_url,
                tags=stream.tags,
                is_mature=stream.is_mature
            ).model_dump()
            
            return {"stream": stream_info, "is_live": True}
        except Exception as e:
            return {"error": str(e)}

    async def _get_streams(self, user_ids: Optional[List[str]] = None, game_id: Optional[str] = None, 
                       first: int = 20, language: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get streams based on various filters"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        try:
            streams_list = []
            # Use async generator to get multiple pages if needed
            async for stream in self._twitch.get_streams(user_id=user_ids, game_id=game_id,
                                                      language=language, first=min(first, 100)):
                streams_list.append(TwitchStreamInfo(
                    id=stream.id,
                    user_id=stream.user_id,
                    user_name=stream.user_name,
                    game_id=stream.game_id,
                    game_name=stream.game_name,
                    type=stream.type,
                    title=stream.title,
                    viewer_count=stream.viewer_count,
                    started_at=stream.started_at,
                    language=stream.language,
                    thumbnail_url=stream.thumbnail_url,
                    tags=stream.tags,
                    is_mature=stream.is_mature
                ).model_dump())
                
                if len(streams_list) >= first:
                    break
            
            return {"streams": streams_list}
        except Exception as e:
            return {"error": str(e)}

    async def _get_followers(self, broadcaster_id: Optional[str] = None, first: int = 20) -> Dict[str, Any]:
        """Get followers of a broadcaster"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not broadcaster_id:
            if not self._user_id:
                return {"error": "No broadcaster ID provided"}
            broadcaster_id = self._user_id
        
        try:
            # Get followers
            followers = []
            total = 0
            
            try:
                # First try getting followers with the current API endpoint
                # Note: As of 2023, the API returns followers with total in the response
                response = await self._twitch.get_channel_followers(broadcaster_id=broadcaster_id, first=min(first, 100))
                
                for follower in response.data:
                    followers.append(TwitchFollower(
                        user_id=follower.user_id,
                        user_login=follower.user_login,
                        user_name=follower.user_name,
                        followed_at=follower.followed_at
                    ).model_dump())
                
                total = response.total
            except Exception as e:
                # If the API call fails, it might be using an older API version or endpoint changed
                logger.warning(f"Could not get followers with standard API: {str(e)}")
                return {"error": "Could not retrieve followers. API endpoint may have changed."}
            
            return {"followers": followers, "total": total}
        except Exception as e:
            return {"error": str(e)}

    async def _get_followed_channels(self, user_id: Optional[str] = None, first: int = 20) -> Dict[str, Any]:
        """Get channels that a user follows"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not user_id:
            if not self._user_id:
                return {"error": "No user ID provided"}
            user_id = self._user_id
        
        try:
            # Get followed channels
            followed_channels = []
            total = 0
            
            try:
                # Get followed channels
                response = await self._twitch.get_followed_channels(user_id=user_id, first=min(first, 100))
                
                for channel in response.data:
                    followed_channels.append({
                        "broadcaster_id": channel.broadcaster_id,
                        "broadcaster_login": channel.broadcaster_login,
                        "broadcaster_name": channel.broadcaster_name,
                        "followed_at": channel.followed_at
                    })
                
                total = response.total
            except Exception as e:
                # If the API call fails, it might be using an older API version or endpoint changed
                logger.warning(f"Could not get followed channels with standard API: {str(e)}")
                return {"error": "Could not retrieve followed channels. API endpoint may have changed."}
            
            return {"followed_channels": followed_channels, "total": total}
        except Exception as e:
            return {"error": str(e)}

    async def _get_chat_settings(self, broadcaster_id: Optional[str] = None, moderator_id: Optional[str] = None) -> Dict[str, Any]:
        """Get chat settings for a channel"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not broadcaster_id:
            if not self._user_authenticated or not self._user_id:
                return {"error": "No broadcaster ID provided"}
            broadcaster_id = self._user_id
        
        if not moderator_id and self._user_authenticated and self._user_id:
            moderator_id = self._user_id
        
        try:
            settings = await self._twitch.get_chat_settings(broadcaster_id=broadcaster_id, moderator_id=moderator_id)
            
            chat_settings = TwitchChatSettings(
                emote_mode=settings.emote_mode,
                follower_mode=settings.follower_mode,
                follower_mode_duration=settings.follower_mode_duration,
                slow_mode=settings.slow_mode,
                slow_mode_delay=settings.slow_mode_wait_time,
                subscriber_mode=settings.subscriber_mode,
                unique_chat_mode=settings.unique_chat_mode
            )
            
            return {"chat_settings": chat_settings.model_dump()}
        except Exception as e:
            return {"error": str(e)}

    async def _update_chat_settings(self, broadcaster_id: str, moderator_id: str, **settings) -> Dict[str, Any]:
        """Update chat settings for a channel"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        try:
            # Map our parameter names to the ones the Twitch API expects
            param_map = {
                "emote_mode": "emote_mode",
                "follower_mode": "follower_mode",
                "follower_mode_duration": "follower_mode_duration",
                "slow_mode": "slow_mode",
                "slow_mode_delay": "slow_mode_wait_time",
                "subscriber_mode": "subscriber_mode",
                "unique_chat_mode": "unique_chat_mode"
            }
            
            # Build parameters dict with only the values to update
            params = {}
            for key, value in settings.items():
                if key in param_map and value is not None:
                    params[param_map[key]] = value
            
            # Need at least one parameter to update
            if not params:
                return {"error": "At least one setting parameter required"}
            
            # Update chat settings
            updated = await self._twitch.update_chat_settings(broadcaster_id=broadcaster_id, 
                                                        moderator_id=moderator_id, 
                                                        **params)
            
            chat_settings = TwitchChatSettings(
                emote_mode=updated.emote_mode,
                follower_mode=updated.follower_mode,
                follower_mode_duration=updated.follower_mode_duration,
                slow_mode=updated.slow_mode,
                slow_mode_delay=updated.slow_mode_wait_time,
                subscriber_mode=updated.subscriber_mode,
                unique_chat_mode=updated.unique_chat_mode
            )
            
            return {"chat_settings": chat_settings.model_dump()}
        except Exception as e:
            return {"error": str(e)}

    async def _create_clip(self, broadcaster_id: Optional[str] = None, has_delay: bool = False) -> Dict[str, Any]:
        """Create a clip of the current broadcast"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not broadcaster_id:
            if not self._user_id:
                return {"error": "No broadcaster ID provided"}
            broadcaster_id = self._user_id
        
        try:
            clip = await self._twitch.create_clip(broadcaster_id=broadcaster_id, has_delay=has_delay)
            
            return {
                "clip_id": clip.id,
                "edit_url": clip.edit_url,
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    async def _get_clips(self, broadcaster_id: Optional[str] = None, 
                     clip_id: Optional[List[str]] = None, 
                     game_id: Optional[str] = None,
                     first: int = 20) -> Dict[str, Any]:
        """Get clips for a broadcaster, game, or specific clip IDs"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        try:
            # Make sure at least one filter is provided
            if not any([broadcaster_id, clip_id, game_id]):
                if self._user_authenticated and self._user_id:
                    broadcaster_id = self._user_id
                else:
                    return {"error": "At least one of broadcaster_id, clip_id, or game_id must be provided"}
            
            clips = []
            async for clip in self._twitch.get_clips(
                broadcaster_id=broadcaster_id,
                game_id=game_id,
                clip_id=clip_id,
                first=min(first, 100)
            ):
                clips.append(TwitchClip(
                    id=clip.id,
                    url=clip.url,
                    embed_url=clip.embed_url,
                    broadcaster_id=clip.broadcaster_id,
                    broadcaster_name=clip.broadcaster_name,
                    creator_id=clip.creator_id,
                    creator_name=clip.creator_name,
                    video_id=clip.video_id,
                    game_id=clip.game_id,
                    language=clip.language,
                    title=clip.title,
                    view_count=clip.view_count,
                    created_at=clip.created_at,
                    thumbnail_url=clip.thumbnail_url,
                    duration=clip.duration
                ).model_dump())
                
                if len(clips) >= first:
                    break
            
            return {"clips": clips}
        except Exception as e:
            return {"error": str(e)}

    async def _create_stream_marker(self, user_id: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Create a stream marker at the current timestamp"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not user_id:
            if not self._user_id:
                return {"error": "No user ID provided"}
            user_id = self._user_id
        
        try:
            marker = await self._twitch.create_stream_marker(user_id=user_id, description=description)
            
            return {
                "marker": {
                    "id": marker.id,
                    "created_at": marker.created_at,
                    "description": marker.description,
                    "position_seconds": marker.position_seconds
                },
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    async def _get_stream_markers(self, user_id: Optional[str] = None, video_id: Optional[str] = None, first: int = 20) -> Dict[str, Any]:
        """Get stream markers for a user or video"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not user_id and not video_id:
            if self._user_id:
                user_id = self._user_id
            else:
                return {"error": "Either user_id or video_id must be provided"}
        
        try:
            markers = []
            videos = []
            
            await self._twitch.get_stream_markers(
                user_id=user_id,
                video_id=video_id,
                first=min(first, 100)
            )
            
            # This is a simplified implementation as the actual response structure is complex
            # In a complete implementation, you'd parse the full response properly
            
            return {"markers": markers, "videos": videos}
        except Exception as e:
            return {"error": str(e)}

    async def _send_chat_announcement(self, broadcaster_id: str, moderator_id: str, message: str, color: Optional[str] = None) -> Dict[str, Any]:
        """Send an announcement message to the broadcaster's chat"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        try:
            # Validate color parameter
            valid_colors = ["blue", "green", "orange", "purple", None]  # None means default color
            if color not in valid_colors:
                return {"error": f"Invalid color: {color}. Must be one of: blue, green, orange, purple, or None"}
            
            await self._twitch.send_chat_announcement(
                broadcaster_id=broadcaster_id,
                moderator_id=moderator_id,
                message=message,
                color=color
            )
            
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def _raid_channel(self, from_broadcaster_id: str, to_broadcaster_id: str) -> Dict[str, Any]:
        """Start a raid from one channel to another"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        try:
            await self._twitch.start_raid(from_broadcaster_id=from_broadcaster_id, to_broadcaster_id=to_broadcaster_id)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def _cancel_raid(self, broadcaster_id: str) -> Dict[str, Any]:
        """Cancel a pending raid"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        try:
            await self._twitch.cancel_raid(broadcaster_id=broadcaster_id)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def _get_channel_rewards(self, broadcaster_id: Optional[str] = None, only_manageable_rewards: bool = False) -> Dict[str, Any]:
        """Get custom channel point rewards for a channel"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        if not broadcaster_id:
            if not self._user_id:
                return {"error": "No broadcaster ID provided"}
            broadcaster_id = self._user_id
        
        try:
            rewards = []
            async for reward in self._twitch.get_custom_rewards(broadcaster_id=broadcaster_id, only_manageable=only_manageable_rewards):
                rewards.append({
                    "id": reward.id,
                    "title": reward.title,
                    "prompt": reward.prompt,
                    "cost": reward.cost,
                    "is_enabled": reward.is_enabled,
                    "background_color": reward.background_color,
                    "is_user_input_required": reward.is_user_input_required,
                    "max_per_stream_setting": {
                        "is_enabled": reward.max_per_stream_setting.is_enabled,
                        "max_per_stream": reward.max_per_stream_setting.max_per_stream
                    },
                    "max_per_user_per_stream_setting": {
                        "is_enabled": reward.max_per_user_per_stream_setting.is_enabled,
                        "max_per_user_per_stream": reward.max_per_user_per_stream_setting.max_per_user_per_stream
                    },
                    "global_cooldown_setting": {
                        "is_enabled": reward.global_cooldown_setting.is_enabled,
                        "global_cooldown_seconds": reward.global_cooldown_setting.global_cooldown_seconds
                    },
                    "is_paused": reward.is_paused,
                    "is_in_stock": reward.is_in_stock,
                    "should_redemptions_skip_request_queue": reward.should_redemptions_skip_request_queue,
                    "redemptions_redeemed_current_stream": reward.redemptions_redeemed_current_stream,
                    "cooldown_expires_at": reward.cooldown_expires_at
                })
            
            return {"rewards": rewards}
        except Exception as e:
            return {"error": str(e)}

    async def _get_stream_tags(self, broadcaster_id: Optional[str] = None) -> Dict[str, Any]:
        """Get stream tags for a channel"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not broadcaster_id:
            if not self._user_authenticated or not self._user_id:
                return {"error": "No broadcaster ID provided"}
            broadcaster_id = self._user_id
        
        try:
            # Get all tags for the broadcaster's stream
            tags = []
            async for tag in self._twitch.get_stream_tags(broadcaster_id=broadcaster_id):
                tags.append({
                    "tag_id": tag.tag_id,
                    "localization_names": tag.localization_names,
                    "localization_descriptions": tag.localization_descriptions,
                    "is_auto": tag.is_auto
                })
                
            return {"tags": tags}
        except Exception as e:
            return {"error": str(e)}

    async def _replace_stream_tags(self, broadcaster_id: str, tag_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Replace all stream tags for a channel"""
        if not self._twitch:
            raise ValueError("Twitch client not initialized")
        
        if not self._user_authenticated:
            return {"error": "User authentication required"}
        
        try:
            # Replace stream tags
            await self._twitch.replace_stream_tags(broadcaster_id=broadcaster_id, tag_ids=tag_ids or [])
            
            # Get updated tags
            return await self._get_stream_tags(broadcaster_id)
        except Exception as e:
            return {"error": str(e)}

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
