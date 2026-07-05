package com.iseelabs.meta_wearables_dat_flutter

import android.os.Handler
import android.os.Looper
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.SpecificDeviceSelector
import com.meta.wearable.dat.core.session.DeviceSession
import com.meta.wearable.dat.core.session.DeviceSessionState
import com.meta.wearable.dat.core.types.DeviceIdentifier
import com.meta.wearable.dat.display.Display
import com.meta.wearable.dat.display.addDisplay
import com.meta.wearable.dat.display.removeDisplay
import com.meta.wearable.dat.display.types.DisplayState
import com.meta.wearable.dat.display.types.VideoCodec
import com.meta.wearable.dat.display.types.VideoPlayerState
import com.meta.wearable.dat.display.types.VideoSource
import com.meta.wearable.dat.display.views.Alignment
import com.meta.wearable.dat.display.views.ButtonStyle
import com.meta.wearable.dat.display.views.ContentScope
import com.meta.wearable.dat.display.views.CornerRadius
import com.meta.wearable.dat.display.views.Direction
import com.meta.wearable.dat.display.views.FlexBoxBackground
import com.meta.wearable.dat.display.views.FlexBoxScope
import com.meta.wearable.dat.display.views.IconName
import com.meta.wearable.dat.display.views.IconStyle
import com.meta.wearable.dat.display.views.ImageSize
import com.meta.wearable.dat.display.views.TextColor
import com.meta.wearable.dat.display.views.TextStyle
import com.meta.wearable.dat.display.views.VideoPlayer
import io.flutter.plugin.common.EventChannel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout

/**
 * Android Display bridge (DAT 0.7.0 `mwdat-display`).
 *
 * Mirrors [MetaDisplayManager] on iOS. Owns:
 *   - One [DeviceSession] targeting a (display-capable) device.
 *   - One [Display] capability attached to that session.
 *   - The display-state EventSink and the display-events EventSink
 *     (tap / click / playback callbacks routed back to Dart by id).
 *
 * Declarative view trees arrive from Dart as plain JSON maps, which we rebuild
 * into Meta's `mwdat-display` component DSL (`flexBox` / `text` / `image` /
 * `button` / `icon` / `video`) inside [Display.sendContent]. Interaction
 * callbacks carry the Dart-assigned `callbackId` so the Dart side can dispatch
 * to the right closure.
 */
internal class MetaDisplayManager {
    private val scope = CoroutineScope(Dispatchers.Main.immediate + SupervisorJob())
    private val mainHandler = Handler(Looper.getMainLooper())

    private var session: DeviceSession? = null
    private var display: Display? = null
    private var displayStateJob: Job? = null
    private var videoStateJob: Job? = null

    /**
     * The `onPlaybackEventId` of the [VideoPlayer] currently on screen, used to
     * route video playback transitions back to the right Dart closure.
     */
    private var currentVideoCallbackId: String? = null

    private var displayStateSink: EventChannel.EventSink? = null
    private var displayEventsSink: EventChannel.EventSink? = null

    fun setDisplayStateSink(sink: EventChannel.EventSink?) {
        displayStateSink = sink
    }

    fun setDisplayEventsSink(sink: EventChannel.EventSink?) {
        displayEventsSink = sink
    }

    // --- Lifecycle ------------------------------------------------------------

