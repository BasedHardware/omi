package com.friend.ios.audio

import android.app.Activity
import android.app.Application
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioRecordingConfiguration
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import com.friend.ios.phonemic.PhoneMicController
import java.util.concurrent.Executor

/**
 * What Android does to a running capture. The OS owns the microphone, so every one of these is a
 * change the app did not ask for and has to answer: a recording never stops without the app knowing
 * why. The Android counterpart of `AudioSessionEvent`, which is what `AVAudioSession` reports.
 */
sealed interface AudioSessionEvent {
    /** Something else took the microphone: a call, the assistant, another recorder. */
    data object Interrupted : AudioSessionEvent

    /**
     * The interruption ended. `shouldResume` is iOS's permission to take the microphone back;
     * Android has no such signal (the recording-config callback and the audio mode both clear
     * without withholding anything), so it is always true here.
     */
    data class InterruptionEnded(val shouldResume: Boolean) : AudioSessionEvent

    /** The input route changed. `input` is the microphone in use now, null when there is none. */
    data class RouteChanged(val input: String?) : AudioSessionEvent

    /** The capture's audio objects were torn down: every session and record is dead and must be rebuilt. */
    data object MediaServicesReset : AudioSessionEvent

    /** The app came back to the front, a chance to take a stopped capture's microphone back. */
    data object AppBecameActive : AudioSessionEvent
}

/**
 * The OS signals a capture has to answer. The store owns the policy; this only parses and forwards.
 * Port of `AudioSessionMonitoring`.
 */
interface AudioSessionMonitoring {
    /** Starts delivering events on the main thread. Calling it twice is a no-op. */
    fun start(onEvent: (AudioSessionEvent) -> Unit)

    /** Stops delivering events and drops the handler. */
    fun stop()
}

/**
 * The Android side of `AVAudioSessionMonitor`, from `AudioManager`:
 *
 *  - the recording-config callback (`registerAudioRecordingCallback`): the system silences a
 *    recording client when a call, the assistant or another recorder takes the microphone. This is
 *    the same signal `PhoneMicController` uses, and the only one that reports the microphone itself
 *    being taken rather than something merely changing around it.
 *  - the audio mode (`addOnModeChangedListener`): `MODE_IN_CALL` / `MODE_IN_COMMUNICATION`, the
 *    call taking the audio.
 *  - the input devices (`registerAudioDeviceCallback`): where `routeChanged(input:)` comes from.
 *  - the app's activities (`registerActivityLifecycleCallbacks`): `appBecameActive`.
 *
 * Deliberately no audio-focus request. The capture path never requests focus either
 * (`PhoneMicCaptureEngine`: "taking focus would pause the user's music/podcast", the Android form of
 * the iOS session's `mixWithOthers`), and a focus request would make the app duck or stop what the
 * user is listening to just because a recording started. Everything iOS learns from an interruption
 * notification arrives here through the silencing callback and the audio mode instead. For the same
 * reason this only listens while a capture is live: the store starts and stops it.
 *
 * Every registered callback is delivered on the main thread, which is where the store's state lives
 * (iOS's `queue: .main`).
 */
