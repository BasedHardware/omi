package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.device.OmiGATT

/**
 * What the button lessons need from asking Omi with the button (`AskOmiStore` on iOS): practice
 * mode and the button's question actions. [AskOmi] adds what the onboarding ask lesson shows.
 */
interface AskOmiPractice {
    /** A practice question: answered, but kept out of the main chat. */
    var isPractice: Boolean
    fun handle(action: ButtonAction)
}

/**
 * Port of `ButtonTutorialStore.swift`: the Omi button lessons (Flutter `DeviceOnboardingProvider`,
 * steps single press and double press). While one runs, the Omi's button events come here first.
 * Asking practises the real thing (the question goes to the chat, the answer can be
 * read aloud); double press only counts the presses and saves the chosen action, so practice
 * never ends, mutes or stars anything.
 *
 * [askOmi] is the app's [AskOmiStore]; null (tests, previews) sends the ask lesson's presses nowhere.
 */
class ButtonTutorialStore(val devices: DeviceStore, val askOmi: AskOmi?) {
    enum class Lesson {
        /** Press once, ask, press again. */
        Ask,

        /** Pick what a double press does, then try it. */
        DoublePress,
    }

    var lesson: Lesson? by mutableStateOf(null)
        private set

    /** Double presses since the action was picked. */
    var doublePresses: Int by mutableIntStateOf(0)
        private set

    /** The last press on the double-press lesson was a single one. */
    var singlePressHint: Boolean by mutableStateOf(false)
        private set

    /** The action double press runs: the same setting as My Devices > Controls. */
    val doublePressAction: DoubleTapAction get() = devices.doubleTapAction

    fun begin(lesson: Lesson) {
        this.lesson = lesson
        doublePresses = 0
        singlePressHint = false
        askOmi?.isPractice = lesson == Lesson.Ask
        devices.buttonInterceptor = { event -> handle(event) }
    }

    /**
     * Ends [only] (when given) or whichever lesson runs; a step leaving after the next one began
     * does not end the new one.
     */
    fun end(only: Lesson? = null) {
        if (lesson == null || (only != null && only != lesson)) return
        lesson = null
        askOmi?.isPractice = false
        devices.buttonInterceptor = null
    }

    /** Picking starts the count over (Flutter `selectDoubleTapAction`). */
    fun choose(action: DoubleTapAction) {
        devices.doubleTapAction = action
        doublePresses = 0
        singlePressHint = false
    }

    /** Every button event while a lesson runs; always consumed. */
    internal fun handle(event: OmiGATT.ButtonEvent): Boolean {
        when (lesson) {
            Lesson.Ask -> when (event) {
                OmiGATT.ButtonEvent.SingleTap -> askOmi?.handle(ButtonAction.AskToggle)
                OmiGATT.ButtonEvent.LongPress -> askOmi?.handle(ButtonAction.AskHoldStart)
                OmiGATT.ButtonEvent.Release -> askOmi?.handle(ButtonAction.AskHoldEnd)
                OmiGATT.ButtonEvent.DoubleTap, OmiGATT.ButtonEvent.Press -> Unit
            }
            Lesson.DoublePress -> when (event) {
                OmiGATT.ButtonEvent.SingleTap -> singlePressHint = true
                OmiGATT.ButtonEvent.DoubleTap -> {
                    singlePressHint = false
                    doublePresses += 1
                }
                OmiGATT.ButtonEvent.LongPress, OmiGATT.ButtonEvent.Release, OmiGATT.ButtonEvent.Press -> Unit
            }
            null -> return false
        }
        return true
    }
}
