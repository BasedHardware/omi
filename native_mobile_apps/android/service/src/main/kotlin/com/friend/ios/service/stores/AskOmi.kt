package com.friend.ios.service.stores

/**
 * The part of `AskOmiStore` the onboarding ask lesson reads: a question asked with the Omi's
 * button really goes to Omi ([AskOmiStore]).
 */
interface AskOmi : AskOmiPractice {
    sealed interface Phase {
        data object Idle : Phase
        data class Listening(val sinceMillis: Long) : Phase
        data object Sending : Phase
    }

    enum class Problem { NothingHeard, NoAnswer }

    data class Exchange(val question: String, val answer: String)

    val phase: Phase
    val lastExchange: Exchange?
    val question: String
    val problem: Problem?
}

/** Nothing asked yet: what the ask lesson shows while there is no AskOmiStore. */
object NoAskOmi : AskOmi {
    override val phase: AskOmi.Phase = AskOmi.Phase.Idle
    override val lastExchange: AskOmi.Exchange? = null
    override val question: String = ""
    override val problem: AskOmi.Problem? = null
    override var isPractice: Boolean = false
    override fun handle(action: ButtonAction) = Unit
}
