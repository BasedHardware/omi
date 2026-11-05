package com.friend.ios.system

import com.friend.ios.BuildConfig
import com.friend.ios.service.stores.SessionStore

/**
 * Port of `SupportChat.swift`: Intercom's messenger, as Flutter's `IntercomManager`: set up at
 * launch, the signed-in account identified by its uid (no email or name leaves the app here),
 * opened from Help. Off unless the build sets `OMI_INTERCOM_APP_ID` and
 * `OMI_INTERCOM_ANDROID_API_KEY` (`local.properties` or Gradle properties, `BuildConfig`) and a
 * [Messenger] is linked; Help then shows only the help center and feedback.
 *
 * Android: the Intercom SDK is not linked yet. 18.9.0 (the Flutter app's, intercom_flutter 9.6.22)
 * imports Compose BOM 2026.06.01 and would move every screen from Compose 1.8.3 to 1.11.4
 * (activity 1.13, core 1.18) with it. [messenger] is where its calls go once it is: `Intercom
 * .initialize`, `loginIdentifiedUser(Registration.create().withUserId(uid))`, `logout`,
 * `present()` and `IntercomPushClient.sendTokenToIntercom`.
 */
object SupportChat {
    /** The SDK's calls this app makes, as `SupportChat.swift` makes them on iOS. */
    interface Messenger {
        fun configure(appID: String, apiKey: String)
        fun login(userID: String)
        fun logout()
        fun present()
        fun registerPushToken(token: String)
    }

    /** The linked messenger; null without the SDK (see above). */
    var messenger: Messenger? = null

    private val appID = BuildConfig.OMI_INTERCOM_APP_ID.ifEmpty { null }
    private val apiKey = BuildConfig.OMI_INTERCOM_ANDROID_API_KEY.ifEmpty { null }
    private var loggedInUser: String? = null

    val isConfigured: Boolean
        get() = appID != null && apiKey != null && messenger != null

    fun configure() {
        val appID = appID ?: return
        val apiKey = apiKey ?: return
        messenger?.configure(appID, apiKey)
    }

    /** Who the conversations belong to; signed out, Intercom forgets them. */
    fun sessionChanged(phase: SessionStore.Phase) {
        val messenger = messenger?.takeIf { isConfigured } ?: return
        val userID = when (phase) {
            is SessionStore.Phase.Ready -> phase.userID
            is SessionStore.Phase.Onboarding -> phase.userID
            is SessionStore.Phase.Consent -> phase.userID
            SessionStore.Phase.SignedOut -> {
                if (loggedInUser == null) return
                loggedInUser = null
                messenger.logout()
                return
            }
            SessionStore.Phase.Launching -> return
        }
        if (loggedInUser == userID) return
        if (loggedInUser != null) messenger.logout()
        loggedInUser = userID
        messenger.login(userID)
    }

    /** Replies from support arrive as pushes. */
    fun registerPushToken(token: String) {
        if (!isConfigured) return
        messenger?.registerPushToken(token)
    }

    fun present() {
        if (!isConfigured) return
        messenger?.present()
    }
}
