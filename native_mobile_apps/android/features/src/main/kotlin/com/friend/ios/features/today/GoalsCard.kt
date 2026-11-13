package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.SubcomposeLayout
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Goal
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiCardSurface
import com.friend.ios.design.pressable
import com.friend.ios.features.components.GoalProgressBar
import com.friend.ios.features.components.GoalRow
import com.friend.ios.features.components.GoalsScreen
import com.friend.ios.service.LocalGoalsStore

/**
 * Port of `GoalsCard.swift`: Home's goals (Flutter `goals_widget.dart`) as one quiet line at the
 * bottom: the first goal's progress as dots and "3/4 workouts", "+1" for more. Only when there
 * are goals; tapping opens all goals, where each one can be moved or edited.
 */
@Composable
fun GoalsCard(modifier: Modifier = Modifier) {
    val goals = LocalGoalsStore.current
    var showsAll by remember { mutableStateOf(false) }
    val goal = goals.goals.firstOrNull() ?: return
    val hint = L("nativeHomeOpenGoals")
    // `ViewThatFits`: one line while it fits, else the same parts stacked (large text sizes).
    ViewThatFits(
        modifier
            .padding(top = DS.Spacing.xl)
            .fillMaxWidth()
            .pressable { showsAll = true }
            .semantics(mergeDescendants = true) { onClick(label = hint) { showsAll = true; true } }
            .heightIn(min = 52.dp)
            .omiCardSurface()
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.md),
        wide = { HStack(Modifier.fillMaxWidth(), spacing = DS.Spacing.md) { Parts(goal, goals.goals.size, Modifier.weight(1f)) } },
        narrow = {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                Parts(goal, goals.goals.size, Modifier.fillMaxWidth())
            }
        },
    )
    if (showsAll) {
        OmiSheet(onDismiss = { showsAll = false }) {
            GoalsScreen()
        }
    }
}

/** The card's parts: the label, the progress, then "3/4 workouts +1" and the chevron. */
@Composable
private fun Parts(goal: Goal, count: Int, fill: Modifier) {
    Text(L("goals"), style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 1, softWrap = false)
    Progress(goal)
    HStack(fill, spacing = DS.Spacing.xs) {
        val style = DS.Typography.callout
        Text(
            "${GoalRow.number(goal.current)}/${GoalRow.number(goal.target)}",
            style = style.copy(fontFeatureSettings = "tnum"),
            color = DS.Palette.ink,
            maxLines = 1,
            softWrap = false,
        )
        Text(goal.title, style = style, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        if (count > 1) Text("+${count - 1}", style = style, color = DS.Palette.inkTertiary, maxLines = 1)
        Spacer(Modifier.weight(1f))
        SFImage("chevron.right", size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
    }
}

/**
 * `ViewThatFits(in: .horizontal)`: [wide] when its ideal width (the max intrinsic width) fits the
 * offered width, else [narrow].
 */
@Composable
private fun ViewThatFits(modifier: Modifier, wide: @Composable () -> Unit, narrow: @Composable () -> Unit) {
    SubcomposeLayout(modifier) { constraints ->
        val ideal = subcompose("ideal", wide).sumOf { it.maxIntrinsicWidth(constraints.maxHeight) }
        val content = if (ideal <= constraints.maxWidth) wide else narrow
        val placeables = subcompose(if (content === wide) "wide" else "narrow", content).map { it.measure(constraints) }
        val width = placeables.maxOfOrNull { it.width } ?: constraints.minWidth
        val height = placeables.maxOfOrNull { it.height } ?: constraints.minHeight
        layout(width, height) { placeables.forEach { it.place(0, 0) } }
    }
}

/** More steps than this read better as a bar than as dots. */
private const val maxDots = 10

@Composable
private fun Progress(goal: Goal) {
    val steps = goal.target.toInt()
    if (goal.target == Math.rint(goal.target) && steps in 1..maxDots) {
        Row(horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
            val tint = GoalRow.tint(goal.progress)
            repeat(steps) { index ->
                Box(Modifier.size(8.dp).background(if (index < goal.current) tint else DS.Palette.fill, ContinuousRoundedShape(2.dp)))
            }
        }
    } else {
        GoalProgressBar(goal.progress, GoalRow.tint(goal.progress), Modifier.width(56.dp))
    }
}
