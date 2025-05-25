import logging
import asyncio
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from pydantic import BaseModel, Field
import traceback
from datetime import datetime

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
    type: str = Field(..., description="Type of audio source")

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
    render_missed_frames: Optional[int] = Field(None, description="Render missed frames")
    render_total_frames: Optional[int] = Field(None, description="Render total frames")
    output_skipped_frames: Optional[int] = Field(None, description="Output skipped frames")
    output_total_frames: Optional[int] = Field(None, description="Output total frames")

class OBSStats(BaseModel):
    """Model representing OBS statistics"""
    fps: float = Field(..., description="Current FPS")
    cpu_usage: float = Field(..., description="CPU usage percentage")
    memory_usage: float = Field(..., description="Memory usage in MB")
    free_disk_space: Optional[float] = Field(None, description="Free disk space in MB")
    average_frame_time: Optional[float] = Field(None, description="Average frame time in ms")
    render_missed_frames: Optional[int] = Field(None, description="Render missed frames")
    render_total_frames: Optional[int] = Field(None, description="Render total frames")

class OBSFilter(BaseModel):
    """Model representing an OBS filter"""
    name: str = Field(..., description="Filter name")
    type: str = Field(..., description="Filter type")
    enabled: bool = Field(..., description="Whether the filter is enabled")

