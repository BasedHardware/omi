package com.friend.ios.phonecalls

import android.telecom.CallAudioState
import android.telecom.Connection
import android.telecom.ConnectionRequest
import android.telecom.ConnectionService
import android.telecom.PhoneAccountHandle
import android.telecom.TelecomManager
import kotlinx.coroutines.CompletableDeferred
import java.util.concurrent.ConcurrentHashMap

/**
 * The CallKit provider's Android counterpart: Telecom asks this service for the outgoing call that
 * [TelecomCallCoordinator] placed, and the [OmiCallConnection] reports what the system does to it
 * (hang-up from a headset or watch, mute, the audio route). Self-managed: no system dialer UI, the
 * app's own call screen is the UI.
 */
class OmiConnectionService : ConnectionService() {
    override fun onCreateOutgoingConnection(account: PhoneAccountHandle?, request: ConnectionRequest): Connection {
        val extras = request.extras
        val id = extras?.getString(TelecomCalls.EXTRA_CALL_ID).orEmpty()
        val connection = OmiCallConnection(id).apply {
            connectionProperties = Connection.PROPERTY_SELF_MANAGED
            connectionCapabilities = Connection.CAPABILITY_MUTE
            audioModeIsVoip = true
            setAddress(request.address, TelecomManager.PRESENTATION_ALLOWED)
            extras?.getString(TelecomCalls.EXTRA_CONTACT_NAME)?.let { setCallerDisplayName(it, TelecomManager.PRESENTATION_ALLOWED) }
            setDialing()
        }
        TelecomCalls.connections[id] = connection
        TelecomCalls.pending[id]?.complete(connection)
        return connection
    }

    override fun onCreateOutgoingConnectionFailed(account: PhoneAccountHandle?, request: ConnectionRequest) {
        val id = request.extras?.getString(TelecomCalls.EXTRA_CALL_ID).orEmpty()
        TelecomCalls.pending[id]?.completeExceptionally(CallSystemError.rejected("Telecom refused the call"))
    }
}

/** One call as Telecom sees it. */
class OmiCallConnection(private val id: String) : Connection() {
    private var lastMuted: Boolean? = null
    private var lastSpeaker: Boolean? = null

    /** Hung up from the system (Bluetooth, Wear, car). */
    override fun onDisconnect() {
        TelecomCalls.connections.remove(id)
        TelecomCalls.listener?.onSystemEndCall()
    }

    override fun onAbort() = onDisconnect()

    @Deprecated("Deprecated in API 34; still delivered")
    override fun onCallAudioStateChanged(state: CallAudioState) {
        // The app mutes through Twilio, not Telecom, so a change of Telecom's own mute is the system's.
        if (lastMuted != null && lastMuted != state.isMuted) TelecomCalls.listener?.onSystemMute(state.isMuted)
        lastMuted = state.isMuted
        val speaker = state.route == CallAudioState.ROUTE_SPEAKER
        if (lastSpeaker != speaker) TelecomCalls.listener?.onSystemSpeaker(speaker)
        lastSpeaker = speaker
    }
}

/** Hands connections from the system-created service to the coordinator (one call at a time). */
object TelecomCalls {
    const val EXTRA_CALL_ID = "com.friend.ios.phonecalls.CALL_ID"
    const val EXTRA_CONTACT_NAME = "com.friend.ios.phonecalls.CONTACT_NAME"

    interface Listener {
        fun onSystemEndCall()
        fun onSystemMute(muted: Boolean)
        fun onSystemSpeaker(on: Boolean)
    }

    val pending = ConcurrentHashMap<String, CompletableDeferred<OmiCallConnection>>()
    val connections = ConcurrentHashMap<String, OmiCallConnection>()

    @Volatile
    var listener: Listener? = null
}
