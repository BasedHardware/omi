package com.friend.ios.phonemic

import android.app.Application
import android.media.AudioManager
import android.os.Looper

/**
 * The phone-mic capture state machine — the Kotlin port of iOS `PhoneMicController`.
 * Owns every decision: permission gate -> resource bring-up -> engine start, the
 * start-retry policy, interruption (client silencing / phone-call) recovery, engine
 * self-heal on stall/read-error, and the drain-ordered teardown that finalizes the
 * batch file before stop() resolves. The other PhoneMic classes are mechanism only.
 *
 * Every OS effect (main loop, permissions, audio mode, recording-config callbacks,
 * foreground service, engine, batch pipeline, logging) is injected through
 * [PhoneMicControllerPorts] so the JVM replay harness drives this exact policy
 * with the canonical phone-mic-native-events/v1 vectors.
 *
 * Threading (the load-bearing constraint):
 *  - ALL control state below is confined to the MAIN loop. Pigeon host handlers,
 *    the heartbeat/resume/rebuild timers, and the recording-config listener are all
 *    delivered on main, so plain (non-atomic) fields are correct. [start]/[stop] hop
 *    to main defensively via [runOnMain] in case they are ever called off-main.
 *  - [PhoneMicCaptureEngine] owns one read thread; it hands chunks back on that thread.
 *  - the audio task queue is serial and does chunk fan-out (encode + write for
 *    batch, or hand to the emitter for stream) and the encoder/writer close+destroy.
 *    INVARIANT: no audioQueue task ever blocks on main — every hop back to main is a
 *    fire-and-forget `main.post`, so stop() never deadlocks on the file finalize.
 *  - [emissionGated] is the ONLY cross-thread flag: written on main, read on the
 *    audio queue to drop audio captured while the mic is silenced.
 *
 * Recovery is self-healing and native: Dart is only told the state so it can keep its
 * own recording flag / UI in sync — it never re-arms capture on an interruption (its
 * batch watchdog stays an outer safety net that calls stop()+start()). Every outbound
 * message goes through [emitter]; the controller never touches the Pigeon api.
 */
class PhoneMicController private constructor(private val ports: PhoneMicControllerPorts) {

    /** Why we are in [PhoneMicCaptureState.INTERRUPTED], which decides how we resume. */
    private enum class Cause {
        /** Not interrupted (running / idle / etc.). */
        NONE,

        /** RecordingConfig listener reports our session is being silenced (call/assistant
         *  took the mic). Engine stays alive; resume in place when the flag clears. */
        SILENCED,

        /** Heartbeat mode-poll fallback: a call mode is up and data stalled but the
         *  silencing callback never fired. Engine stays alive (starved); resume by a
         *  full rebuild when the call mode clears. */
        MODE,

        /** Self-heal gave up after [MAX_CONSECUTIVE_REBUILDS]; the 3s resume ticker
         *  probes a rebuild forever. */
        REBUILD,
    }

    private val main = ports.main
    private val emitter = PhoneMicEventEmitter(main)
    private val audioQueue = ports.audioQueue

    // ── Control state (MAIN loop only) ──
    private var state: PhoneMicCaptureState = PhoneMicCaptureState.IDLE
    private var mode: PhoneMicCaptureMode = PhoneMicCaptureMode.STREAM
    // Dart-minted identity for the live session (main only). Every emitted event
    // carries it; a start() onto a live session adopts the new id so future
    // events converge to that caller's Dart session.
    private var currentSessionId: Long = 0L
    private var pendingStop = false

