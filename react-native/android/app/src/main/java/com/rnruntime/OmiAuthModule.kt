package com.rnruntime

import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Base64
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.BaseActivityEventListener
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import java.util.concurrent.Executors

class OmiAuthModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  private val executor = Executors.newSingleThreadExecutor()
  private val handler = Handler(Looper.getMainLooper())
  private data class Attempt(val state: String, val verifier: String, val revision: Long, val promise: Promise)
  private var pending: Attempt? = null
  private var exchanging = false
  private val timeout = Runnable { cancel("Sign-in timed out. Please try again.") }
  private val listener = object : BaseActivityEventListener() {
    override fun onNewIntent(intent: Intent) {
      val value = intent.dataString ?: return
      handler.post { callback(value) }
    }
  }

  init { context.addActivityEventListener(listener) }

  override fun getName() = "OmiAuth"

  @ReactMethod fun signIn(promise: Promise) {
    handler.post {
      if (pending != null) {
        promise.reject("OMI_AUTH_BUSY", "Sign-in is already in progress")
        return@post
      }
      val activity = context.currentActivity
      if (activity == null) {
        promise.reject("OMI_AUTH_UNAVAILABLE", "Sign-in requires an active application")
        return@post
      }
      try {
        val attempt = Attempt(OmiAuthPolicy.randomToken(), OmiAuthPolicy.randomToken(), OmiCloudSession.currentRevision(), promise)
        val query = OmiCloudSession.form(mapOf("provider" to "google", "redirect_uri" to OmiAuthPolicy.REDIRECT,
          "state" to attempt.state, "code_challenge" to Base64.encodeToString(OmiAuthPolicy.challenge(attempt.verifier), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING), "code_challenge_method" to "S256"))
        pending = attempt
        exchanging = false
        activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://api.omi.me/v1/auth/authorize?$query")))
        handler.postDelayed(timeout, 300_000)
      } catch (_: Exception) {
        if (pending != null) cancel("Unable to open sign-in")
        else promise.reject("OMI_AUTH_UNAVAILABLE", "Unable to open sign-in")
      }
    }
  }

  private fun callback(value: String) {
    val attempt = pending ?: return
    if (exchanging) return
    val code = OmiAuthPolicy.callbackCode(value, attempt.state) ?: return
    exchanging = true
    handler.removeCallbacks(timeout)
    executor.execute {
      val success = runCatching { OmiCloudSession.exchange(context, code, attempt.verifier, attempt.revision) }.isSuccess
      handler.post {
        if (pending !== attempt) return@post
        pending = null
        exchanging = false
        handler.removeCallbacks(timeout)
        if (success) attempt.promise.resolve(Arguments.createMap().apply { putBoolean("signedIn", true) })
        else attempt.promise.reject("OMI_AUTH_FAILED", "Sign-in failed. Please try again.")
      }
    }
  }

  private fun cancel(message: String) {
    val attempt = pending
    pending = null
    exchanging = false
    handler.removeCallbacks(timeout)
    if (attempt != null) {
      OmiCloudSession.cancelAttempt(attempt.revision)
      attempt.promise.reject("OMI_AUTH_CANCELLED", message)
    }
  }

  @ReactMethod fun cancelSignIn(promise: Promise) {
    handler.post {
      cancel("Sign-in cancelled")
      promise.resolve(null)
    }
  }

  @ReactMethod fun signOut(promise: Promise) {
    handler.post {
      cancel("Sign-in cancelled")
      executor.execute {
        try {
          OmiCloudSession.signOut(context)
          context.getNativeModule(OmiBackendModule::class.java)?.cancelAllGenerations()
          promise.resolve(Arguments.createMap().apply { putBoolean("signedOut", true) })
        } catch (_: Exception) {
          promise.reject("OMI_AUTH_STORAGE", "Unable to clear the native session")
        }
      }
    }
  }

  @ReactMethod fun hasCloudSession(promise: Promise) {
    executor.execute {
      try { promise.resolve(OmiCloudSession.hasSession(context)) }
      catch (_: Exception) { promise.reject("OMI_AUTH_STORAGE", "Unable to read the native session") }
    }
  }

  @ReactMethod fun hasCompletedOnboarding(promise: Promise) {
    promise.resolve(context.getSharedPreferences("omi-onboarding", 0).getInt("setupRevision", 0) == 1)
  }

  @ReactMethod fun markOnboardingComplete(promise: Promise) {
    executor.execute {
      if (context.getSharedPreferences("omi-onboarding", 0).edit().putInt("setupRevision", 1).commit()) promise.resolve(null)
      else promise.reject("OMI_AUTH_STORAGE", "Unable to save onboarding state")
    }
  }

  override fun invalidate() {
    context.removeActivityEventListener(listener)
    handler.post { cancel("Sign-in cancelled") }
    super.invalidate()
  }
}
