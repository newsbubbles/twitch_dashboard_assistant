# Context Analyzer Research

This document explores approaches to building a context-aware system for the Twitch Dashboard Assistant that can understand stream state, analyze engagement, and provide intelligent suggestions.

## Core Requirements

The context analyzer should:

1. **Collect Data**: Gather information from multiple sources
2. **Process Metrics**: Analyze real-time and historical metrics
3. **Detect Patterns**: Identify trends and anomalies 
4. **Generate Insights**: Provide actionable recommendations
5. **Adapt Over Time**: Learn from streamer preferences

## Data Sources

### 1. Twitch Stream Data

#### Metrics to Track
- Viewer count (current, peak, average)
- Stream duration
- Stream title, category, tags
- Stream quality metrics (bitrate, dropped frames)
- Chat message volume and frequency
- New follows, subscribers, bits
- Clip creation rate

#### Collection Methods
- Twitch API polling (every 30-60 seconds)
- Twitch EventSub for real-time events
- Chat WebSocket for message monitoring

#### Example Implementation
```python
async def collect_twitch_metrics(twitch_client, channel_id):
    # Stream info
    stream_data = await twitch_client.get_streams(user_id=channel_id)
    if not stream_data.data:
        return None  # Not streaming
    
    stream = stream_data.data[0]
    
    # Chat stats
    chat_stats = await twitch_client.get_chat_stats(broadcaster_id=channel_id)
    
    # Engagement stats
    follows = await twitch_client.get_channel_follows(broadcaster_id=channel_id, first=100)
    subs = await twitch_client.get_broadcaster_subscriptions(broadcaster_id=channel_id)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "viewer_count": stream.viewer_count,
        "started_at": stream.started_at,
        "category_id": stream.game_id,
        "category_name": stream.game_name,
        "title": stream.title,
        "chat_message_count": chat_stats.message_count,
        "unique_chatters": chat_stats.unique_chatter_count,
        "new_follows": len(follows.data),
        "subscriber_count": len(subs.data),
    }
```

### 2. OBS/Streaming Software Data

#### Metrics to Track
- Current scene
- Active sources
- CPU/GPU usage
- Encoding quality
- Audio levels
- Recording status

#### Collection Methods
- OBS WebSocket API polling
- OBS WebSocket events

#### Example Implementation
```python
async def collect_obs_metrics(obs_client):
    # Current scene
    scene_info = obs_client.call(requests.GetCurrentProgramScene())
    
    # Stats
    stats = obs_client.call(requests.GetStats())
    
    # Audio levels
    audio_sources = obs_client.call(requests.GetInputList(inputKind="audio")).inputs
    audio_levels = {}
    for source in audio_sources:
        level = obs_client.call(requests.GetInputVolume(inputName=source["inputName"]))
        audio_levels[source["inputName"]] = level.inputVolumeDb
    
    return {
        "timestamp": datetime.now().isoformat(),
        "current_scene": scene_info.currentProgramSceneName,
        "cpu_usage": stats.cpuUsage,
        "memory_usage": stats.memoryUsage,
        "fps": stats.renderTotalFrames / stats.renderTotalFrames if stats.renderTotalFrames > 0 else 0,
        "dropped_frames": stats.outputSkippedFrames,
        "audio_levels": audio_levels,
        "streaming": stats.outputActive,
    }
```

### 3. Chat Analysis

#### Metrics to Track
- Message sentiment (positive/negative/neutral)
- Keyword frequency
- Questions asked
- Emote usage
- User engagement patterns
- Command usage

#### Collection Methods
- IRC connection to Twitch chat
- Chat message processing pipeline

