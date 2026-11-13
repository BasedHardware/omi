package com.friend.ios.features.settings

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.background
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.NonRestartableComposable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.AppDetail
import com.friend.ios.core.models.OmiApp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSecondaryButton
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.MarkdownBlocks
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.service.LocalAppCatalogStore
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.stores.AppCatalogStore
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.text.NumberFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * Port of `AppDetailScreen.swift`. One app's page (Flutter `app_detail.dart`): what it does,
 * setup, get / remove / subscribe, chat with it, reviews (and the user's own rating), share.
 * Opened from a link (`h.omi.me/apps/<id>`), an app the backend does not know shows Flutter's "not
 * available" instead (`AppLinkScreen.swift`).
 */
@Composable
fun AppDetailScreen(appID: String, onBack: () -> Unit) {
    val catalog = LocalAppCatalogStore.current
    val context = LocalContext.current
    var notice by remember { mutableStateOf<String?>(null) }
    var purchase by remember { mutableStateOf<Job?>(null) }
    var notFound by remember(appID) { mutableStateOf(false) }
    LaunchedEffect(appID) {
        catalog.loadDetail(appID)
        notFound = catalog.details[appID] == null
    }
    DisposableEffect(Unit) { onDispose { purchase?.cancel() } }
    val detail = catalog.details[appID]
    // The list row the user tapped is known on iOS (`preview`); here the catalog's copy stands in.
    val preview = detail?.app ?: catalog.results.firstOrNull { it.id == appID }
    if (preview == null) {
        AppLinkPlaceholder(notFound, onBack)
        return
    }
    val app = preview
    val shareURL = detail?.shareURL
    val shareLabel = L("share")
    SettingsListPage(app.name, onBack, trailing = { if (shareURL != null) GlassCircleButton("square.and.arrow.up", Modifier.semantics { contentDescription = shareLabel }) { shareText(context, shareURL) } }) {
        header(app, detail, catalog, { notice = it }, { purchase = it })
        if (detail != null && (detail.setupSteps.isNotEmpty() || detail.setupInstructionsURL != null || detail.setupInstructionsText != null)) setupSection(detail, catalog)
        if (app.description.isNotEmpty()) {
            section(header = L("nativeAppAbout")) { row { MarkdownBlocks(app.description, Modifier.padding(vertical = DS.Spacing.xxs)) } }
        }
        if (detail != null) promptsSection(detail)
        if (detail != null && detail.app.isPaid) paymentSection(detail, catalog) { notice = it }
        if (detail != null) appReviewsSection(detail, catalog)
    }
    notice?.let {
        OmiAlert(it, listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { notice = null })
    }
}

/**
 * Port of `AppLinkScreen.swift`'s states before the page: loading, or Flutter's "not available"
 * when the backend does not know the app (`ContentUnavailableView`).
 */
@Composable
private fun AppLinkPlaceholder(notFound: Boolean, onBack: () -> Unit) {
    SettingsPage(null, onBack) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            if (notFound) OmiEmptyState(L("appNotAvailable"), "square.grid.2x2") else OmiProgress()
        }
    }
}