class AndroidAudioSessionMonitor(
    application: Application,
    /**
     * The live capture's `AudioRecord` session id, `AudioRecord.ERROR` when nothing records: only a
     * config with this id is this app's own recording (`PhoneMicController.audioSessionId`).
     */
    private val ourSessionId: () -> Int = {
        if (PhoneMicController.isInitialized) PhoneMicController.instance.audioSessionId else AudioRecord.ERROR
    },
) : AudioSessionMonitoring {

    private val app = application
    private val main = Handler(Looper.getMainLooper())
    private val mainExecutor = Executor { command -> main.post(command) }
    private val audioManager: AudioManager? = application.getSystemService(AudioManager::class.java)

    private var handler: ((AudioSessionEvent) -> Unit)? = null

    private var recordingCallback: AudioManager.AudioRecordingCallback? = null
    private var deviceCallback: AudioDeviceCallback? = null
    private var modeListener: AudioManager.OnModeChangedListener? = null

    /**
     * This app's session has appeared in the config list at least once. Until it has, an absent
     * config means "not registered yet", not "preempted", so a startup callback cannot fake a
     * silencing (`PhoneMicController.sawCurrentSession`).
     */
    private var sawOurSession = false
    private var silenced = false
    private var inCall = false

    private val activityCallbacks = object : Application.ActivityLifecycleCallbacks {
        override fun onActivityStarted(activity: Activity) = emit(AudioSessionEvent.AppBecameActive)

        override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {}
        override fun onActivityResumed(activity: Activity) {}
        override fun onActivityPaused(activity: Activity) {}
        override fun onActivityStopped(activity: Activity) {}
        override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
        override fun onActivityDestroyed(activity: Activity) {}
    }

    override fun start(onEvent: (AudioSessionEvent) -> Unit) {
        if (handler != null) return
        handler = onEvent
        val manager = audioManager ?: return
        val ids = ourSessionId
        recordingCallback = object : AudioManager.AudioRecordingCallback() {
            override fun onRecordingConfigChanged(configs: MutableList<AudioRecordingConfiguration>) {
                val ours = configs.firstOrNull { it.clientAudioSessionId == ids() }
                if (ours != null) {
                    sawOurSession = true
                    applySilenced(ours.isClientSilenced)
                } else if (sawOurSession) {
                    // Full preemption drops our entry instead of flipping its flag: the record is
                    // gone, and with it every object the capture was built on.
                    sawOurSession = false
                    silenced = false
                    emit(AudioSessionEvent.MediaServicesReset)
                }
            }
        }.also { manager.registerAudioRecordingCallback(it, main) }

        deviceCallback = object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>?) =
                emit(AudioSessionEvent.RouteChanged(currentInput()))

            override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>?) =
                emit(AudioSessionEvent.RouteChanged(currentInput()))
        }.also { manager.registerAudioDeviceCallback(it, main) }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            modeListener = AudioManager.OnModeChangedListener { mode -> applyCall(inCallMode(mode)) }
                .also { manager.addOnModeChangedListener(mainExecutor, it) }
            applyCall(inCallMode(manager.mode))
        }
        app.registerActivityLifecycleCallbacks(activityCallbacks)
    }

    override fun stop() {
        handler = null
        val manager = audioManager
        recordingCallback?.let { manager?.unregisterAudioRecordingCallback(it) }
        deviceCallback?.let { manager?.unregisterAudioDeviceCallback(it) }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            modeListener?.let { manager?.removeOnModeChangedListener(it) }
        }
        app.unregisterActivityLifecycleCallbacks(activityCallbacks)
        recordingCallback = null
        deviceCallback = null
        modeListener = null
        sawOurSession = false
        silenced = false
        inCall = false
    }

    /** One silencing verdict, from the config list or from where the session was seeded. */
    private fun applySilenced(nowSilenced: Boolean) {
        if (nowSilenced == silenced) return
        silenced = nowSilenced
        emit(if (nowSilenced) AudioSessionEvent.Interrupted else AudioSessionEvent.InterruptionEnded(shouldResume = true))
    }

    /** A call taking the audio, or giving it back (the audio-mode listener). */
    private fun applyCall(nowInCall: Boolean) {
        if (nowInCall == inCall) return
        inCall = nowInCall
        emit(if (nowInCall) AudioSessionEvent.Interrupted else AudioSessionEvent.InterruptionEnded(shouldResume = true))
    }

    /** The microphone in use now; nil when the device list has no input at all. */
    private fun currentInput(): String? =
        audioManager?.getDevices(AudioManager.GET_DEVICES_INPUTS)?.firstOrNull()?.productName?.toString()

    private fun emit(event: AudioSessionEvent) {
        val deliver: () -> Unit = { handler?.invoke(event) }
        if (Looper.myLooper() == Looper.getMainLooper()) deliver() else main.post(deliver)
    }

    private companion object {
        fun inCallMode(mode: Int): Boolean =
            mode == AudioManager.MODE_IN_CALL || mode == AudioManager.MODE_IN_COMMUNICATION
    }
}