#### Example Implementation
```python
class ChatAnalyzer:
    def __init__(self):
        self.message_buffer = []
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        self.common_words = Counter()
        self.emote_usage = Counter()
        self.questions = []
    
    async def process_message(self, message):
        # Add to buffer
        self.message_buffer.append({
            "timestamp": datetime.now().isoformat(),
            "user": message.user,
            "content": message.content,
            "is_sub": message.is_sub,
            "is_mod": message.is_mod,
        })
        
        # Limit buffer size
        if len(self.message_buffer) > 1000:
            self.message_buffer = self.message_buffer[-1000:]
        
        # Process sentiment
        sentiment = self.sentiment_analyzer.polarity_scores(message.content)
        
        # Track words
        words = message.content.lower().split()
        self.common_words.update(words)
        
        # Track emotes
        for emote in message.emotes:
            self.emote_usage.update([emote])
        
        # Detect questions
        if "?" in message.content:
            self.questions.append(message.content)
            if len(self.questions) > 100:
                self.questions = self.questions[-100:]
    
    def get_metrics(self):
        # Calculate metrics from buffer
        message_count = len(self.message_buffer)
        if message_count == 0:
            return {}
        
        unique_users = len(set(m["user"] for m in self.message_buffer))
        
        # Calculate average sentiment
        sentiments = [self.sentiment_analyzer.polarity_scores(m["content"])["compound"] 
                     for m in self.message_buffer]
        avg_sentiment = sum(sentiments) / len(sentiments)
        
        return {
            "message_count": message_count,
            "unique_users": unique_users,
            "messages_per_minute": message_count / (self.get_buffer_duration().total_seconds() / 60),
            "sentiment": avg_sentiment,
            "top_words": dict(self.common_words.most_common(10)),
            "top_emotes": dict(self.emote_usage.most_common(5)),
            "recent_questions": self.questions[-5:],
        }
    
    def get_buffer_duration(self):
        if not self.message_buffer:
            return timedelta(0)
        oldest = datetime.fromisoformat(self.message_buffer[0]["timestamp"])
        newest = datetime.fromisoformat(self.message_buffer[-1]["timestamp"])
        return newest - oldest
```

### 4. Historical Performance

#### Metrics to Track
- Average viewer counts by day/time
- Average viewer counts by game/category
- Retention rates
- Growth patterns
- Engagement by content type

#### Collection Methods
- Database of historical stream data
- Periodic aggregation of metrics

#### Example Implementation
```python
class HistoricalAnalyzer:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def get_historical_metrics(self, channel_id, days=30):
        # Get streams in time period
        query = """
        SELECT 
            date_trunc('day', started_at) as stream_date,
            AVG(viewer_count) as avg_viewers,
            MAX(viewer_count) as peak_viewers,
            COUNT(*) as stream_count,
            SUM(duration_minutes) as total_minutes
        FROM streams
        WHERE channel_id = ? AND started_at > datetime('now', ?)
        GROUP BY date_trunc('day', started_at)
        ORDER BY stream_date DESC;
        """
        
        days_param = f"-{days} days"
        results = await self.db.execute_query(query, (channel_id, days_param))
        
        # Get category performance
        category_query = """
        SELECT 
            category_name,
            AVG(viewer_count) as avg_viewers,
            MAX(viewer_count) as peak_viewers,
            SUM(duration_minutes) as total_minutes
        FROM streams
        WHERE channel_id = ? AND started_at > datetime('now', ?)
        GROUP BY category_name
        ORDER BY avg_viewers DESC;
        """
        
        category_results = await self.db.execute_query(category_query, (channel_id, days_param))
        
        # Get time-of-day performance
        time_query = """
        SELECT 
            strftime('%H', started_at) as hour_of_day,
            AVG(viewer_count) as avg_viewers
        FROM streams
        WHERE channel_id = ? AND started_at > datetime('now', ?)
        GROUP BY hour_of_day
        ORDER BY hour_of_day;
        """
        
        time_results = await self.db.execute_query(time_query, (channel_id, days_param))
        
        return {
            "daily_metrics": results,
            "category_performance": category_results,
            "time_performance": time_results
        }
    
    async def get_growth_metrics(self, channel_id, days=90):
        # Calculate growth over time
        query = """
        SELECT 
            date_trunc('week', timestamp) as week,
            COUNT(DISTINCT user_id) as new_followers,
            COUNT(DISTINCT sub_user_id) as new_subscribers
        FROM events
        WHERE channel_id = ? AND timestamp > datetime('now', ?)
        AND (event_type = 'follow' OR event_type = 'subscribe')
        GROUP BY date_trunc('week', timestamp)
        ORDER BY week;
        """
        
        days_param = f"-{days} days"
        results = await self.db.execute_query(query, (channel_id, days_param))
        
        return {
            "weekly_growth": results
        }
```