    // Dart's stop() is fire-and-forget (IMicRecorderService.stop is void), so a start()
    // can land while [finishStop]'s executor drain is still finalizing — the mid-session
    // Live<->Later toggle roll does exactly stop();start(). On iOS the synchronous
    // control-queue stop makes a subsequent start always see idle; here the drain window
    // must be bridged explicitly: such a start is a NEW session (its mode is honoured,
    // latest wins) queued to run once the drain flips to IDLE — never a piggyback onto
    // the dying session.
    private var stopDrainInFlight = false
    private var restartModeAfterStop: PhoneMicCaptureMode? = null
    private var restartSessionIdAfterStop: Long = 0L
    private val pendingStartCallbacks = mutableListOf<(Result<Unit>) -> Unit>()
    private val pendingStopCallbacks = mutableListOf<(Result<Unit>) -> Unit>()
    private var startRetriesUsed = 0
    private var consecutiveRebuilds = 0
    private var interruptionCause = Cause.NONE
    private var engine: PhoneMicEngineHandle? = null

    // Batch-mode sink. `mode` is fixed on the idle->starting edge; encoder+writer are
    // created once at bring-up and survive every rebuild (the opus byte stream must stay
    // contiguous across interruptions), released only at stop/failStart after the
    // audio queue has drained.
    private var encoder: PhoneMicEncoderHandle? = null
    private var writer: PhoneMicWriterHandle? = null
    private var batchMarker = "omibatchphone"

    /** Set true on main when the mic is silenced; read on the audio queue to drop the
     * zeros a silenced AudioRecord delivers. The one and only cross-thread flag. */
    @Volatile
    private var emissionGated = false

    /** Latest client-silencing verdict for the live session (main only). Read by the
     * heartbeat stall rule so we never "rebuild" a session that is merely muted. */
    private var silenced = false

    /** Whether the current engine's session has appeared in the recording-config list at
     * least once. Until it has, an absent config means "not registered yet", not
     * "preempted" — so a transient startup callback cannot fake a silencing. */
    private var sawCurrentSession = false

    private var recordingListenerRegistered = false

    // Timers (main). Each guarded by an armed flag so a callback already dispatched
    // before cancel() drops harmlessly.
    private var heartbeatArmed = false
    private val heartbeatToken = Any()
    private var resumeTickerArmed = false
    private val resumeTickerToken = Any()
    private var rebuildScheduled = false
    private val rebuildToken = Any()

    // MARK: - Public surface (main-confined)

    fun bindFlutterApi(api: PhoneMicFlutterApi) {
        emitter.bind(PhoneMicFlutterApiEventSink(api))
    }

    /**
     * Called from MainActivity.onDestroy(isFinishing): the Flutter engine and the main
     * isolate die with the activity, so a live capture session must not outlive its
     * consumer. Run the full native stop (stream: teardown; batch: finalize + promote,
     * zero data loss) and unbind the emitter so any late post is dropped. Batch capture
     * does NOT continue across a task swipe in v1.
     */
    fun onFlutterEngineDestroyed() = runOnMain {
        // A restart queued behind a stop drain must die with its consumer — running it
        // would bring up a headless session (zombie mic) nobody can stop from the UI.
        restartModeAfterStop = null
        if (state != PhoneMicCaptureState.IDLE || stopDrainInFlight) {
            handleStop {}
        } else {
            ports.stopForegroundService()
        }
        emitter.unbind()
    }

    /** Test-only: bind the event sink directly (JVM replay harness). */
    internal fun bindEventSinkForReplay(sink: PhoneMicEventSink) {
        emitter.bind(sink)
    }


    fun start(mode: PhoneMicCaptureMode, sessionId: Long, callback: (Result<Unit>) -> Unit) = runOnMain {
        handleStart(mode, sessionId, callback)
    }

    fun stop(callback: (Result<Unit>) -> Unit) = runOnMain {
        handleStop(callback)
    }

    /** Host handler runs on main; a plain field read is correct. Non-idle == "busy" for
     * the arbiter (includes STARTING, unlike iOS — see the module notes). */
    val isRecording: Boolean
        get() = state != PhoneMicCaptureState.IDLE

    // MARK: - Command handling (main)