@Composable
@NonRestartableComposable
private fun OmiListBuilder.header(app: OmiApp, detail: AppDetail?, catalog: AppCatalogStore, onNotice: (String) -> Unit, onPurchase: (Job) -> Unit) {
    val uriHandler = LocalUriHandler.current
    val navigator = LocalSettingsNavigator.current
    val chat = LocalChatStore.current
    val scope = rememberCoroutineScope()
    var working by remember { mutableStateOf(false) }
    val couldNotChange = L("nativeAppCouldNotChange")
    section {
        // The header sits on the page (like an App Store listing); the actions under it.
        plainRow(inset = DS.Spacing.gutter - 16.dp) {
            Row(Modifier.padding(vertical = DS.Spacing.xs), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                AppIcon(app.imageURL, app.name, 64.dp)
                Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                    Text(app.name, style = DS.Typography.sectionTitle, color = DS.Palette.ink)
                    app.author?.let { Text(it, style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
                    Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically) {
                        val rating = app.rating
                        if (rating != null && app.ratingCount > 0) {
                            Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xxs), verticalAlignment = Alignment.CenterVertically) {
                                SFImage("star.fill", size = 12.sp, tint = DS.Palette.inkTertiary)
                                Text(oneDecimal(rating), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                            }
                        }
                        Text(L("nativeAppInstalls", NumberFormat.getIntegerInstance().format(app.installs)), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                        val price = app.price
                        if (app.isPaid && price != null) Text(usd(price), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                    }
                }
            }
        }
        plainRow(inset = DS.Spacing.gutter - 16.dp) {
            val link = detail?.paymentLink
            Box(Modifier.padding(top = DS.Spacing.sm)) {
                if (detail?.needsPurchase == true && link != null) {
                    val waiting = app.id in catalog.awaitingPurchase
                    val price = app.price
                    OmiPrimaryButton(if (waiting) L("nativeAppWaitingForPayment") else price?.let { L("nativeAppSubscribePrice", usd(it)) } ?: L("nativeAppSubscribe")) {
                        uriHandler.openUri(link)
                        onPurchase(scope.launch { catalog.awaitPurchase(app.id) })
                    }
                } else {
                    val title = if (app.isEnabled) L("nativeRemove") else L("nativeGet")
                    val action: () -> Unit = {
                        scope.launch {
                            working = true
                            val reason = catalog.setEnabled(app, !app.isEnabled)
                            val home = detail?.homeURL
                            if (reason != null) onNotice(if (reason == AppCatalogStore.COULD_NOT_CHANGE) couldNotChange else reason)
                            else if (!app.isEnabled && home != null) uriHandler.openUri(catalog.signedSetupURL(home))
                            working = false
                        }
                    }
                    if (app.isEnabled) OmiSecondaryButton(title, onClick = { if (!working) action() }) else OmiPrimaryButton(title, enabled = !working, onClick = action)
                }
            }
        }
        if (app.isEnabled && app.worksWithChat) {
            plainRow(inset = DS.Spacing.gutter - 16.dp) {
                OmiSecondaryButton(L("nativeAppChatWith", app.name), Modifier.padding(top = DS.Spacing.sm)) {
                    scope.launch {
                        // The chat talks to this app from now on (its own history), then opens.
                        chat.talk(app)
                        navigator.dismiss()
                        navigator.openChat()
                    }
                }
            }
        }
    }
}

@Composable
@NonRestartableComposable
private fun OmiListBuilder.setupSection(detail: AppDetail, catalog: AppCatalogStore) {
    val uriHandler = LocalUriHandler.current
    val guide = L("nativeAppSetupGuide")
    section(header = L("nativeAppSetup"), footer = L("nativeAppSetupFooter")) {
        detail.setupSteps.forEachIndexed { index, step ->
            row(onClick = { uriHandler.openUri(catalog.signedSetupURL(step.url)) }) {
                Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
                    SFImage("arrow.up.right.square", tint = DS.Palette.agent)
                    Text("${index + 1}. ${step.name}", style = DS.Typography.body, color = DS.Palette.agent)
                }
            }
        }
        detail.setupInstructionsURL?.let { url -> row(onClick = { uriHandler.openUri(url) }) { Text(guide, style = DS.Typography.body, color = DS.Palette.agent) } }
        detail.setupInstructionsText?.let { text -> row { MarkdownBlocks(text) } }
    }
}

@Composable
@NonRestartableComposable
private fun OmiListBuilder.promptsSection(detail: AppDetail) {
    if (detail.chatPrompt == null && detail.conversationPrompt == null && detail.app.capabilities.isEmpty()) return
    val kinds = detail.app.capabilities.sorted().map { appKindTitle(it) }.joinToString(" · ")
    section(header = L("nativeAppWhatItDoes")) {
        if (detail.app.capabilities.isNotEmpty()) row { Text(kinds, style = DS.Typography.callout, color = DS.Palette.ink) }
        detail.chatPrompt?.let { prompt -> row { DisclosureGroup(L("nativeAppChatPersonality"), prompt) } }
        detail.conversationPrompt?.let { prompt -> row { DisclosureGroup(L("nativeAppConversationPrompt"), prompt) } }
    }
}

/** `DisclosureGroup(title) { Text(prompt) }`: the title with a chevron that turns, the text under it. */
@Composable
private fun DisclosureGroup(title: String, text: String) {
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().plainButton { open = !open }, verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
            SFImage(if (open) "chevron.down" else "chevron.right", size = 13.sp, weight = androidx.compose.ui.text.font.FontWeight.SemiBold, tint = DS.Palette.agent)
        }
        AnimatedVisibility(open) { Text(text, style = DS.Typography.callout, color = DS.Palette.ink, modifier = Modifier.padding(top = DS.Spacing.sm)) }
    }
}

@Composable
@NonRestartableComposable
private fun OmiListBuilder.paymentSection(detail: AppDetail, catalog: AppCatalogStore, onNotice: (String) -> Unit) {
    val subscription = catalog.subscriptions[detail.app.id] ?: return
    if (!detail.isUserPaid) return
    val scope = rememberCoroutineScope()
    var confirmsCancel by remember { mutableStateOf(false) }
    val couldNotChange = L("nativeAppCouldNotChange")
    val cancelTitle = L("nativeAppCancelSubscription")
    val ends = subscription.periodEnd?.let { L("nativeAppSubscriptionEnds", mediumDate(it)) }
    section(header = L("nativeAppSubscription")) {
        if (subscription.isActive) {
            row(onClick = { confirmsCancel = true }) { SettingsButtonText(cancelTitle, DS.Palette.live) }
        } else if (ends != null) {
            row { Text(ends, style = DS.Typography.body, color = DS.Palette.inkSecondary) }
        }
    }
    if (confirmsCancel) {
        OmiConfirmationDialog(
            L("nativeAppCancelQuestion"),
            listOf(DialogButton(cancelTitle, DialogButton.Role.Destructive) { scope.launch { if (!catalog.cancelSubscription(detail.app.id)) onNotice(couldNotChange) } }),
            onDismiss = { confirmsCancel = false },
            message = L("nativeAppCancelFooter"),
        )
    }
}

