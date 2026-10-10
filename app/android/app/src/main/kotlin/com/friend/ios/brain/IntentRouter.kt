package com.friend.ios.brain

import android.content.Context
import android.util.Log
import com.google.ai.edge.litert.Accelerator
import com.google.ai.edge.litert.CompiledModel
import com.google.ai.edge.litert.TensorBuffer
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.sqrt

/**
 * The local brain's routing layer: maps a free-text request to a phone action, or
 * declines.
 *
 * Why this exists rather than a language model: measured on a Samsung SM-A145F
 * (Exynos 3830, 3.5 GB RAM), a 270M function-calling LiteRT-LM bundle routed tool
 * calls at 22% with 72% refusals, at 3120 ms and 983 MB peak RSS per prompt. It
 * was failing at *routing* -- matching prompt tokens against action vocabulary --
 * not at generation. MiniLM-L6-v2 over the same prompts: 67% on a held-out set,
 * ~600 ms, 285 MB peak RSS. Peak RSS is `VmHWM`; a heap delta is not a memory
 * measurement because the collector runs between samples.
 *
 * Three properties of the scoring are the transferable part:
 *
 *  1. Prototypes, not one embedded description per action. Users phrase requests
 *     many ways; max cosine over a prototype bank is the largest accuracy lever.
 *  2. `no_action` competes as a real class. An argmax over actions has no "none
 *     of these" and will invent an answer for every input.
 *  3. The margin is returned so the caller can decide act-vs-ask. That decision,
 *     not the accuracy number, is what an agent actually faces.
 *
 * Two documented limits, both reproduced by the shipped action set:
 *
 *  - Antonyms. "switch the torch on" and "switch the torch off" sit at cosine
 *    0.949. Embeddings encode topic, not polarity, so on/off pairs need a lexical
 *    check; more prototypes do not separate them.
 *  - Negation inverts. Asked "do not switch the torch on" a router will plausibly
 *    pick the off action. [NEGATION] gates ahead of the model for that reason.
 *
 * The reference implementation is google-ai-edge/litert-samples PR #383
 * (`samples/litert/intent_router`) and the measurement record is issue #382.
 */
class IntentRouter(private val context: Context) {

    companion object {
        private const val TAG = "IntentRouter"
        private const val MODEL = "minilm.tflite"
        private const val TOKENS = "minilm_tokens.json"
        private const val SEQ = 128
        private const val DIM = 384

        /**
         * Decline when the winner is this close to the best alternative,
         * including `no_action`. Calibrated on one device with one action set;
         * treat as a starting point, not a constant.
         */
        private const val ABSTAIN_MARGIN = 0.02f

        /** Emitted when the router declines, or when a request is negated. */
        const val NO_ACTION = "no_action"

        /** Emitted when the request is to launch another app. */
        const val OPEN_APP = "open_app"

        /**
         * A prohibition means do not act. Held-out measurement: unguarded, 4 of 5
         * negated requests executed the inverse of the instruction, which for an
         * agent is worse than any accuracy miss.
         */
        /**
         * A prohibition means do not act, so the match has to cover every way English
         * negates. The bare `not` alternative is what catches "I meant not to turn on
         * the flashlight", which the other forms miss entirely.
         *
         * Bare `not` is deliberately broad rather than clever about scope. The cost is
         * false positives on sentences that merely mention negation -- "I am not sure
         * whether I should set a timer" declines instead of scoring -- and that is the
         * right trade for this class of error. Held-out measurement on the shipped
         * action set: unguarded, 4 of 5 negated requests executed the inverse of the
         * instruction, which for an agent is worse than any accuracy miss. A miss
         * costs one clarifying question; an inverse execution acts on the opposite of
         * what was asked.
         */
        private val NEGATION =
            Regex("\\b(?:don'?t|do\\s+not|not|never|no\\s+need|without\\s+doing)\\b", RegexOption.IGNORE_CASE)

        /**
         * Whether the hard guard should fire. Exposed so the negation rule can be
         * tested without a model: this is a safety gate, and the review that added the
         * bare "not" alternative is exactly the kind of one-line regex edit that needs
         * a test pinning the sentence it was written for.
         */
        internal fun isNegated(text: String): Boolean = NEGATION.containsMatchIn(text)
    }

    data class Decision(
        val action: String,
        val margin: Double,
        val declined: Boolean,
        val negated: Boolean,
        val runnerUp: String,
        val latencyMs: Long,
        val reason: String,
    )

    private var model: CompiledModel? = null
    private var inputBuffers: List<TensorBuffer>? = null
    private var outputBuffers: List<TensorBuffer>? = null
    private var tokenizer: BertWordPiece? = null

    /** action name -> prototype vectors. */
    private val prototypes = LinkedHashMap<String, List<FloatArray>>()
    private var ready = false
    private var initError: String? = null

    val isReady: Boolean get() = ready

    /** Blocking load. Call off the UI thread; takes a few seconds on a budget phone. */
    @Synchronized
    fun load() {
        if (ready) return
        if (initError != null) throw IllegalStateException(initError)

        try {
            val created =
                CompiledModel.create(
                    context.assets,
                    MODEL,
                    CompiledModel.Options(Accelerator.CPU),
                    null,
                )
            model = created
            inputBuffers = created.createInputBuffers()
            outputBuffers = created.createOutputBuffers()

            tokenizer =
                BertWordPiece(
                    context.assets.open("vocab.txt").bufferedReader().readText().lineSequence()
                        .mapIndexed { index, line -> line to index }
                        .toMap()
                )

            val spec = JSONObject(context.assets.open(TOKENS).bufferedReader().readText())
            val tools = spec.getJSONObject("tools")
            for (name in tools.keys()) {
                prototypes[name] = embedAll(tools.getJSONObject(name))
            }
            // The decline class ships alongside the actions, under a reserved name.
            prototypes[NO_ACTION] =
                embedArray(spec.getJSONArray("out_of_domain"))
            prototypes[OPEN_APP] = embedArray(spec.getJSONArray("app_prototypes"))

            ready = true
            Log.i(TAG, "loaded ${prototypes.size} action groups")
        } catch (t: Throwable) {
            initError = "IntentRouter failed to load: ${t.message}"
            Log.e(TAG, "load failed", t)
            throw IllegalStateException(initError, t)
        }
    }