    private fun handleStart(mode: PhoneMicCaptureMode, sessionId: Long, callback: (Result<Unit>) -> Unit) {
        if (stopDrainInFlight) {
            // See [stopDrainInFlight]: queue a fresh session (with its id) for after
            // the drain, so the queued start comes up under the right identity.
            restartModeAfterStop = mode
            restartSessionIdAfterStop = sessionId
            pendingStartCallbacks.add(callback)
            return
        }
        when (state) {
            PhoneMicCaptureState.RUNNING -> {
                // Already live (a de-synced Dart restart): adopt the new id so all
                // future events carry it, re-emit RUNNING now so the caller's fresh Dart
                // session converges, and resolve. A late start() cannot re-select the
                // mode — the session keeps its original one.
                currentSessionId = sessionId
                emitter.emitState(PhoneMicCaptureState.RUNNING, sessionId)
                callback(Result.success(Unit))
            }

            PhoneMicCaptureState.STARTING,
            PhoneMicCaptureState.REBUILDING,
            PhoneMicCaptureState.INTERRUPTED -> {
                // Bring-up / recovery already in flight; adopt the new id so the eventual
                // transition emission carries it, and resolve together with it (keeping the
                // in-flight mode).
                currentSessionId = sessionId
                pendingStartCallbacks.add(callback)
                // INTERRUPTED has no imminent transition to piggyback the emission on, so
                // re-emit it now: the new Dart session shows the right state while the
                // resume ticker keeps probing.
                if (state == PhoneMicCaptureState.INTERRUPTED) {
                    emitter.emitState(PhoneMicCaptureState.INTERRUPTED, sessionId)
                }
            }

            PhoneMicCaptureState.IDLE -> {
                this.mode = mode
                currentSessionId = sessionId
                startRetriesUsed = 0
                pendingStop = false
                silenced = false
                emissionGated = false
                consecutiveRebuilds = 0
                interruptionCause = Cause.NONE
                pendingStartCallbacks.add(callback)
                enterState(PhoneMicCaptureState.STARTING)
                info("starting mode=${if (mode == PhoneMicCaptureMode.BATCH) "batch" else "stream"}")
                beginStartSequence()
            }
        }
    }

    private fun handleStop(callback: (Result<Unit>) -> Unit) {
        if (stopDrainInFlight) {
            // Already draining (state flips to IDLE only when it completes): resolve with it.
            pendingStopCallbacks.add(callback)
            return
        }
        when (state) {
            PhoneMicCaptureState.IDLE ->
                callback(Result.success(Unit))

            PhoneMicCaptureState.STARTING -> {
                // Permission is a synchronous pre-check, so the only STARTING pause is the
                // bring-up retry delay: defer to the next decision point, which aborts the
                // start (start_aborted) and resolves this stop.
                pendingStop = true
                pendingStopCallbacks.add(callback)
            }

            PhoneMicCaptureState.RUNNING,
            PhoneMicCaptureState.INTERRUPTED,
            PhoneMicCaptureState.REBUILDING -> {
                pendingStopCallbacks.add(callback)
                finishStop()
            }
        }
    }

    // MARK: - Bring-up (initial start)

    /** Steps 1-3 run once per session; step 4 (the engine) is retried by [performBringUp]. */
    private fun beginStartSequence() {
        // (1) Permission pre-check. Dart requests RECORD_AUDIO before calling start(), so
        // here it is a hard gate, not an async prompt.
        if (!ports.checkRecordAudioPermission()) {
            failStart("permission_denied", "RECORD_AUDIO permission is not granted")
            return
        }

        // (2) Batch resources (idempotent, reused across rebuilds).
        if (mode == PhoneMicCaptureMode.BATCH) {
            val failure = ensureBatchResources()
            if (failure != null) {
                failStart(failure, batchFailureMessage(failure))
                return
            }
        }

        // (3) Foreground service. A rejected promotion is non-fatal — capture continues
        // foreground-only rather than failing the start.
        if (!ports.startForegroundService()) {
            emitter.emitError(
                "foreground_service_failed",
                "foreground service promotion was rejected; capturing foreground-only",
                currentSessionId,
            )
        }

        // (4) Engine.
        performBringUp()
    }

