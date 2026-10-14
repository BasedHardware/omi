package com.friend.ios.features.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import com.friend.ios.design.Detent
import com.friend.ios.design.OmiCircleIcon
import com.friend.ios.design.OmiNavBar
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.TextStyles
import com.friend.ios.design.pressable
import com.friend.ios.service.stores.GoalsStore
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Goal
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiHairline
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalGoalsStore
import kotlinx.coroutines.launch

/**
 * Port of `GoalViews.swift`. One goal: title, a progress bar, "3 of 10", and minus / plus to move
 * the number.
 */
@Composable
fun GoalRow(goal: Goal, modifier: Modifier = Modifier) {
    val goals = LocalGoalsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    @Composable
    fun step(symbol: String, label: String, delta: Double, enabled: Boolean = true) {
        Box(
            Modifier
                .size(32.dp)
                .background(DS.Palette.fill, CircleShape)
                .plainButton(enabled) {
                    haptics.selection()
                    scope.launch { goals.setProgress(goal.id, goal.current + delta) }
                },
            contentAlignment = Alignment.Center,
        ) {
            SFImage(symbol, size = 13.sp, weight = FontWeight.Bold, tint = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
        }
    }
    HStack(modifier.padding(vertical = DS.Spacing.xs), spacing = DS.Spacing.md) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
            Text(goal.title, style = DS.Typography.body, color = DS.Palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
            GoalProgressBar(goal.progress, GoalRow.tint(goal.progress))
            Text(
                L("nativeGoalProgress", GoalRow.number(goal.current), GoalRow.number(goal.target)),
                style = DS.Typography.caption.copy(fontFeatureSettings = "tnum"),
                color = DS.Palette.inkTertiary,
            )
        }
        step("minus", L("nativeDecreaseProgress"), -1.0, enabled = goal.current > 0)
        step("plus", L("nativeIncreaseProgress"), 1.0)
    }
}

/** A linear `ProgressView(value:)`: a 4 pt capsule track with the tinted part. */
@Composable
fun GoalProgressBar(progress: Double, tint: Color, modifier: Modifier = Modifier.fillMaxWidth(), height: Dp = 4.dp) {
    Box(modifier.height(height).background(DS.Palette.fill, CircleShape)) {
        Box(Modifier.fillMaxHeight().fillMaxWidth(progress.toFloat().coerceIn(0f, 1f)).background(tint, CircleShape))
    }
}

object GoalRow {
    /** Flutter's colors: green from 80 %, orange from 20 %. */
    @Composable
    fun tint(progress: Double): Color = when {
        progress >= 0.8 -> DS.Palette.success
        progress >= 0.2 -> DS.Palette.warning
        else -> DS.Palette.inkTertiary
    }

    /** Accepts "2,5" as well as "2.5". */
    fun parse(text: String): Double? = text.trim().replace(",", ".").toDoubleOrNull()

    fun number(value: Double): String =
        if (value == Math.rint(value)) value.toLong().toString() else String.format(java.util.Locale.getDefault(), "%.1f", value)
}

/**
 * Port of `GoalFormSheet` (Flutter `goal_form_sheet.dart`): add or edit a goal: title, current,
 * target; delete when editing. `goal == null` adds one. Medium detent, as iOS.
 */
@Composable
fun GoalFormSheet(goal: Goal?, onDismiss: () -> Unit) {
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium)) {
        GoalForm(goal, onDismiss)
    }
}

@Composable
private fun GoalForm(goal: Goal?, onDismiss: () -> Unit) {
    val goals = LocalGoalsStore.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    var title by remember { mutableStateOf(goal?.title ?: "") }
    var current by remember { mutableStateOf(goal?.let { GoalRow.number(it.current) } ?: "0") }
    var target by remember { mutableStateOf(goal?.let { GoalRow.number(it.target) } ?: "100") }
    var isSaving by remember { mutableStateOf(false) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { if (goal == null) focus.requestFocus() }
    val canSave = title.isNotBlank() && !isSaving

    fun save() {
        val currentValue = GoalRow.parse(current) ?: goal?.current ?: 0.0
        val targetValue = GoalRow.parse(target) ?: goal?.target ?: 100.0
        isSaving = true
        scope.launch {
            val saved = if (goal != null) goals.update(goal.id, title, currentValue, targetValue) else goals.create(title, currentValue, targetValue)
            isSaving = false
            if (saved) {
                haptics.success()
                onDismiss()
            }
        }
    }

    Column {
        Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
            Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onDismiss))
            Text(if (goal == null) L("addGoal") else L("editGoal"), style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
            Text(
                if (goal == null) L("addGoal") else L("save"), style = TextStyles.headline, color = if (canSave) DS.Palette.ink else DS.Palette.inkDisabled,
                modifier = Modifier.align(Alignment.CenterEnd).plainButton(enabled = canSave, onClick = ::save),
            )
        }
        val placeholder = L("goalTitle")
        val currentLabel = L("current")
        val targetLabel = L("target")
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                row {
                    Box(Modifier.fillMaxWidth()) {
                        if (title.isEmpty()) Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary)
                        BasicTextField(
                            title, { title = it }, singleLine = true,
                            textStyle = DS.Typography.body.copy(color = DS.Palette.ink), cursorBrush = SolidColor(DS.Palette.agent),
                            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                            modifier = Modifier.fillMaxWidth().focusRequester(focus).semantics { contentDescription = placeholder },
                        )
                    }
                }
                row { NumberRow(currentLabel, current) { current = it } }
                row { NumberRow(targetLabel, target) { target = it } }
                goals.lastError?.let { error -> row { Text(error, style = DS.Typography.caption, color = DS.Palette.live) } }
            }
            if (goal != null) {
                val delete = L("deleteGoal")
                section {
                    row(onClick = {
                        onDismiss()
                        goals.deleteWithUndo(goal.id)
                    }) { Text(delete, style = DS.Typography.body, color = DS.Palette.live) }
                }
            }
        }
    }
}

