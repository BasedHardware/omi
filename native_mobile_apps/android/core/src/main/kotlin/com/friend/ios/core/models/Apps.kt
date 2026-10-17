package com.friend.ios.core.models

import java.time.Instant

/**
 * Port of the models in `APIClient+Integrations.swift`, `APIClient+Apps.swift` and
 * `APIClient+AppStore.swift`: connections (calendar, mail, task apps) and Omi apps.
 */
data class Integration(val id: String, val kind: Kind, val isConnected: Boolean) {
    enum class Kind { Integration, TaskApp }
}

data class OmiApp(
    val id: String,
    val name: String,
    val description: String,
    val author: String?,
    val imageURL: String?,
    val category: String?,
    val rating: Double?,
    val installs: Int,
    val isEnabled: Boolean,
    /** `chat`, `persona`, `memories`, `external_integration`, `proactive_notification` ... */
    val capabilities: Set<String> = emptySet(),
    val ratingCount: Int = 0,
    val isPaid: Boolean = false,
    val price: Double? = null,
) {
    /** Can be chatted with (Flutter `worksWithChat`). */
    val worksWithChat: Boolean get() = "chat" in capabilities || "persona" in capabilities
}

/** One review of an app (backend `AppReview`). */
data class AppReview(
    val uid: String,
    val score: Double,
    val text: String,
    val username: String?,
    val ratedAt: Instant?,
    /** The app maker's answer. */
    val response: String?,
) {
    val id: String get() = uid
}

/** Everything the app page shows (`GET v1/apps/{id}`). */
data class AppDetail(
    val app: OmiApp,
    val reviews: List<AppReview> = emptyList(),
    val userReview: AppReview? = null,
    /** Signed in-app links to connect an outside service (`external_integration.auth_steps`). */
    val setupSteps: List<SetupStep> = emptyList(),
    /** A setup guide: a web page, or markdown text (`setup_instructions_file_path`). */
    val setupInstructionsURL: String? = null,
    val setupInstructionsText: String? = null,
    /** Opened after the app is turned on (`app_home_url`). */
    val homeURL: String? = null,
    val chatPrompt: String? = null,
    val conversationPrompt: String? = null,
    val paymentLink: String? = null,
    val paymentPlan: String? = null,
    val isUserPaid: Boolean = false,
    val isPrivate: Boolean = false,
    /** The user made this app (reviewing it is refused). */
    val isOwn: Boolean = false,
) {
    data class SetupStep(val name: String, val url: String)

    /** The user must pay before turning it on. */
    val needsPurchase: Boolean get() = app.isPaid && !isUserPaid

    /** Share link (Flutter `share_links.dart`); private apps have none. */
    val shareURL: String? get() = if (isPrivate) null else "https://h.omi.me/apps/${app.id}"
}

/** `GET v1/app-categories`. */
data class AppCategory(val id: String, val title: String)

/** The browse list's search and filters (`GET v2/apps/search`). */
data class AppQuery(
    val text: String = "",
    val category: String? = null,
    /** `chat`, `memories`, `external_integration`, `proactive_notification`, `tasks`. */
    val capability: String? = null,
    val minimumRating: Double? = null,
    val sort: Sort = Sort.Installs,
) {
    enum class Sort(val rawValue: String) { Installs("installs_desc"), Rating("rating_desc"), Name("name_asc") }
}

/** A paid app's subscription (`GET v1/apps/{id}/subscription`). */
data class AppSubscription(val status: String, val cancelAtPeriodEnd: Boolean, val periodEnd: Instant?) {
    /** Renews (Flutter `app_detail.dart`: active and not cancelling). */
    val isActive: Boolean get() = status == "active" && !cancelAtPeriodEnd
}