    /**
     * Creates a [DeviceSession] (targeting [deviceUuid] when given, otherwise
     * the first paired device), attaches the display capability, and waits for
     * both to reach `STARTED`.
     */
    suspend fun startDisplaySession(deviceUuid: String?) {
        if (display != null) return

        val allIds: List<DeviceIdentifier> = try {
            Wearables.devices.first().toList()
        } catch (_: Throwable) {
            emptyList()
        }
        val target: DeviceIdentifier = when {
            deviceUuid != null ->
                allIds.firstOrNull { it.toString() == deviceUuid }
                    ?: error(
                        "Display session failed: deviceUuid=$deviceUuid is not " +
                            "in the current paired set (paired=${allIds.size}).",
                    )
            allIds.isNotEmpty() -> allIds.first()
            else -> error(
                "No glasses are currently paired. Open Meta AI to pair " +
                    "Ray-Ban Display glasses, then try again.",
            )
        }

        var created: DeviceSession? = null
        var createError: String? = null
        Wearables.createSession(SpecificDeviceSelector(target))
            .fold(
                onSuccess = { created = it },
                onFailure = { error, _ -> createError = error.description },
            )
        val newSession = created
            ?: error("createSession failed: ${createError ?: "unknown"}")
        session = newSession

        newSession.start()
        try {
            withTimeout(SESSION_STARTED_TIMEOUT_MS) {
                newSession.state.first { it == DeviceSessionState.STARTED }
            }
        } catch (t: Throwable) {
            try {
                newSession.stop()
            } catch (_: Throwable) {
                // ignore
            }
            session = null
            throw IllegalStateException(
                "Glasses did not connect in time. Take them out of the case " +
                    "and put them on, then try again.",
                t,
            )
        }

        var attached: Display? = null
        var attachError: String? = null
        newSession.addDisplay()
            .fold(
                onSuccess = { attached = it },
                onFailure = { error, _ -> attachError = error.description },
            )
        val newDisplay = attached
            ?: run {
                try {
                    newSession.stop()
                } catch (_: Throwable) {
                    // ignore
                }
                session = null
                error("addDisplay failed: ${attachError ?: "unknown"}")
            }
        display = newDisplay

        displayStateJob = scope.launch {
            newDisplay.state.collect { state -> postDisplayState(state) }
        }
        try {
            withTimeout(DISPLAY_STARTED_TIMEOUT_MS) {
                newDisplay.state.first { it == DisplayState.STARTED }
            }
        } catch (_: Throwable) {
            // The display state stream keeps flowing; surface whatever state we
            // reach via the display_state channel rather than hard-failing.
        }
    }

    /** Rebuilds [view] into the DSL and sends it to the glasses. */
    suspend fun sendDisplayView(view: Map<String, Any?>) {
        val currentDisplay = display
            ?: error("No display session - call startDisplaySession first")

        if (view["type"] == "videoPlayer") {
            val url = view["uri"] as? String ?: ""
            currentVideoCallbackId = view["onPlaybackEventId"] as? String
            val player = VideoPlayer(
                source = VideoSource.Url(url),
                codec = VideoCodec.MP4,
            )
            var sendError: String? = null
            currentDisplay.sendContent { video(player = player) }
                .fold(
                    onSuccess = {},
                    onFailure = { error, _ -> sendError = error.description },
                )
            if (sendError != null) error("send failed: $sendError")
            videoStateJob?.cancel()
            videoStateJob = scope.launch {
                player.state.collect { state -> onVideoState(state) }
            }
            player.play()
        } else {
            currentVideoCallbackId = null
            var sendError: String? = null
            currentDisplay.sendContent { renderRoot(view) }
                .fold(
                    onSuccess = {},
                    onFailure = { error, _ -> sendError = error.description },
                )
            if (sendError != null) error("send failed: $sendError")
        }
    }

    /** Detaches the display capability and tears down its device session. */
    fun stopDisplaySession() {
        videoStateJob?.cancel(); videoStateJob = null
        displayStateJob?.cancel(); displayStateJob = null
        currentVideoCallbackId = null
        try {
            session?.removeDisplay()
        } catch (_: Throwable) {
            // ignore
        }
        display = null
        try {
            session?.stop()
        } catch (_: Throwable) {
            // ignore
        }
        session = null
    }

    fun dispose() {
        stopDisplaySession()
        scope.cancel()
    }

    // --- Callback plumbing ----------------------------------------------------

    private fun emitCallback(id: String, type: String) {
        mainHandler.post {
            displayEventsSink?.success(
                mapOf("callbackId" to id, "type" to type),
            )
        }
    }

    private fun onVideoState(state: VideoPlayerState) {
        val id = currentVideoCallbackId ?: return
        val event = when (state.name.uppercase()) {
            "PLAYING", "STARTED" -> "playing"
            "PAUSED" -> "paused"
            "ENDED" -> "ended"
            "STOPPED" -> "stopped"
            "ERROR" -> "error"
            else -> "unknown"
        }
        mainHandler.post {
            displayEventsSink?.success(
                mapOf(
                    "callbackId" to id,
                    "type" to "playback",
                    "event" to event,
                ),
            )
        }
    }

    private fun postDisplayState(state: DisplayState) {
        val encoded = when (state.name.uppercase()) {
            "STARTING" -> 0
            "STARTED" -> 1
            "STOPPING" -> 2
            "STOPPED" -> 3
            else -> 3
        }
        mainHandler.post { displayStateSink?.success(encoded) }
    }

    // --- Tree builders --------------------------------------------------------

