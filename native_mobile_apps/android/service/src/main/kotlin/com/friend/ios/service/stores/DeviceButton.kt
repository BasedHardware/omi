package com.friend.ios.service.stores

import com.friend.ios.device.OmiGATT

/**
 * Port of `DeviceButton.swift`: what a double tap on the Omi does. Raw values are the Flutter
 * app's `doubleTapAction` preference (`device_control_sheets.dart`): 0 end and process,
 * 1 mute/unmute, 2 star.
 */
enum class DoubleTapAction(val rawValue: Int) {
    EndConversation(0),
    ToggleMute(1),
    Star(2);

    companion object {
        fun fromRaw(raw: Int): DoubleTapAction? = entries.firstOrNull { it.rawValue == raw }
    }
}

/** What the app does for a button event (`capture_controller.dart` `_handleButtonEvent`). */
enum class ButtonAction {
    EndConversation,

    /** Stars the conversation when it ends; a second double tap takes the star back. */
    ToggleStar,
    ToggleMute,

    /** Single press: start a question, or send it on the next press. */
    AskToggle,

    /** Older firmware: a long press records a question until the button is released. */
    AskHoldStart,
    AskHoldEnd;

    companion object {
        /**
         * Routes a firmware button event. With button actions off nothing happens; a plain
         * press/release (sent around every tap) only matters to a question held since a long press.
         */
        fun route(event: OmiGATT.ButtonEvent, doubleTap: DoubleTapAction, actionsEnabled: Boolean): ButtonAction? {
            if (!actionsEnabled) return null
            return when (event) {
                OmiGATT.ButtonEvent.SingleTap -> AskToggle
                OmiGATT.ButtonEvent.DoubleTap -> when (doubleTap) {
                    DoubleTapAction.EndConversation -> EndConversation
                    DoubleTapAction.ToggleMute -> ToggleMute
                    DoubleTapAction.Star -> ToggleStar
                }
                OmiGATT.ButtonEvent.LongPress -> AskHoldStart
                OmiGATT.ButtonEvent.Release -> AskHoldEnd
                OmiGATT.ButtonEvent.Press -> null
            }
        }
    }
}
