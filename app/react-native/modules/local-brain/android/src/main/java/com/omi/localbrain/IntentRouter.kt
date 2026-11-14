package com.omi.localbrain

import android.content.Context
import android.util.Log
import com.google.ai.edge.litert.Accelerator
import com.google.ai.edge.litert.CompiledModel
import com.google.ai.edge.litert.TensorBuffer
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
class IntentRouter(
    private val context: Context,
    private val routePrototypes: Map<String, List<String>>? = null,
    private val outOfDomain: List<String> = emptyList(),
) {

    companion object {
        private const val TAG = "IntentRouter"
        private const val MODEL = "minilm.tflite"
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


        /**
         * A prohibition means do not act. Held-out measurement: unguarded, 4 of 5
         * negated requests executed the inverse of the instruction, which for an
         * agent is worse than any accuracy miss.
         */
        private val NEGATION =
            Regex("\\b(?:don'?t|do\\s+not|never|no\\s+need|without\\s+doing)\\b", RegexOption.IGNORE_CASE)
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

            // Prototype banks are supplied by JS (see ROUTE_PROTOTYPES in
            // src/services/localBrainRouter.ts) rather than baked into the asset,
            // so the routing vocabulary is reviewable in TypeScript. Each entry is
            // tokenized here with the same contract as any other utterance.
            require(!routePrototypes.isNullOrEmpty()) {
                "routePrototypes required: supply ROUTE_PROTOTYPES from JS"
            }
            for ((route, texts) in routePrototypes) {
                if (texts.isEmpty()) continue
                prototypes[route] = texts.map { embed(encodeText(it)) }
            }
            prototypes[NO_ACTION] = outOfDomain.map { embed(encodeText(it)) }

            ready = true
            Log.i(TAG, "loaded ${prototypes.size} action groups")
        } catch (t: Throwable) {
            initError = "IntentRouter failed to load: ${t.message}"
            Log.e(TAG, "load failed", t)
            throw IllegalStateException(initError, t)
        }
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
        val top = ranked[0]
        val runnerUpValue = ranked[1].value
        val margin = (top.value - runnerUpValue).toDouble()

        if (margin < ABSTAIN_MARGIN) {
            val why =
                if (NO_ACTION in scores && scores[NO_ACTION]!! >= top.value) "out of domain"
                else "ambiguous between ${top.key} and ${ranked[1].key}"
            return Decision(top.key, margin, true, false, ranked[1].key, ms, why)
        }

        // no_action winning outright is a decline, whatever the margin says.
        // Measured on an SM-A145F: "what is the weather" scored no_action 0.93
        // over the runner-up, so it cleared ABSTAIN_MARGIN and fell through to the
        // line below with declined=false -- i.e. the router's most confident correct
        // answer, the abstention, was reported to JS as a route commitment.
        if (top.key == NO_ACTION) {
            return Decision(NO_ACTION, margin, true, false, ranked[1].key, ms,
                "out of domain")
        }

        return Decision(top.key, margin, false, false, ranked[1].key, ms, "")
    }

    // ---------------------------------------------------------------- internals

    /** Tokenizes free text with the same contract used for utterances. */
    private fun encodeText(text: String): Pair<LongArray, LongArray> =
        tokenizer!!.encode(text, SEQ)

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

    /** Route names this router can emit, excluding the decline class. */
    val knownRoutes: Set<String>
        get() = prototypes.keys - NO_ACTION
}