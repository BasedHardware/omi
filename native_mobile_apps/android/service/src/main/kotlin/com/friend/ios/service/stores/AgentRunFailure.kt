package com.friend.ios.service.stores

import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.ChatStreamEvent
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/**
 * Port of `AgentRunFailure.swift`: why an agent run stopped, as a short code the app words in
 * plain language (`AgentWording`). The code is what the run state and the workstream carry
 * (`failedSummary [code]`), so another device words it the same way.
 */
enum class RunFailure(val rawValue: String) {
    /** The plan's chat allowance is used up. */
    QuotaExceeded("quota_exceeded"),
    /** The answer took longer than the backend allows. */
    Timeout("timeout"),
    /** The agent went round in circles (the safety guard's tool-call, loop or context limits). */
    ToolLoop("tool_loop"),
    /** The backend failed. */
    ServerError("server_error"),
    /** The phone had no connection. */
    Offline("offline"),
    /** No progress for a long time and no live stream: the run died with the app. */
    Stopped("stopped"),
    /** The stream ended without an answer. */
    NoAnswer("no_answer"),
    /** The model declined the request (retrying the same thing would be declined again). */
    Refused("refused"),
    /** The task needs an app that is not connected (calendar, mail ...). */
    NotConnected("not_connected"),
    /** Anything else (also what older runs recorded). */
    CouldNotFinish("could_not_finish");

    /** Worth trying again as it is (not a used-up plan, not a refusal). */
    val canRetry: Boolean get() = this != QuotaExceeded && this != Refused

    /** The event summary that records this failure. */
    val eventSummary: String get() = "${AgentStore.FAILED_SUMMARY} [$rawValue]"

    companion object {
        /** The agent's other fixed answers (`agentic.py` `AGENT_REFUSAL_MESSAGE`, `AGENT_EMPTY_ANSWER_MESSAGE`). */
        const val REFUSAL_TEXT = "I can't help with that one. Try asking me something else."
        const val EMPTY_ANSWER_TEXT = "I wasn't able to put a response together for that. Please try again."

        fun from(rawValue: String): RunFailure? = entries.firstOrNull { it.rawValue == rawValue }

        /** A typed `error:` code (`X-Omi-Chat-Failure-Protocol`) or a plain-text `error:` frame. */
        fun fromStreamError(text: String): RunFailure = when (text.trim()) {
            "quota_exceeded" -> QuotaExceeded
            "timeout", "idle_timeout", "setup_timeout" -> Timeout
            "server_error" -> ServerError
            "offline" -> Offline
            else -> fromAnswer(text) ?: if (mentionsMissingConnection(text)) NotConnected else CouldNotFinish
        }

        /**
         * The canned texts the agent streams as an answer (`ChatStreamEvent.serviceFailureTexts`),
         * alone or appended to what it wrote so far; null for a real answer.
         */
        fun fromAnswer(text: String): RunFailure? {
            val trimmed = text.trim()
            if (trimmed.endsWith(REFUSAL_TEXT)) return Refused
            if (trimmed.endsWith(EMPTY_ANSWER_TEXT)) return NoAnswer
            val index = ChatStreamEvent.serviceFailureTexts.indexOfFirst { trimmed.endsWith(it) }
            if (index < 0) return null
            return when (index) {
                0, 1 -> ServerError
                2 -> Timeout
                else -> ToolLoop
            }
        }

        /** A thrown stream or request error. */
        fun fromError(error: Throwable): RunFailure = when (error) {
            is SocketTimeoutException -> Timeout
            is UnknownHostException, is ConnectException -> Offline
            is APIError.Http -> when {
                error.status == 402 -> QuotaExceeded
                error.status >= 500 -> ServerError
                else -> CouldNotFinish
            }
            is APIError.Transport -> Offline
            else -> CouldNotFinish
        }

        /**
         * Reads the code back from a workstream event (`"<failedSummary> [timeout]"`); the bare
         * marker older runs wrote reads as `CouldNotFinish`. Null for other events.
         */
        fun fromEvent(event: String): RunFailure? {
            val summary = event.trim()
            if (!summary.startsWith(AgentStore.FAILED_SUMMARY)) return null
            val rest = summary.removePrefix(AgentStore.FAILED_SUMMARY).trim { it == ' ' || it == '[' || it == ']' || it.isWhitespace() }
            return from(rest) ?: CouldNotFinish
        }

        private fun mentionsMissingConnection(text: String): Boolean {
            val lowered = text.lowercase()
            return listOf("not connected", "isn't connected", "aren't connected", "no integration", "connect your").any { lowered.contains(it) }
        }
    }
}