    /** One bring-up attempt with the initial-start retry policy (<= [MAX_START_RETRIES]
     *  attempts at [BRING_UP_RETRY_DELAY_MS]); pendingStop is honoured before each try. */
    private fun performBringUp() {
        if (state != PhoneMicCaptureState.STARTING) return
        if (pendingStop) {
            failStart("start_aborted", "stop() superseded start()")
            return
        }
        val failure = attemptBringUp()
        if (failure == null) {
            enterRunning()
            return
        }
        if (startRetriesUsed < MAX_START_RETRIES) {
            startRetriesUsed++
            warn("bring-up failed ($failure), retry $startRetriesUsed")
            main.postDelayed(retryToken(), BRING_UP_RETRY_DELAY_MS) { performBringUp() }
        } else {
            failStart(failure, "engine bring-up failed after retries")
        }
    }

    /**
     * Build a brand-new engine under a fresh epoch and start it. Returns null on success,
     * else an error code. Precondition: no live engine (the resume/rebuild callers tear
     * down first; the initial/retry path has none). Never tears down here, so the epoch /
     * discardPartial ordering stays owned by [teardownEngine].
     */
    private fun attemptBringUp(): String? {
        val epoch = emitter.generation.advance()
        // Capture the session id alongside the epoch: a frame belongs to the session
        // that was current when this engine (its epoch) was built.
        val sid = currentSessionId
        val newEngine = ports.makeEngine(
            { chunk -> audioQueue.execute { handleChunkOnAudio(chunk, epoch, sid) } },
            { code -> main.post { handleReadError(code) } },
        )
        try {
            newEngine.start()
        } catch (t: Throwable) {
            warn("engine.start() failed", t)
            newEngine.teardown()
            return "engine_start_failed"
        }
        engine = newEngine
        ensureRecordingCallbackRegistered()
        seedSilenceState() // evaluate silencing against this session's id
        return null
    }

    private fun enterRunning() {
        cancelResumeTicker()
        interruptionCause = Cause.NONE
        emissionGated = false
        consecutiveRebuilds = 0 // first good bring-up is the reset point (not first good read: not observable from main)
        enterState(PhoneMicCaptureState.RUNNING)
        startHeartbeatIfNeeded() // armed once per session; survives interruptions/rebuilds
        resolvePendingStarts(Result.success(Unit))
        if (pendingStop) {
            finishStop()
            return
        }
        // Rare: brought up while already silenced — reflect it immediately.
        if (silenced) enterInterrupted(Cause.SILENCED)
    }

    private fun failStart(code: String, message: String) {
        warn("start failed: $code ($message)")
        emitter.generation.invalidate()
        cancelHeartbeat()
        cancelResumeTicker()
        cancelRebuildSchedule()
        unregisterRecordingCallback()
        engine?.teardown()
        engine = null
        // Null the batch fields synchronously (state goes IDLE synchronously below, so a
        // fast re-start must not reuse a to-be-destroyed encoder); finalize+destroy the
        // captured refs on the audio queue.
        val w = writer
        val enc = encoder
        writer = null
        encoder = null
        silenced = false
        emissionGated = false
        interruptionCause = Cause.NONE
        pendingStop = false
        state = PhoneMicCaptureState.IDLE
        resolvePendingStarts(Result.failure(PhoneMicPigeonError(code, message, null)))
        resolvePendingStops(Result.success(Unit)) // a stop pending during STARTING now succeeds
        if (w != null || enc != null) {
            audioQueue.execute {
                w?.closeNow("aborted")
                enc?.destroy()
            }
        }
        ports.stopForegroundService()
        emitter.emitState(PhoneMicCaptureState.IDLE, currentSessionId)
    }

    // MARK: - Stop

