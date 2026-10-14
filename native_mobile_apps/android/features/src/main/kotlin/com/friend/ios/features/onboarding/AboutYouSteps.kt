package com.friend.ios.features.onboarding

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.bold
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.stores.OnboardingStore
import kotlinx.coroutines.launch

// About you

@Composable
internal fun NameStep(store: OnboardingStore) {
    val scope = rememberCoroutineScope()
    val focus = remember { FocusRequester() }
    OnboardingLayout(
        kicker = L("nativeKickerAboutYou"), title = L("nativeWhatShouldOmiCallYou"),
        button = StepButton(
            title = L("continueButton"),
            isEnabled = store.givenName.isNotBlank(),
            action = { scope.launch { store.saveName() } },
        ),
    ) {
        val style = TextStyles.title2.semibold().copy(color = DS.Palette.ink)
        Box(
            Modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard(padding = 0.dp).height(60.dp).padding(horizontal = DS.Spacing.lg),
            contentAlignment = Alignment.CenterStart,
        ) {
            if (store.givenName.isEmpty()) Text(L("enterYourName"), style = style, color = DS.Palette.inkTertiary)
            BasicTextField(
                value = store.givenName,
                onValueChange = { store.givenName = it },
                textStyle = style,
                singleLine = true,
                cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Next),
                keyboardActions = KeyboardActions(onNext = { scope.launch { store.saveName() } }),
                modifier = Modifier.fillMaxWidth().focusRequester(focus),
            )
        }
        LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
    }
}

/**
 * Every language the user speaks, as simple as a list can be: the common ones and a search
 * field for the rest. A tap picks, another tap takes it out; the order of the taps is the order
 * of importance (a small 1, 2, 3), the first is the main language. Nothing is picked to begin.
 */
@Composable
internal fun LanguageStep(store: OnboardingStore) {
    val scope = rememberCoroutineScope()
    var search by remember { mutableStateOf("") }
    val focusManager = LocalFocusManager.current
    LaunchedEffect(Unit) { store.loadLanguages() }
    OnboardingLayout(
        kicker = L("nativeKickerAboutYou"), title = L("nativeWhichLanguages"), subtitle = L("nativeLanguagesTapHint"),
        button = StepButton(
            title = L("continueButton"), isEnabled = store.spokenLanguages.isNotEmpty(),
            action = { scope.launch { store.saveLanguage() } },
        ),
        scrolls = false,
    ) {
        Column(Modifier.padding(horizontal = DS.Spacing.gutter).weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            // Search field
            HStack(Modifier.onboardingCard(padding = 0.dp).height(48.dp).padding(horizontal = DS.Spacing.lg), spacing = DS.Spacing.sm) {
                SFImage("magnifyingglass", tint = DS.Palette.inkTertiary)
                Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
                    if (search.isEmpty()) Text(L("nativeSearchLanguages"), style = TextStyles.body, color = DS.Palette.inkTertiary)
                    BasicTextField(
                        value = search,
                        onValueChange = { search = it },
                        textStyle = TextStyles.body.copy(color = DS.Palette.ink),
                        singleLine = true,
                        cursorBrush = SolidColor(DS.Palette.agent),
                        keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                if (search.isNotEmpty()) {
                    Box(Modifier.plainButton { search = "" }) { SFImage("xmark.circle.fill", tint = DS.Palette.inkTertiary, contentDescription = L("nativeClearSearch")) }
                }
            }
            // The common languages show at once; only searching the full list waits for it.
            if (store.languages.isEmpty() && search.isNotEmpty()) {
                Box(Modifier.fillMaxWidth().padding(top = DS.Spacing.xl), contentAlignment = Alignment.Center) { OmiProgress() }
            } else {
                val rows = store.languageRows(search)
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                    Column(Modifier.onboardingCard(padding = 0.dp)) {
                        rows.forEachIndexed { index, language ->
                            LanguageRow(language.name, store.rank(language.code)) {
                                store.toggleLanguage(language.code)
                                if (search.isNotEmpty()) {
                                    search = ""
                                    focusManager.clearFocus()
                                }
                            }
                            if (index < rows.size - 1) {
                                Box(Modifier.fillMaxWidth().padding(start = DS.Spacing.lg).height(0.5.dp).background(DS.Palette.ink.copy(alpha = 0.08f)))
                            }
                        }
                        if (rows.isEmpty()) {
                            Box(Modifier.fillMaxWidth().heightIn(min = 52.dp), contentAlignment = Alignment.Center) {
                                Text(L("nativeNoLanguageMatches"), color = DS.Palette.inkSecondary)
                            }
                        }
                    }
                }
            }
            store.errorMessage?.let { Text(it, style = DS.Typography.caption, color = DS.Palette.live) }
        }
    }
}

/** A language: its name, and when picked its place (1 is the main language) in a small badge. */
@Composable
private fun LanguageRow(name: String, rank: Int?, action: () -> Unit) {
    val haptics = rememberHaptics()
    val value = rank?.let { L("nativeLanguageRank", "$it") }
    HStack(
        Modifier
            .fillMaxWidth()
            .height(48.dp)
            .plainButton { haptics.selection(); action() }
            // The badge reads as the row's value ("1st"), and a picked row is selected.
            .semantics(mergeDescendants = true) {
                selected = rank != null
                if (value != null) stateDescription = value
            }
            .padding(horizontal = DS.Spacing.lg),
        spacing = DS.Spacing.md,
    ) {
        Text(name, style = if (rank == null) TextStyles.body else TextStyles.body.semibold(), color = DS.Palette.ink, modifier = Modifier.weight(1f))
        Box(
            Modifier.size(26.dp).then(
                if (rank != null) Modifier.background(DS.Palette.agent, CircleShape)
                else Modifier.border(1.5.dp, DS.Palette.ink.copy(alpha = 0.22f), CircleShape),
            ),
            contentAlignment = Alignment.Center,
        ) {
            if (rank != null) Text("$rank", style = TextStyles.footnote.bold(), color = androidx.compose.ui.graphics.Color.White, modifier = Modifier.clearAndSetSemantics {})
        }
    }
}

@Composable
internal fun SourceStep(store: OnboardingStore) {
    var picked by remember { mutableStateOf<String?>(null) }
    val haptics = rememberHaptics()
    val options = listOf("Friend", "TikTok", "Instagram", "YouTube", "X / Twitter", "Reddit", "Podcast", "Google", "Other")
    OnboardingLayout(
        kicker = L("nativeKickerAboutYou"), title = L("whereDidYouHearAboutOmi"),
        button = StepButton(title = L("continueButton"), isEnabled = picked != null, action = { store.saveSource(picked) }),
        secondary = StepButton(title = L("skip"), action = { store.saveSource(null) }),
    ) {
        FlowLayout(DS.Spacing.sm, Modifier.padding(horizontal = DS.Spacing.gutter)) {
            options.forEach { option ->
                val selected = picked == option
                Box(
                    Modifier.heightIn(min = 44.dp)
                        .background(if (selected) DS.Palette.accent else DS.Palette.ink.copy(alpha = 0.07f), CircleShape)
                        .plainButton { haptics.selection(); picked = option }
                        .padding(horizontal = DS.Spacing.lg),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(option, style = TextStyles.body.medium(), color = if (selected) DS.Palette.onAccent else DS.Palette.ink)
                }
            }
        }
    }
}