    /**
     * The decision table, as a pure function of scores. No model, no Context, no
     * Android dependency, which is what makes the safety-critical part testable on
     * the JVM.
     *
     * [route] does the embedding and delegates here. That split exists because this
     * function is where a wrong answer does damage: the gate that decides whether
     * the assistant acts, declines, or asks. Testing it through [route] would need
     * a 90 MB model and a device for what is a pure comparison.
     */
    fun decide(
        scores: Map<String, Double>,
        margin: Double,
        latencyMs: Long,
    ): Decision {
        val ranked = scores.entries.sortedByDescending { it.value }
        val top = ranked[0]
        val runnerUp = if (ranked.size > 1) ranked[1].key else ""

        // The margin gate governs ambiguity between candidates only. It is not a
        // decline for its own sake.
        if (margin < ABSTAIN_MARGIN) {
            val why = when {
                scores.containsKey(NO_ACTION) && scores[NO_ACTION]!! >= top.value -> "out of domain"
                scores.containsKey(OPEN_APP) && scores[OPEN_APP]!! >= top.value ->
                    "app launch vs action"
                else -> "ambiguous between ${top.key} and $runnerUp"
            }
            return Decision(top.key, margin, true, false, runnerUp, latencyMs, why)
        }

        // A confident no_action winner is a decline regardless of margin. This has
        // to be a separate condition: the gate above only fires on ambiguity, so
        // out-of-domain text winning by a wide margin otherwise fell through to the
        // executable return below, and Dart's actionFor() handed the literal
        // "no_action" sentinel back as an action. A caller cannot distinguish a
        // sentinel from a real action string, which makes this the worst outcome
        // available -- worse than a wrong action, and worse than declining wrongly.
        if (top.key == NO_ACTION) {
            return Decision(NO_ACTION, margin, true, false, runnerUp, latencyMs, "out of domain")
        }

        return Decision(top.key, margin, false, false, runnerUp, latencyMs, "")
    }

    /**
     * Routes one utterance. Blocking; roughly 600 ms per call on the reference
     * device, so call it off the UI thread.
     */
    fun route(utterance: String): Decision {
        check(ready) { "call load() first" }
        val text = utterance.trim()
        if (text.isEmpty()) return Decision(NO_ACTION, 0.0, true, false, "", 0, "empty")

        if (NEGATION.containsMatchIn(text)) {
            return Decision(NO_ACTION, 0.0, true, negated = true, runnerUp = "", latencyMs = 0,
                reason = "negated request, hard guard")
        }

        val started = System.nanoTime()
        val vec = embed(tokenizer!!.encode(text, SEQ))
        val ms = (System.nanoTime() - started) / 1_000_000

        // Best prototype per action, then winner against every alternative.
        val scores = prototypes.mapValues { (_, protos) -> protos.maxOf { cosine(it, vec) } }
        val ranked = scores.entries.sortedByDescending { it.value }
        val margin = (ranked[0].value - ranked[1].value).toDouble()

        return decide(scores, margin, ms)
    }

    // ---------------------------------------------------------------- internals

    private fun embedAll(o: JSONObject): List<FloatArray> {
        // Tool descriptions ship as a single {ids, mask} object.
        return listOf(embedOne(toLongs(o.getJSONArray("ids")), toLongs(o.getJSONArray("mask"))))
    }

    private fun embedArray(arr: JSONArray): List<FloatArray> =
        (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            embedOne(toLongs(o.getJSONArray("ids")), toLongs(o.getJSONArray("mask")))
        }

    private fun toLongs(arr: JSONArray): LongArray = LongArray(arr.length()) { arr.getLong(it) }

    /**
     * Output 0 is the already-pooled [DIM] vector: the sentence-transformers export
     * bakes mean pooling into the graph, so it is not [SEQ] x [DIM] and must not be
     * pooled again here. L2-normalized so a dot product is cosine.
     */
    private fun embedOne(ids: LongArray, mask: LongArray): FloatArray {
        val ins = inputBuffers!!
        val outs = outputBuffers!!
        ins[0].writeLong(ids)
        if (ins.size > 1) ins[1].writeLong(mask)
        // By signature NAME: the numeric overload takes a raw index and fails on a
        // single-signature graph.
        model!!.run(ins, outs, "serving_default")
        val v = outs[0].readFloat()
        var norm = 0f
        for (x in v) norm += x * x
        norm = sqrt(norm)
        if (norm > 0f) for (i in v.indices) v[i] = v[i] / norm
        return v
    }

    private fun embed(pair: Pair<LongArray, LongArray>): FloatArray =
        embedOne(pair.first, pair.second)

    private fun cosine(a: FloatArray, b: FloatArray): Float {
        var dot = 0f
        for (i in a.indices) dot += a[i] * b[i]
        return dot
    }

    /** Action names this router can emit. Kept in sync with the assets file. */
    val knownActions: Set<String>
        get() = (prototypes.keys - NO_ACTION - OPEN_APP) + OPEN_APP
}