    private fun ContentScope.renderRoot(node: Map<String, Any?>) {
        if (node["type"] == "flexBox") {
            // The root `ContentScope.flexBox` has no `flexGrow` (it isn't a
            // child of another flex container); only nested boxes do.
            flexBox(
                direction = direction(node["direction"] as? String),
                gap = intOf(node["spacing"]),
                padding = intOf(node["padding"]),
                background = background(node["background"] as? String),
                alignment = alignment(node["alignment"] as? String),
                crossAlignment = alignment(node["crossAlignment"] as? String),
                wrap = (node["wrap"] as? Boolean) ?: false,
                onClick = tapHandler(node["onTapId"] as? String),
            ) {
                renderChildren(node)
            }
        } else {
            flexBox { renderNode(node) }
        }
    }

    private fun FlexBoxScope.renderChildren(node: Map<String, Any?>) {
        @Suppress("UNCHECKED_CAST")
        val kids = node["children"] as? List<Map<String, Any?>> ?: emptyList()
        kids.forEach { renderNode(it) }
    }

    private fun FlexBoxScope.renderNode(node: Map<String, Any?>) {
        when (node["type"]) {
            "flexBox" -> flexBox(
                direction = direction(node["direction"] as? String),
                gap = intOf(node["spacing"]),
                padding = intOf(node["padding"]),
                background = background(node["background"] as? String),
                alignment = alignment(node["alignment"] as? String),
                crossAlignment = alignment(node["crossAlignment"] as? String),
                wrap = (node["wrap"] as? Boolean) ?: false,
                flexGrow = floatOf(node["flexGrow"]),
                onClick = tapHandler(node["onTapId"] as? String),
            ) {
                renderChildren(node)
            }
            "text" -> text(
                node["text"] as? String ?: "",
                style = textStyle(node["style"] as? String),
                color = textColor(node["color"] as? String),
            )
            "image" -> image(
                uri = node["uri"] as? String ?: "",
                sizePreset = imageSize(node["sizePreset"] as? String),
                cornerRadius = cornerRadius(node["cornerRadius"] as? String),
            )
            "button" -> button(
                node["label"] as? String ?: "",
                style = buttonStyle(node["style"] as? String),
                iconName = iconName(node["iconName"] as? String),
                onClick = clickHandler(node["onClickId"] as? String),
            )
            "icon" -> {
                val name = iconName(node["iconName"] as? String) ?: IconName.CHECKMARK
                icon(name = name, style = IconStyle.FILLED)
            }
        }
    }

    // --- Enum + value mapping -------------------------------------------------

    private fun direction(value: String?): Direction = when (value) {
        "row" -> Direction.ROW
        else -> Direction.COLUMN
    }

    private fun alignment(value: String?): Alignment = when (value) {
        "center" -> Alignment.CENTER
        "end" -> Alignment.END
        else -> Alignment.START
    }

    private fun textStyle(value: String?): TextStyle = when (value) {
        "heading" -> TextStyle.HEADING
        "meta" -> TextStyle.META
        else -> TextStyle.BODY
    }

    private fun textColor(value: String?): TextColor =
        if (value == "secondary") TextColor.SECONDARY else TextColor.PRIMARY

    private fun imageSize(value: String?): ImageSize =
        if (value == "icon") ImageSize.ICON else ImageSize.FILL

    private fun cornerRadius(value: String?): CornerRadius = when (value) {
        "small" -> CornerRadius.SMALL
        // The display SDK only ships none/small/medium; large collapses to medium.
        "medium", "large" -> CornerRadius.MEDIUM
        else -> CornerRadius.NONE
    }

    private fun buttonStyle(value: String?): ButtonStyle =
        if (value == "secondary") ButtonStyle.SECONDARY else ButtonStyle.PRIMARY

    private fun background(value: String?): FlexBoxBackground =
        if (value == "card") FlexBoxBackground.CARD else FlexBoxBackground.NONE

    private fun iconName(value: String?): IconName? {
        if (value == null) return null
        val token = value
            .replace(Regex("([a-z0-9])([A-Z])"), "$1_$2")
            .uppercase()
        return runCatching { IconName.valueOf(token) }.getOrNull()
    }

    private fun tapHandler(id: String?): (() -> Unit)? =
        id?.let { cid -> { emitCallback(cid, "tap") } }

    private fun clickHandler(id: String?): () -> Unit =
        { id?.let { emitCallback(it, "click") } }

    private fun intOf(value: Any?): Int = (value as? Number)?.toInt() ?: 0

    private fun floatOf(value: Any?): Float = (value as? Number)?.toFloat() ?: 0f

    private companion object {
        private const val SESSION_STARTED_TIMEOUT_MS = 45_000L
        private const val DISPLAY_STARTED_TIMEOUT_MS = 30_000L
    }
}
