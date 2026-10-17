package com.friend.ios

import com.friend.ios.core.models.DeviceContact
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.service.stores.ButtonAction
import com.friend.ios.service.stores.ButtonTutorialStore
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.stores.PendingDeviceTool
import com.friend.ios.service.stores.showDemoQuestion
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `DebugAskOmi.swift` and the "Omi asks" demo of `DebugHooks.swift` (debug builds only).
 *
 * - `--es omiAskTranscript "What is on my calendar today?"` with `--es omiFakeDevice connected`:
 *   once the press-once lesson is up (or right away with `--ez omiAskNow true`), presses the
 *   Omi's button; the scripted recognizer says the question and the pause sends it.
 * - `--es omiDemoOmiAsks message|contacts|access`: an "Omi asks" card without a run.
 */
object DebugAskOmi {
    private var started = false

    fun start(environment: AppEnvironment) {
        if (!BuildConfig.DEBUG || started) return
        started = true
        DebugLaunch.string("omiDemoOmiAsks")?.let { kind -> environment.agent.showDemoQuestion(demoQuestion(kind)) }
        if (DebugLaunch.string("omiAskTranscript") == null) return
        val now = DebugLaunch.flag("omiAskNow")
        environment.scope.launch {
            val askOmi = environment.askOmi
            while (!now && environment.buttonTutorial.lesson != ButtonTutorialStore.Lesson.Ask) delay(300)
            while (environment.devices.connection != DeviceStore.Connection.Connected) delay(300)
            delay(2500)
            askOmi.handle(ButtonAction.AskToggle)
        }
    }

    private fun demoQuestion(kind: String): PendingDeviceTool {
        val anna = DeviceContact(
            id = "demo-anna", name = "Anna Schmidt", phoneNumbers = listOf(DeviceContact.Handle("mobile", "+49 170 1234567")),
            emailAddresses = emptyList(), preferredHandle = "+49 170 1234567",
        )
        val annabel = DeviceContact(id = "demo-annabel", name = "Annabel Lee", phoneNumbers = emptyList(), emailAddresses = emptyList(), preferredHandle = "")
        val title = "Send Anna the Thursday follow-up"
        return when (kind) {
            "contacts" -> PendingDeviceTool(
                "demo", title, DeviceToolRequest(id = "demo-call", toolName = "search_contacts", query = "Anna"), matches = listOf(anna, annabel),
            )
            "access" -> PendingDeviceTool(
                "demo", title, DeviceToolRequest(id = "demo-call", toolName = "search_contacts", query = "Anna"), needsContactsAccess = true,
            )
            else -> PendingDeviceTool(
                "demo", title,
                DeviceToolRequest(
                    id = "demo-call", toolName = "propose_message", recipients = listOf("Anna Schmidt"),
                    text = "Hi Anna, following up on our roadmap chat: does Thursday at 7 pm still work for you?",
                ),
            )
        }
    }
}
