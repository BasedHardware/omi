#!/usr/bin/env python3
"""
Debug script for audio clicking and time slippage issues.
This script helps identify and test audio buffering problems.
"""

import asyncio
import time
import struct
import json
import logging
from collections import deque
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AudioDebugger:
    def __init__(self):
        self.packet_timestamps = deque()
        self.packet_sizes = deque()
        self.sequence_numbers = deque()
        self.overflow_events = []
        self.corruption_events = []
        self.start_time = time.time()
        
    def log_packet_received(self, packet_size: int, sequence_number: int = None):
        """Log when a packet is received"""
        current_time = time.time()
        self.packet_timestamps.append(current_time)
        self.packet_sizes.append(packet_size)
        if sequence_number is not None:
            self.sequence_numbers.append(sequence_number)
            
    def log_overflow_event(self, buffer_size: int, max_size: int):
        """Log buffer overflow events"""
        self.overflow_events.append({
            'timestamp': time.time(),
            'buffer_size': buffer_size,
            'max_size': max_size
        })
        logger.warning(f"Buffer overflow detected: {buffer_size}/{max_size} bytes")
        
    def log_corruption_event(self, frame_index: int, error: str):
        """Log Opus frame corruption events"""
        self.corruption_events.append({
            'timestamp': time.time(),
            'frame_index': frame_index,
            'error': error
        })
        logger.warning(f"Frame corruption at index {frame_index}: {error}")
        
    def analyze_timing(self) -> Dict[str, Any]:
        """Analyze timing patterns to detect slippage"""
        if len(self.packet_timestamps) < 2:
            return {'error': 'Not enough data for analysis'}
            
        intervals = []
        for i in range(1, len(self.packet_timestamps)):
            interval = self.packet_timestamps[i] - self.packet_timestamps[i-1]
            intervals.append(interval)
            
        avg_interval = sum(intervals) / len(intervals)
        max_interval = max(intervals)
        min_interval = min(intervals)
        
        # Detect potential time slippage (intervals much larger than expected)
        expected_interval = 0.02  # 20ms for typical audio frames
        slippage_threshold = expected_interval * 3  # 3x expected interval
        
        slippage_events = [i for i in intervals if i > slippage_threshold]
        
        return {
            'total_packets': len(self.packet_timestamps),
            'avg_interval_ms': avg_interval * 1000,
            'max_interval_ms': max_interval * 1000,
            'min_interval_ms': min_interval * 1000,
            'slippage_events': len(slippage_events),
            'overflow_events': len(self.overflow_events),
            'corruption_events': len(self.corruption_events),
            'total_duration_seconds': time.time() - self.start_time
        }
        
    def generate_report(self) -> str:
        """Generate a comprehensive debug report"""
        analysis = self.analyze_timing()
        
        report = f"""
=== Audio Debug Report ===
Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {analysis.get('total_duration_seconds', 0):.2f} seconds

Packet Statistics:
- Total packets: {analysis.get('total_packets', 0)}
- Average interval: {analysis.get('avg_interval_ms', 0):.2f} ms
- Max interval: {analysis.get('max_interval_ms', 0):.2f} ms
- Min interval: {analysis.get('min_interval_ms', 0):.2f} ms

Issues Detected:
- Time slippage events: {analysis.get('slippage_events', 0)}
- Buffer overflow events: {analysis.get('overflow_events', 0)}
- Frame corruption events: {analysis.get('corruption_events', 0)}

Recommendations:
"""
        
        if analysis.get('slippage_events', 0) > 0:
            report += "- Time slippage detected: Consider reducing buffer sizes or improving connection stability\n"
            
        if analysis.get('overflow_events', 0) > 0:
            report += "- Buffer overflow detected: Increase buffer sizes or implement better overflow handling\n"
            
        if analysis.get('corruption_events', 0) > 0:
            report += "- Frame corruption detected: Check Bluetooth connection quality and packet loss\n"
            
        if analysis.get('slippage_events', 0) == 0 and analysis.get('overflow_events', 0) == 0:
            report += "- No major issues detected in this session\n"
            
        return report

class MockAudioBuffer:
    """Mock audio buffer for testing"""
    def __init__(self, max_size: int = 1024 * 1024):
        self.max_size = max_size
        self.buffer = bytearray()
        self.debugger = AudioDebugger()
        
    def add_data(self, data: bytes) -> bool:
        """Add data to buffer with overflow detection"""
        if len(self.buffer) + len(data) > self.max_size:
            self.debugger.log_overflow_event(len(self.buffer), self.max_size)
            # Remove oldest data to make space
            overflow_amount = len(self.buffer) + len(data) - self.max_size
            if overflow_amount < len(self.buffer):
                self.buffer = self.buffer[overflow_amount:]
            else:
                self.buffer.clear()
                
        self.buffer.extend(data)
        self.debugger.log_packet_received(len(data))
        return True
        
    def get_data(self, max_bytes: int) -> bytes:
        """Get data from buffer"""
        if len(self.buffer) == 0:
            return b''
            
        data_to_return = self.buffer[:max_bytes]
        self.buffer = self.buffer[max_bytes:]
        return data_to_return
        
    def get_debugger(self) -> AudioDebugger:
        return self.debugger

async def simulate_audio_stream():
    """Simulate an audio stream to test buffering"""
    buffer = MockAudioBuffer(max_size=1024 * 100)  # 100KB buffer
    sample_rate = 8000
    frame_size = 160  # 20ms at 8kHz
    
    # Simulate normal audio flow
    for i in range(100):
        # Simulate 20ms of audio data
        audio_data = b'\x00' * frame_size * 2  # 16-bit samples
        success = buffer.add_data(audio_data)
        
        if not success:
            logger.error(f"Failed to add audio data at frame {i}")
            
        await asyncio.sleep(0.02)  # 20ms
        
    # Simulate burst of data (like network congestion)
    logger.info("Simulating network burst...")
    for i in range(10):
        audio_data = b'\x00' * frame_size * 2 * 5  # 5 frames at once
        success = buffer.add_data(audio_data)
        await asyncio.sleep(0.01)  # 10ms
        
    # Generate report
    debugger = buffer.get_debugger()
    report = debugger.generate_report()
    print(report)

if __name__ == "__main__":
    asyncio.run(simulate_audio_stream()) 