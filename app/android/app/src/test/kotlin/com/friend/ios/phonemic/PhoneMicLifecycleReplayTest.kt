package com.friend.ios.phonemic

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.PriorityQueue

/**
 * Replays the canonical `phone-mic-native-events/v1` vectors (the same JSON
 * fixtures the Dart guard test and the iOS ruby harness consume) through the
 * PRODUCTION [PhoneMicController] + [PhoneMicEventEmitter] on the JVM
 * (SCA-491 / C5). Only OS audio/radio I/O is faked via
 * [PhoneMicControllerPorts]; the lifecycle policy under test is the shipping
 * code. The oracle is strict sequence equality against the vector (minus the
 * stale-stimulus steps, which must be DROPPED), so a broken epoch gate,
 * session adoption, or terminal cleanup fails the run instead of passing
 * vacuously.
 */
class PhoneMicLifecycleReplayTest {

    // ── Virtual main loop ────────────────────────────────────────────────────

    private class VirtualMainLoop : PhoneMicMainLoop {
        private class Task(val time: Long, val seq: Long, val token: Any?, val block: () -> Unit)

        private var seq = 0L
        private var now = 0L
        private val queue = PriorityQueue<Task>(compareBy({ it.time }, { it.seq }))
        private var running = false

        override val isCurrent: Boolean
            get() = running

        override fun post(block: () -> Unit) {
            queue.add(Task(now, seq++, null, block))
        }

        override fun postDelayed(token: Any, delayMs: Long, block: () -> Unit) {
            queue.add(Task(now + delayMs, seq++, token, block))
        }

        override fun cancel(token: Any) {
            // The controller's armed-flag discipline makes late callbacks drop
            // harmlessly; cancellation here is hygiene only (removeCallbacks parity).
            queue.removeIf { it.token === token }
        }

        override fun uptimeMillis(): Long = now

        fun runUntilIdle() {
            running = true
            try {
                while (queue.isNotEmpty() && queue.peek().time <= now) {
                    queue.poll().block()
                }
            } finally {
                running = false
            }
        }

        fun advanceBy(ms: Long) {
            val target = now + ms
            running = true
            try {
                while (queue.isNotEmpty() && queue.peek().time <= target) {
                    now = queue.peek().time
                    queue.poll().block()
                }
            } finally {
                running = false
            }
            now = target
        }
    }

    // ── Manual serial audio queue ────────────────────────────────────────────

    private class ManualQueue : PhoneMicTaskQueue {
        private val tasks = ArrayDeque<() -> Unit>()

        override fun execute(task: () -> Unit) {
            tasks.add(task)
        }

        fun runAll() {
            while (tasks.isNotEmpty()) tasks.removeFirst()()
        }
    }

    // ── Recorded sink ────────────────────────────────────────────────────────

    private class Delivery(val kind: String, val sessionId: Long, val state: String?, val frame: ByteArray?) {
        override fun toString(): String = "$kind@$sessionId:${state ?: frame?.size ?: ""}"
    }

    private class RecordingSink : PhoneMicEventSink {
        val deliveries = mutableListOf<Delivery>()

        override fun onAudioFrame(pcm16leMono16k: ByteArray, sessionId: Long) {
            deliveries.add(Delivery("audioFrame", sessionId, null, pcm16leMono16k))
        }

        override fun onStateChanged(state: PhoneMicCaptureState, sessionId: Long) {
            deliveries.add(Delivery("stateChanged", sessionId, state.name.lowercase(), null))
        }

        override fun onCaptureError(code: String, message: String, sessionId: Long) {
            deliveries.add(Delivery("captureError:$code", sessionId, null, null))
        }

        override fun onBatchProgress(capturedSeconds: Double, sessionId: Long) {
            deliveries.add(Delivery("batchProgress", sessionId, null, null))
        }
    }

    // ── Fake engine ──────────────────────────────────────────────────────────

    private class FakeEngine(
        private val loop: VirtualMainLoop,
        private val onChunk: (ByteArray) -> Unit,
        private val onReadError: (Int) -> Unit,
        startFailuresRemaining: Int,
    ) : PhoneMicEngineHandle {
        var startFailures = startFailuresRemaining
        var lastData = 0L

        override fun start() {
            if (startFailures > 0) {
                startFailures -= 1
                throw IllegalStateException("simulated AudioRecord start failure")
            }
            lastData = loop.uptimeMillis()
        }

        override fun teardown() {}

        override val audioSessionId: Int = 1000 + (instanceCount++)
        override val lastDataUptimeMs: Long
            get() = lastData

        fun fireChunk(chunk: ByteArray) {
            lastData = loop.uptimeMillis()
            onChunk(chunk)
        }

        fun fireReadError() = onReadError(-38)

        companion object {
            var instanceCount = 0
        }
    }