## Analysis Techniques

### 1. Moving Window Analysis

#### Overview
Analyze metrics over sliding time windows to detect trends and changes.

#### Implementation
```python
class MetricWindowAnalyzer:
    def __init__(self, window_size=5):
        self.window_size = window_size
        self.metric_history = defaultdict(deque)
    
    def add_metric(self, name, value):
        history = self.metric_history[name]
        history.append({
            "timestamp": datetime.now(),
            "value": value
        })
        
        # Maintain window size
        while len(history) > self.window_size:
            history.popleft()
    
    def get_trend(self, name):
        history = self.metric_history[name]
        if len(history) < 2:
            return "stable"  # Not enough data
        
        first = history[0]["value"]
        last = history[-1]["value"]
        
        # Calculate percent change
        if first == 0:  # Avoid division by zero
            percent_change = 100 if last > 0 else 0
        else:
            percent_change = ((last - first) / first) * 100
        
        # Determine trend
        if percent_change > 10:
            return "rising_rapidly"
        elif percent_change > 5:
            return "rising"
        elif percent_change < -10:
            return "falling_rapidly"
        elif percent_change < -5:
            return "falling"
        else:
            return "stable"
    
    def get_anomalies(self, name, threshold=2.0):
        history = self.metric_history[name]
        if len(history) < 3:
            return False  # Not enough data
        
        values = [item["value"] for item in history]
        mean = sum(values) / len(values)
        
        # Standard deviation
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5
        
        # Check if latest value is an anomaly
        latest = values[-1]
        z_score = (latest - mean) / std_dev if std_dev > 0 else 0
        
        return abs(z_score) > threshold
```

### 2. Pattern Recognition

#### Overview
Identify common patterns in stream metrics that correlate with success or issues.

#### Implementation
```python
class PatternRecognizer:
    def __init__(self):
        self.patterns = {
            "viewer_drop": self._check_viewer_drop,
            "chat_surge": self._check_chat_surge,
            "audio_issues": self._check_audio_issues,
            "stream_quality": self._check_stream_quality,
            "engagement_decline": self._check_engagement_decline,
        }
    
    def check_patterns(self, metrics):
        results = {}
        for pattern_name, check_func in self.patterns.items():
            results[pattern_name] = check_func(metrics)
        return results
    
    def _check_viewer_drop(self, metrics):
        # Check for sudden viewer count drop
        viewer_history = metrics.get("viewer_count_history", [])
        if len(viewer_history) < 3:
            return {"detected": False}
        
        current = viewer_history[-1]
        previous = viewer_history[-2]
        
        # If we lost more than 15% of viewers suddenly
        if previous > 0 and (previous - current) / previous > 0.15:
            return {
                "detected": True,
                "severity": "high" if (previous - current) / previous > 0.25 else "medium",
                "details": f"Viewer count dropped from {previous} to {current}"
            }
        return {"detected": False}
    
    def _check_chat_surge(self, metrics):
        # Check for sudden increase in chat activity
        chat_rate = metrics.get("chat_messages_per_minute", 0)
        chat_rate_history = metrics.get("chat_rate_history", [])
        
        if len(chat_rate_history) < 3:
            return {"detected": False}
        
        avg_rate = sum(chat_rate_history[:-1]) / len(chat_rate_history[:-1])
        
        # If chat activity doubled
        if avg_rate > 0 and chat_rate / avg_rate > 2:
            return {
                "detected": True,
                "severity": "medium",
                "details": f"Chat activity increased from {avg_rate:.1f} to {chat_rate:.1f} messages per minute"
            }
        return {"detected": False}
    
    # Other pattern check methods...
```

