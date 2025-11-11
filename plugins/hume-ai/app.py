"""
Helper functions and services for Omi Audio Emotion Analysis
Includes: Audio processing, Hume AI integration, Omi notifications, etc.
"""

import os
import json
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from hume import AsyncHumeClient
from hume.expression_measurement.stream import StreamLanguage
from hume.expression_measurement.stream.stream.types import Config


# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

# Emotion categories for Rizz Meter
POSITIVE_EMOTIONS = {
    "Joy", "Amusement", "Satisfaction", "Excitement", "Pride", "Triumph",
    "Relief", "Romance", "Desire", "Admiration", "Adoration", "Love",
    "Calmness", "Contentment", "Realization", "Interest"
}

NEGATIVE_EMOTIONS = {
    "Anger", "Sadness", "Fear", "Disgust", "Anxiety", "Distress",
    "Shame", "Guilt", "Embarrassment", "Contempt", "Boredom",
    "Confusion", "Disappointment", "Awkwardness"
}

# Store recent audio processing stats
audio_stats = {
    "total_requests": 0,
    "successful_analyses": 0,
    "failed_analyses": 0,
    "last_request_time": None,
    "last_uid": None,
    "recent_emotions": [],
    "emotion_counts": {},
    "rizz_score": 75,
    "recent_notifications": [],
    "last_notification_time": None
}

# Notification cooldown in seconds (configurable)
NOTIFICATION_COOLDOWN_SECONDS = 30


def can_send_notification() -> bool:
    """Check if enough time has passed since last notification"""
    if audio_stats["last_notification_time"] is None:
        return True

    time_since_last = (datetime.utcnow() - audio_stats["last_notification_time"]).total_seconds()
    return time_since_last >= NOTIFICATION_COOLDOWN_SECONDS


def update_notification_time():
    """Update the last notification timestamp"""
    audio_stats["last_notification_time"] = datetime.utcnow()


