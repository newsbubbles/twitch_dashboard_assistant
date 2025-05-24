import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ConnectionStatus(str, Enum):
    """Enum representing the connection status of an integration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

class IntegrationCapability(str, Enum):
    """Enum representing capabilities that an integration might support"""
    SCENE_CONTROL = "scene_control"
    SOURCE_CONTROL = "source_control"
    STREAMING_CONTROL = "streaming_control"
    RECORDING_CONTROL = "recording_control"
    CHAT_INTERACTION = "chat_interaction"
    ALERT_MANAGEMENT = "alert_management"
    EVENT_SUBSCRIPTION = "event_subscription"
    COMMAND_MANAGEMENT = "command_management"
    ANALYTICS = "analytics"
    MEDIA_SHARING = "media_sharing"
    BOT_COMMANDS = "bot_commands"
    SERVER_MANAGEMENT = "server_management"

class IntegrationAdapter(ABC):
    """Base class for all integration adapters"""

    def __init__(self, name: str):
        self.name = name
        self._status = ConnectionStatus.DISCONNECTED
        self._capabilities: List[IntegrationCapability] = []
        self._error_message: Optional[str] = None
        
    @property
    def status(self) -> ConnectionStatus:
        """Get the current connection status"""
        return self._status
    
    @property
    def error_message(self) -> Optional[str]:
        """Get the last error message if status is ERROR"""
        return self._error_message
    
    @property
    def capabilities(self) -> List[IntegrationCapability]:
        """Get the capabilities supported by this integration"""
        return self._capabilities
    
    @abstractmethod
    async def connect(self, **kwargs) -> bool:
        """Connect to the integration
        
        Args:
            **kwargs: Integration-specific connection parameters
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the integration
        
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        pass

    @abstractmethod
    async def execute_action(self, action: str, **params) -> Dict[str, Any]:
        """Execute an action with the given parameters
        
        Args:
            action: The name of the action to execute
            **params: Parameters for the action
            
        Returns:
            Dict[str, Any]: Result of the action
        """
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Get detailed status information about the integration
        
        Returns:
            Dict[str, Any]: A dictionary with status information
        """
        pass
    
    def _update_status(self, status: ConnectionStatus, error_message: Optional[str] = None):
        """Update the connection status
        
        Args:
            status: New connection status
            error_message: Error message if status is ERROR
        """
        prev_status = self._status
        self._status = status
        self._error_message = error_message if status == ConnectionStatus.ERROR else None
        
        if prev_status != status:
            if status == ConnectionStatus.ERROR:
                logger.error(f"{self.name} integration status changed to {status}: {error_message}")
            else:
                logger.info(f"{self.name} integration status changed to {status}")
    
    def supports_capability(self, capability: IntegrationCapability) -> bool:
        """Check if this integration supports a specific capability
        
        Args:
            capability: The capability to check
            
        Returns:
            bool: True if supported, False otherwise
        """
        return capability in self._capabilities
    
    async def __aenter__(self):
        """Context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.disconnect()