    /**
     * Async, drain-ordered stop. Main never blocks on I/O: teardown the engine (bounded
     * join), then finalize on the audio queue and flip to IDLE + resolve the callbacks
     * on the main hop after. Ordering guarantees:
     *  - executor FIFO puts closeNow after every pending chunk write;
     *  - main FIFO puts the IDLE emission after every already-posted (epoch-dead) frame;
     *  - the .bin is fsynced + promoted before the Pigeon stop() future resolves.
     */
    private fun finishStop() {
        pendingStop = false
        stopDrainInFlight = true
        cancelHeartbeat()
        cancelResumeTicker()
        cancelRebuildSchedule()
        interruptionCause = Cause.NONE
        emitter.generation.invalidate()
        unregisterRecordingCallback()
        teardownEngine()
        val w = writer
        val enc = encoder
        audioQueue.execute {
            w?.closeNow("manual")
            enc?.destroy()
            main.post {
                writer = null
                encoder = null
                silenced = false
                emissionGated = false
                ports.stopForegroundService()
                enterState(PhoneMicCaptureState.IDLE)
                stopDrainInFlight = false
                info("stopped")
                resolvePendingStops(Result.success(Unit))
                val restartMode = restartModeAfterStop
                val restartSessionId = restartSessionIdAfterStop
                restartModeAfterStop = null
                if (restartMode != null) {
                    // Starts queued during the drain are one fresh session (latest mode +
                    // id won), so it comes up under the queued id.
                    val queued = pendingStartCallbacks.toList()
                    pendingStartCallbacks.clear()
                    handleStart(restartMode, restartSessionId) { result -> queued.forEach { it(result) } }
                } else {
                    resolvePendingStarts(Result.failure(PhoneMicPigeonError("start_aborted", "capture stopped", null)))
                }
            }
        }
    }

    // MARK: - Chunk fan-out (audio queue)

    private fun handleChunkOnAudio(chunk: ByteArray, epoch: Long, sessionId: Long) {
        if (emissionGated) return // drop the zeros a silenced mic delivers
        when (mode) {
            PhoneMicCaptureMode.STREAM ->
                emitter.emitFrame(chunk, epoch, sessionId) // frame gate re-checked on main (iOS parity)

            PhoneMicCaptureMode.BATCH -> {
                val enc = encoder ?: return
                val w = writer ?: return
                val packets = enc.encode(chunk)
                if (packets.isNotEmpty()) w.append(packets, batchMarker)
                // Deliberately NOT epoch-gated: the executor FIFO already separates epochs
                // (teardown joins the read thread before discardPartial is enqueued, before
                // any new-epoch chunk), and dropping a late frame here would lose audio that
                // belongs before the split.
            }
        }
    }

    // MARK: - Heartbeat (1Hz, main; both modes; cancelled at stop)

    private fun startHeartbeatIfNeeded() {
        if (heartbeatArmed) return
        heartbeatArmed = true
        main.postDelayed(heartbeatToken, HEARTBEAT_INTERVAL_MS) { runHeartbeat() }
    }

    private fun cancelHeartbeat() {
        heartbeatArmed = false
        main.cancel(heartbeatToken)
    }

    private fun runHeartbeat() {
        if (!heartbeatArmed) return
        onHeartbeatTick()
        if (heartbeatArmed) main.postDelayed(heartbeatToken, HEARTBEAT_INTERVAL_MS) { runHeartbeat() }
    }

    private fun onHeartbeatTick() {
        val audioMode = ports.audioMode()

        // Rule 2 (resume): a mode-poll interruption whose call mode has cleared -> rebuild.
        if (interruptionCause == Cause.MODE && !inCall(audioMode)) {
            attemptResume()
        }

        // Rules 1 & 2 (detect): read the engine FRESH so a resume this same tick is not
        // re-flagged as a stall.
        run {
            val eng = engine ?: return@run
            if (state != PhoneMicCaptureState.RUNNING) return@run
            val stale = main.uptimeMillis() - eng.lastDataUptimeMs >= STALL_THRESHOLD_MS
            if (!stale) return@run
            when {
                // Rule 2: a call mode is up and data stalled -> interruption, not a rebuild.
                // Mode alone never drives this (Omi's own Twilio calls set
                // MODE_IN_COMMUNICATION while data still flows -> not stale); it only
                // corroborates a genuine data stall.
                inCall(audioMode) -> enterInterrupted(Cause.MODE)
                // Rule 1: genuine stall on a normal route -> self-heal by rebuild.
                !silenced -> beginRebuild("stall")
            }
        }

        // Rule 3 (batch progress + storage-full edge): async double-hop, never blocks main.
        if (mode == PhoneMicCaptureMode.BATCH && state != PhoneMicCaptureState.IDLE) {
            val w = writer ?: return
            val sid = currentSessionId // read on main before the queue hop
            audioQueue.execute {
                val frames = w.sessionFramesWritten
                val edge = w.consumeStorageFullTransition()
                main.post {
                    if (edge) emitter.emitError("batch_storage_full", "free space below the batch writer minimum", sid)
                    // 320 samples per opus frame @16kHz == 20ms == 0.02s.
                    emitter.emitBatchProgress(frames * 0.02, sid)
                }
            }
        }
    }