/** `LabeledContent` with a trailing decimal field. */
@Composable
private fun NumberRow(label: String, value: String, onChange: (String) -> Unit) {
    HStack(Modifier.fillMaxWidth()) {
        Text(label, style = DS.Typography.body, color = DS.Palette.ink)
        Spacer(Modifier.width(DS.Spacing.md))
        Box(Modifier.weight(1f), contentAlignment = Alignment.CenterEnd) {
            if (value.isEmpty()) Text("0", style = DS.Typography.body, color = DS.Palette.inkTertiary)
            BasicTextField(
                value, onChange, singleLine = true,
                textStyle = DS.Typography.body.copy(color = DS.Palette.ink, textAlign = TextAlign.End, fontFeatureSettings = "tnum"),
                cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth().semantics { contentDescription = label },
            )
        }
    }
}

/**
 * Port of `GoalsScreen`: all goals: tap to edit, swipe to delete (with Undo), plus to add (at
 * most four). Opened from Home's goals line, Tasks and the chat's goal card; it draws its own
 * bar (the title and the plus, iOS's `.omiPage` with the toolbar).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GoalsScreen(modifier: Modifier = Modifier) {
    val goals = LocalGoalsStore.current
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf<Goal?>(null) }
    var adding by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { goals.load() }
    Column(modifier.fillMaxSize()) {
        val addGoal = L("addGoal")
        OmiNavBar(L("goals"), onBack = null) {
            OmiCircleIcon(
                "plus",
                Modifier
                    .plainButton(enabled = goals.canAdd) { adding = true }
                    .semantics { contentDescription = addGoal }
                    .alpha(if (goals.canAdd) 1f else 0.35f),
            )
        }
        Box(Modifier.fillMaxSize()) {
            val refreshing = remember { mutableStateOf(false) }
            PullToRefreshBox(
                isRefreshing = refreshing.value,
                onRefresh = {
                    refreshing.value = true
                    scope.launch {
                        goals.load()
                        refreshing.value = false
                    }
                },
                modifier = Modifier.fillMaxSize(),
            ) {
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = DS.Spacing.gutter)) {
                    items(goals.goals, key = { it.id }) { goal ->
                        SwipeToDelete(onDelete = { goals.deleteWithUndo(goal.id) }) {
                            Column(Modifier.background(DS.Palette.background).fillMaxWidth().pressable(pressedScale = 1f, haptic = false) { editing = goal }) {
                                GoalRow(goal, Modifier.padding(vertical = DS.Spacing.sm))
                                OmiHairline()
                            }
                        }
                    }
                    if (!goals.canAdd) {
                        item {
                            Text(
                                L("maximumGoalsAllowed", "${GoalsStore.maxGoals}"),
                                style = DS.Typography.caption,
                                color = DS.Palette.inkTertiary,
                                modifier = Modifier.padding(vertical = DS.Spacing.md),
                            )
                        }
                    }
                }
            }
            if (goals.phase == GoalsStore.Phase.Loaded && goals.goals.isEmpty()) {
                OmiEmptyState(
                    L("nativeNoGoals"), "flag", Modifier.align(Alignment.Center), message = L("nativeNoGoalsBody"),
                    actionTitle = addGoal, action = { adding = true },
                )
            }
            GoalUndoToast(Modifier.align(Alignment.BottomCenter).padding(bottom = DS.Spacing.lg))
        }
    }
    if (adding) GoalFormSheet(null) { adding = false }
    editing?.let { goal -> GoalFormSheet(goal) { editing = null } }
}

/**
 * `.swipeActions { Button(role: .destructive) }`: a leftward swipe past the threshold deletes
 * (red behind the row, the trash glyph at the end). TalkBack gets the same action ("Delete").
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeToDelete(onDelete: () -> Unit, content: @Composable () -> Unit) {
    val state = rememberSwipeToDismissBoxState()
    LaunchedEffect(state.currentValue) {
        if (state.currentValue == SwipeToDismissBoxValue.EndToStart) {
            onDelete()
            state.snapTo(SwipeToDismissBoxValue.Settled)
        }
    }
    val delete = L("delete")
    SwipeToDismissBox(
        state = state,
        enableDismissFromStartToEnd = false,
        modifier = Modifier.semantics {
            customActions = listOf(CustomAccessibilityAction(delete) { onDelete(); true })
        },
        backgroundContent = {
            Box(Modifier.fillMaxSize().background(DS.Palette.live).padding(horizontal = DS.Spacing.lg), contentAlignment = Alignment.CenterEnd) {
                SFImage("trash", tint = Color.White)
            }
        },
    ) { content() }
}