### 3. Sentiment Analysis

#### Overview
Analyze chat sentiment to gauge audience reaction and mood.

#### Implementation
```python
from nltk.sentiment.vader import SentimentIntensityAnalyzer

class ChatSentimentAnalyzer:
    def __init__(self):
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        self.message_buffer = []
        self.sentiment_history = []
    
    def add_message(self, message):
        # Calculate sentiment
        sentiment = self.sentiment_analyzer.polarity_scores(message)
        self.message_buffer.append({
            "message": message,
            "sentiment": sentiment["compound"]
        })
        
        # Keep buffer manageable
        if len(self.message_buffer) > 200:
            self.message_buffer = self.message_buffer[-200:]
    
    def get_current_sentiment(self):
        if not self.message_buffer:
            return 0  # Neutral
        
        # Average of last 50 messages
        recent = self.message_buffer[-50:]
        avg_sentiment = sum(m["sentiment"] for m in recent) / len(recent)
        
        # Track history
        self.sentiment_history.append(avg_sentiment)
        if len(self.sentiment_history) > 20:
            self.sentiment_history = self.sentiment_history[-20:]
        
        return avg_sentiment
    
    def get_sentiment_trend(self):
        if len(self.sentiment_history) < 3:
            return "neutral"
        
        current = self.sentiment_history[-1]
        
        if current > 0.5:
            return "very_positive"
        elif current > 0.2:
            return "positive"
        elif current < -0.5:
            return "very_negative"
        elif current < -0.2:
            return "negative"
        else:
            return "neutral"
    
    def sentiment_change_detected(self):
        if len(self.sentiment_history) < 5:
            return False
        
        # Average of previous 4 sentiment values
        prev_avg = sum(self.sentiment_history[-5:-1]) / 4
        current = self.sentiment_history[-1]
        
        # Check for significant change
        return abs(current - prev_avg) > 0.3
```

### 4. Correlation Analysis

#### Overview
Identify relationships between different metrics and outcomes.

#### Implementation
```python
class CorrelationAnalyzer:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def find_correlations(self, channel_id):
        # Query for multiple metrics
        query = """
        SELECT 
            s.category_name,
            s.title,
            s.avg_viewers,
            s.duration_minutes,
            s.started_at_hour,
            s.started_at_day_of_week,
            c.messages_per_minute,
            c.emote_percentage,
            c.sentiment_score,
            e.new_followers,
            e.new_subscribers
        FROM 
            stream_stats s
            JOIN chat_stats c ON s.stream_id = c.stream_id
            JOIN engagement_stats e ON s.stream_id = e.stream_id
        WHERE s.channel_id = ?
        ORDER BY s.started_at DESC
        LIMIT 100;
        """
        
        results = await self.db.execute_query(query, (channel_id,))
        if not results:
            return {}
        
        # Analyze correlations
        correlations = {}
        
        # Convert to pandas DataFrame for analysis
        import pandas as pd
        import numpy as np
        
        df = pd.DataFrame(results)
        
        # Calculate correlation matrix
        corr_matrix = df.corr(method='pearson')
        
        # Extract key correlations
        viewer_correlations = corr_matrix['avg_viewers'].sort_values(ascending=False)
        follower_correlations = corr_matrix['new_followers'].sort_values(ascending=False)
        sub_correlations = corr_matrix['new_subscribers'].sort_values(ascending=False)
        
        # Find categorical correlations
        category_impact = df.groupby('category_name')['avg_viewers'].mean().sort_values(ascending=False)
        day_impact = df.groupby('started_at_day_of_week')['avg_viewers'].mean().sort_values(ascending=False)
        hour_impact = df.groupby('started_at_hour')['avg_viewers'].mean().sort_values(ascending=False)
        
        return {
            "viewer_correlations": viewer_correlations.to_dict(),
            "follower_correlations": follower_correlations.to_dict(),
            "sub_correlations": sub_correlations.to_dict(),
            "category_impact": category_impact.to_dict(),
            "best_days": day_impact.to_dict(),
            "best_hours": hour_impact.to_dict()
        }
```

