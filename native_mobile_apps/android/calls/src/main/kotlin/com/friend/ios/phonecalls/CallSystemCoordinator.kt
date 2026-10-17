package com.friend.ios.phonecalls

import android.annotation.SuppressLint
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.telecom.CallAudioState
import android.telecom.DisconnectCause
import android.telecom.PhoneAccount
import android.telecom.PhoneAccountHandle
import android.telecom.TelecomManager
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import java.util.UUID

/**
 * Port of `CallSystemCoordinator.swift`. Who owns the call's audio: Telecom (the system knows the
 * call: Bluetooth and Wear hang-up, other apps' audio yields, the call survives in the background)
 * or, where Telecom is missing, the app itself. Flutter `OmiCallCoordinatorProtocol`.
 *
 * iOS starts its audio unit when CallKit activates the session; on Android Twilio drives the audio
 * device itself, so there is no activation hook here.
 */
interface CallSystemCoordinator {
    /** Hung up from the system (a Bluetooth headset, a watch, the notification). */
    var onSystemEndCall: (() -> Unit)?

    /** Muted from the system. */
    var onSystemMute: ((Boolean) -> Unit)?

    /** The system moved the audio to (or off) the speaker. */
    var onSystemSpeaker: ((Boolean) -> Unit)?

    /** Returns once the system allowed the call. */
    suspend fun startCall(id: UUID, phoneNumber: String, contactName: String?)

    fun endCall(id: UUID)

    fun reportConnected(id: UUID)

    fun reportEnded(id: UUID, failed: Boolean)

    /** `false`: the route could not change (the button keeps showing it). */
    fun setSpeaker(on: Boolean): Boolean

    companion object {
        /** Telecom where the device has it (phones), otherwise the app's own audio handling. */
        fun make(context: Context): CallSystemCoordinator =
            if (context.packageManager.hasSystemFeature(PackageManager.FEATURE_CONNECTION_SERVICE)) TelecomCallCoordinator(context) else DirectCallCoordinator(context)
    }
}

class CallSystemError(message: String) : Exception(message) {
    companion object {
        fun notReady() = CallSystemError("The call system is not ready")
        fun rejected(detail: String) = CallSystemError("The call system rejected the call: $detail")
    }
}

/**
 * Telecom with a self-managed phone account: the call shows like any VoIP call. Telecom creates the
 * [OmiCallConnection] in [OmiConnectionService]; [TelecomCalls] hands it back here.
 */
class TelecomCallCoordinator(private val context: Context) : CallSystemCoordinator {
    override var onSystemEndCall: (() -> Unit)? = null
    override var onSystemMute: ((Boolean) -> Unit)? = null
    override var onSystemSpeaker: ((Boolean) -> Unit)? = null

    private val telecom = context.getSystemService(TelecomManager::class.java)
    private val handle = PhoneAccountHandle(ComponentName(context, OmiConnectionService::class.java), ACCOUNT_ID)
    private var registered = false

    private fun register() {
        if (registered) return
        val account = PhoneAccount.builder(handle, "Omi")
            .setCapabilities(PhoneAccount.CAPABILITY_SELF_MANAGED)
            .setSupportedUriSchemes(listOf(PhoneAccount.SCHEME_TEL))
            .build()
        telecom.registerPhoneAccount(account)
        registered = true
    }

    @SuppressLint("MissingPermission") // MANAGE_OWN_CALLS is a normal permission, granted at install.
    override suspend fun startCall(id: UUID, phoneNumber: String, contactName: String?) {
        register()
        if (!telecom.isOutgoingCallPermitted(handle)) throw CallSystemError.rejected("another call is in progress")
        val pending = CompletableDeferred<OmiCallConnection>()
        TelecomCalls.pending[id.toString()] = pending
        TelecomCalls.listener = listener
        val extras = Bundle().apply {
            putParcelable(TelecomManager.EXTRA_PHONE_ACCOUNT_HANDLE, handle)
            putBundle(
                TelecomManager.EXTRA_OUTGOING_CALL_EXTRAS,
                Bundle().apply {
                    putString(TelecomCalls.EXTRA_CALL_ID, id.toString())
                    putString(TelecomCalls.EXTRA_CONTACT_NAME, contactName)
                },
            )
        }
        try {
            telecom.placeCall(Uri.fromParts(PhoneAccount.SCHEME_TEL, phoneNumber, null), extras)
            // Telecom answers through the connection service within moments; wait up to 3 s like Flutter.
            withTimeout(3_000) { pending.await() }
        } catch (error: TimeoutCancellationException) {
            throw CallSystemError.notReady()
        } catch (error: SecurityException) {
            throw CallSystemError.rejected(error.message ?: "permission")
        } finally {
            TelecomCalls.pending.remove(id.toString())
        }
    }

    override fun endCall(id: UUID) {
        TelecomCalls.connections.remove(id.toString())?.let {
            it.setDisconnected(DisconnectCause(DisconnectCause.LOCAL))
            it.destroy()
        }
    }

    override fun reportConnected(id: UUID) {
        TelecomCalls.connections[id.toString()]?.setActive()
    }

    override fun reportEnded(id: UUID, failed: Boolean) {
        TelecomCalls.connections.remove(id.toString())?.let {
            it.setDisconnected(DisconnectCause(if (failed) DisconnectCause.ERROR else DisconnectCause.REMOTE))
            it.destroy()
        }
    }

    @Suppress("DEPRECATION") // requestCallEndpointChange (34+) needs the endpoint list; the route API still works.
    override fun setSpeaker(on: Boolean): Boolean {
        val connection = TelecomCalls.connections.values.firstOrNull() ?: return false
        connection.setAudioRoute(if (on) CallAudioState.ROUTE_SPEAKER else CallAudioState.ROUTE_WIRED_OR_EARPIECE)
        return true
    }

    private val listener = object : TelecomCalls.Listener {
        override fun onSystemEndCall() {
            onSystemEndCall?.invoke()
        }

        override fun onSystemMute(muted: Boolean) {
            onSystemMute?.invoke(muted)
        }

        override fun onSystemSpeaker(on: Boolean) {
            onSystemSpeaker?.invoke(on)
        }
    }

    companion object {
        const val ACCOUNT_ID = "omi-phone-calls"
    }
}

/** Without Telecom: the app puts the audio in communication mode itself (Flutter's Android plugin). */
class DirectCallCoordinator(context: Context) : CallSystemCoordinator {
    override var onSystemEndCall: (() -> Unit)? = null
    override var onSystemMute: ((Boolean) -> Unit)? = null
    override var onSystemSpeaker: ((Boolean) -> Unit)? = null

    private val audio = context.getSystemService(AudioManager::class.java)

    override suspend fun startCall(id: UUID, phoneNumber: String, contactName: String?) {
        audio.mode = AudioManager.MODE_IN_COMMUNICATION
    }

    override fun endCall(id: UUID) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) audio.clearCommunicationDevice()
        audio.mode = AudioManager.MODE_NORMAL
    }

    override fun reportConnected(id: UUID) {}

    override fun reportEnded(id: UUID, failed: Boolean) = endCall(id)

    override fun setSpeaker(on: Boolean): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (!on) {
                audio.clearCommunicationDevice()
                return true
            }
            val speaker = audio.availableCommunicationDevices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER } ?: return false
            return audio.setCommunicationDevice(speaker)
        }
        @Suppress("DEPRECATION")
        audio.isSpeakerphoneOn = on
        return true
    }
}