    private fun inCall(audioMode: Int): Boolean =
        audioMode == AudioManager.MODE_IN_CALL || audioMode == AudioManager.MODE_IN_COMMUNICATION

    // MARK: - Interruption via client silencing (recording-config listener)

    /**
     * Registered once per session, kept across rebuilds. An unprivileged app only sees its
     * own recording configs, and every rebuild mints a NEW session id, so the handler
     * always re-matches against the CURRENT engine's [PhoneMicEngineHandle.audioSessionId]
     * read live. Callbacks are delivered on main.
     */
    private fun ensureRecordingCallbackRegistered() {
        if (recordingListenerRegistered) return
        recordingListenerRegistered = true
        ports.setRecordingConfigListener { configs -> onRecordingConfigsChanged(configs) }
    }

    private fun unregisterRecordingCallback() {
        if (!recordingListenerRegistered) return
        recordingListenerRegistered = false
        ports.setRecordingConfigListener(null)
    }

    /** Seed [silenced] for a freshly brought-up session. Absence here means "not
     * registered yet" (assume healthy), unlike the live callback below. Does NOT touch
     * [emissionGated] — [enterRunning] re-checks [silenced] to gate if truly muted. */
    private fun seedSilenceState() {
        sawCurrentSession = false
        val eng = engine ?: return
        val ours = ports.activeRecordingConfigs().firstOrNull { it.clientAudioSessionId == eng.audioSessionId }
        if (ours != null) {
            sawCurrentSession = true
            silenced = ours.clientSilenced
        } else {
            silenced = false
        }
    }

    private fun onRecordingConfigsChanged(configs: List<PhoneMicRecordingConfig>) {
        val eng = engine ?: return
        val ours = configs.firstOrNull { it.clientAudioSessionId == eng.audioSessionId }
        val nowSilenced = if (ours != null) {
            sawCurrentSession = true
            ours.clientSilenced
        } else {
            // Full preemption can drop our entry entirely instead of flipping the flag —
            // but only treat absence as silenced once we have actually seen the session,
            // so a pre-registration startup callback can't fake it.
            sawCurrentSession
        }
        applySilence(nowSilenced)
    }

    private fun applySilence(nowSilenced: Boolean) {
        if (nowSilenced == silenced) return
        silenced = nowSilenced
        when {
            nowSilenced && state == PhoneMicCaptureState.RUNNING ->
                enterInterrupted(Cause.SILENCED)

            !nowSilenced && state == PhoneMicCaptureState.INTERRUPTED && interruptionCause == Cause.SILENCED ->
                resumeToRunning()
            // Other combinations only update `silenced` (read by the stall rule); the gate
            // is owned by enterInterrupted/resumeToRunning/beginRebuild so it never races a
            // rebuild's first frames.
        }
    }

    // MARK: - State transitions

    /** Enter interruption. The engine STAYS ALIVE for SILENCED (drops zeros, batch progress
     * freezes = iOS semantics) and for MODE (starved but rebuilt on resume); for REBUILD
     * it was already torn down by [beginRebuild]. */
    private fun enterInterrupted(cause: Cause) {
        interruptionCause = cause
        enterState(PhoneMicCaptureState.INTERRUPTED)
        if (cause == Cause.SILENCED) {
            emissionGated = true
            audioQueue.execute { encoder?.discardPartial() } // never splice across the gap
        }
        info("interrupted (cause=$cause)")
    }

