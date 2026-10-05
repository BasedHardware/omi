package com.omi.localbrain

import android.content.Context
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.util.concurrent.Executors

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
  private val worker = Executors.newSingleThreadExecutor { r ->
    Thread(r, "local-brain-router").apply { priority = Thread.NORM_PRIORITY + 1 }
  }

  // Set by `configure` before the first `route`.
  private var prototypeArgument: Map<String, List<String>> = emptyMap()
  private var outOfDomainArgument: List<String> = emptyList()
  @Volatile private var loaded = false

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
      awaitLoad()
      mapOf("ok" to true, "ready" to loaded)
    }

    AsyncFunction("route") { text: String ->
      awaitLoad()
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

    OnDestroy { worker.shutdown() }
  }

  /**
   * Runs the blocking load on the worker and blocks the caller until it finishes.
   * AsyncFunction already dispatches off the JS thread, so waiting here does not
   * block the UI; it only serializes the first call behind the load.
   */
  private fun awaitLoad() {
    if (loaded) return
    worker.execute {
      if (!loaded) {
        // applicationContext: the router owns a CompiledModel and a worker
        // thread that outlive any single bridge.
        val context = appContext.reactContext?.applicationContext
          ?: throw Exceptions.AppContextLost()
        val created = IntentRouter(context, prototypeArgument, outOfDomainArgument)
        created.load()
        router = created
        loaded = true
      }
    }
    while (!loaded) {
      Thread.sleep(10)
    }
  }
}