package com.friend.ios.features.settings

import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.friend.ios.design.CalmBackground
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.Pill
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.service.LocalPhoneCallStore
import com.friend.ios.service.phonecalls.PhoneNumberFormat
import com.friend.ios.service.stores.PhoneCallStore
import com.friend.ios.service.stores.PhoneCallStore.Phase
import com.friend.ios.service.stores.PhoneCallStore.TranscriptionStatus
import kotlinx.coroutines.delay
import java.time.Instant

/** `.fullScreenCover { ActiveCallScreen() }`: the call over everything; Back minimizes it. */
@Composable
fun ActiveCallCover(onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        ActiveCallScreen(onDismiss)
    }
}

/**
 * Port of `ActiveCallScreen.swift`. The call in progress (Flutter `active_call_page`): who, how
 * long, the live transcript of both sides, mute / keypad (tones) / speaker / audio route / end.
 * Minimizing keeps the call going.
 */
@Composable
fun ActiveCallScreen(onDismiss: () -> Unit) {
    val phone = LocalPhoneCallStore.current
    var showsKeypad by remember { mutableStateOf(false) }
    // `isIdleTimerDisabled`: the screen stays on while the call is shown.
    val view = LocalView.current
    DisposableEffect(view) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }
    Box(Modifier.fillMaxSize()) {
        CalmBackground()
        Column(
            Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            TopBar(onDismiss)
            Header(phone)
            if (phone.phase == Phase.Active) transcriptionChip(phone.transcription)?.let { (text, tint) -> Pill(text, tint = tint) }
            CallTranscriptView(phone, Modifier.weight(1f))
            Controls(phone) { showsKeypad = true }
        }
    }
    if (showsKeypad) DTMFSheet(phone) { showsKeypad = false }
}

@Composable
private fun TopBar(onDismiss: () -> Unit) {
    val context = LocalContext.current
    Row(Modifier.fillMaxWidth().padding(top = DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(36.dp).plainButton(onClick = onDismiss), contentAlignment = Alignment.CenterStart) {
            SFImage("chevron.down", size = 20.sp, weight = FontWeight.SemiBold, tint = DS.Palette.ink, contentDescription = L("nativePhoneMinimize"))
        }
        Spacer(Modifier.weight(1f))
        // iOS `AVRoutePickerView`: Android has no route picker view to embed, so the button opens the
        // system's volume and output panel (`Settings.Panel.ACTION_VOLUME`: Bluetooth, wired, phone).
        Box(
            Modifier.size(36.dp).plainButton {
                runCatching { context.startActivity(Intent(Settings.Panel.ACTION_VOLUME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            },
            contentAlignment = Alignment.Center,
        ) { SFImage("speaker.wave.2", size = 20.sp, tint = DS.Palette.ink, contentDescription = L("audioOutput")) }
    }
}

@Composable
private fun Header(phone: PhoneCallStore) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Text(phone.otherParty, style = DS.Typography.largeTitle, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
        val number = phone.remoteNumber
        if (phone.contactName != null && number != null) {
            Text(PhoneNumberFormat.display(number), style = DS.Typography.body, color = DS.Palette.inkSecondary)
        }
        val style = DS.Typography.callout.copy(fontFeatureSettings = "tnum")
        when (phone.phase) {
            Phase.Idle, Phase.Connecting -> Text(L("callStateConnecting"), style = style, color = DS.Palette.inkSecondary)
            Phase.Ringing -> Text(L("callStateRinging"), style = style, color = DS.Palette.inkSecondary)
            Phase.Active -> phone.connectedAt?.let { Text(elapsed(it), style = style, color = DS.Palette.inkSecondary) }
            Phase.Ended -> {
                val failure = phone.failure
                Text(
                    failure?.let { PhoneCallWording.failure(it) } ?: L("callStateEnded"),
                    style = style,
                    color = if (failure == null) DS.Palette.inkSecondary else DS.Palette.live,
                )
            }
        }
    }
}

/** `TimelineView(.periodic(from: start, by: 1))` with `.time(pattern: .minuteSecond)`: "0:42", "12:05". */
@Composable
private fun elapsed(start: Instant): String {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(start) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1_000 - (now - start.toEpochMilli()).mod(1_000L))
        }
    }
    val seconds = ((now - start.toEpochMilli()) / 1_000).coerceAtLeast(0)
    return minuteSecond(seconds)
}

