import logging
import asyncio
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from pydantic import BaseModel, Field
from obswebsocket import obsws, requests, events
from obswebsocket.base_classes import Callback

from .base_adapter import IntegrationAdapter, ConnectionStatus, IntegrationCapability

logger = logging.getLogger(__name__)

class OBSSceneItem(BaseModel):
    """Model representing an OBS scene item"""
    id: int = Field(..., description="Scene item ID")
    source_name: str = Field(..., description="Name of the source")
    source_type: str = Field(..., description="Type of the source")
    source_kind: Optional[str] = Field(None, description="Kind of the source")
    visible: bool = Field(..., description="Whether the source is visible")

class OBSScene(BaseModel):
    """Model representing an OBS scene"""
    name: str = Field(..., description="Scene name")
    items: List[OBSSceneItem] = Field(default_factory=list, description="Items in the scene")

class OBSAudioSource(BaseModel):
    """Model representing an OBS audio source"""
    name: str = Field(..., description="Audio source name")
    volume_db: float = Field(..., description="Volume in dB")
    volume_mul: float = Field(..., description="Volume multiplier (0.0-1.0)")
    muted: bool = Field(..., description="Whether the source is muted")

class OBSStreamStatus(BaseModel):
    """Model representing OBS streaming status"""
    streaming: bool = Field(..., description="Whether OBS is streaming")
    recording: bool = Field(..., description="Whether OBS is recording")
    replay_buffer_active: bool = Field(False, description="Whether the replay buffer is active")
    bytes_per_sec: Optional[int] = Field(None, description="Bytes per second")
    kbits_per_sec: Optional[int] = Field(None, description="Kilobits per second")
    strain: Optional[float] = Field(None, description="Encoding strain")
    total_stream_time: Optional[int] = Field(None, description="Total stream time in seconds")
    num_total_frames: Optional[int] = Field(None, description="Total frames")
    num_dropped_frames: Optional[int] = Field(None, description="Dropped frames")
    fps: Optional[float] = Field(None, description="Current FPS")

class OBSStats(BaseModel):
    """Model representing OBS statistics"""
    fps: float = Field(..., description="Current FPS")
    cpu_usage: float = Field(..., description="CPU usage percentage")
    memory_usage: float = Field(..., description="Memory usage in MB")
    free_disk_space: Optional[float] = Field(None, description="Free disk space in MB")

