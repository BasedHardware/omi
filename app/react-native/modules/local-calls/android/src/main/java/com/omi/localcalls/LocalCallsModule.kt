package com.omi.localcalls

import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Expo bridge over [CallStateDetector]. All logic lives there; this only adapts
 * to Expo's module API and forwards the permission state so JS can prompt rather
 * than guess.
 *
 * Permission *requests* deliberately live in JS via `PermissionsAndroid`, not
 * here. Doing it natively needs an activity-result round trip whose promise only
 * resolves from a callback this module API does not expose cleanly, and
 * `PermissionsAndroid` already does it correctly. The manifest declarations still
 * have to exist; see the module README.
 */
class LocalCallsModule : Module() {
  // applicationContext rather than the react context: this registers a
  // TelephonyCallback that outlives any single bridge, and holding a
  // ReactApplicationContext for that long would leak it.
  private val detector: CallStateDetector by lazy {
    val context = appContext.reactContext?.applicationContext
      ?: throw Exceptions.AppContextLost()
    CallStateDetector(context)
  }

  override fun definition() = ModuleDefinition {
    Name("LocalCalls")

    AsyncFunction("permissionState") {
      mapOf(
        "READ_PHONE_STATE" to detector.hasReadPhoneState(),
        "ANSWER_PHONE_CALLS" to detector.hasAnswerPermission(),
        "canDetect" to detector.hasReadPhoneState(),
        "canAnswer" to detector.hasAnswerPermission(),
      )
    }

    /**
     * Starts listening. `onEvent` is invoked as `onEvent("callState", state, caller)`
     * so JS can subscribe with addListener. Null caller is expected: identifying
     * the caller needs READ_CALL_LOG, which this does not request.
     */
    AsyncFunction("start") { promise: Promise ->
      val ok =
          detector.start(
              object : CallStateDetector.Listener {
                override fun onStateChanged(state: String, caller: String?) {
                  sendEvent("callState", mapOf("state" to state, "caller" to caller))
                }
              })
      if (ok) {
        promise.resolve(true)
      } else {
        promise.reject(
            "E_NO_PERMISSION",
            "READ_PHONE_STATE not granted; call requestCallPermissions() from JS first",
            null,
        )
      }
    }

    AsyncFunction("stop") {
      detector.stop()
      true
    }

    AsyncFunction("answer") { promise: Promise ->
      val error = detector.answer()
      if (error == null) promise.resolve(true) else promise.reject("E_ANSWER", error, null)
    }

    AsyncFunction("endCall") { promise: Promise ->
      val error = detector.endCall()
      if (error == null) promise.resolve(true) else promise.reject("E_END_CALL", error, null)
    }
  }
}