    // ── Fake ports ───────────────────────────────────────────────────────────

    private class FakePorts(
        val loop: VirtualMainLoop,
        val audio: ManualQueue,
        var permissionGranted: Boolean = true,
        var engineStartFailures: Int = 0,
    ) {
        val sink = RecordingSink()
        val engines = mutableListOf<FakeEngine>()
        var recordingListener: ((List<PhoneMicRecordingConfig>) -> Unit)? = null
        var foregroundStarts = 0
        var foregroundStops = 0
        val logs = mutableListOf<String>()

        fun build(): PhoneMicControllerPorts {
            val self = this
            return PhoneMicControllerPorts(
                main = self.loop,
                audioQueue = self.audio,
                checkRecordAudioPermission = { self.permissionGranted },
                audioMode = { android.media.AudioManager.MODE_NORMAL },
                activeRecordingConfigs = { emptyList() },
                setRecordingConfigListener = { listener -> self.recordingListener = listener },
                startForegroundService = {
                    self.foregroundStarts++
                    true
                },
                stopForegroundService = { self.foregroundStops++ },
                makeEngine = { onChunk, onReadError ->
                    FakeEngine(self.loop, onChunk, onReadError, self.engineStartFailures)
                        .also { self.engines.add(it) }
                },
                batchDirectory = { null },
                batchAutoMarker = { false },
                makeEncoder = { null },
                makeWriter = { error("stream-mode vectors never build a batch writer") },
                log = { _, _, message, _ -> self.logs.add(message) },
            )
        }

        fun deliverConfigs(vararg configs: PhoneMicRecordingConfig) {
            recordingListener?.invoke(configs.toList())
        }
    }

    // ── Vectors ──────────────────────────────────────────────────────────────

    private data class VectorEvent(val kind: String, val sessionId: Long, val state: String?, val frame: ByteArray?)

    private data class Vector(val id: String, val startSessionId: Long, val events: List<VectorEvent>)

    private fun loadVectors(): Map<String, Vector> {
        val dir = fixturesDir()
        val vectors = dir.listFiles { f -> f.extension == "json" }!!.map { file ->
            val doc = JSONObject(file.readText())
            val id = doc.getString("id")
            check(doc.getString("schema_version") == "phone-mic-native-events/v1") { "$id: wrong schema" }
            val events = doc.getJSONArray("events").let { array ->
                (0 until array.length()).map { i ->
                    val raw = array.getJSONObject(i)
                    VectorEvent(
                        kind = raw.getString("kind"),
                        sessionId = raw.getLong("session_id"),
                        state = raw.optString("state").takeIf { it.isNotEmpty() },
                        frame = raw.optString("pcm_frame_base64").takeIf { it.isNotEmpty() }
                            ?.let { java.util.Base64.getDecoder().decode(it) },
                    )
                }
            }
            Vector(id, doc.getLong("start_session_id"), events)
        }.associateBy { it.id }
        check(vectors.size == 8) { "expected the canonical 8 vectors, found ${vectors.size}" }
        return vectors
    }

    private fun fixturesDir(): File {
        System.getProperty("omi.phoneMicVectors")?.let { return File(it) }
        var dir: File? = File(System.getProperty("user.dir") ?: ".")
        repeat(6) {
            val candidate = File(dir!!, "app/test/fixtures/phone_mic_native_events")
            if (candidate.isDirectory) return candidate
            dir = dir.parentFile
        }
        error("cannot locate app/test/fixtures/phone_mic_native_events from user.dir=${System.getProperty("user.dir")}")
    }

    // ── Comparator ───────────────────────────────────────────────────────────

    private fun assertDeliveriesMatch(
        vector: Vector,
        staleIndices: Set<Int>,
        delivered: List<Delivery>,
        label: String,
    ) {
        val expected = vector.events.mapIndexedNotNull { index, event ->
            if (index in staleIndices) return@mapIndexedNotNull null
            when (event.kind) {
                "stateChanged" -> Delivery("stateChanged", event.sessionId, event.state, null)
                "audioFrame" -> Delivery("audioFrame", event.sessionId, null, event.frame)
                else -> error("${vector.id}: unexpected kind ${event.kind}")
            }
        }
        assertTrue(
            "$label: delivered ${delivered.size} events, expected ${expected.size}\n" +
                "delivered: $delivered\nexpected: $expected",
            delivered.size == expected.size,
        )
        for ((got, want) in delivered.zip(expected)) {
            val framesMatch = when {
                got.frame == null && want.frame == null -> true
                got.frame != null && want.frame != null -> got.frame!!.contentEquals(want.frame!!)
                else -> false
            }
            assertTrue(
                "$label: mismatch got $got want $want",
                got.kind == want.kind && got.sessionId == want.sessionId && got.state == want.state && framesMatch,
            )
        }
        if (staleIndices.isNotEmpty()) {
            // Oracle detection proof: an ungated emitter would deliver the stale
            // steps too, and this exact comparator would then fail on the count.
            assertEquals("$label: stale steps leaked into delivery", vector.events.size - staleIndices.size, delivered.size)
        }
    }

