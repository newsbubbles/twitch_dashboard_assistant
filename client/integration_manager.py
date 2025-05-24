import logging
import asyncio
from typing import Dict, List, Optional, Any, Union, Type
import os
from pydantic import BaseModel, Field

from .integrations.base_adapter import IntegrationAdapter, ConnectionStatus, IntegrationCapability
from .integrations.obs_adapter import OBSAdapter
from .integrations.twitch_adapter import TwitchAdapter

logger = logging.getLogger(__name__)

# Will add more adapters as we implement them
# from .integrations.discord_adapter import DiscordAdapter
# from .integrations.streamlabs_adapter import StreamlabsAdapter
# from .integrations.streamelements_adapter import StreamElementsAdapter
# from .integrations.nightbot_adapter import NightbotAdapter

class IntegrationConfig(BaseModel):
    """Configuration for an integration"""
    name: str = Field(..., description="Name of the integration")
    enabled: bool = Field(True, description="Whether the integration is enabled")
    auto_connect: bool = Field(True, description="Whether to connect automatically on startup")
    connection_params: Dict[str, Any] = Field(default_factory=dict, description="Connection parameters")

class IntegrationStatus(BaseModel):
    """Status information for an integration"""
    name: str = Field(..., description="Name of the integration")
    status: ConnectionStatus = Field(..., description="Connection status")
    error: Optional[str] = Field(None, description="Error message if status is ERROR")
    capabilities: List[IntegrationCapability] = Field(default_factory=list, description="Supported capabilities")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional status details")

