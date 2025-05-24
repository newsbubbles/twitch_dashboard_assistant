import logging
import asyncio
from collections import deque, Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable, Deque
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class TrendDirection(str, Enum):
    """Enum representing trend directions"""
    RISING_RAPIDLY = "rising_rapidly"
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"
    FALLING_RAPIDLY = "falling_rapidly"

class SeverityLevel(str, Enum):
    """Enum representing severity levels for insights"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class MetricPoint(BaseModel):
    """Model representing a single metric data point"""
    timestamp: datetime = Field(..., description="Time when the metric was recorded")
    value: Any = Field(..., description="Value of the metric")

class MetricType(str, Enum):
    """Enum representing types of metrics"""
    VIEWER_COUNT = "viewer_count"
    CHAT_ACTIVITY = "chat_activity"
    STREAM_QUALITY = "stream_quality"
    AUDIO_LEVELS = "audio_levels"
    ENGAGEMENT = "engagement"
    FOLLOWS = "follows"
    SUBSCRIPTIONS = "subscriptions"
    STREAM_DURATION = "stream_duration"

class InsightType(str, Enum):
    """Enum representing types of insights"""
    STREAM_HEALTH = "stream_health"
    ENGAGEMENT = "engagement" 
    TECHNICAL = "technical"
    GROWTH = "growth"
    CONTENT = "content"

class SuggestionAction(BaseModel):
    """Model representing a suggested action to take"""
    service: str = Field(..., description="Service to use for this action")
    method: str = Field(..., description="Method to call")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the method call")
    description: str = Field(..., description="Human-readable description of this action")

class Insight(BaseModel):
    """Model representing an insight generated from metrics"""
    id: str = Field(..., description="Unique identifier for this insight")
    timestamp: datetime = Field(..., description="When this insight was generated")
    type: InsightType = Field(..., description="Category of this insight")
    title: str = Field(..., description="Short title")
    description: str = Field(..., description="Detailed description")
    severity: SeverityLevel = Field(SeverityLevel.MEDIUM, description="Importance level")
    metrics: List[str] = Field(default_factory=list, description="Related metric types")
    suggested_actions: List[SuggestionAction] = Field(
        default_factory=list, description="Suggested actions to address this insight"
    )
    is_actionable: bool = Field(
        True, description="Whether there are concrete actions to address this insight"
    )
    expiration: Optional[datetime] = Field(
        None, description="When this insight is no longer relevant"
    )

class ContextAnalyzer:
    """Analyzer for stream context data that generates insights and recommendations"""

    def __init__(self, integration_manager):
        self.integration_manager = integration_manager
        # Stores historical metric data with limited buffer size
        self._metrics: Dict[str, Deque[MetricPoint]] = {}
        # Stores generated insights
        self._insights: List[Insight] = []
        # Store the latest state of the stream context
        self._current_context: Dict[str, Any] = {}
        # Configuration for metric collection
        self._config = {
            "max_metric_points": 100,  # Maximum points to keep in history
            "collection_interval": 30,  # Seconds between collection runs
            "insight_retention_hours": 24,  # Hours to keep insights
            "anomaly_threshold": 2.0,  # Standard deviations for anomaly detection
        }
        # Collection task
        self._collection_task: Optional[asyncio.Task] = None
        # Collection active flag
        self._is_collecting = False
    
    async def start_collection(self):
        """Start the metric collection loop"""
        if self._is_collecting:
            logger.info("Metric collection already running")
            return
        
        self._is_collecting = True
        self._collection_task = asyncio.create_task(self._collection_loop())
        logger.info("Started metric collection")
    
    async def stop_collection(self):
        """Stop the metric collection loop"""
        if not self._is_collecting:
            logger.info("Metric collection not running")
            return
        
        self._is_collecting = False
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped metric collection")
    
    async def _collection_loop(self):
        """Main loop for collecting metrics"""
        try:
            while self._is_collecting:
                try:
                    await self._collect_metrics()
                    await self._analyze_metrics()
                    await self._clean_expired_insights()
                except Exception as e:
                    logger.error(f"Error in metric collection cycle: {str(e)}")
                
                await asyncio.sleep(self._config["collection_interval"])
        
        except asyncio.CancelledError:
            logger.debug("Metric collection loop cancelled")
    
    async def _collect_metrics(self):
        """Collect metrics from all integrations"""
        twitch_metrics = await self._collect_twitch_metrics()
        obs_metrics = await self._collect_obs_metrics()
        
        # Update current context with latest metrics
        if twitch_metrics:
            self._current_context.update(twitch_metrics)
        if obs_metrics:
            self._current_context.update(obs_metrics)
        
        # Add timestamp if not present
        if "timestamp" not in self._current_context:
            self._current_context["timestamp"] = datetime.now()
        
        # Store metrics in history
        timestamp = self._current_context["timestamp"]
        
        # Store individual metrics
        self._store_metric("viewer_count", timestamp, self._current_context.get("viewer_count"))
        self._store_metric("chat_messages_per_minute", timestamp, 
                        self._current_context.get("chat_messages_per_minute"))
        
        # Stream quality metrics
        if "dropped_frames_percent" in self._current_context:
            self._store_metric("dropped_frames_percent", timestamp, 
                            self._current_context["dropped_frames_percent"])
        
        # Audio levels
        if "audio_levels" in self._current_context:
            for source, level in self._current_context["audio_levels"].items():
                self._store_metric(f"audio_level_{source}", timestamp, level)
    
    def _store_metric(self, name: str, timestamp: datetime, value: Any):
        """Store a metric value in history
        
        Args:
            name: Metric name
            timestamp: When the metric was collected
            value: Metric value
        """
        if value is None:
            return
        
        # Initialize deque if doesn't exist
        if name not in self._metrics:
            self._metrics[name] = deque(maxlen=self._config["max_metric_points"])
        
        # Add new data point
        self._metrics[name].append(MetricPoint(timestamp=timestamp, value=value))
    
    async def _collect_twitch_metrics(self) -> Dict[str, Any]:
        """Collect metrics from Twitch
        
        Returns:
            Dict[str, Any]: Collected metrics
        """
        twitch_adapter = self.integration_manager.get_integration("twitch")
        if not twitch_adapter or twitch_adapter.status != "connected":
            return {}
        
        try:
            metrics = {}
            
            # Get stream info
            stream_result = await twitch_adapter.execute_action("get_stream")
            if "stream" in stream_result and stream_result["stream"]:
                stream = stream_result["stream"]
                metrics["viewer_count"] = stream.get("viewer_count", 0)
                metrics["stream_title"] = stream.get("title", "")
                metrics["category_name"] = stream.get("game_name", "")
                metrics["category_id"] = stream.get("game_id", "")
                
                # Calculate stream duration if start time available
                if "started_at" in stream:
                    start_time = datetime.fromisoformat(stream["started_at"].replace("Z", "+00:00"))
                    duration = (datetime.now(start_time.tzinfo) - start_time).total_seconds() / 60
                    metrics["stream_duration_minutes"] = duration
            
            # Get chat stats - simplified as we don't have direct chat stats API
            # In a real implementation, we would track these over time
            metrics["chat_messages_per_minute"] = self._current_context.get("chat_messages_per_minute", 0)
            
            return metrics
        
        except Exception as e:
            logger.error(f"Error collecting Twitch metrics: {str(e)}")
            return {}
    
    async def _collect_obs_metrics(self) -> Dict[str, Any]:
        """Collect metrics from OBS
        
        Returns:
            Dict[str, Any]: Collected metrics
        """
        obs_adapter = self.integration_manager.get_integration("obs")
        if not obs_adapter or obs_adapter.status != "connected":
            return {}
        
        try:
            metrics = {}
            
            # Get streaming status
            status_result = await obs_adapter.execute_action("get_streaming_status")
            metrics["streaming"] = status_result.get("streaming", False)
            metrics["recording"] = status_result.get("recording", False)
            
            if metrics["streaming"]:
                metrics["stream_kbits_per_sec"] = status_result.get("kbits_per_sec", 0)
                metrics["stream_fps"] = status_result.get("fps", 0)
                
                # Calculate dropped frames percentage
                total_frames = status_result.get("num_total_frames", 0)
                dropped_frames = status_result.get("num_dropped_frames", 0)
                if total_frames > 0:
                    metrics["dropped_frames_percent"] = (dropped_frames / total_frames) * 100
                else:
                    metrics["dropped_frames_percent"] = 0
            
            # Get current scene
            scene_result = await obs_adapter.execute_action("get_current_scene")
            metrics["current_scene"] = scene_result.get("current_scene", "")
            
            # Get audio levels
            audio_result = await obs_adapter.execute_action("get_audio_sources")
            if "audio_sources" in audio_result:
                audio_levels = {}
                for source in audio_result["audio_sources"]:
                    audio_levels[source["name"]] = {
                        "db": source["volume_db"],
                        "muted": source["muted"]
                    }
                metrics["audio_levels"] = audio_levels
            
            # Get OBS stats
            stats_result = await obs_adapter.execute_action("get_stats")
            metrics["cpu_usage"] = stats_result.get("cpu_usage", 0)
            metrics["memory_usage"] = stats_result.get("memory_usage", 0)
            
            return metrics
        
        except Exception as e:
            logger.error(f"Error collecting OBS metrics: {str(e)}")
            return {}
    
    async def _analyze_metrics(self):
        """Analyze metrics to generate insights"""
        # Run various analyzers
        await self._analyze_stream_health()
        await self._analyze_viewer_trends()
        await self._analyze_audio_levels()
        await self._analyze_engagement()
    
    async def _analyze_stream_health(self):
        """Analyze stream health metrics"""
        # Check if streaming
        if not self._current_context.get("streaming", False):
            return
        
        # Check dropped frames
        if "dropped_frames_percent" in self._metrics:
            latest = list(self._metrics["dropped_frames_percent"])[-1].value
            
            # High dropped frames warning
            if latest > 5.0:  # More than 5% dropped frames is concerning
                severity = SeverityLevel.HIGH if latest > 10.0 else SeverityLevel.MEDIUM
                
                insight = Insight(
                    id=f"dropped_frames_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.TECHNICAL,
                    title="High dropped frames detected",
                    description=f"Your stream is experiencing {latest:.1f}% dropped frames, "
                              f"which may impact viewer experience.",
                    severity=severity,
                    metrics=["dropped_frames_percent"],
                    suggested_actions=[
                        SuggestionAction(
                            service="internal",
                            method="notify",
                            params={"message": "Consider lowering your bitrate or resolution"},
                            description="Lower your stream bitrate or resolution"
                        )
                    ]
                )
                
                self._add_insight(insight)
        
        # Check CPU usage
        if "cpu_usage" in self._current_context:
            cpu_usage = self._current_context["cpu_usage"]
            
            # High CPU usage warning
            if cpu_usage > 80:  # CPU usage over 80% is concerning
                insight = Insight(
                    id=f"high_cpu_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.TECHNICAL,
                    title="High CPU usage",
                    description=f"OBS is using {cpu_usage:.1f}% CPU, which may cause "
                              f"encoding issues and dropped frames.",
                    severity=SeverityLevel.MEDIUM,
                    metrics=["cpu_usage"],
                    suggested_actions=[
                        SuggestionAction(
                            service="internal",
                            method="notify",
                            params={"message": "Consider using a faster x264 preset or NVENC"},
                            description="Switch to a faster encoding preset"
                        )
                    ]
                )
                
                self._add_insight(insight)
    
    async def _analyze_viewer_trends(self):
        """Analyze viewer count trends"""
        if "viewer_count" not in self._metrics or len(self._metrics["viewer_count"]) < 3:
            return
        
        # Get recent viewer counts
        recent_points = list(self._metrics["viewer_count"])[-10:]
        if len(recent_points) < 3:
            return
        
        # Calculate trend
        trend = self._calculate_trend("viewer_count", window=10)
        
        # Check for significant viewer drops
        if trend == TrendDirection.FALLING_RAPIDLY:
            # Get current and previous values
            current = recent_points[-1].value
            previous = recent_points[-3].value  # A few points back to smooth out noise
            
            # Calculate percentage drop
            if previous > 0:
                drop_percent = ((previous - current) / previous) * 100
                
                # Only alert if it's a significant drop
                if drop_percent > 20 and previous >= 10:  # At least 20% drop from 10+ viewers
                    insight = Insight(
                        id=f"viewer_drop_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        timestamp=datetime.now(),
                        type=InsightType.ENGAGEMENT,
                        title="Significant viewer drop",
                        description=f"You've lost approximately {drop_percent:.0f}% of your viewers "
                                  f"in the last few minutes ({previous} → {current}).",
                        severity=SeverityLevel.MEDIUM,
                        metrics=["viewer_count"],
                        suggested_actions=[
                            SuggestionAction(
                                service="internal",
                                method="notify",
                                params={"message": "Consider increasing interaction with chat"},
                                description="Increase interaction with chat"
                            )
                        ]
                    )
                    
                    self._add_insight(insight)
        
        # Check for viewer growth
        elif trend == TrendDirection.RISING_RAPIDLY:
            # Only notify of significant growth
            current = recent_points[-1].value
            start = recent_points[0].value
            
            if start > 0 and current > start * 1.5 and current - start >= 10:
                insight = Insight(
                    id=f"viewer_growth_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.GROWTH,
                    title="Rapid viewer growth",
                    description=f"Your viewer count has increased significantly "
                              f"from {start} to {current}.",
                    severity=SeverityLevel.LOW,
                    metrics=["viewer_count"],
                    is_actionable=False
                )
                
                self._add_insight(insight)
    
    async def _analyze_audio_levels(self):
        """Analyze audio levels"""
        if not self._current_context.get("streaming", False):
            return
        
        if "audio_levels" not in self._current_context:
            return
        
        audio_levels = self._current_context["audio_levels"]
        
        # Check for mic audio issues
        if "Mic/Aux" in audio_levels:
            mic_data = audio_levels["Mic/Aux"]
            mic_level = mic_data["db"]
            mic_muted = mic_data["muted"]
            
            # Check if mic is muted but should be on
            if mic_muted and self._current_context.get("streaming", False):
                insight = Insight(
                    id=f"mic_muted_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.TECHNICAL,
                    title="Microphone is muted",
                    description="Your microphone is currently muted while you are streaming.",
                    severity=SeverityLevel.HIGH,
                    metrics=["audio_levels"],
                    suggested_actions=[
                        SuggestionAction(
                            service="obs",
                            method="set_mute",
                            params={"source_name": "Mic/Aux", "muted": False},
                            description="Unmute your microphone"
                        )
                    ]
                )
                
                self._add_insight(insight)
            
            # Check if mic level is too low
            elif not mic_muted and mic_level < -30:  # Very quiet
                insight = Insight(
                    id=f"mic_low_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.TECHNICAL,
                    title="Microphone level too low",
                    description=f"Your microphone volume is very low ({mic_level} dB).",
                    severity=SeverityLevel.MEDIUM,
                    metrics=["audio_levels"],
                    suggested_actions=[
                        SuggestionAction(
                            service="obs",
                            method="set_volume",
                            params={"source_name": "Mic/Aux", "volume": -20, "volume_type": "db"},
                            description="Increase your microphone volume"
                        )
                    ]
                )
                
                self._add_insight(insight)
        
        # Check for desktop audio issues (too loud compared to mic)
        if "Desktop Audio" in audio_levels and "Mic/Aux" in audio_levels:
            desktop_data = audio_levels["Desktop Audio"]
            mic_data = audio_levels["Mic/Aux"]
            
            desktop_level = desktop_data["db"]
            mic_level = mic_data["db"]
            
            # Desktop audio drowning out mic
            if not desktop_data["muted"] and not mic_data["muted"] and desktop_level > mic_level + 10:
                insight = Insight(
                    id=f"audio_balance_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.TECHNICAL,
                    title="Game audio overpowering microphone",
                    description="Your desktop/game audio is much louder than your microphone, "
                              "which may make it hard for viewers to hear you.",
                    severity=SeverityLevel.MEDIUM,
                    metrics=["audio_levels"],
                    suggested_actions=[
                        SuggestionAction(
                            service="obs",
                            method="set_volume",
                            params={"source_name": "Desktop Audio", "volume": -20, "volume_type": "db"},
                            description="Reduce game/desktop audio volume"
                        )
                    ]
                )
                
                self._add_insight(insight)
    
    async def _analyze_engagement(self):
        """Analyze engagement metrics"""
        # This is a simplified version - in a real implementation we would
        # analyze chat activity, follows, subscriptions, etc.
        
        # We need both viewer count and chat activity
        if ("viewer_count" not in self._metrics or 
            "chat_messages_per_minute" not in self._metrics):
            return
        
        if len(self._metrics["viewer_count"]) < 5:
            return
        
        # Get current values
        viewers = list(self._metrics["viewer_count"])[-1].value
        chat_rate = list(self._metrics["chat_messages_per_minute"])[-1].value if \
            self._metrics["chat_messages_per_minute"] else 0
        
        # Calculate engagement ratio (messages per viewer)
        if viewers > 0:
            engagement_ratio = chat_rate / viewers
            
            # Low engagement warning
            if viewers >= 20 and engagement_ratio < 0.1 and chat_rate < 2:
                insight = Insight(
                    id=f"low_engagement_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now(),
                    type=InsightType.ENGAGEMENT,
                    title="Low chat engagement",
                    description=f"You have {viewers} viewers but very little chat activity. "
                              f"Consider engaging more with your audience.",
                    severity=SeverityLevel.LOW,
                    metrics=["viewer_count", "chat_messages_per_minute"],
                    suggested_actions=[
                        SuggestionAction(
                            service="internal",
                            method="notify",
                            params={"message": "Try asking your audience a question"},
                            description="Ask your audience a question to prompt participation"
                        )
                    ]
                )
                
                self._add_insight(insight)
    
    def _calculate_trend(self, metric_name: str, window: int = 5) -> TrendDirection:
        """Calculate the trend direction for a metric
        
        Args:
            metric_name: Name of the metric
            window: Number of recent points to consider
            
        Returns:
            TrendDirection: The detected trend direction
        """
        if metric_name not in self._metrics:
            return TrendDirection.STABLE
        
        points = list(self._metrics[metric_name])[-window:]
        if len(points) < 2:
            return TrendDirection.STABLE
        
        # Simple approach: compare first and last values
        first_value = points[0].value
        last_value = points[-1].value
        
        # Avoid division by zero
        if first_value == 0:
            return TrendDirection.RISING if last_value > 0 else TrendDirection.STABLE
        
        # Calculate percentage change
        percent_change = ((last_value - first_value) / first_value) * 100
        
        # Determine trend based on magnitude of change
        if percent_change > 25:
            return TrendDirection.RISING_RAPIDLY
        elif percent_change > 10:
            return TrendDirection.RISING
        elif percent_change < -25:
            return TrendDirection.FALLING_RAPIDLY
        elif percent_change < -10:
            return TrendDirection.FALLING
        else:
            return TrendDirection.STABLE
    
    def _calculate_anomaly(self, metric_name: str, window: int = 20) -> bool:
        """Detect if the latest value is an anomaly
        
        Args:
            metric_name: Name of the metric
            window: Number of points to use for baseline
            
        Returns:
            bool: True if the latest point is an anomaly
        """
        if metric_name not in self._metrics:
            return False
        
        points = list(self._metrics[metric_name])[-window:]
        if len(points) < 5:  # Need enough points for a baseline
            return False
        
        # Calculate mean and standard deviation (excluding the last point)
        values = [point.value for point in points[:-1]]
        mean = sum(values) / len(values)
        
        # Calculate standard deviation
        squared_diff = sum((x - mean) ** 2 for x in values)
        std_dev = (squared_diff / len(values)) ** 0.5
        
        # Get the latest value
        latest = points[-1].value
        
        # If standard deviation is too small, avoid false positives
        if std_dev < 0.01 * abs(mean) and std_dev > 0:
            std_dev = 0.01 * abs(mean)
        
        # Calculate z-score
        if std_dev == 0:
            # If all values are identical, any change is an anomaly
            return latest != mean
        
        z_score = abs((latest - mean) / std_dev)
        
        # Check if z-score exceeds threshold
        return z_score > self._config["anomaly_threshold"]
    
    def _add_insight(self, insight: Insight) -> bool:
        """Add a new insight, avoiding duplicates
        
        Args:
            insight: The insight to add
            
        Returns:
            bool: True if added, False if duplicate
        """
        # Check for similar recent insights to avoid duplicates
        recent_cutoff = datetime.now() - timedelta(minutes=30)
        
        for existing in self._insights:
            # If similar insight exists and is recent
            if (existing.type == insight.type and 
                existing.title == insight.title and 
                existing.timestamp > recent_cutoff):
                return False
        
        self._insights.append(insight)
        logger.info(f"New insight: {insight.title} ({insight.severity})")
        return True
    
    async def _clean_expired_insights(self):
        """Remove expired insights"""
        now = datetime.now()
        retention_delta = timedelta(hours=self._config["insight_retention_hours"])
        cutoff = now - retention_delta
        
        # Remove insights older than the cutoff or with passed expiration
        self._insights = [
            insight for insight in self._insights 
            if (insight.timestamp > cutoff and 
                (insight.expiration is None or insight.expiration > now))
        ]
    
    def get_insights(self, 
                   insight_type: Optional[InsightType] = None, 
                   severity: Optional[SeverityLevel] = None,
                   limit: int = 10) -> List[Dict[str, Any]]:
        """Get insights with optional filtering
        
        Args:
            insight_type: Optional insight type to filter by
            severity: Optional minimum severity level
            limit: Maximum number of insights to return
            
        Returns:
            List[Dict[str, Any]]: Filtered insights
        """
        # Filter insights
        filtered = self._insights
        
        if insight_type:
            filtered = [i for i in filtered if i.type == insight_type]
        
        if severity:
            # Convert severity levels to numeric for comparison
            severity_order = {
                SeverityLevel.LOW: 0,
                SeverityLevel.MEDIUM: 1,
                SeverityLevel.HIGH: 2,
                SeverityLevel.CRITICAL: 3
            }
            
            min_level = severity_order[severity]
            filtered = [i for i in filtered if severity_order[i.severity] >= min_level]
        
        # Sort by timestamp (newest first) and limit
        sorted_insights = sorted(filtered, key=lambda x: x.timestamp, reverse=True)[:limit]
        
        # Convert to dict for serialization
        return [insight.model_dump() for insight in sorted_insights]
    
    def get_metric_history(self, metric_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get historical values for a metric
        
        Args:
            metric_name: Name of the metric
            limit: Maximum number of points to return
            
        Returns:
            List[Dict[str, Any]]: Historical metric points
        """
        if metric_name not in self._metrics:
            return []
        
        # Get the most recent points up to the limit
        points = list(self._metrics[metric_name])[-limit:]
        
        # Convert to dict for serialization
        return [{
            "timestamp": point.timestamp.isoformat(),
            "value": point.value
        } for point in points]
    
    def get_current_context(self) -> Dict[str, Any]:
        """Get the current stream context
        
        Returns:
            Dict[str, Any]: Current context data
        """
        # Create a copy to avoid external modification
        context = self._current_context.copy()
        
        # Add derived metrics
        context["metrics"] = list(self._metrics.keys())
        
        # Add trends for key metrics
        trends = {}
        for metric in ["viewer_count", "chat_messages_per_minute", "dropped_frames_percent"]:
            if metric in self._metrics and len(self._metrics[metric]) >= 3:
                trends[metric] = self._calculate_trend(metric)
        
        context["trends"] = trends
        
        return context
    
    def update_config(self, config_updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update the analyzer configuration
        
        Args:
            config_updates: Configuration updates
            
        Returns:
            Dict[str, Any]: Updated configuration
        """
        for key, value in config_updates.items():
            if key in self._config:
                self._config[key] = value
        
        return self._config.copy()
    
    def simulate_metric(self, name: str, value: Any) -> None:
        """Simulate a metric value (for testing)
        
        Args:
            name: Metric name
            value: Metric value
        """
        self._store_metric(name, datetime.now(), value)
        
        # Update current context
        self._current_context[name] = value
    
    async def close(self):
        """Stop collection and clean up resources"""
        await self.stop_collection()
