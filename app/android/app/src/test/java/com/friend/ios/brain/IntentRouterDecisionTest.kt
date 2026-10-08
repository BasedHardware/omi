package com.friend.ios.brain

import com.friend.ios.brain.IntentRouter.Companion.NO_ACTION
import com.friend.ios.brain.IntentRouter.Companion.OPEN_APP
import com.friend.ios.brain.IntentRouter.Companion.decide
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The decision table, which is where a wrong answer does damage.
 *
 * These are JVM tests on purpose. [IntentRouter.route] needs a 90 MB MiniLM and a
 * device; [decide] is a pure function of the scores, and the gate that decides
 * whether the assistant acts, declines, or asks deserves coverage that does not
 * require either.
 *
 * The ordering of the assertions matters as much as their content: the case that
 * motivated extracting this function is [confidentNoActionWinnerIsDeclined], and it
 * sits above the happy path so a future edit that reintroduces the bug fails a test
 * whose name says exactly what broke.
 */
class IntentRouterDecisionTest {

    private fun scores(vararg pairs: Pair<String, Double>) = mapOf(*pairs)

    /**
     * The regression this whole refactor exists for. Out-of-domain text winning by a
     * wide margin must not come back as an executable "no_action" string, because
     * Dart's actionFor() cannot tell a sentinel from a real action and would run it.
     */
    @Test
    fun confidentNoActionWinnerIsDeclined() {
        val d = decide(scores(NO_ACTION to 0.97, "set_timer" to 0.41), margin = 0.56, latencyMs = 12)

        assertTrue("out-of-domain win must be declined", d.declined)
        assertEquals(NO_ACTION, d.action)
        assertEquals("out of domain", d.reason)
    }

    /** The margin must be reported even when declining, so callers can log or ask. */
    @Test
    fun confidentNoActionWinnerStillReportsMargin() {
        val d = decide(scores(NO_ACTION to 0.97, "set_timer" to 0.41), margin = 0.56, latencyMs = 12)

        assertEquals(0.56, d.margin, 1e-9)
    }

    /**
     * The happy path: a real action winning by a wide margin acts. Guards against
     * "fixing" the sentinel bug by over-declining everything.
     */
    @Test
    fun clearRealActionActs() {
        val d = decide(scores("set_timer" to 0.91, NO_ACTION to 0.22), margin = 0.69, latencyMs = 12)

        assertFalse(d.declined)
        assertEquals("set_timer", d.action)
    }

    /** Two real actions too close together: decline and name the alternative. */
    @Test
    fun ambiguousRealActionsDecline() {
        val d = decide(scores("set_timer" to 0.70, "add_task" to 0.695), margin = 0.005, latencyMs = 12)

        assertTrue(d.declined)
        assertEquals("add_task", d.runnerUp)
        assertTrue(d.reason.startsWith("ambiguous between"))
    }

    /**
     * open_app is a real action class, unlike the no_action sentinel, so a confident
     * win must act. The "app launch vs action" reason only fires on the ambiguity
     * gate, where open_app ties with a genuine action.
     */
    @Test
    fun clearOpenAppWinActs() {
        val d = decide(scores(OPEN_APP to 0.88, "set_timer" to 0.30), margin = 0.58, latencyMs = 12)

        assertFalse("a confident open_app is an action, not a decline", d.declined)
        assertEquals(OPEN_APP, d.action)
    }

    /** The app-vs-action reason belongs to the ambiguity gate only. */
    @Test
    fun openAppTieDeclines() {
        val d = decide(scores(OPEN_APP to 0.70, "set_timer" to 0.70), margin = 0.0, latencyMs = 12)

        assertTrue(d.declined)
        assertEquals("app launch vs action", d.reason)
    }

    /** The ambiguity gate alone must not decide which kind of decline it is. */
    @Test
    fun outOfDomainTieNamesOutOfDomainReason() {
        val d = decide(scores(NO_ACTION to 0.60, "set_timer" to 0.60), margin = 0.0, latencyMs = 12)

        assertTrue(d.declined)
        assertEquals("out of domain", d.reason)
    }

    /**
     * Exactly at the abstain margin counts as decisive. If this ever flips, the
     * boundary is arbitrary -- worth pinning deliberately rather than discovering.
     */
    @Test
    fun marginExactlyAtThresholdActs() {
        val d = decide(scores("set_timer" to 0.90, NO_ACTION to 0.88), margin = 0.02, latencyMs = 12)

        assertFalse("margin == ABSTAIN_MARGIN is decisive, not ambiguous", d.declined)
    }

    /** A single candidate has no runner-up; must not index off the end. */
    @Test
    fun singleActionDoesNotCrash() {
        val d = decide(scores("set_timer" to 0.9), margin = 1.0, latencyMs = 12)

        assertFalse(d.declined)
        assertEquals("", d.runnerUp)
    }

    /** Latency must pass through untouched; callers report it. */
    @Test
    fun latencyPassesThrough() {
        val d = decide(scores("set_timer" to 0.9, NO_ACTION to 0.1), margin = 0.8, latencyMs = 613)

        assertEquals(613L, d.latencyMs)
    }

    /** Latency passes through on the decline path too. */
    @Test
    fun latencyPassesThroughOnDecline() {
        val d = decide(scores(NO_ACTION to 0.9, "set_timer" to 0.1), margin = 0.8, latencyMs = 613)

        assertEquals(613L, d.latencyMs)
    }

    /**
     * Whatever else changes, no decision may ever come back as an executable
     * sentinel. Stated directly so the invariant has a name.
     */
    @Test
    fun noActionIsNeverExecutable() {
        val cases =
            listOf(
                scores(NO_ACTION to 0.97, "set_timer" to 0.41) to 0.56,
                scores(NO_ACTION to 0.60, "set_timer" to 0.60) to 0.0,
                scores(NO_ACTION to 0.10, "set_timer" to 0.90) to 0.80,
                scores(NO_ACTION to 0.95, OPEN_APP to 0.93) to 0.02,
            )

        for ((s, margin) in cases) {
            val d = decide(s, margin = margin, latencyMs = 1)
            // The invariant is about what comes back, not about no_action appearing in
            // the scores: in the third case no_action loses, so acting is correct. What
            // must never happen is a Decision whose action *is* the sentinel arriving
            // undeclined, which actionFor() would then hand to a caller as executable.
            if (d.action == NO_ACTION && !d.declined) {
                throw AssertionError("no_action leaked as executable at margin=$margin")
            }
        }
    }

    /** And the positive control: no_action losing is allowed to act. */
    @Test
    fun noActionLosingActsNormally() {
        val d = decide(scores(NO_ACTION to 0.10, "set_timer" to 0.90), margin = 0.80, latencyMs = 1)

        assertFalse(d.declined)
        assertEquals("set_timer", d.action)
    }
}