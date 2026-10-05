// PhoneStateListener is deprecated in favour of TelephonyCallback and does not
// deliver an incoming ring on API 31+. It is retained only for the pre-31 branch,
// where TelephonyCallback.CallStateListener does not exist yet.
@file:Suppress("DEPRECATION")

package com.omi.localcalls

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.telecom.TelecomManager
import android.telephony.PhoneStateListener
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import android.util.Log

/**
 * Detects incoming cellular call state, and answers a ringing call.
 *
 * Deliberately separate from any Expo or React type, so it can be compiled and
 * reasoned about on its own. [LocalCallsModule] is the thin bridge over it.
 *
 * ## What this can and cannot see
 *
 * The distinction matters and is easy to get wrong:
 *
 *  - **VoIP calls the app places itself** are visible through
 *    `TelecomManager.registerPhoneStateListener` with no extra permission. The
 *    Flutter `PhoneCallsPlugin` already consumes that path, and it is how omi's
 *    own outbound calls report `ringing`/`active`/`connecting`.
 *
 *  - **Incoming cellular calls** are a different path and need `READ_PHONE_STATE`.
 *    `PhoneStateListener` alone does not report an incoming ring on modern
 *    Android; `TelephonyCallback.CallStateListener` does, and it is what this uses.
 *
 *  - **Who is calling is not available** without `READ_CALL_LOG`, which is a much
 *    heavier permission covering the whole call history. This deliberately does
 *    not request it, so [onStateChanged] reports *that* a call is ringing, never
 *    *who*. Number identification needs Contacts plus a lookup, which is a product
 *    decision rather than a technical one.
 *
 * ## Answering
 *
 * `TelecomManager.acceptRingingCall()` requires `ANSWER_PHONE_CALLS`, which is a
 * runtime permission the user grants. This class checks and reports rather than
 * assuming, because the grant can be revoked between calls.
 *
 * What answering does NOT enable: injecting audio into an active cellular call.
 * The carrier call takes exclusive audio and Android exposes no supported API for
 * it. Playback into a call is only possible on a call path this app controls.
 */
class CallStateDetector(private val context: Context) {

    companion object {
        private const val TAG = "CallStateDetector"

        /** Reported to JS. `null` caller means unknown, by design. */
        const val STATE_IDLE = "idle"
        const val STATE_RINGING = "ringing"
        const val STATE_OFFHOOK = "offhook"
        const val STATE_INCOMING = "incoming"
    }

    interface Listener {
        /** @param caller always null here; see the class note on READ_CALL_LOG. */
        fun onStateChanged(state: String, caller: String?)
    }

    private val appContext = context.applicationContext
    private val telephony =
        appContext.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager
    private val telecom =
        appContext.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager

    private var executor: java.util.concurrent.Executor? = null
    private var callback: Any? = null
    private var listener: Listener? = null

    fun hasReadPhoneState(): Boolean =
        appContext.checkSelfPermission(Manifest.permission.READ_PHONE_STATE) ==
            PackageManager.PERMISSION_GRANTED

    fun hasAnswerPermission(): Boolean =
        appContext.checkSelfPermission(Manifest.permission.ANSWER_PHONE_CALLS) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * Starts listening. Returns false when `READ_PHONE_STATE` is missing, which
     * is the normal state until the user grants it; the caller surfaces that as a
     * permission prompt rather than an error.
     */
    fun start(l: Listener): Boolean {
        if (!hasReadPhoneState()) {
            Log.i(TAG, "start refused: READ_PHONE_STATE not granted")
            return false
        }
        val tm = telephony ?: return false
        listener = l
        // A dedicated thread: TelephonyCallback callbacks arrive on this executor,
        // and binding them to the main looper would put telephony work on the UI
        // thread for the life of the app.
        val thread = android.os.HandlerThread("call-detect").apply { start() }
        val exec = java.util.concurrent.Executor { command -> command.run() }
        executor = exec

        // API 31+ prefers TelephonyCallback; PhoneStateListener is deprecated and
        // does not deliver an incoming ring on newer releases.
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            val cb =
                object : TelephonyCallback(), TelephonyCallback.CallStateListener {
                    private var last = STATE_IDLE

                    override fun onCallStateChanged(state: Int) {
                        val mapped =
                            when (state) {
                                TelephonyManager.CALL_STATE_IDLE -> STATE_IDLE
                                TelephonyManager.CALL_STATE_RINGING -> STATE_RINGING
                                TelephonyManager.CALL_STATE_OFFHOOK -> STATE_OFFHOOK
                                else -> STATE_IDLE
                            }
                        if (mapped != last) {
                            last = mapped
                            // No caller number: that needs READ_CALL_LOG.
                            listener?.onStateChanged(mapped, null)
                        }
                    }
                }
            tm.registerTelephonyCallback(exec, cb)
            callback = cb
        } else {
            val psl =
                @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
                object : PhoneStateListener() {
                    override fun onCallStateChanged(state: Int, phoneNumber: String?) {
                        val mapped =
                            when (state) {
                                TelephonyManager.CALL_STATE_IDLE -> STATE_IDLE
                                TelephonyManager.CALL_STATE_RINGING -> STATE_RINGING
                                TelephonyManager.CALL_STATE_OFFHOOK -> STATE_OFFHOOK
                                else -> STATE_IDLE
                            }
                        listener?.onStateChanged(mapped, phoneNumber)
                    }
                }
            tm.listen(psl, PhoneStateListener.LISTEN_CALL_STATE)
            callback = psl
        }
        return true
    }

    fun stop() {
        val tm = telephony
        when (val cb = callback) {
            is TelephonyCallback ->
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                    runCatching { tm?.unregisterTelephonyCallback(cb) }
                }
            is PhoneStateListener ->
                runCatching { tm?.listen(cb, PhoneStateListener.LISTEN_NONE) }
        }
        callback = null
        listener = null
    }

    /**
     * Answers a ringing call.
     *
     * @return null on success, or a reason string. Never throws, because the grant
     *   can disappear between the permission check and the call.
     */
    fun answer(): String? {
        val tm = telecom ?: return "TelecomManager unavailable"
        if (!hasAnswerPermission()) return "ANSWER_PHONE_CALLS not granted"
        return runCatching { tm.acceptRingingCall() }
            .fold({ null }, { "acceptRingingCall failed: ${it.message}" })
    }

    /** Hangs up an active call. Same permission story as [answer]. */
    fun endCall(): String? {
        val tm = telecom ?: return "TelecomManager unavailable"
        if (!hasAnswerPermission()) return "ANSWER_PHONE_CALLS not granted"
        return runCatching { tm.endCall() }
            .fold({ null }, { "endCall failed: ${it.message}" })
    }
}
