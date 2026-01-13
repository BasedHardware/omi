"""
Safety guards for agentic chat system.

Prevents infinite loops, context overflow, and excessive tool usage.
"""

from typing import Dict, List, Tuple, Optional
import time


class SafetyGuardError(Exception):
    """Raised when a safety limit is exceeded."""

    pass


class AgentSafetyGuard:
    """
    Safety guard for ReAct agents to prevent:
    - Tool call loops (repeated calls with same parameters)
    - Excessive tool calls (max 25 per query)
    - Context overflow (max 500K tokens)
    - Suspicious parameter patterns
    """

    def __init__(self, max_tool_calls: int = 25, max_context_tokens: int = 500000):
        self.max_tool_calls = max_tool_calls
        self.max_context_tokens = max_context_tokens

        # Tracking
        self.tool_call_count = 0
        self.tool_call_history: List[Tuple[str, Dict, float]] = []  # (tool_name, params, timestamp)
        self.estimated_tokens = 0
        self.start_time = time.time()

        # Loop detection window (check last N calls)
        self.loop_detection_window = 3

    def validate_tool_call(self, tool_name: str, params: Dict) -> None:
        """
        Validate a tool call before execution.

        Args:
            tool_name: Name of the tool being called
            params: Parameters for the tool call

        Raises:
            SafetyGuardError: If any safety limit is exceeded
        """
        # Check tool call limit
        if self.tool_call_count >= self.max_tool_calls:
            raise SafetyGuardError(
                "I'm having trouble finding all the information you need. "
                "Could you try asking a simpler question or breaking this into separate questions?"
            )

        # Check for tool call loops
        if self._is_loop_detected(tool_name, params):
            raise SafetyGuardError(
                "I seem to be stuck trying to answer your question. " "Could you rephrase it in a different way?"
            )

        # Record the call
        self.tool_call_count += 1
        self.tool_call_history.append((tool_name, params, time.time()))

        print(f"🛡️ Safety Guard: Tool call {self.tool_call_count}/{self.max_tool_calls} - {tool_name}")

    def estimate_response_tokens(self, response: str) -> int:
        """
        Estimate token count for a response.
        Uses rough heuristic: ~4 characters per token for English text.

        Args:
            response: The response text

        Returns:
            Estimated token count
        """
        # Rough estimate: 1 token ≈ 4 characters
        return len(response) // 4

    def check_context_size(self, new_data: str) -> None:
        """
        Check if adding new data would exceed context limit.

        Args:
            new_data: The new data being added to context

        Raises:
            SafetyGuardError: If context limit would be exceeded
        """
        new_tokens = self.estimate_response_tokens(new_data)
        total_tokens = self.estimated_tokens + new_tokens

        if total_tokens > self.max_context_tokens:
            raise SafetyGuardError(
                "That's a lot of information to process at once! "
                "Could you narrow down your request? Try asking about a smaller time period or being more specific about what you're looking for."
            )

        self.estimated_tokens = total_tokens
        print(f"🛡️ Safety Guard: Context size: {self.estimated_tokens}/{self.max_context_tokens} tokens (+{new_tokens})")

    def _is_loop_detected(self, tool_name: str, params: Dict) -> bool:
        """
        Detect if the same tool is being called repeatedly with similar parameters.

        Args:
            tool_name: Name of the tool
            params: Tool parameters

        Returns:
            True if a loop is detected
        """
        if len(self.tool_call_history) < self.loop_detection_window:
            return False

        # Check last N calls
        recent_calls = self.tool_call_history[-self.loop_detection_window :]

        # Count how many times this exact tool+params combination appears
        similar_count = 0
        for past_tool, past_params, _ in recent_calls:
            if past_tool == tool_name and self._params_similar(params, past_params):
                similar_count += 1

        # If more than half of recent calls are the same tool with similar params, it's likely a loop
        return similar_count >= (self.loop_detection_window // 2 + 1)

    def _params_similar(self, params1: Dict, params2: Dict, threshold: float = 0.8) -> bool:
        """
        Check if two parameter sets are similar (for loop detection).

        Args:
            params1: First parameter set
            params2: Second parameter set
            threshold: Similarity threshold (0-1)

        Returns:
            True if parameters are similar
        """
        # Get keys from both dicts
        all_keys = set(params1.keys()) | set(params2.keys())
        if not all_keys:
            return True

        # Count matching values
        matching = 0
        for key in all_keys:
            val1 = params1.get(key)
            val2 = params2.get(key)

            # Consider None and missing keys as equivalent
            if val1 is None and val2 is None:
                matching += 1
            elif val1 == val2:
                matching += 1

        # Calculate similarity ratio
        similarity = matching / len(all_keys)
        return similarity >= threshold

    def get_stats(self) -> Dict:
        """
        Get statistics about the current session.

        Returns:
            Dictionary with session statistics
        """
        elapsed = time.time() - self.start_time

        return {
            'tool_calls': self.tool_call_count,
            'max_tool_calls': self.max_tool_calls,
            'estimated_tokens': self.estimated_tokens,
            'max_context_tokens': self.max_context_tokens,
            'elapsed_seconds': elapsed,
            'tools_used': list(set(tool for tool, _, _ in self.tool_call_history)),
        }

    def should_warn_user(self) -> Optional[str]:
        """
        Check if user should be warned about approaching limits.

        Returns:
            Warning message if applicable, None otherwise
        """
        # Warn at 80% of limits
        if self.tool_call_count >= self.max_tool_calls * 0.8:
            print(
                f"🛡️ Safety Guard: Warning - Tool calls at {self.tool_call_count}/{self.max_tool_calls} (80% threshold)"
            )
            return "⚠️ I'm processing a lot of information. Your response might take a moment..."

        if self.estimated_tokens >= self.max_context_tokens * 0.8:
            print(
                f"🛡️ Safety Guard: Warning - Context size at {self.estimated_tokens}/{self.max_context_tokens} tokens (80% threshold)"
            )
            return "⚠️ Processing a large amount of data. Almost done..."

        return None