class IntegrationManager:
    """Manager for all integrations"""

    def __init__(self):
        self._integrations: Dict[str, IntegrationAdapter] = {}
        self._configs: Dict[str, IntegrationConfig] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize the integration manager"""
        logger.info("Initializing integration manager")
        
        # Register all available integration types
        self._register_integration("obs", OBSAdapter)
        self._register_integration("twitch", TwitchAdapter)
        # These will be added as we implement them
        # self._register_integration("discord", DiscordAdapter)
        # self._register_integration("streamlabs", StreamlabsAdapter)
        # self._register_integration("streamelements", StreamElementsAdapter)
        # self._register_integration("nightbot", NightbotAdapter)
        
        # Set default configurations
        self._set_default_configs()
        
        self._initialized = True
        logger.info(f"Registered {len(self._integrations)} integrations")
    
    def _register_integration(self, name: str, integration_class: Type[IntegrationAdapter]):
        """Register an integration
        
        Args:
            name: Unique name for this integration
            integration_class: The integration adapter class
        """
        self._integrations[name] = integration_class()
        logger.debug(f"Registered integration: {name}")
    
    def _set_default_configs(self):
        """Set default configurations for all integrations"""
        # OBS Configuration
        self._configs["obs"] = IntegrationConfig(
            name="OBS Studio",
            enabled=True,
            auto_connect=True,
            connection_params={
                "host": "localhost",
                "port": 4455,
                "password": os.getenv("OBS_WEBSOCKET_PASSWORD", ""),
                "auto_reconnect": True
            }
        )
        
        # Twitch Configuration
        self._configs["twitch"] = IntegrationConfig(
            name="Twitch",
            enabled=True,
            auto_connect=True,
            connection_params={
                "client_id": os.getenv("TWITCH_CLIENT_ID", ""),
                "client_secret": os.getenv("TWITCH_CLIENT_SECRET", ""),
                "callback_url": os.getenv("TWITCH_CALLBACK_URL", None)
            }
        )
        
        # These will be added as we implement them
        # Discord Configuration
        # StreamLabs Configuration
        # StreamElements Configuration
        # Nightbot Configuration
    
    async def connect_integration(self, name: str, **override_params) -> Dict[str, Any]:
        """Connect to an integration
        
        Args:
            name: Name of the integration to connect to
            **override_params: Parameters to override defaults
            
        Returns:
            Dict[str, Any]: Connection result
        """
        if name not in self._integrations:
            return {"error": f"Integration '{name}' not found"}
        
        if name not in self._configs:
            return {"error": f"No configuration found for '{name}'"}
        
        config = self._configs[name]
        if not config.enabled:
            return {"error": f"Integration '{name}' is disabled"}
        
        adapter = self._integrations[name]
        if adapter.status in [ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING]:
            return {"message": f"Integration '{name}' is already connected or connecting"}
        
        # Merge default params with overrides
        params = {**config.connection_params, **override_params}
        
        logger.info(f"Connecting to integration '{name}'")
        success = await adapter.connect(**params)
        
        if success:
            return {"success": True, "message": f"Connected to {name} successfully"}
        else:
            return {"success": False, "error": adapter.error_message or "Unknown connection error"}
    
    async def disconnect_integration(self, name: str) -> Dict[str, Any]:
        """Disconnect from an integration
        
        Args:
            name: Name of the integration to disconnect from
            
        Returns:
            Dict[str, Any]: Disconnection result
        """
        if name not in self._integrations:
            return {"error": f"Integration '{name}' not found"}
        
        adapter = self._integrations[name]
        if adapter.status not in [ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING]:
            return {"message": f"Integration '{name}' is not connected"}
        
        logger.info(f"Disconnecting from integration '{name}'")
        success = await adapter.disconnect()
        
        if success:
            return {"success": True, "message": f"Disconnected from {name} successfully"}
        else:
            return {"success": False, "error": adapter.error_message or "Unknown disconnection error"}
    
    async def connect_all(self) -> Dict[str, Any]:
        """Connect to all enabled integrations with auto-connect enabled
        
        Returns:
            Dict[str, Any]: Connection results by integration name
        """
        results = {}
        
        for name, config in self._configs.items():
            if config.enabled and config.auto_connect:
                results[name] = await self.connect_integration(name)
        
        return results
    
    async def disconnect_all(self) -> Dict[str, Any]:
        """Disconnect from all connected integrations
        
        Returns:
            Dict[str, Any]: Disconnection results by integration name
        """
        results = {}
        
        for name, adapter in self._integrations.items():
            if adapter.status in [ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING]:
                results[name] = await self.disconnect_integration(name)
        
        return results
    
    async def execute_action(self, integration_name: str, action: str, **params) -> Dict[str, Any]:
        """Execute an action on an integration
        
        Args:
            integration_name: Name of the integration
            action: Action name to execute
            **params: Parameters for the action
            
        Returns:
            Dict[str, Any]: Action result
        """
        if integration_name not in self._integrations:
            return {"error": f"Integration '{integration_name}' not found"}
        
        adapter = self._integrations[integration_name]
        if adapter.status != ConnectionStatus.CONNECTED:
            return {"error": f"Integration '{integration_name}' is not connected"}
        
        try:
            logger.debug(f"Executing action '{action}' on '{integration_name}'")
            return await adapter.execute_action(action, **params)
        except Exception as e:
            logger.error(f"Error executing action '{action}' on '{integration_name}': {str(e)}")
            return {"error": str(e)}
    
    def get_integration_status(self, name: Optional[str] = None) -> Union[IntegrationStatus, List[IntegrationStatus], Dict[str, Any]]:
        """Get status of one or all integrations
        
        Args:
            name: Optional name of specific integration
            
        Returns:
            Union[IntegrationStatus, List[IntegrationStatus], Dict[str, Any]]: 
                Status of requested integration(s) or error
        """
        if name is not None:
            if name not in self._integrations:
                return {"error": f"Integration '{name}' not found"}
            
            adapter = self._integrations[name]
            config = self._configs.get(name)
            
            return IntegrationStatus(
                name=name,
                status=adapter.status,
                error=adapter.error_message,
                capabilities=adapter.capabilities,
                details={
                    "enabled": config.enabled if config else False,
                    "auto_connect": config.auto_connect if config else False,
                }
            )
        
        # Return status of all integrations
        statuses = []
        for name, adapter in self._integrations.items():
            config = self._configs.get(name)
            statuses.append(IntegrationStatus(
                name=name,
                status=adapter.status,
                error=adapter.error_message,
                capabilities=adapter.capabilities,
                details={
                    "enabled": config.enabled if config else False,
                    "auto_connect": config.auto_connect if config else False,
                }
            ))
        
        return statuses
    
    async def get_detailed_status(self, name: str) -> Dict[str, Any]:
        """Get detailed status information for an integration
        
        Args:
            name: Name of the integration
            
        Returns:
            Dict[str, Any]: Detailed status information
        """
        if name not in self._integrations:
            return {"error": f"Integration '{name}' not found"}
        
        adapter = self._integrations[name]
        config = self._configs.get(name)
        
        # Get basic status
        status = IntegrationStatus(
            name=name,
            status=adapter.status,
            error=adapter.error_message,
            capabilities=adapter.capabilities,
            details={
                "enabled": config.enabled if config else False,
                "auto_connect": config.auto_connect if config else False,
            }
        ).model_dump()
        
        # Add detailed status if connected
        if adapter.status == ConnectionStatus.CONNECTED:
            try:
                detailed_status = await adapter.get_status()
                status["details"].update(detailed_status)
            except Exception as e:
                logger.error(f"Error getting detailed status for '{name}': {str(e)}")
                status["detail_error"] = str(e)
        
        return status
    
    def update_integration_config(self, name: str, config_updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update configuration for an integration
        
        Args:
            name: Name of the integration
            config_updates: Dictionary with configuration updates
            
        Returns:
            Dict[str, Any]: Update result
        """
        if name not in self._integrations:
            return {"error": f"Integration '{name}' not found"}
        
        if name not in self._configs:
            self._configs[name] = IntegrationConfig(name=name, enabled=True)
        
        config = self._configs[name]
        
        # Update top-level fields
        for key in ["enabled", "auto_connect"]:
            if key in config_updates:
                setattr(config, key, config_updates[key])
        
        # Update connection params
        if "connection_params" in config_updates and isinstance(config_updates["connection_params"], dict):
            for param_key, param_value in config_updates["connection_params"].items():
                config.connection_params[param_key] = param_value
        
        logger.info(f"Updated configuration for integration '{name}'")
        return {
            "success": True,
            "message": f"Configuration for '{name}' updated",
            "config": config.model_dump()
        }
    
    def get_integration(self, name: str) -> Optional[IntegrationAdapter]:
        """Get an integration adapter by name
        
        Args:
            name: Name of the integration
            
        Returns:
            Optional[IntegrationAdapter]: The integration adapter if found, None otherwise
        """
        return self._integrations.get(name)
    
    def get_integration_config(self, name: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """Get configuration for one or all integrations
        
        Args:
            name: Optional name of specific integration
            
        Returns:
            Union[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]: 
                Configuration of requested integration(s) or error
        """
        if name is not None:
            if name not in self._configs:
                return {"error": f"Configuration for '{name}' not found"}
            
            return self._configs[name].model_dump()
        
        # Return all configurations
        return [config.model_dump() for config in self._configs.values()]
    
    def find_by_capability(self, capability: IntegrationCapability) -> List[str]:
        """Find integrations that support a specific capability
        
        Args:
            capability: Capability to search for
            
        Returns:
            List[str]: List of integration names that support the capability
        """
        return [name for name, adapter in self._integrations.items() 
                if adapter.supports_capability(capability)]
    
    async def execute_capability(self, capability: IntegrationCapability, 
                              action: str, **params) -> Dict[str, Any]:
        """Execute an action on the first available integration with the given capability
        
        Args:
            capability: Required capability
            action: Action name to execute
            **params: Parameters for the action
            
        Returns:
            Dict[str, Any]: Action result or error
        """
        # Find integrations with this capability
        candidates = self.find_by_capability(capability)
        
        if not candidates:
            return {"error": f"No integration supports capability '{capability}'"}
        
        # Try each candidate until one succeeds
        errors = {}
        for name in candidates:
            adapter = self._integrations[name]
            
            # Skip if not connected
            if adapter.status != ConnectionStatus.CONNECTED:
                errors[name] = "Not connected"
                continue
            
            try:
                result = await adapter.execute_action(action, **params)
                if "error" not in result:
                    return {"integration": name, **result}
                errors[name] = result["error"]
            except Exception as e:
                errors[name] = str(e)
        
        return {"error": f"Failed to execute capability '{capability}'", "details": errors}
    
    async def close(self):
        """Close all connections and perform cleanup"""
        logger.info("Shutting down integration manager")
        await self.disconnect_all()