internal fun minuteSecond(seconds: Long): String = "%d:%02d".format(seconds / 60, seconds % 60)

@Composable
private fun transcriptionChip(status: TranscriptionStatus): Pair<String, Color>? = when (status) {
    TranscriptionStatus.Idle, TranscriptionStatus.Active -> null
    TranscriptionStatus.Connecting -> L("transcriptionConnecting") to DS.Palette.inkSecondary
    TranscriptionStatus.Reconnecting -> L("transcriptionReconnecting") to DS.Palette.warning
    TranscriptionStatus.Failed -> L("transcriptionUnavailable") to DS.Palette.live
    TranscriptionStatus.NoAudio -> L("transcriptionNoAudio") to DS.Palette.warning
}

@Composable
private fun Controls(phone: PhoneCallStore, onKeypad: () -> Unit) {
    val live = phone.isInProgress
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xl)) {
            CallControl(
                if (phone.isMuted) "mic.slash.fill" else "mic.fill",
                if (phone.isMuted) L("phoneUnmute") else L("phoneMute"),
                isOn = phone.isMuted, enabled = live,
            ) { phone.toggleMute() }
            CallControl("circle.grid.3x3.fill", L("phoneKeypad"), isOn = false, enabled = phone.phase == Phase.Active, action = onKeypad)
            CallControl("speaker.wave.2.fill", L("phoneSpeaker"), isOn = phone.isSpeakerOn, enabled = live) { phone.toggleSpeaker() }
        }
        Box(
            Modifier
                .size(76.dp)
                .alpha(if (live) 1f else 0.5f)
                .background(DS.Palette.live, CircleShape)
                .plainButton(enabled = live) { phone.end() },
            contentAlignment = Alignment.Center,
        ) { SFImage("phone.down.fill", size = 28.sp, tint = Color.White, contentDescription = L("phoneEndCall")) }
    }
}

@Composable
private fun CallControl(icon: String, title: String, isOn: Boolean, enabled: Boolean, action: () -> Unit) {
    Column(
        Modifier.alpha(if (enabled) 1f else 0.4f).plainButton(enabled = enabled, onClick = action),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
    ) {
        Box(Modifier.size(64.dp).background(if (isOn) DS.Palette.ink else DS.Palette.fill, CircleShape), contentAlignment = Alignment.Center) {
            SFImage(icon, size = 22.sp, tint = if (isOn) DS.Palette.onAccent else DS.Palette.ink)
        }
        Text(title, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
    }
}

/** Both sides as bubbles, you on the right; translations (live interpreter) under the line. */
@Composable
private fun CallTranscriptView(phone: PhoneCallStore, modifier: Modifier) {
    val state = rememberLazyListState()
    val segments = phone.transcript.segments
    val lastID = segments.lastOrNull()?.id
    LaunchedEffect(lastID) { if (segments.isNotEmpty()) state.animateScrollToItem(segments.lastIndex) }
    val placeholder = L("transcriptPlaceholder")
    LazyColumn(
        modifier.fillMaxWidth(),
        state = state,
        contentPadding = PaddingValues(vertical = DS.Spacing.sm),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        if (phone.transcript.isEmpty && phone.phase == Phase.Active && phone.transcription != TranscriptionStatus.NoAudio) {
            item {
                Box(Modifier.fillMaxWidth().padding(top = DS.Spacing.xl), contentAlignment = Alignment.Center) {
                    Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary)
                }
            }
        }
        items(segments, key = { it.id }) { segment -> Bubble(segment, phone.otherParty, phone.transcript.translations[segment.id].orEmpty()) }
    }
}