## Recommendation Engine

### 1. Immediate Suggestions

#### Overview
Real-time recommendations based on current stream state.

#### Implementation
```python
class ImmediateRecommendationEngine:
    def __init__(self):
        self.recommendation_rules = [
            self._check_audio_levels,
            self._check_viewer_retention,
            self._check_chat_engagement,
            self._check_stream_quality,
            # More rules...
        ]
    
    def generate_recommendations(self, context):
        recommendations = []
        
        for rule in self.recommendation_rules:
            result = rule(context)
            if result:
                recommendations.append(result)
        
        return recommendations
    
    def _check_audio_levels(self, context):
        audio_levels = context.get("audio_levels", {})
        
        # Check for mic audio being too low
        mic_level = audio_levels.get("Mic/Aux", -100)
        if mic_level < -30:  # Very quiet
            return {
                "type": "audio_issue",
                "priority": "high",
                "message": "Your microphone volume is very low. Consider increasing it.",
                "suggested_action": {
                    "service": "obs",
                    "method": "SetInputVolume",
                    "params": {
                        "inputName": "Mic/Aux",
                        "inputVolumeDb": -20
                    }
                }
            }
        
        # Check for desktop audio being too high
        desktop_level = audio_levels.get("Desktop Audio", -100)
        if desktop_level > -10:  # Very loud
            return {
                "type": "audio_issue",
                "priority": "medium",
                "message": "Your game/desktop audio is very loud and might be drowning out your voice.",
                "suggested_action": {
                    "service": "obs",
                    "method": "SetInputVolume",
                    "params": {
                        "inputName": "Desktop Audio",
                        "inputVolumeDb": -20
                    }
                }
            }
        
        return None
    
    def _check_viewer_retention(self, context):
        # Get viewer metrics
        current_viewers = context.get("current_viewers", 0)
        viewer_history = context.get("viewer_history", [])
        
        if len(viewer_history) < 3:
            return None
        
        # Check for declining viewers
        if viewer_history[-1] < viewer_history[-3] * 0.7:  # 30% drop
            # Get recent chat sentiment
            sentiment = context.get("chat_sentiment", 0)
            
            if sentiment < -0.2:  # Negative sentiment
                return {
                    "type": "engagement_issue",
                    "priority": "high",
                    "message": "You're losing viewers and chat seems negative. Consider addressing concerns or switching activities."
                }
            else:
                return {
                    "type": "engagement_issue",
                    "priority": "medium",
                    "message": "Viewer count is declining. Consider increasing interaction with chat or trying something new."
                }
        
        return None
    
    # More recommendation rules...
```

### 2. Strategic Recommendations

#### Overview
Longer-term suggestions based on historical performance.