/** Port of `AppReviewsSection.swift`: an app's reviews and, once the app is on (and not the user's own), the user's own rating. */
@Composable
@NonRestartableComposable
private fun OmiListBuilder.appReviewsSection(detail: AppDetail, catalog: AppCatalogStore) {
    val app = detail.app
    val rating = app.rating
    val header = if (app.ratingCount > 0 && rating != null) L("nativeAppReviewsSummary", oneDecimal(rating), "${app.ratingCount}") else L("nativeAppReviews")
    val noReviews = L("nativeAppNoReviews")
    val anonymous = L("nativeAppAnonymous")
    section(header = header) {
        if (app.isEnabled && !detail.isOwn) row { YourRating(detail, catalog) }
        if (detail.reviews.isEmpty()) row { Text(noReviews, style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
        detail.reviews.forEach { review ->
            row(key = review.id) {
                Column(Modifier.padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                        Stars(Math.round(review.score).toInt())
                        Text(review.username ?: anonymous, style = DS.Typography.caption.semibold(), color = DS.Palette.ink)
                        Spacer(Modifier.weight(1f))
                        review.ratedAt?.let { Text(mediumDate(it), style = DS.Typography.caption, color = DS.Palette.inkTertiary) }
                    }
                    Text(review.text, style = DS.Typography.callout, color = DS.Palette.ink)
                    review.response?.let {
                        Text(L("nativeAppDeveloperReply", it), style = DS.Typography.caption, color = DS.Palette.inkSecondary, modifier = Modifier.padding(start = DS.Spacing.md))
                    }
                }
            }
        }
    }
}

@Composable
private fun YourRating(detail: AppDetail, catalog: AppCatalogStore) {
    val scope = rememberCoroutineScope()
    var score by remember(detail.userReview) { mutableIntStateOf(Math.round(detail.userReview?.score ?: 0.0).toInt()) }
    var text by remember(detail.userReview) { mutableStateOf(detail.userReview?.text.orEmpty()) }
    var saving by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Text(if (detail.userReview == null) L("nativeAppRateIt") else L("nativeAppYourRating"), style = DS.Typography.cardTitle, color = DS.Palette.ink)
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            (1..5).forEach { value ->
                SFImage(
                    if (value <= score) "star.fill" else "star", size = 20.sp, tint = if (value <= score) DS.Palette.warning else DS.Palette.inkTertiary,
                    modifier = Modifier.plainButton { score = value }.semantics { selected = value == score },
                    contentDescription = L("nativeAppStars", value.toString()),
                )
            }
        }
        Box(Modifier.fillMaxWidth()) {
            if (text.isEmpty()) Text(L("nativeAppReviewPlaceholder"), style = DS.Typography.callout, color = DS.Palette.inkTertiary)
            BasicTextField(text, { text = it }, textStyle = DS.Typography.callout.copy(color = DS.Palette.ink), cursorBrush = SolidColor(DS.Palette.agent), maxLines = 4, modifier = Modifier.fillMaxWidth())
        }
        // `.buttonStyle(.bordered)`: a quiet capsule in the accent tint.
        val enabled = score != 0 && !saving
        Text(
            if (detail.userReview == null) L("nativeAppPostReview") else L("nativeAppUpdateReview"),
            style = TextStyles.subheadline.semibold(),
            color = if (enabled) DS.Palette.agent else DS.Palette.inkDisabled,
            modifier = Modifier
                .plainButton(enabled = enabled) {
                    scope.launch {
                        saving = true
                        failed = !catalog.review(detail.app.id, score, text)
                        saving = false
                    }
                }
                .background(DS.Palette.fill, CircleShape)
                .padding(horizontal = DS.Spacing.md, vertical = 7.dp),
        )
    }
    if (failed) OmiAlert(L("nativeAppReviewFailed"), listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { failed = false })
}

@Composable
private fun Stars(score: Int) {
    val label = L("nativeAppStars", score.toString())
    Row(Modifier.clearAndSetSemantics { contentDescription = label }, horizontalArrangement = Arrangement.spacedBy(1.dp)) {
        (1..5).forEach { SFImage(if (it <= score) "star.fill" else "star", size = 11.sp, tint = DS.Palette.warning) }
    }
}

private fun oneDecimal(value: Double): String = NumberFormat.getNumberInstance().apply { minimumFractionDigits = 1; maximumFractionDigits = 1 }.format(value)

/** `.formatted(date: .abbreviated, time: .omitted)`. */
internal fun mediumDate(instant: Instant): String =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(Locale.getDefault()).format(instant.atZone(ZoneId.systemDefault()))