    private fun assertNoFrameAfterIdle(delivered: List<Delivery>, label: String) {
        val idleAt = delivered.indexOfLast { it.kind == "stateChanged" && it.state == "idle" }
        if (idleAt >= 0) {
            assertTrue(
                "$label: a frame was delivered after the terminal idle event",
                delivered.drop(idleAt + 1).none { it.kind == "audioFrame" },
            )
        }
    }

    private fun flush(audio: ManualQueue, loop: VirtualMainLoop) {
        audio.runAll()
        loop.runUntilIdle()
    }

    private fun start(controller: PhoneMicController, loop: VirtualMainLoop, sessionId: Long): Result<Unit> {
        val box = arrayOfNulls<Result<Unit>>(1)
        controller.start(PhoneMicCaptureMode.STREAM, sessionId) { box[0] = it }
        loop.runUntilIdle()
        return box[0] ?: error("start did not resolve")
    }

    private fun stop(controller: PhoneMicController, world: FakePorts): Result<Unit> {
        val box = arrayOfNulls<Result<Unit>>(1)
        controller.stop { box[0] = it }
        // stop is drain-ordered: main posts handleStop -> the audio queue
        // finalizes -> the main hop resolves IDLE + the stop callback.
        world.loop.runUntilIdle()
        world.audio.runAll()
        world.loop.runUntilIdle()
        return box[0] ?: error("stop did not resolve")
    }

    private fun replayController(world: FakePorts): PhoneMicController =
        PhoneMicController.forReplay(world.build()).also { it.bindEventSinkForReplay(world.sink) }

    private fun frame(vector: Vector, index: Int): ByteArray = vector.events[index].frame!!

    // ── The eight canonical vectors ──────────────────────────────────────────