#### Implementation
```python
class StrategicRecommendationEngine:
    def __init__(self, db_connection):
        self.db = db_connection
        self.correlation_analyzer = CorrelationAnalyzer(db_connection)
    
    async def generate_recommendations(self, channel_id):
        # Get correlations
        correlations = await self.correlation_analyzer.find_correlations(channel_id)
        
        # Get recent stream history
        history_query = """SELECT * FROM stream_stats WHERE channel_id = ? ORDER BY started_at DESC LIMIT 20;"""
        stream_history = await self.db.execute_query(history_query, (channel_id,))
        
        recommendations = []
        
        # Recommend optimal schedule
        best_days = correlations.get("best_days", {})
        best_hours = correlations.get("best_hours", {})
        
        if best_days and best_hours:
            top_days = [day for day, _ in sorted(best_days.items(), key=lambda x: x[1], reverse=True)[:3]]
            top_hours = [hour for hour, _ in sorted(best_hours.items(), key=lambda x: x[1], reverse=True)[:3]]
            
            recommendations.append({
                "type": "schedule_optimization",
                "priority": "medium",
                "message": f"Your streams perform best on {', '.join(top_days)} between {min(top_hours)}:00-{max(top_hours)}:00."
            })
        
        # Recommend content types
        category_impact = correlations.get("category_impact", {})
        if category_impact:
            top_categories = list(category_impact.items())[:3]
            bottom_categories = list(category_impact.items())[-3:]
            
            if top_categories:
                recommendations.append({
                    "type": "content_suggestion",
                    "priority": "high",
                    "message": f"Your highest performing categories are {', '.join([c[0] for c in top_categories])}"
                })
            
            if bottom_categories and len(bottom_categories) > 3:  # Only if we have enough data
                recommendations.append({
                    "type": "content_warning",
                    "priority": "low",
                    "message": f"Your lowest performing categories are {', '.join([c[0] for c in bottom_categories])}"
                })
        
        # Identify engagement factors
        follower_correlations = correlations.get("follower_correlations", {})
        if "messages_per_minute" in follower_correlations and follower_correlations["messages_per_minute"] > 0.5:
            recommendations.append({
                "type": "engagement_tip",
                "priority": "medium",
                "message": "Higher chat engagement strongly correlates with new followers. Consider activities that encourage more chat participation."
            })
        
        # Growth strategies
        avg_stream_duration = sum(s["duration_minutes"] for s in stream_history) / len(stream_history) if stream_history else 0
        
        if avg_stream_duration < 120:  # Less than 2 hours
            recommendations.append({
                "type": "growth_strategy",
                "priority": "medium",
                "message": "Your streams are relatively short. Longer streams often lead to more discovery and viewer growth."
            })
        
        return recommendations
```

### 3. Content Suggestions

#### Overview
Ideas for stream content based on trends and viewer engagement.

