package com.omi.localbrain

import android.content.Context
import android.util.Log
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Expo module wrapping the LiteRT embedding router.
 *
 * The routing logic is [IntentRouter], unchanged from the Android implementation
 * whose numbers are on the recipe page of google-ai-edge/litert-samples PR #383.
 * This file only adapts it to Expo's module API.
 *
 * Blocking work runs on one background thread. One, not a pool: the CompiledModel
 * reuses its tensor buffers in place, so concurrent invocations would race. A
 * ~600 ms route on a budget phone is slow enough that it must not be on the JS
 * thread; it is also fast enough that a queue is the right shape.
 */
class LocalBrainModule : Module() {
  private companion object {
    const val TAG = "LocalBrain"
    const val LOAD_TIMEOUT_SECONDS = 30L
  }

  private val worker = Executors.newSingleThreadExecutor { r ->
    Thread(r, "local-brain-router").apply { priority = Thread.NORM_PRIORITY + 1 }
  }

  // Set by `configure` before the first `route`.
  private var prototypeArgument: Map<String, List<String>> = emptyMap()
  private var outOfDomainArgument: List<String> = emptyList()
  @Volatile private var loaded = false

  /**
   * Set once a load has failed, so the failure is reported instead of retried on
   * every keystroke. Null while no load has been attempted.
   */
  @Volatile private var loadFailure: String? = null

  /** Serializes the first load. The worker thread alone does not: two callers can
   *  both see `loaded == false` and both enqueue a load. */
  private val loadLock = Any()

  // Built on first load rather than at construction: appContext is not safe to
  // touch before the module is attached, and reactContext is nullable, so the
  // fallback is resolved at the point of use.
  private var router: IntentRouter? = null

  override fun definition() = ModuleDefinition {
    Name("LocalBrain")

    AsyncFunction("configure") { prototypes: Map<String, List<String>>, outOfDomain: List<String> ->
      prototypeArgument = prototypes
      outOfDomainArgument = outOfDomain
      mapOf("ok" to true, "routes" to prototypes.keys.toList())
    }

    AsyncFunction("load") {
      ensureLoaded()
      mapOf("ok" to true, "ready" to loaded)
    }

    AsyncFunction("route") { text: String ->
      ensureLoaded()
      val d = router?.route(text) ?: return@AsyncFunction mapOf(
          "route" to IntentRouter.NO_ACTION,
          "declined" to true,
          "reason" to "router unavailable",
          "margin" to 0.0,
          "negated" to false,
          "runnerUp" to "",
          "latencyMs" to 0L,
      )
      mapOf(
          "route" to d.action,
          "margin" to d.margin,
          "declined" to d.declined,
          "negated" to d.negated,
          "runnerUp" to d.runnerUp,
          "latencyMs" to d.latencyMs,
          "reason" to d.reason,
      )
    }

    AsyncFunction("isReady") { loaded }

    /**
     * Loads without routing, so the one-off cost is not paid on a user's first
     * command.
     *
     * Measured on an SM-A145F: first route including model load is ~19.5 s, while
     * steady-state routing is ~600 ms. That gap is large enough that paying it
     * inside the first tap is indistinguishable from a hang. Rejects instead of
     * throwing past the bridge so a failed warm-up leaves the router declined
     * rather than fatal.
     */
    AsyncFunction("warmUp") { promise: Promise ->
      worker.execute {
        try {
          ensureLoaded()
          promise.resolve(true)
        } catch (t: Throwable) {
          promise.resolve(false)
        }
      }
    }

    OnDestroy { worker.shutdown() }
  }

  /**
   * Loads the router once, off the JS thread, and returns once it is ready.
   *
   * The previous version spun on `while (!loaded) Thread.sleep(10)` after
   * enqueueing the load. That was wrong in a way only a device could show: when
   * `IntentRouter.load()` throws -- which it does when minilm.tflite is not in the
   * APK assets, i.e. whenever the model has not been fetched -- `loaded` is never
   * set, so the spin never ended and the app froze. It did not even throw, so
   * nothing reached JS. Verified on an SM-A145F: the probe's own 15 s timeout
   * never fired, because the thread it would have fired on was blocked.
   *
   * The wait is now a bounded latch and a failure is recorded and rethrown, so
   * the JS layer sees a rejection and falls back to the heuristic, which is what
   * routeWithProvider already does with a thrown error.
   */
  private fun ensureLoaded() {
    if (loaded) return
    loadFailure?.let { throw loadError(it) }

    synchronized(loadLock) {
      // Re-checked inside the lock: another caller may have finished the load
      // between the check above and acquiring it.
      if (loaded) return
      loadFailure?.let { throw loadError(it) }

      val latch = CountDownLatch(1)
      worker.execute {
        try {
          // applicationContext: the router owns a CompiledModel and a worker
          // thread that outlive any single bridge.
          val context = appContext.reactContext?.applicationContext
            ?: throw Exceptions.AppContextLost()
          val created = IntentRouter(context, prototypeArgument, outOfDomainArgument)
          created.load()
          router = created
          loaded = true
        } catch (t: Throwable) {
          // Recorded rather than swallowed, and not retried: a missing model will
          // still be missing on the next keystroke, and retrying would pay the
          // load cost again for nothing.
          loadFailure = t.message ?: t.javaClass.simpleName
          Log.w(TAG, "local brain load failed: ${loadFailure}", t)
        } finally {
          // Always released, including on failure. This is the whole point: the
          // caller must never be left waiting on a latch nobody counts down.
          latch.countDown()
        }
      }

      // Bounded so a worker that dies without running the block still cannot hang
      // the caller. LOAD_TIMEOUT is generous for a one-off asset load; exceeding it
      // is a bug worth surfacing rather than waiting on indefinitely.
      if (!latch.await(LOAD_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
        loadFailure = "load did not finish within ${LOAD_TIMEOUT_SECONDS}s"
        throw loadError(loadFailure!!)
      }
    }

    loadFailure?.let { throw loadError(it) }
  }

  // The (code, message, cause) constructor takes all three: there is no
  // two-argument overload, and (message, cause) would silently swallow the code.
  private fun loadError(detail: String) =
      CodedException("E_ROUTER_LOAD", "local brain unavailable: $detail", null)
}