    @Test
    fun `start-running delivers starting then running with frames under the live epoch`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue())
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-start-running")
        val result = start(controller, loop, vector.startSessionId)
        assertTrue("start must succeed, got $result", result.isSuccess)
        world.engines[0].fireChunk(frame(vector, 2))
        world.engines[0].fireChunk(frame(vector, 3))
        flush(world.audio, loop)
        assertDeliveriesMatch(vector, emptySet(), world.sink.deliveries, "start-running")
    }

    @Test
    fun `interruption-resume mirrors silenced-flag recovery in place`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue())
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-interruption-resume")
        start(controller, loop, vector.startSessionId)
        world.engines[0].fireChunk(frame(vector, 2))
        flush(world.audio, loop)
        // Silencing flips us INTERRUPTED (engine stays alive — Android resumes in place).
        world.deliverConfigs(PhoneMicRecordingConfig(world.engines[0].audioSessionId, clientSilenced = true))
        loop.runUntilIdle()
        world.deliverConfigs(PhoneMicRecordingConfig(world.engines[0].audioSessionId, clientSilenced = false))
        loop.runUntilIdle()
        world.engines[0].fireChunk(frame(vector, 5))
        flush(world.audio, loop)
        assertEquals("silence resume must NOT rebuild the engine", 1, world.engines.size)
        assertTrue(stop(controller, world).isSuccess)
        flush(world.audio, loop)
        assertDeliveriesMatch(vector, emptySet(), world.sink.deliveries, "interruption-resume")
        assertNoFrameAfterIdle(world.sink.deliveries, "interruption-resume")
    }

    @Test
    fun `rebuild self-heals a read error under a fresh epoch`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue())
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-rebuild")
        start(controller, loop, vector.startSessionId)
        world.engines[0].fireChunk(frame(vector, 2))
        flush(world.audio, loop)
        world.engines[0].fireReadError()
        loop.runUntilIdle()
        loop.advanceBy(250) // REBUILD_BACKOFF_MS = 200ms, virtual
        loop.runUntilIdle()
        assertEquals("rebuild must build a fresh engine", 2, world.engines.size)
        world.engines[1].fireChunk(frame(vector, 5))
        flush(world.audio, loop)
        assertTrue(stop(controller, world).isSuccess)
        flush(world.audio, loop)
        assertDeliveriesMatch(vector, emptySet(), world.sink.deliveries, "rebuild")
        assertNoFrameAfterIdle(world.sink.deliveries, "rebuild")
    }

    @Test
    fun `stale-event drops the old epoch's late frame across a rebuild`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue())
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-stale-event")
        start(controller, loop, vector.startSessionId)
        world.engines[0].fireChunk(frame(vector, 2))
        flush(world.audio, loop)
        world.engines[0].fireReadError()
        loop.runUntilIdle()
        loop.advanceBy(250)
        loop.runUntilIdle()
        // Stale stimulus: the pre-rebuild engine's chunk arrives late — must be dropped.
        world.engines[0].fireChunk(frame(vector, 4))
        // Fresh frame under the new epoch is delivered normally.
        world.engines[1].fireChunk(frame(vector, 6))
        flush(world.audio, loop)
        assertTrue(stop(controller, world).isSuccess)
        flush(world.audio, loop)
        // Vector index 4 is the stale frame (between rebuilding and running).
        assertDeliveriesMatch(vector, setOf(4), world.sink.deliveries, "stale-event")
        assertNoFrameAfterIdle(world.sink.deliveries, "stale-event")
    }

    @Test
    fun `idle-stop resolves idle and a late frame from the dead epoch never lands`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue())
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-idle-stop")
        start(controller, loop, vector.startSessionId)
        world.engines[0].fireChunk(frame(vector, 2))
        flush(world.audio, loop)
        assertTrue(stop(controller, world).isSuccess)
        flush(world.audio, loop)
        // Terminal-cleanup stimulus: the trailing vector frame after idle.
        world.engines[0].fireChunk(frame(vector, 4))
        flush(world.audio, loop)
        assertDeliveriesMatch(vector, setOf(4), world.sink.deliveries, "idle-stop")
        assertNoFrameAfterIdle(world.sink.deliveries, "idle-stop")
    }

    @Test
    fun `start-error-permission fails with the exact code and terminates idle`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue()).also { it.permissionGranted = false }
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-start-error-permission")
        val result = start(controller, loop, vector.startSessionId)
        val exception = result.exceptionOrNull()
        assertTrue("expected failure, got $result", exception is PhoneMicPigeonError)
        assertEquals("permission_denied", (exception as PhoneMicPigeonError).code)
        assertDeliveriesMatch(vector, emptySet(), world.sink.deliveries, "start-error-permission")
    }

    @Test
    fun `start-error-engine exhausts the retry budget then fails`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue()).also { it.engineStartFailures = 3 }
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-start-error-engine")
        val box = arrayOfNulls<Result<Unit>>(1)
        controller.start(PhoneMicCaptureMode.STREAM, vector.startSessionId) { box[0] = it }
        loop.advanceBy(1500) // three attempts at 350ms retry spacing, virtual time
        loop.runUntilIdle()
        val exception = box[0]!!.exceptionOrNull()
        assertTrue("expected failure, got ${box[0]}", exception is PhoneMicPigeonError)
        assertEquals("engine_start_failed", (exception as PhoneMicPigeonError).code)
        assertEquals("the retry policy must attempt exactly 1+2 bring-ups", 3, world.engines.size)
        assertDeliveriesMatch(vector, emptySet(), world.sink.deliveries, "start-error-engine")
    }

    @Test
    fun `session-adoption re-emits under the new id and the next engine bakes it`() {
        val loop = VirtualMainLoop()
        val world = FakePorts(loop, ManualQueue())
        val controller = replayController(world)
        val vector = loadVectors().getValue("phone-mic-session-adoption")
        val original = vector.startSessionId
        val adopted = original + 16
        assertTrue(start(controller, loop, original).isSuccess)
        world.engines[0].fireChunk(frame(vector, 2))
        flush(world.audio, loop)
        // Second start() onto the live session: adopt + re-emit RUNNING.
        assertTrue("adoption start must piggyback successfully", start(controller, loop, adopted).isSuccess)
        // Frame from the pre-adoption engine closure: keeps the original id.
        world.engines[0].fireChunk(frame(vector, 4))
        flush(world.audio, loop)
        // Rebuild: REBUILDING/RUNNING carry the adopted id; the new engine bakes it.
        world.engines[0].fireReadError()
        loop.runUntilIdle()
        loop.advanceBy(250)
        loop.runUntilIdle()
        world.engines[1].fireChunk(frame(vector, 7))
        flush(world.audio, loop)
        assertTrue(stop(controller, world).isSuccess)
        flush(world.audio, loop)
        assertDeliveriesMatch(vector, emptySet(), world.sink.deliveries, "session-adoption")
    }
}