#### Implementation
```python
class ContentSuggestionEngine:
    def __init__(self, twitch_client):
        self.twitch_client = twitch_client
        self.last_poll_time = datetime.now() - timedelta(hours=1)  # Initialize to trigger first update
        self.trending_categories = []
        self.recent_suggestions = []  # Track to avoid repeats
    
    async def update_trending_categories(self):
        # Only update every 30 minutes
        if datetime.now() - self.last_poll_time < timedelta(minutes=30):
            return
        
        # Get top games on Twitch
        top_games = await self.twitch_client.get_top_games(first=20)
        self.trending_categories = [{
            "id": game.id,
            "name": game.name,
            "viewer_count": game.viewer_count if hasattr(game, 'viewer_count') else 0
        } for game in top_games.data]
        
        self.last_poll_time = datetime.now()
    
    async def generate_content_suggestions(self, context):
        await self.update_trending_categories()
        
        # Current stream context
        current_category = context.get("category_name")
        stream_duration = context.get("stream_duration_minutes", 0)
        viewer_trend = context.get("viewer_trend", "stable")
        chat_sentiment = context.get("chat_sentiment", 0)
        chat_questions = context.get("recent_chat_questions", [])
        
        suggestions = []
        
        # Category suggestions based on trends
        if viewer_trend in ["falling", "falling_rapidly"] and stream_duration > 60:
            # Find related trending categories
            current_category_tags = context.get("category_tags", [])
            related_trending = []
            
            for category in self.trending_categories[:10]:  # Top 10 trending
                if category["name"] != current_category:  # Don't suggest current category
                    # Get category tags (would need to implement this lookup)
                    category_tags = await self.get_category_tags(category["id"])
                    # Check for tag overlap
                    if any(tag in current_category_tags for tag in category_tags):
                        related_trending.append(category)
            
            if related_trending:
                # Suggest top related trending game
                suggestions.append({
                    "type": "category_switch",
                    "priority": "medium",
                    "message": f"Viewer count is declining. Consider switching to {related_trending[0]['name']}, which is trending and similar to your current content.",
                    "metadata": {
                        "suggested_category": related_trending[0]["name"],
                        "category_id": related_trending[0]["id"]
                    }
                })
        
        # Content ideas based on chat
        if chat_questions:
            # Find recurring themes in questions
            common_words = self.extract_common_themes(chat_questions)
            if common_words:
                suggestions.append({
                    "type": "content_focus",
                    "priority": "low",
                    "message": f"Chat seems interested in {', '.join(common_words[:3])}. Consider focusing on this aspect of your stream."
                })
        
        # Activity suggestions based on stream duration
        if stream_duration > 150 and chat_sentiment < 0:  # Over 2.5 hours and negative sentiment
            suggestions.append({
                "type": "engagement_activity",
                "priority": "high",
                "message": "Stream has been running a while and chat mood is declining. Consider a brief high-engagement activity like a poll, prediction, or viewer interaction."
            })
        
        # Filter out recently suggested items
        filtered_suggestions = [s for s in suggestions if s["message"] not in self.recent_suggestions]
        
        # Update recent suggestions
        for suggestion in filtered_suggestions:
            self.recent_suggestions.append(suggestion["message"])
            if len(self.recent_suggestions) > 20:
                self.recent_suggestions = self.recent_suggestions[-20:]
        
        return filtered_suggestions
    
    def extract_common_themes(self, questions):
        # Simple implementation - in reality would use NLP
        all_words = []
        for question in questions:
            words = question.lower().split()
            all_words.extend(words)
        
        # Count frequencies
        from collections import Counter
        word_counts = Counter(all_words)
        
        # Filter common words and stopwords
        stopwords = ["what", "why", "how", "when", "is", "are", "do", "does", "the", "a", "an", "in", "on", "at"]
        filtered_words = [word for word, count in word_counts.most_common(10) 
                        if word not in stopwords and len(word) > 3]
        
        return filtered_words[:5]  # Top 5 meaningful words
    
    async def get_category_tags(self, category_id):
        # Would implement API call to get category tags
        # Simplified example
        return ["action", "adventure", "multiplayer"]
```

## Architecture Integration

The context analyzer will be integrated with the rest of our system as follows:

### 1. Data Collection Layer

- **ComponentCollectors**: Individual collectors for each data source
- **DataAggregator**: Central service that coordinates data collection
- **MetricStorage**: Temporary and long-term storage of metrics

### 2. Analysis Layer

- **RealTimeAnalyzer**: Processes current metrics for immediate insights
- **HistoricalAnalyzer**: Analyzes performance over time
- **PatternMatcher**: Identifies known patterns and situations

### 3. Recommendation Layer

- **SuggestionEngine**: Generates actionable recommendations
- **AlertGenerator**: Creates alerts for critical issues
- **InsightFormatter**: Formats insights for presentation

### 4. Integration with MCP

- Expose insights and recommendations through MCP tools
- Allow triggering of data collection and analysis
- Present formatted recommendations in natural language

## Implementation Plan

### Phase 1: Core Data Collection

1. Implement Twitch API metrics collection
2. Create OBS WebSocket data collector
3. Develop basic chat message processor
4. Build metric storage system

### Phase 2: Basic Analysis

1. Create simple trending detection
2. Implement chat sentiment analysis
3. Build viewer retention analysis
4. Set up stream quality monitoring

### Phase 3: Recommendations

1. Develop technical issue detection and recommendations
2. Implement engagement suggestions
3. Create content recommendation engine
4. Build scheduling optimization

### Phase 4: Advanced Features

1. Implement historical correlation analysis
2. Create streamer-specific learning models
3. Develop advanced NLP for chat analysis
4. Build predictive viewer models