class OBSTransition(BaseModel):
    """Model representing an OBS transition"""
    name: str = Field(..., description="Transition name")
    kind: str = Field(..., description="Transition type")
    duration: Optional[int] = Field(None, description="Duration in milliseconds")

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
        self._version_info: Optional[Dict[str, str]] = None
        # Internal memory of scene items to avoid excessive queries
        self._scene_items_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._scene_items_cache_time: Dict[str, datetime] = {}

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
            
            # Add default event handlers
            self._client.register_event(events.ExitStarted, self._handle_connection_lost)
            self._client.register_event(events.SceneItemEnableStateChanged, self._handle_source_visibility_changed)
            self._client.register_event(events.CurrentProgramSceneChanged, self._handle_scene_changed)
            self._client.register_event(events.StreamStateChanged, self._handle_stream_state_changed)
            self._client.register_event(events.RecordStateChanged, self._handle_record_state_changed)
            
            # Connect to OBS
            self._client.connect()
            
            # Test connection
            response = self._client.call(requests.GetVersion())
            self._version_info = {
                "obs_version": response.getObsVersion(),
                "websocket_version": response.getObsWebSocketVersion(),
                "platform": response.getObsStudioVersion(),
                "rpc_version": response.getRpcVersion()
            }
            
            logger.info(f"Connected to OBS {self._version_info['obs_version']} with WebSocket {self._version_info['websocket_version']}")
            
            # Clear scene items cache
            self._scene_items_cache = {}
            self._scene_items_cache_time = {}
            
            self._update_status(ConnectionStatus.CONNECTED)
            return True
        except Exception as e:
            error_message = f"Failed to connect to OBS: {str(e)}"
            self._update_status(ConnectionStatus.ERROR, error_message)
            logger.error(error_message)
            logger.debug(traceback.format_exc())
            return False
    
    # Event handlers
    async def _handle_connection_lost(self, event=None):
        """Handle connection lost event"""
        if self._status == ConnectionStatus.CONNECTED:
            self._update_status(ConnectionStatus.DISCONNECTED)
            logger.warning("Connection to OBS lost")
            
            if self._auto_reconnect and not self._reconnect_task:
                self._start_reconnect_task()
    
    async def _handle_source_visibility_changed(self, event):
        """Handle source visibility changed event"""
        try:
            scene_name = event.getSceneName()
            item_id = event.getSceneItemId()
            visible = event.getSceneItemEnabled()
            
            # Update cache if we have it
            if scene_name in self._scene_items_cache:
                for item in self._scene_items_cache[scene_name]:
                    if item["id"] == item_id:
                        item["visible"] = visible
                        break
            
            logger.debug(f"Source visibility changed in scene {scene_name}: item ID {item_id} -> {visible}")
        except Exception as e:
            logger.error(f"Error handling source visibility event: {str(e)}")
    
    async def _handle_scene_changed(self, event):
        """Handle scene changed event"""
        try:
            scene_name = event.getSceneName()
            logger.debug(f"Scene changed to: {scene_name}")
        except Exception as e:
            logger.error(f"Error handling scene changed event: {str(e)}")
    
    async def _handle_stream_state_changed(self, event):
        """Handle stream state changed event"""
        try:
            active = event.getOutputActive()
            logger.debug(f"Stream state changed: {'active' if active else 'inactive'}")
        except Exception as e:
            logger.error(f"Error handling stream state event: {str(e)}")
    
    async def _handle_record_state_changed(self, event):
        """Handle recording state changed event"""
        try:
            state = event.getOutputState()
            logger.debug(f"Recording state changed: {state}")
        except Exception as e:
            logger.error(f"Error handling record state event: {str(e)}")
    
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
        
        # Clear cache
        self._scene_items_cache = {}
        self._scene_items_cache_time = {}
        
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
                # Scene control
                "get_scene_list": self._get_scene_list,
                "get_current_scene": self._get_current_scene,
                "set_current_scene": self._set_current_scene,
                "get_scene_item_list": self._get_scene_item_list,
                "set_scene_item_properties": self._set_scene_item_properties,
                
                # Audio control
                "get_audio_sources": self._get_audio_sources,
                "set_mute": self._set_mute,
                "set_volume": self._set_volume,
                "toggle_mute": self._toggle_mute,
                
                # Streaming and recording control
                "start_streaming": self._start_streaming,
                "stop_streaming": self._stop_streaming,
                "toggle_streaming": self._toggle_streaming,
                "start_recording": self._start_recording,
                "stop_recording": self._stop_recording,
                "pause_recording": self._pause_recording,
                "resume_recording": self._resume_recording,
                "start_replay_buffer": self._start_replay_buffer,
                "stop_replay_buffer": self._stop_replay_buffer,
                "save_replay_buffer": self._save_replay_buffer,
                "toggle_replay_buffer": self._toggle_replay_buffer,
                
                # Status and statistics
                "get_streaming_status": self._get_streaming_status,
                "get_stats": self._get_stats,
                
                # Transitions
                "get_transitions": self._get_transitions,
                "set_current_transition": self._set_current_transition,
                "set_transition_duration": self._set_transition_duration,
                "get_transition_duration": self._get_transition_duration,
                
                # Source control
                "create_source": self._create_source,
                "remove_source": self._remove_source,
                "duplicate_source": self._duplicate_source,
                "get_source_settings": self._get_source_settings,
                "set_source_settings": self._set_source_settings,
                "get_source_filters": self._get_source_filters,
                "add_source_filter": self._add_source_filter,
                "remove_source_filter": self._remove_source_filter,
                
                # Media control
                "play_pause_media": self._play_pause_media,
                "restart_media": self._restart_media,
                "stop_media": self._stop_media,
                "set_media_time": self._set_media_time,
                "get_media_time": self._get_media_time,
                "set_media_source": self._set_media_source,
                
                # Text control (GDI+ and FreeType2)
                "get_text_content": self._get_text_content,
                "set_text_content": self._set_text_content,
                
                # Studio mode
                "get_studio_mode": self._get_studio_mode,
                "set_studio_mode": self._set_studio_mode,
                "get_preview_scene": self._get_preview_scene,
                "set_preview_scene": self._set_preview_scene,
                "studio_mode_transition": self._studio_mode_transition,
                
                # Virtual camera
                "start_virtual_camera": self._start_virtual_camera,
                "stop_virtual_camera": self._stop_virtual_camera,
                "toggle_virtual_camera": self._toggle_virtual_camera,
            }
            
            if action not in request_map:
                return {"error": f"Unknown action: {action}"}
            
            # Execute the action
            result = await request_map[action](**params)
            return result
        
        except Exception as e:
            error_message = f"Error executing OBS action '{action}': {str(e)}"
            logger.error(error_message)
            logger.debug(traceback.format_exc())
            return {"error": error_message}
    
    # Scene control methods
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
    
    async def _get_scene_item_list(self, scene_name: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get items in a scene"""
        # Check cache first unless force refresh is requested
        cache_valid = (
            not force_refresh and 
            scene_name in self._scene_items_cache and 
            scene_name in self._scene_items_cache_time and
            (datetime.now() - self._scene_items_cache_time[scene_name]).total_seconds() < 60
        )
        
        if cache_valid:
            return {
                "scene_name": scene_name, 
                "items": self._scene_items_cache[scene_name],
                "cached": True
            }
            
        response = self._client.call(requests.GetSceneItemList(sceneName=scene_name))
        
        items = []
        for item in response.getSceneItems():
            item_obj = OBSSceneItem(
                id=item["sceneItemId"],
                source_name=item["sourceName"],
                source_type=item["sourceType"],
                source_kind=item.get("sourceKind"),
                visible=item["sceneItemEnabled"]
            )
            items.append(item_obj.model_dump())
        
        # Update cache
        self._scene_items_cache[scene_name] = items
        self._scene_items_cache_time[scene_name] = datetime.now()
        
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
            
            # Update our cache
            if scene_name in self._scene_items_cache:
                for item in self._scene_items_cache[scene_name]:
                    if item["id"] == item_id:
                        item["visible"] = visible
                        break
        
        return {"success": True, "scene_name": scene_name, "item_id": item_id}
    
    # Audio control methods
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
                muted=muted.getInputMuted(),
                type=source["inputKind"]
            ).model_dump())
        
        return {"audio_sources": audio_sources}
    
    async def _set_mute(self, source_name: str, muted: bool) -> Dict[str, Any]:
        """Set mute state of an audio source"""
        self._client.call(requests.SetInputMute(inputName=source_name, inputMuted=muted))
        return {"success": True, "source_name": source_name, "muted": muted}
    
    async def _toggle_mute(self, source_name: str) -> Dict[str, Any]:
        """Toggle mute state of an audio source"""
        response = self._client.call(requests.ToggleInputMute(inputName=source_name))
        return {
            "success": True, 
            "source_name": source_name, 
            "muted": response.getInputMuted()
        }
    
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
    
    # Streaming and recording control methods
    async def _start_streaming(self) -> Dict[str, Any]:
        """Start streaming"""
        self._client.call(requests.StartStream())
        return {"success": True, "action": "start_streaming"}
    
    async def _stop_streaming(self) -> Dict[str, Any]:
        """Stop streaming"""
        self._client.call(requests.StopStream())
        return {"success": True, "action": "stop_streaming"}
    
    async def _toggle_streaming(self) -> Dict[str, Any]:
        """Toggle streaming state"""
        response = self._client.call(requests.ToggleStream())
        return {
            "success": True, 
            "action": "toggle_streaming",
            "streaming": response.getOutputActive() if hasattr(response, "getOutputActive") else None
        }
    
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
    
    async def _pause_recording(self) -> Dict[str, Any]:
        """Pause recording"""
        self._client.call(requests.PauseRecord())
        return {"success": True, "action": "pause_recording"}
    
    async def _resume_recording(self) -> Dict[str, Any]:
        """Resume recording"""
        self._client.call(requests.ResumeRecord())
        return {"success": True, "action": "resume_recording"}
    
    async def _start_replay_buffer(self) -> Dict[str, Any]:
        """Start replay buffer"""
        self._client.call(requests.StartReplayBuffer())
        return {"success": True, "action": "start_replay_buffer"}
    
    async def _stop_replay_buffer(self) -> Dict[str, Any]:
        """Stop replay buffer"""
        self._client.call(requests.StopReplayBuffer())
        return {"success": True, "action": "stop_replay_buffer"}
    
    async def _save_replay_buffer(self) -> Dict[str, Any]:
        """Save replay buffer"""
        response = self._client.call(requests.SaveReplayBuffer())
        return {
            "success": True,
            "action": "save_replay_buffer",
            "saved": True
        }
    
    async def _toggle_replay_buffer(self) -> Dict[str, Any]:
        """Toggle replay buffer"""
        response = self._client.call(requests.ToggleReplayBuffer())
        return {
            "success": True, 
            "action": "toggle_replay_buffer",
            "active": response.getOutputActive() if hasattr(response, "getOutputActive") else None
        }
    
    # Status and statistics methods
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
    
    # Transitions methods
    async def _get_transitions(self) -> Dict[str, Any]:
        """Get available transitions"""
        response = self._client.call(requests.GetTransitionList())
        transitions = [
            OBSTransition(
                name=t["name"],
                kind=t["type"],
                duration=None
            ).model_dump()
            for t in response.getTransitions()
        ]
        
        # Current transition
        current_transition = response.getCurrentTransitionName()
        current_duration = self._client.call(requests.GetTransitionDuration()).getTransitionDuration()
        
        # Update duration for current transition
        for transition in transitions:
            if transition["name"] == current_transition:
                transition["duration"] = current_duration
                break
        
        return {
            "transitions": transitions,
            "current_transition": current_transition,
            "current_duration": current_duration
        }
    
    async def _set_current_transition(self, transition_name: str) -> Dict[str, Any]:
        """Set current transition"""
        self._client.call(requests.SetCurrentSceneTransition(transitionName=transition_name))
        return {"success": True, "transition_name": transition_name}
    
    async def _set_transition_duration(self, duration: int) -> Dict[str, Any]:
        """Set transition duration"""
        self._client.call(requests.SetTransitionDuration(transitionDuration=duration))
        return {"success": True, "duration": duration}
    
    async def _get_transition_duration(self) -> Dict[str, Any]:
        """Get current transition duration"""
        response = self._client.call(requests.GetTransitionDuration())
        return {"duration": response.getTransitionDuration()}
    
    # Source control methods
    async def _create_source(self, scene_name: str, source_name: str, source_kind: str, 
                         settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new source"""
        # First create the input
        input_settings = settings or {}
        self._client.call(requests.CreateInput(
            sceneName=scene_name,
            inputName=source_name,
            inputKind=source_kind,
            inputSettings=input_settings,
            sceneItemEnabled=True
        ))
        
        # Invalidate cache for this scene
        if scene_name in self._scene_items_cache:
            del self._scene_items_cache[scene_name]
            del self._scene_items_cache_time[scene_name]
        
        return {"success": True, "scene_name": scene_name, "source_name": source_name}
    
    async def _remove_source(self, scene_name: str, source_name: str) -> Dict[str, Any]:
        """Remove a source from a scene"""
        # First get the source ID
        items = await self._get_scene_item_list(scene_name)
        source_id = None
        for item in items["items"]:
            if item["source_name"] == source_name:
                source_id = item["id"]
                break
        
        if not source_id:
            return {"error": f"Source '{source_name}' not found in scene '{scene_name}'"}
        
        # Remove the item
        self._client.call(requests.RemoveSceneItem(
            sceneName=scene_name,
            sceneItemId=source_id
        ))
        
        # Invalidate cache for this scene
        if scene_name in self._scene_items_cache:
            del self._scene_items_cache[scene_name]
            del self._scene_items_cache_time[scene_name]
        
        return {"success": True, "scene_name": scene_name, "source_name": source_name}
    
    async def _duplicate_source(self, scene_name: str, source_name: str, 
                           new_name: str) -> Dict[str, Any]:
        """Duplicate a source in a scene
        
        Note: This is a higher-level operation that may not correspond directly to an OBS WebSocket request.
        """
        # Get the source settings
        settings_result = await self._get_source_settings(source_name=source_name)
        if "error" in settings_result:
            return settings_result
        
        # Get the source kind
        items = await self._get_scene_item_list(scene_name)
        source_kind = None
        for item in items["items"]:
            if item["source_name"] == source_name:
                source_kind = item["source_kind"]
                break
        
        if not source_kind:
            return {"error": f"Could not determine source kind for '{source_name}'"}
        
        # Create a new source with the same settings
        create_result = await self._create_source(
            scene_name=scene_name,
            source_name=new_name,
            source_kind=source_kind,
            settings=settings_result["settings"]
        )
        
        if "error" in create_result:
            return create_result
        
        return {
            "success": True, 
            "scene_name": scene_name, 
            "original_source": source_name,
            "new_source": new_name
        }
    
    async def _get_source_settings(self, source_name: str) -> Dict[str, Any]:
        """Get settings of a source"""
        response = self._client.call(requests.GetInputSettings(inputName=source_name))
        return {
            "settings": response.getInputSettings(),
            "source_name": source_name
        }
    
    async def _set_source_settings(self, source_name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Set settings of a source"""
        self._client.call(requests.SetInputSettings(
            inputName=source_name,
            inputSettings=settings
        ))
        return {"success": True, "source_name": source_name}
    
    async def _get_source_filters(self, source_name: str) -> Dict[str, Any]:
        """Get filters of a source"""
        response = self._client.call(requests.GetSourceFilterList(sourceName=source_name))
        filters = [
            OBSFilter(
                name=f["name"],
                type=f["type"],
                enabled=f["enabled"]
            ).model_dump()
            for f in response.getFilters()
        ]
        return {"source_name": source_name, "filters": filters}
    
    async def _add_source_filter(self, source_name: str, filter_name: str, 
                             filter_type: str, filter_settings: Dict[str, Any] = None) -> Dict[str, Any]:
        """Add a filter to a source"""
        self._client.call(requests.CreateSourceFilter(
            sourceName=source_name,
            filterName=filter_name,
            filterType=filter_type,
            filterSettings=filter_settings or {}
        ))
        return {"success": True, "source_name": source_name, "filter_name": filter_name}
    
    async def _remove_source_filter(self, source_name: str, filter_name: str) -> Dict[str, Any]:
        """Remove a filter from a source"""
        self._client.call(requests.RemoveSourceFilter(
            sourceName=source_name,
            filterName=filter_name
        ))
        return {"success": True, "source_name": source_name, "filter_name": filter_name}
    
    # Media control methods
    async def _play_pause_media(self, source_name: str, play: Optional[bool] = None) -> Dict[str, Any]:
        """Play or pause a media source"""
        if play is not None:
            self._client.call(requests.SetMediaInputCursor(
                inputName=source_name,
                mediaCursor=0  # Reset to beginning if we're explicitly playing
            ))
            self._client.call(requests.SetInputMute(
                inputName=source_name,
                inputMuted=False  # Unmute when playing
            ))
            self._client.call(requests.TriggerMediaInputAction(
                inputName=source_name,
                mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY" if play else "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE"
            ))
            action = "play" if play else "pause"
        else:
            self._client.call(requests.TriggerMediaInputAction(
                inputName=source_name,
                mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY_PAUSE"
            ))
            action = "toggle"
            
        return {"success": True, "source_name": source_name, "action": action}
    
    async def _restart_media(self, source_name: str) -> Dict[str, Any]:
        """Restart a media source"""
        self._client.call(requests.TriggerMediaInputAction(
            inputName=source_name,
            mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        ))
        return {"success": True, "source_name": source_name, "action": "restart"}
    
    async def _stop_media(self, source_name: str) -> Dict[str, Any]:
        """Stop a media source"""
        self._client.call(requests.TriggerMediaInputAction(
            inputName=source_name,
            mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        ))
        return {"success": True, "source_name": source_name, "action": "stop"}
    
    async def _get_media_time(self, source_name: str) -> Dict[str, Any]:
        """Get current time of a media source"""
        response = self._client.call(requests.GetMediaInputStatus(inputName=source_name))
        return {
            "source_name": source_name,
            "duration": response.getMediaDuration(),
            "position": response.getMediaCursor(),
            "state": response.getMediaState()
        }
    
    async def _set_media_time(self, source_name: str, time: float) -> Dict[str, Any]:
        """Set current time of a media source"""
        self._client.call(requests.SetMediaInputCursor(
            inputName=source_name,
            mediaCursor=time
        ))
        return {"success": True, "source_name": source_name, "time": time}
    
    async def _set_media_source(self, source_name: str, file_path: str) -> Dict[str, Any]:
        """Set the file path of a media source"""
        # Get the current settings
        settings = self._client.call(requests.GetInputSettings(inputName=source_name)).getInputSettings()
        
        # Update just the local_file setting
        settings["local_file"] = file_path
        
        # Apply the new settings
        self._client.call(requests.SetInputSettings(
            inputName=source_name,
            inputSettings=settings
        ))
        
        return {"success": True, "source_name": source_name, "file_path": file_path}
    
    # Text control methods
    async def _get_text_content(self, source_name: str) -> Dict[str, Any]:
        """Get text content of a text source"""
        response = self._client.call(requests.GetInputSettings(inputName=source_name))
        settings = response.getInputSettings()
        
        # Different text sources store the text in different properties
        text = settings.get("text", settings.get("from_file", None))
        
        return {"source_name": source_name, "text": text}
    
    async def _set_text_content(self, source_name: str, text: str) -> Dict[str, Any]:
        """Set text content of a text source"""
        # Get the current settings
        settings = self._client.call(requests.GetInputSettings(inputName=source_name)).getInputSettings()
        
        # Update just the text setting (works for GDI+ and FreeType2)
        settings["text"] = text
        
        # Apply the new settings
        self._client.call(requests.SetInputSettings(
            inputName=source_name,
            inputSettings=settings
        ))
        
        return {"success": True, "source_name": source_name, "text": text}
    
    # Studio mode methods
    async def _get_studio_mode(self) -> Dict[str, Any]:
        """Get studio mode status"""
        response = self._client.call(requests.GetStudioModeEnabled())
        return {"enabled": response.getStudioModeEnabled()}
    
    async def _set_studio_mode(self, enabled: bool) -> Dict[str, Any]:
        """Set studio mode status"""
        if enabled:
            self._client.call(requests.EnableStudioMode())
        else:
            self._client.call(requests.DisableStudioMode())
        return {"success": True, "enabled": enabled}
    
    async def _get_preview_scene(self) -> Dict[str, Any]:
        """Get current preview scene in studio mode"""
        response = self._client.call(requests.GetCurrentPreviewScene())
        return {"scene_name": response.getCurrentPreviewSceneName()}
    
    async def _set_preview_scene(self, scene_name: str) -> Dict[str, Any]:
        """Set preview scene in studio mode"""
        self._client.call(requests.SetCurrentPreviewScene(sceneName=scene_name))
        return {"success": True, "scene_name": scene_name}
    
    async def _studio_mode_transition(self) -> Dict[str, Any]:
        """Transition from preview to program in studio mode"""
        self._client.call(requests.TriggerStudioModeTransition())
        return {"success": True}
    
    # Virtual camera methods
    async def _start_virtual_camera(self) -> Dict[str, Any]:
        """Start virtual camera"""
        self._client.call(requests.StartVirtualCam())
        return {"success": True}
    
    async def _stop_virtual_camera(self) -> Dict[str, Any]:
        """Stop virtual camera"""
        self._client.call(requests.StopVirtualCam())
        return {"success": True}
    
    async def _toggle_virtual_camera(self) -> Dict[str, Any]:
        """Toggle virtual camera"""
        response = self._client.call(requests.ToggleVirtualCam())
        return {
            "success": True, 
            "active": response.getOutputActive() if hasattr(response, "getOutputActive") else None
        }
    
    # Status method
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
                # Add version info if available
                if self._version_info:
                    result.update(self._version_info)
                
                # Add streaming status
                streaming_status = await self._get_streaming_status()
                result["streaming"] = streaming_status["streaming"]
                result["recording"] = streaming_status["recording"]
                
                # Add current scene
                current_scene = await self._get_current_scene()
                result["current_scene"] = current_scene["current_scene"]
                
                # Add stats
                stats = await self._get_stats()
                result["stats"] = stats
            except Exception as e:
                logger.error(f"Error getting OBS status: {str(e)}")
                result["error"] = str(e)
        
        return result