    /** In-place resume from a SILENCED interruption — the engine never died, so no rebuild. */
    private fun resumeToRunning() {
        cancelResumeTicker()
        interruptionCause = Cause.NONE
        emissionGated = false
        consecutiveRebuilds = 0
        enterState(PhoneMicCaptureState.RUNNING)
        info("resumed after silencing")
    }

    /**
     * Probe a rebuild-resume from INTERRUPTED (MODE poll cleared, or the 3s resume ticker).
     * Tears down the old/starved engine, then a fresh bring-up. Failure is silent by design
     * (during a real call this keeps failing until it ends) — the probing source restores
     * the cause so it keeps retrying and never terminally gives up.
     */
    private fun attemptResume() {
        if (state != PhoneMicCaptureState.INTERRUPTED) return
        val priorCause = interruptionCause
        teardownEngine()
        emissionGated = false
        if (attemptBringUp() == null) {
            enterRunning()
        } else {
            interruptionCause = priorCause // keep probing under the same cause
        }
    }

    /** Self-heal from a RUNNING stall / read error: drop to REBUILDING and rebuild after a
     * short backoff so the HAL can settle before we reacquire the AudioRecord. */
    private fun beginRebuild(reason: String) {
        info("rebuilding ($reason)")
        emissionGated = false
        interruptionCause = Cause.NONE
        enterState(PhoneMicCaptureState.REBUILDING)
        teardownEngine() // invalidate epoch + teardown + discardPartial before the new engine feeds
        scheduleRebuild()
    }

    private fun scheduleRebuild() {
        if (rebuildScheduled) return
        rebuildScheduled = true
        main.postDelayed(rebuildToken, REBUILD_BACKOFF_MS) { runScheduledRebuild() }
    }

    private fun cancelRebuildSchedule() {
        rebuildScheduled = false
        main.cancel(rebuildToken)
    }

    private fun runScheduledRebuild() {
        rebuildScheduled = false
        if (state != PhoneMicCaptureState.REBUILDING) return
        if (attemptBringUp() == null) {
            enterRunning() // resets consecutiveRebuilds
            return
        }
        consecutiveRebuilds++
        if (consecutiveRebuilds >= MAX_CONSECUTIVE_REBUILDS) {
            // Give up self-heal; fall to INTERRUPTED and let the 3s resume ticker probe
            // forever. Never terminally gives up.
            enterInterrupted(Cause.REBUILD)
            emitter.emitError("rebuild_failed", "capture rebuild failed repeatedly; probing to recover in the background", currentSessionId)
            armResumeTicker()
        } else {
            scheduleRebuild()
        }
    }

    private fun handleReadError(code: Int) {
        // Stale errors from a torn-down engine arrive with state != RUNNING and are ignored;
        // a genuine read failure on the live engine self-heals.
        if (state != PhoneMicCaptureState.RUNNING) return
        warn("read error ($code)")
        beginRebuild("read_error")
    }

    // MARK: - Resume ticker (3s, main; armed only after rebuild exhaustion)

    private fun armResumeTicker() {
        cancelResumeTicker()
        resumeTickerArmed = true
        main.postDelayed(resumeTickerToken, RESUME_TICK_INTERVAL_MS) { runResumeTick() }
    }

    private fun cancelResumeTicker() {
        resumeTickerArmed = false
        main.cancel(resumeTickerToken)
    }

    private fun runResumeTick() {
        if (!resumeTickerArmed) return
        attemptResume() // success -> enterRunning -> cancelResumeTicker
        if (resumeTickerArmed && state == PhoneMicCaptureState.INTERRUPTED) {
            main.postDelayed(resumeTickerToken, RESUME_TICK_INTERVAL_MS) { runResumeTick() }
        }
    }