class OBSAdapter(IntegrationAdapter):
    """Adapter for OBS Studio via OBS WebSocket"""

    def __init__(self):
        super().__init__("OBS Studio")
        self._capabilities = [
            IntegrationCapability.SCENE_CONTROL,
            IntegrationCapability.SOURCE_CONTROL,
            IntegrationCapability.STREAMING_CONTROL,
            IntegrationCapability.RECORDING_CONTROL,
        ]
        self._client: Optional[obsws] = None
        self._event_callbacks: Dict[str, List[Callable]] = {}
        self._host: str = "localhost"
        self._port: int = 4455
        self._password: str = ""
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_interval: int = 10  # seconds
        self._auto_reconnect: bool = True

    async def connect(self, host: str = "localhost", port: int = 4455, 
                     password: str = "", auto_reconnect: bool = True) -> bool:
        """Connect to OBS WebSocket
        
        Args:
            host: OBS WebSocket host, defaults to localhost
            port: OBS WebSocket port, defaults to 4455
            password: OBS WebSocket password if needed
            auto_reconnect: Whether to automatically reconnect if connection is lost
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        self._update_status(ConnectionStatus.CONNECTING)
        
        self._host = host
        self._port = port
        self._password = password
        self._auto_reconnect = auto_reconnect
        
        try:
            # Create new client instance
            self._client = obsws(host, port, password)
            
            # Set up event handlers
            for event_type, callbacks in self._event_callbacks.items():
                for callback in callbacks:
                    self._client.register_event(event_type, callback)
            
            # Add connection lost handler
            self._client.register_event(events.ExitStarted, self._handle_connection_lost)
            
            # Connect to OBS
            self._client.connect()
            
            # Test connection
            response = self._client.call(requests.GetVersion())
            obs_version = response.getObsVersion()
            websocket_version = response.getObsWebSocketVersion()
            logger.info(f"Connected to OBS {obs_version} with WebSocket {websocket_version}")
            
            self._update_status(ConnectionStatus.CONNECTED)
            return True
        except Exception as e:
            error_message = f"Failed to connect to OBS: {str(e)}"
            self._update_status(ConnectionStatus.ERROR, error_message)
            logger.error(error_message)
            return False
    
    async def _handle_connection_lost(self, event=None):
        """Handle connection lost event
        
        Args:
            event: The event that triggered this handler
        """
        if self._status == ConnectionStatus.CONNECTED:
            self._update_status(ConnectionStatus.DISCONNECTED)
            logger.warning("Connection to OBS lost")
            
            if self._auto_reconnect and not self._reconnect_task:
                self._start_reconnect_task()
    
    def _start_reconnect_task(self):
        """Start the reconnection task"""
        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
    
    async def _reconnect_loop(self):
        """Reconnection loop"""
        while self._status != ConnectionStatus.CONNECTED and self._auto_reconnect:
            logger.info(f"Attempting to reconnect to OBS in {self._reconnect_interval} seconds...")
            await asyncio.sleep(self._reconnect_interval)
            
            try:
                success = await self.connect(
                    self._host, self._port, self._password, self._auto_reconnect
                )
                if success:
                    logger.info("Successfully reconnected to OBS")
                    break
            except Exception as e:
                logger.error(f"Reconnection attempt failed: {str(e)}")
    
    async def disconnect(self) -> bool:
        """Disconnect from OBS WebSocket
        
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        # Cancel reconnect task if running
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        
        # Disconnect from OBS
        if self._client and self._status == ConnectionStatus.CONNECTED:
            try:
                self._client.disconnect()
                self._update_status(ConnectionStatus.DISCONNECTED)
                return True
            except Exception as e:
                error_message = f"Error disconnecting from OBS: {str(e)}"
                self._update_status(ConnectionStatus.ERROR, error_message)
                logger.error(error_message)
                return False
        else:
            self._update_status(ConnectionStatus.DISCONNECTED)
            return True
    
    def register_event_callback(self, event_type: str, callback: Callable):
        """Register a callback for an OBS event
        
        Args:
            event_type: The OBS event type to listen for
            callback: Callback function to execute when event occurs
        """
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        
        self._event_callbacks[event_type].append(callback)
        
        # If already connected, register with client
        if self._client and self._status == ConnectionStatus.CONNECTED:
            self._client.register_event(event_type, callback)
    
    def unregister_event_callback(self, event_type: str, callback: Callable) -> bool:
        """Unregister a callback for an OBS event
        
        Args:
            event_type: The OBS event type
            callback: The callback to remove
            
        Returns:
            bool: True if callback was removed, False if not found
        """
        if event_type in self._event_callbacks and callback in self._event_callbacks[event_type]:
            self._event_callbacks[event_type].remove(callback)
            
            # If already connected, unregister from client
            if self._client and self._status == ConnectionStatus.CONNECTED:
                self._client.unregister_event(event_type, callback)
            
            return True
        return False

    async def execute_action(self, action: str, **params) -> Dict[str, Any]:
        """Execute an OBS action
        
        Args:
            action: The name of the action to execute
            **params: Parameters for the action
            
        Returns:
            Dict[str, Any]: Result of the action
        """
        if not self._client or self._status != ConnectionStatus.CONNECTED:
            return {"error": "Not connected to OBS"}
        
        try:
            # Map action names to OBS WebSocket requests
            request_map = {
                "get_scene_list": self._get_scene_list,
                "get_current_scene": self._get_current_scene,
                "set_current_scene": self._set_current_scene,
                "get_scene_item_list": self._get_scene_item_list,
                "set_scene_item_properties": self._set_scene_item_properties,
                "get_audio_sources": self._get_audio_sources,
                "set_mute": self._set_mute,
                "set_volume": self._set_volume,
                "start_streaming": self._start_streaming,
                "stop_streaming": self._stop_streaming,
                "start_recording": self._start_recording,
                "stop_recording": self._stop_recording,
                "start_replay_buffer": self._start_replay_buffer,
                "save_replay_buffer": self._save_replay_buffer,
                "get_streaming_status": self._get_streaming_status,
                "get_stats": self._get_stats
            }
            
            if action not in request_map:
                return {"error": f"Unknown action: {action}"}
            
            # Execute the action
            result = await request_map[action](**params)
            return result
        
        except Exception as e:
            logger.error(f"Error executing OBS action '{action}': {str(e)}")
            return {"error": str(e)}
    
    async def _get_scene_list(self) -> Dict[str, Any]:
        """Get list of scenes"""
        response = self._client.call(requests.GetSceneList())
        scenes = []
        
        for scene in response.getScenes():
            scenes.append({
                "name": scene["name"],
                "is_program_scene": scene["name"] == response.getCurrentProgramSceneName()
            })
        
        return {
            "scenes": scenes,
            "current_scene": response.getCurrentProgramSceneName()
        }
    
    async def _get_current_scene(self) -> Dict[str, Any]:
        """Get current active scene"""
        response = self._client.call(requests.GetCurrentProgramScene())
        return {"current_scene": response.getCurrentProgramSceneName()}
    
    async def _set_current_scene(self, scene_name: str) -> Dict[str, Any]:
        """Set current scene"""
        self._client.call(requests.SetCurrentProgramScene(sceneName=scene_name))
        return {"success": True, "scene_name": scene_name}
    
    async def _get_scene_item_list(self, scene_name: str) -> Dict[str, Any]:
        """Get items in a scene"""
        response = self._client.call(requests.GetSceneItemList(sceneName=scene_name))
        
        items = []
        for item in response.getSceneItems():
            items.append(OBSSceneItem(
                id=item["sceneItemId"],
                source_name=item["sourceName"],
                source_type=item["sourceType"],
                source_kind=item.get("sourceKind"),
                visible=item["sceneItemEnabled"]
            ).model_dump())
        
        return {"scene_name": scene_name, "items": items}
    
    async def _set_scene_item_properties(self, scene_name: str, item_id: int, 
                                      visible: Optional[bool] = None) -> Dict[str, Any]:
        """Set properties of a scene item"""
        if visible is not None:
            self._client.call(requests.SetSceneItemEnabled(
                sceneName=scene_name,
                sceneItemId=item_id,
                sceneItemEnabled=visible
            ))
        
        return {"success": True, "scene_name": scene_name, "item_id": item_id}
    
    async def _get_audio_sources(self) -> Dict[str, Any]:
        """Get audio sources"""
        response = self._client.call(requests.GetInputList(inputKind="audio"))
        
        audio_sources = []
        for source in response.getInputs():
            volume = self._client.call(requests.GetInputVolume(inputName=source["inputName"]))
            muted = self._client.call(requests.GetInputMute(inputName=source["inputName"]))
            
            audio_sources.append(OBSAudioSource(
                name=source["inputName"],
                volume_db=volume.getInputVolumeDb(),
                volume_mul=volume.getInputVolumeMul(),
                muted=muted.getInputMuted()
            ).model_dump())
        
        return {"audio_sources": audio_sources}
    
    async def _set_mute(self, source_name: str, muted: bool) -> Dict[str, Any]:
        """Set mute state of an audio source"""
        self._client.call(requests.SetInputMute(inputName=source_name, inputMuted=muted))
        return {"success": True, "source_name": source_name, "muted": muted}
    
    async def _set_volume(self, source_name: str, volume: float, 
                       volume_type: str = "db") -> Dict[str, Any]:
        """Set volume of an audio source
        
        Args:
            source_name: Name of the audio source
            volume: Volume value
            volume_type: Either 'db' for decibels or 'mul' for multiplier (0.0-1.0)
        """
        if volume_type == "db":
            self._client.call(requests.SetInputVolume(
                inputName=source_name, inputVolumeDb=volume
            ))
        else:
            self._client.call(requests.SetInputVolume(
                inputName=source_name, inputVolumeMul=volume
            ))
        
        return {"success": True, "source_name": source_name, "volume": volume}
    
    async def _start_streaming(self) -> Dict[str, Any]:
        """Start streaming"""
        self._client.call(requests.StartStream())
        return {"success": True, "action": "start_streaming"}
    
    async def _stop_streaming(self) -> Dict[str, Any]:
        """Stop streaming"""
        self._client.call(requests.StopStream())
        return {"success": True, "action": "stop_streaming"}
    
    async def _start_recording(self) -> Dict[str, Any]:
        """Start recording"""
        self._client.call(requests.StartRecord())
        return {"success": True, "action": "start_recording"}
    
    async def _stop_recording(self) -> Dict[str, Any]:
        """Stop recording"""
        response = self._client.call(requests.StopRecord())
        return {
            "success": True, 
            "action": "stop_recording",
            "output_path": response.getOutputPath()
        }
    
    async def _start_replay_buffer(self) -> Dict[str, Any]:
        """Start replay buffer"""
        self._client.call(requests.StartReplayBuffer())
        return {"success": True, "action": "start_replay_buffer"}
    
    async def _save_replay_buffer(self) -> Dict[str, Any]:
        """Save replay buffer"""
        response = self._client.call(requests.SaveReplayBuffer())
        return {
            "success": True,
            "action": "save_replay_buffer",
            "saved": True
        }
    
    async def _get_streaming_status(self) -> Dict[str, Any]:
        """Get streaming status"""
        response = self._client.call(requests.GetStreamStatus())
        output_status = self._client.call(requests.GetRecordStatus())
        replay_status = self._client.call(requests.GetReplayBufferStatus())
        
        status = OBSStreamStatus(
            streaming=response.getOutputActive(),
            recording=output_status.getOutputActive(),
            replay_buffer_active=replay_status.getOutputActive(),
            bytes_per_sec=response.getOutputBytes(),
            kbits_per_sec=response.getOutputBytes() * 8 / 1000 if response.getOutputActive() else 0,
            strain=response.getOutputCongestion(),
            total_stream_time=response.getOutputDuration(),
            num_total_frames=response.getOutputTotalFrames(),
            num_dropped_frames=response.getOutputSkippedFrames(),
            fps=response.getOutputTotalFrames() / response.getOutputDuration() 
                if response.getOutputDuration() > 0 else 0
        )
        
        return status.model_dump()
    
    async def _get_stats(self) -> Dict[str, Any]:
        """Get OBS stats"""
        response = self._client.call(requests.GetStats())
        
        stats = OBSStats(
            fps=response.getActiveFps(),
            cpu_usage=response.getCpuUsage(),
            memory_usage=response.getMemoryUsage(),
            free_disk_space=response.getAvailableDiskSpace() if hasattr(response, "getAvailableDiskSpace") else None
        )
        
        return stats.model_dump()
    
    async def get_status(self) -> Dict[str, Any]:
        """Get detailed status information
        
        Returns:
            Dict[str, Any]: A dictionary with status information
        """
        result = {
            "connection_status": self._status,
            "capabilities": self._capabilities,
            "host": self._host,
            "port": self._port
        }
        
        if self._status == ConnectionStatus.CONNECTED and self._client:
            try:
                version_info = self._client.call(requests.GetVersion())
                result["obs_version"] = version_info.getObsVersion()
                result["websocket_version"] = version_info.getObsWebSocketVersion()
                
                streaming_status = await self._get_streaming_status()
                result["streaming"] = streaming_status["streaming"]
                result["recording"] = streaming_status["recording"]
                
                current_scene = await self._get_current_scene()
                result["current_scene"] = current_scene["current_scene"]
            except Exception as e:
                logger.error(f"Error getting OBS status: {str(e)}")
                result["error"] = str(e)
        
        return result