# Load emotion configuration
def load_emotion_config():
    """Load emotion notification configuration from file or environment variable"""
    # Try environment variable first
    env_config = os.getenv('EMOTION_NOTIFICATION_CONFIG')
    if env_config:
        try:
            config = json.loads(env_config)
            print(f"✓ Loaded emotion config from environment variable")
            return config
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid EMOTION_NOTIFICATION_CONFIG JSON: {e}")

    # Fall back to config file
    config_file = Path("emotion_config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
            print(f"✓ Loaded emotion config from {config_file}")
            return config

    # Default configuration
    default_config = {
        "notification_enabled": True,
        "emotion_thresholds": {},
        "notification_message_template": "🎭 Emotion Alert: Detected {emotions}"
    }
    print(f"ℹ️ Using default emotion config")
    return default_config

EMOTION_CONFIG = load_emotion_config()


# ============================================================================
# RIZZ METER FUNCTIONS
# ============================================================================

def update_rizz_score(emotions: list):
    """Update rizz score based on detected emotions"""
    global audio_stats

    positive_count = sum(1 for e in emotions if e.get('name') in POSITIVE_EMOTIONS)
    negative_count = sum(1 for e in emotions if e.get('name') in NEGATIVE_EMOTIONS)

    # Adjust score
    score_change = (positive_count * 2) - (negative_count * 3)
    audio_stats["rizz_score"] = max(0, min(100, audio_stats["rizz_score"] + score_change))


def get_rizz_status_text(score: float) -> str:
    """Get rizz meter status text based on score"""
    if score >= 90:
        return "🔥 LEGENDARY RIZZ"
    elif score >= 75:
        return "💯 PEAK PERFORMANCE"
    elif score >= 60:
        return "✨ SMOOTH OPERATOR"
    elif score >= 40:
        return "📈 BUILDING MOMENTUM"
    elif score >= 25:
        return "📉 NEEDS WORK"
    else:
        return "❄️ RIZZ FROZEN"


def get_rizz_notification_message(score: float, emotions: list) -> str:
    """Generate notification message for rizz score update"""
    status = get_rizz_status_text(score)
    emotion_names = [e.get('name') for e in emotions[:3]]
    return f"Rizz {score:.0f}% - {status}, emotion: {', '.join(emotion_names)}"


# ============================================================================
# AUDIO PROCESSING FUNCTIONS
# ============================================================================

def create_wav_header(sample_rate: int, data_size: int) -> bytes:
    """Create a WAV header for raw PCM audio data"""
    import struct

    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8

    header = bytearray()
    header.extend(b'RIFF')
    header.extend(struct.pack('<I', 36 + data_size))
    header.extend(b'WAVE')
    header.extend(b'fmt ')
    header.extend(struct.pack('<I', 16))
    header.extend(struct.pack('<H', 1))
    header.extend(struct.pack('<H', num_channels))
    header.extend(struct.pack('<I', sample_rate))
    header.extend(struct.pack('<I', byte_rate))
    header.extend(struct.pack('<H', block_align))
    header.extend(struct.pack('<H', bits_per_sample))
    header.extend(b'data')
    header.extend(struct.pack('<I', data_size))

    return bytes(header)


async def cleanup_old_audio_files():
    """Background task to clean up old audio files every minute"""
    import asyncio

    while True:
        try:
            await asyncio.sleep(60)

            audio_dir = Path("audio_files")
            if not audio_dir.exists():
                continue

            current_time = datetime.now()
            deleted_count = 0

            for audio_file in audio_dir.glob("*.wav"):
                try:
                    file_age = current_time - datetime.fromtimestamp(audio_file.stat().st_mtime)

                    if file_age.total_seconds() > 300:
                        audio_file.unlink()
                        deleted_count += 1

                except Exception as e:
                    print(f"Error deleting {audio_file}: {e}")

            if deleted_count > 0:
                print(f"🗑️ Cleaned up {deleted_count} old audio files")

        except Exception as e:
            print(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)


# ============================================================================
# OMI INTEGRATION FUNCTIONS
# ============================================================================

async def send_omi_notification(
    uid: str,
    message: str,
    app_id: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Send notification to Omi mobile app"""
    import httpx
    from urllib.parse import quote

    app_id = app_id or os.getenv('OMI_APP_ID')
    api_key = api_key or os.getenv('OMI_API_KEY')

    if not app_id or not api_key:
        return {
            "success": False,
            "error": "OMI_APP_ID or OMI_API_KEY not configured"
        }

    try:
        url = f"https://api.omi.me/v2/integrations/{app_id}/notification?uid={quote(uid)}&message={quote(message)}"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Content-Length": "0"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, timeout=30.0)

        if response.status_code >= 200 and response.status_code < 300:
            print(f"✓ Sent Omi notification to user {uid}: {message}")
            return {"success": True, "message": message}
        else:
            error_msg = f"Omi API error: {response.status_code} - {response.text}"
            print(f"✗ {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Failed to send Omi notification: {str(e)}"
        print(f"✗ {error_msg}")
        return {"success": False, "error": error_msg}


async def create_omi_memory(
    uid: str,
    text: str,
    emotions: Optional[List[Dict[str, Any]]] = None,
    app_id: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Create a memory in Omi app"""
    import httpx

    app_id = app_id or os.getenv('OMI_APP_ID')
    api_key = api_key or os.getenv('OMI_API_KEY')

    if not app_id or not api_key:
        return {
            "success": False,
            "error": "OMI_APP_ID or OMI_API_KEY not configured"
        }

    try:
        url = f"https://api.omi.me/v1/integrations/{app_id}/memories?uid={uid}"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "text": text,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        if emotions:
            payload["emotions"] = emotions

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)

        if response.status_code >= 200 and response.status_code < 300:
            print(f"✓ Created Omi memory for user {uid}")
            return {"success": True, "memory": text}
        else:
            error_msg = f"Omi API error: {response.status_code} - {response.text}"
            print(f"✗ {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Failed to create Omi memory: {str(e)}"
        print(f"✗ {error_msg}")
        return {"success": False, "error": error_msg}


def generate_emotion_summary() -> Dict[str, Any]:
    """Generate a summary of emotions for memory"""
    if not audio_stats["emotion_counts"]:
        return {
            "success": False,
            "error": "No emotion data available"
        }

    # Get current date and time
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S UTC")

    # Get top 3 emotions from aggregated stats
    sorted_emotions = sorted(
        audio_stats["emotion_counts"].items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]

    total_count = sum(audio_stats["emotion_counts"].values())

    # Build top 3 emotions list
    top_3_emotions = []
    emotions_list = []

    for emotion, count in sorted_emotions:
        percentage = (count / total_count) * 100
        top_3_emotions.append(f"{emotion} ({percentage:.1f}%)")
        emotions_list.append({"name": emotion, "count": count, "percentage": percentage})

    # Get rizz score and status
    rizz_score = audio_stats.get("rizz_score", 75)
    rizz_status = get_rizz_status_text(rizz_score)

    # Build memory summary
    summary = f"""📅 {date_str} at {time_str}

Top 3 Emotions: {', '.join(top_3_emotions)}

Rizz {rizz_score:.0f}% - {rizz_status}"""

    return {
        "success": True,
        "summary": summary,
        "emotions": emotions_list
    }


async def save_emotion_memory(uid: Optional[str] = None):
    """Save current emotion statistics to Omi memories"""
    target_uid = uid or audio_stats.get("last_uid")

    if not target_uid:
        print("⚠️ No user ID available for emotion memory")
        return {
            "success": False,
            "error": "No user ID available"
        }

    summary = generate_emotion_summary()

    if not summary["success"]:
        print(f"⚠️ Cannot create memory: {summary['error']}")
        return summary

    result = await create_omi_memory(
        uid=target_uid,
        text=summary["summary"],
        emotions=summary["emotions"]
    )

    return result


async def emotion_memory_background_task():
    """Background task that saves emotion summaries every hour"""
    import asyncio

    while True:
        try:
            await asyncio.sleep(3600)

            if audio_stats.get("last_uid") and audio_stats["emotion_counts"]:
                print("💾 Auto-saving emotion memory (hourly task)...")
                result = await save_emotion_memory()

                if result.get("success"):
                    print("✓ Hourly emotion memory saved")
                else:
                    print(f"✗ Failed to save hourly memory: {result.get('error')}")

        except Exception as e:
            print(f"Error in emotion memory background task: {e}")
            await asyncio.sleep(3600)


# ============================================================================
# EMOTION DETECTION FUNCTIONS
# ============================================================================

def check_emotion_triggers(
    predictions: List[Dict[str, Any]],
    emotion_thresholds: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Check if any emotions meet the trigger thresholds"""
    if emotion_thresholds is None:
        emotion_thresholds = EMOTION_CONFIG.get("emotion_thresholds", {})

    triggered_emotions = []

    for pred in predictions:
        top_emotions = pred.get("top_3_emotions", [])

        for emotion in top_emotions:
            emotion_name = emotion.get("name")
            emotion_score = emotion.get("score", 0)

            if not emotion_thresholds:
                triggered_emotions.append({
                    "name": emotion_name,
                    "score": emotion_score
                })
            elif emotion_name in emotion_thresholds:
                threshold = emotion_thresholds[emotion_name]
                if emotion_score >= threshold:
                    triggered_emotions.append({
                        "name": emotion_name,
                        "score": emotion_score,
                        "threshold": threshold
                    })

    return {
        "triggered": len(triggered_emotions) > 0,
        "count": len(triggered_emotions),
        "emotions": triggered_emotions
    }


# ============================================================================
# HUME AI INTEGRATION FUNCTIONS
# ============================================================================

async def analyze_text_with_hume(text: str) -> Dict[str, Any]:
    """Analyze text emotion using Hume AI Language model"""
    hume_api_key = os.getenv('HUME_API_KEY')
    if not hume_api_key:
        return {
            "success": False,
            "error": "HUME_API_KEY not configured",
            "predictions": []
        }

    try:
        print(f"Analyzing text with Hume AI (length: {len(text)} chars)")

        client = AsyncHumeClient(api_key=hume_api_key)
        model_config = Config(language=StreamLanguage())

        async with client.expression_measurement.stream.connect() as socket:
            result = await socket.send_text(text, config=model_config)

            if hasattr(result, 'error'):
                return {
                    "success": False,
                    "error": f"Hume API error: {result.error}",
                    "predictions": []
                }

            predictions = []

            if hasattr(result, 'language') and result.language and result.language.predictions:
                for pred in result.language.predictions:
                    emotions = []
                    if hasattr(pred, 'emotions'):
                        emotions = [
                            {"name": e.name, "score": e.score}
                            for e in sorted(pred.emotions, key=lambda x: x.score, reverse=True)
                        ]

                    predictions.append({
                        "text": pred.text if hasattr(pred, 'text') else text,
                        "emotions": emotions,
                        "top_3_emotions": emotions[:3]
                    })

            print(f"✓ Hume text analysis complete: {len(predictions)} predictions")

            return {
                "success": True,
                "total_predictions": len(predictions),
                "predictions": predictions
            }

    except Exception as e:
        print(f"✗ Hume text analysis failed: {e}")
        import traceback
        traceback.print_exc()

        return {
            "success": False,
            "error": str(e),
            "predictions": []
        }


async def analyze_audio_with_hume(wav_file_path: str) -> Dict[str, Any]:
    """Analyze audio emotion using Hume AI Prosody model with automatic chunking"""
    import wave

    hume_api_key = os.getenv('HUME_API_KEY')
    if not hume_api_key:
        return {
            "success": False,
            "error": "HUME_API_KEY not configured",
            "predictions": []
        }

    try:
        with wave.open(wav_file_path, 'rb') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / float(rate)

        print(f"Audio duration: {duration:.2f} seconds")

        MAX_DURATION = 5.0
        CHUNK_DURATION = 4.5

        if duration <= MAX_DURATION:
            return await _analyze_single_audio(wav_file_path, hume_api_key)

        print(f"Audio exceeds {MAX_DURATION}s limit, chunking into {CHUNK_DURATION}s segments...")

        import wave
        import struct

        with wave.open(wav_file_path, 'rb') as wav_file:
            params = wav_file.getparams()
            frames_per_chunk = int(params.framerate * CHUNK_DURATION)
            total_frames = wav_file.getnframes()

            all_predictions = []
            chunk_index = 0

            while wav_file.tell() < total_frames:
                chunk_frames = wav_file.readframes(frames_per_chunk)

                if not chunk_frames:
                    break

                chunk_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                chunk_path = chunk_file.name
                chunk_file.close()

                try:
                    with wave.open(chunk_path, 'wb') as chunk_wav:
                        chunk_wav.setparams(params)
                        chunk_wav.writeframes(chunk_frames)

                    chunk_result = await _analyze_single_audio(chunk_path, hume_api_key)

                    if chunk_result.get("success"):
                        for pred in chunk_result.get("predictions", []):
                            pred["chunk_index"] = chunk_index
                            all_predictions.append(pred)

                finally:
                    Path(chunk_path).unlink(missing_ok=True)

                chunk_index += 1

            print(f"✓ Analyzed {chunk_index} chunks, {len(all_predictions)} total predictions")

            return {
                "success": True,
                "chunked": True,
                "num_chunks": chunk_index,
                "total_duration_seconds": duration,
                "total_predictions": len(all_predictions),
                "predictions": all_predictions
            }

    except Exception as e:
        print(f"✗ Audio chunking failed: {e}")
        import traceback
        traceback.print_exc()

        return {
            "success": False,
            "error": str(e),
            "predictions": []
        }


async def _analyze_single_audio(wav_file_path: str, hume_api_key: str) -> Dict[str, Any]:
    """Analyze a single audio file (≤5 seconds) with Hume AI"""
    try:
        client = AsyncHumeClient(api_key=hume_api_key)
        model_config = Config(prosody={})

        async with client.expression_measurement.stream.connect() as socket:
            result = await socket.send_file(wav_file_path, config=model_config)

            if hasattr(result, 'error'):
                return {
                    "success": False,
                    "error": f"Hume API error: {result.error}",
                    "predictions": []
                }

            predictions = []

            if hasattr(result, 'prosody') and result.prosody and result.prosody.predictions:
                for pred in result.prosody.predictions:
                    emotions = []
                    if hasattr(pred, 'emotions'):
                        emotions = [
                            {"name": e.name, "score": e.score}
                            for e in sorted(pred.emotions, key=lambda x: x.score, reverse=True)
                        ]

                    time_info = {
                        "begin": pred.time.begin if hasattr(pred, 'time') else 0,
                        "end": pred.time.end if hasattr(pred, 'time') else 0
                    }

                    predictions.append({
                        "time": time_info,
                        "emotions": emotions,
                        "top_3_emotions": emotions[:3]
                    })

            return {
                "success": True,
                "total_predictions": len(predictions),
                "predictions": predictions
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "predictions": []
        }