    // MARK: - Teardown helper (main)

    /**
     * Invalidate the epoch (happens-before the emitter drops in-flight frames), tear down
     * the engine (stop -> bounded join -> release), then discard the encoder's sub-frame
     * remainder on the audio queue. The discardPartial is enqueued AFTER the read thread
     * is joined, so it lands between epochs and pre/post-gap audio is never spliced.
     */
    private fun teardownEngine() {
        emitter.generation.invalidate()
        engine?.teardown()
        engine = null
        audioQueue.execute { encoder?.discardPartial() }
    }

    // MARK: - Batch resources

    /** Idempotent: created on the first bring-up, reused across rebuilds/resumes, released
     * only at stop/failStart. Returns an error code on failure (a missing dir or
     * unbuildable encoder won't fix on retry, but the code surfaces as the start error). */
    private fun ensureBatchResources(): String? {
        if (encoder != null && writer != null) return null
        val dir = ports.batchDirectory() ?: return "batch_dir_unavailable"
        val enc = ports.makeEncoder() ?: return "opus_init_failed"
        batchMarker = if (ports.batchAutoMarker()) "omibatchphoneauto" else "omibatchphone"
        encoder = enc
        writer = ports.makeWriter(dir)
        return null
    }

    private fun batchFailureMessage(code: String): String = when (code) {
        "batch_dir_unavailable" -> "flutter.batchAudioDir is unset or empty"
        "opus_init_failed" -> "could not create the native opus encoder"
        else -> code
    }

    // MARK: - Pending completion fan-out (main)

    private fun resolvePendingStarts(result: Result<Unit>) {
        if (pendingStartCallbacks.isEmpty()) return
        val callbacks = pendingStartCallbacks.toList()
        pendingStartCallbacks.clear()
        callbacks.forEach { it(result) }
    }

    private fun resolvePendingStops(result: Result<Unit>) {
        if (pendingStopCallbacks.isEmpty()) return
        val callbacks = pendingStopCallbacks.toList()
        pendingStopCallbacks.clear()
        callbacks.forEach { it(result) }
    }

    // MARK: - Helpers

    private fun enterState(newState: PhoneMicCaptureState) {
        state = newState
        emitter.emitState(newState, currentSessionId)
    }

    private fun runOnMain(block: () -> Unit) {
        if (main.isCurrent) block() else main.post { block() }
    }

    private fun info(message: String) = ports.log(PhoneMicLogLevel.INFO, TAG, message, null)

    private fun warn(message: String, error: Throwable? = null) = ports.log(PhoneMicLogLevel.WARN, TAG, message, error)

    /** Per-attempt retry token (the armed state machine makes exact cancel non-critical). */
    private fun retryToken(): Any = retryScratch

    companion object {
        private const val TAG = "PhoneMic.Controller"

        // iOS-parity constants (shared timings) plus the Android rebuild backoff.
        private const val BRING_UP_RETRY_DELAY_MS = 350L
        private const val MAX_START_RETRIES = 2
        private const val RESUME_TICK_INTERVAL_MS = 3000L
        private const val HEARTBEAT_INTERVAL_MS = 1000L
        private const val REBUILD_BACKOFF_MS = 200L
        private const val MAX_CONSECUTIVE_REBUILDS = 3
        private const val STALL_THRESHOLD_MS = 2000L

        private val retryScratch = Any()

        @Volatile
        private var _instance: PhoneMicController? = null

        val instance: PhoneMicController
            get() = _instance ?: throw IllegalStateException("PhoneMicController not initialized")

        val isInitialized: Boolean
            get() = _instance != null

        fun initialize(application: Application) {
            if (_instance == null) {
                synchronized(this) {
                    if (_instance == null) {
                        _instance = PhoneMicController(PhoneMicControllerPorts.production(application))
                    }
                }
            }
        }

        /** Test-only construction: the JVM replay harness injects its ports. */
        internal fun forReplay(ports: PhoneMicControllerPorts): PhoneMicController = PhoneMicController(ports)
    }
}