@Composable
private fun Bubble(segment: LiveSegment, otherParty: String, translations: List<String>) {
    val you = L("nativePhoneCallYou")
    Column(
        Modifier
            .fillMaxWidth()
            .padding(start = if (segment.isUser) DS.Spacing.section else 0.dp, end = if (segment.isUser) 0.dp else DS.Spacing.section),
        horizontalAlignment = if (segment.isUser) Alignment.End else Alignment.Start,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs),
    ) {
        Text(if (segment.isUser) you else otherParty, style = DS.Typography.micro, color = DS.Palette.inkTertiary)
        Column(
            Modifier
                .background(if (segment.isUser) DS.Palette.cardRaised else DS.Palette.card, RoundedCornerShape(DS.Radius.md))
                .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.sm),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
        ) {
            Text(segment.text, style = DS.Typography.callout, color = DS.Palette.ink)
            translations.forEach { translated ->
                Text(translated, style = DS.Typography.callout.copy(fontStyle = FontStyle.Italic), color = DS.Palette.inkSecondary)
            }
        }
    }
}

/** Tones into the call (menus, extensions). */
@Composable
private fun DTMFSheet(phone: PhoneCallStore, onDismiss: () -> Unit) {
    var typed by remember { mutableStateOf("") }
    val hide = L("phoneHideKeypad")
    OmiSheet(onDismiss = onDismiss) {
        Column(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(DS.Spacing.gutter),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
        ) {
            Text(typed.ifEmpty { " " }, style = TextStyles.system(30, FontWeight.Medium).copy(fontFeatureSettings = "tnum"), color = DS.Palette.ink)
            PhoneKeypad(onKey = { digit ->
                typed += digit
                phone.sendDigit(digit)
            })
            com.friend.ios.design.OmiPillButton(hide, prominent = false, onClick = onDismiss)
        }
    }
}

/**
 * Port of `OngoingCallPresenter` (the app shell's part): while a call goes on and its screen is
 * down, a banner on top returns to it. Wraps the shell's content, as `.safeAreaInset(edge: .top)`.
 * Debug (`--es omiFakeCall active|banner`): a pretend connected call for screenshots, nothing dialed.
 */
@Composable
fun OngoingCallPresenter(content: @Composable () -> Unit) {
    val phone = LocalPhoneCallStore.current
    var showsCall by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        val mode = DebugLaunch.string("omiFakeCall") ?: return@LaunchedEffect
        phone.debugPresent("+4930123456", "Anna", DebugCall.segments, DebugCall.translations)
        phone.showsCallScreen = false
        showsCall = mode == "active"
    }
    LaunchedEffect(phone.phase) { if (phone.phase == Phase.Idle) showsCall = false }
    val showsBanner = phone.isInProgress && !phone.showsCallScreen && !showsCall
    Column(Modifier.fillMaxSize()) {
        if (showsBanner) Box(Modifier.statusBarsPadding()) { Banner(phone) { showsCall = true } }
        Box(Modifier.weight(1f).then(if (showsBanner) Modifier.consumeWindowInsets(WindowInsets.statusBars) else Modifier)) { content() }
    }
    if (showsCall && phone.phase != Phase.Idle) ActiveCallCover(onDismiss = { showsCall = false })
}

@Composable
private fun Banner(phone: PhoneCallStore, onClick: () -> Unit) {
    val style = DS.Typography.callout
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = DS.Spacing.lg)
            .background(DS.Palette.success, CircleShape)
            .plainButton(onClick = onClick)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        SFImage("phone.fill", size = 15.sp, tint = Color.White)
        Text(phone.otherParty, style = DS.Typography.cardTitle, color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        val start = phone.connectedAt
        Text(
            if (start != null) elapsed(start) else if (phone.phase == Phase.Ringing) L("callStateRinging") else L("callStateConnecting"),
            style = style.copy(fontFeatureSettings = "tnum"),
            color = Color.White,
        )
    }
}

/** The pretend call's lines (debug screenshots only; not shown in release builds). */
private object DebugCall {
    val segments = listOf(
        LiveSegment("d1", "Hi, this is Anna from the dental office. I'm calling about your appointment on Thursday.", "SPEAKER_01", 1, false, 0.0, 4.0),
        LiveSegment("d2", "Oh hi Anna, yes. Is everything still okay for 10 am?", "SPEAKER_00", 0, true, 4.5, 7.0),
        LiveSegment("d3", "We need to move it to 11:30, would that work for you?", "SPEAKER_01", 1, false, 7.5, 10.0),
        LiveSegment("d4", "11:30 works. Thanks for letting me know.", "SPEAKER_00", 0, true, 10.5, 12.5),
    )
    val translations = emptyMap<String, List<String>>()
}
