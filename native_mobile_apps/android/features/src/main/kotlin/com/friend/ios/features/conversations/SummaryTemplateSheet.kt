package com.friend.ios.features.conversations

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.SubcomposeAsyncImage
import com.friend.ios.core.models.OmiApp
import com.friend.ios.core.models.SummaryTemplateDraft
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.SkeletonBlock
import com.friend.ios.design.TextStyles
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.SummaryTemplatesStore
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream

/**
 * Port of `SummaryTemplateSheet.swift`: "Summary template": which app summarizes this
 * conversation. Tap an app to summarize again with it; long-press to make it the default for
 * future conversations (iOS also swipes); "Create custom template" writes a new one (Flutter
 * `summarized_apps_sheet`, `create_template_bottom_sheet`). The form is pushed inside the sheet.
 */
@Composable
fun SummaryTemplateSheet(templates: SummaryTemplatesStore, detail: ConversationDetailStore, creating: Boolean = false, onDismiss: () -> Unit) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var makingDefault by remember { mutableStateOf<OmiApp?>(null) }
    var isCreating by remember { mutableStateOf(creating) }
    LaunchedEffect(Unit) { if (templates.phase == SummaryTemplatesStore.Phase.Loading) templates.load(detail.conversation.id) }

    OmiSheet(onDismiss = onDismiss) {
        if (isCreating) {
            CreateTemplateForm(templates, onBack = { isCreating = false }, onDone = { isCreating = false })
            return@OmiSheet
        }
        SheetBar(L("summaryTemplate"), leading = { SheetBarButton(L("cancel"), onClick = onDismiss) })
        val suggestedTitle = L("suggestedTemplates")
        val appsTitle = if (templates.suggested.isEmpty()) L("availableTemplates") else L("otherTemplates")
        val creative = L("getCreative")
        val createTitle = L("createCustomTemplate")
        val setDefault = L("setDefaultButton")

        fun summarize(app: OmiApp) {
            haptics.tap()
            scope.launch { if (templates.summarize(detail, app, conversations)) onDismiss() }
        }

        OmiGroupedList {
            if (templates.phase == SummaryTemplatesStore.Phase.Loading) {
                section {
                    repeat(3) { index -> plainRow(key = "skeleton$index") { SkeletonBlock(Modifier.padding(vertical = DS.Spacing.xs), height = 44.dp) } }
                }
            } else {
                if (templates.suggested.isNotEmpty()) {
                    section(header = suggestedTitle) {
                        templates.suggested.forEach { app ->
                            row(key = app.id, enabled = templates.working == null, onClick = { summarize(app) }) { TemplateRow(app, templates, detail) }
                        }
                    }
                }
                if (templates.apps.isNotEmpty()) {
                    section(header = appsTitle) {
                        templates.apps.forEach { app ->
                            row(key = app.id, enabled = templates.working == null) {
                                // The default action lives in the long-press menu (iOS: swipe or context menu).
                                val canDefault = app.id != templates.defaultAppID
                                ContextMenuBox(
                                    sections = {
                                        if (canDefault) listOf(MenuSection(items = listOf(MenuItem(setDefault, "star") { makingDefault = app }))) else emptyList()
                                    },
                                    modifier = Modifier.weight(1f),
                                    onTap = { if (templates.working == null) summarize(app) },
                                ) { Box { HStack(spacing = DS.Spacing.md) { TemplateRow(app, templates, detail) } } }
                            }
                        }
                    }
                }
                section(header = creative) {
                    row(key = "create", onClick = { isCreating = true }) { ActionLabel(createTitle, "plus.circle") }
                }
            }
        }
    }

    makingDefault?.let { app ->
        OmiAlert(
            L("setDefaultApp"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("setDefaultButton")) { scope.launch { templates.setDefault(app) } },
            ),
            onDismiss = { makingDefault = null },
            message = L("setDefaultAppContent", app.name),
        )
    }
    templates.failure?.let { failure ->
        val title = when (failure) {
            is SummaryTemplatesStore.Failure.Install -> L("failedToInstallApp", failure.name)
            SummaryTemplatesStore.Failure.SaveDefault -> L("failedToSaveCheckConnection")
            SummaryTemplatesStore.Failure.Create -> L("failedToCreateApp")
            SummaryTemplatesStore.Failure.Reprocess -> L("nativeSummaryFailed")
        }
        OmiAlert(title, listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { templates.failure = null })
    }
}

/** One app: its icon, name with a "Default" / "Last used" tag, description; a check on the current one. */
@Composable
private fun androidx.compose.foundation.layout.RowScope.TemplateRow(app: OmiApp, templates: SummaryTemplatesStore, detail: ConversationDetailStore) {
    AppIcon(app)
    Spacer(Modifier.width(DS.Spacing.md))
    Column(Modifier.weight(1f)) {
        HStack(spacing = DS.Spacing.xs) {
            Text(app.name, style = DS.Typography.cardTitle, color = DS.Palette.ink)
            when (app.id) {
                templates.defaultAppID -> Tag(L("defaultLabel"), "star.fill")
                templates.lastUsedAppID -> Tag(L("lastUsedLabel"), "clock")
            }
        }
        if (app.description.isNotEmpty()) {
            Text(app.description, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 2, modifier = Modifier.padding(top = DS.Spacing.xxs))
        }
    }
    if (templates.working == app.id) {
        OmiProgress()
    } else if (app.id == detail.detail?.summaryAppID) {
        SFImage("checkmark", tint = DS.Palette.agent, contentDescription = L("nativeSelected"))
    }
}

@Composable
private fun Tag(title: String, systemImage: String) {
    HStack(
        Modifier.background(DS.Palette.agentSoft, CircleShape).padding(horizontal = DS.Spacing.xs + 2.dp, vertical = 2.dp),
        spacing = 3.dp,
    ) {
        SFImage(systemImage, size = 10.sp, tint = DS.Palette.agent)
        Text(title, style = DS.Typography.micro, color = DS.Palette.agent)
    }
}

/** An app's picture, or its initial on a tinted square. */
@Composable
fun AppIcon(app: OmiApp) {
    val shape = ContinuousRoundedShape(9.dp)
    val placeholder: @Composable () -> Unit = {
        Box(Modifier.fillMaxSize().background(DS.Palette.agentSoft), contentAlignment = Alignment.Center) {
            Text(app.name.take(1).uppercase(), style = TextStyles.headline, color = DS.Palette.agent)
        }
    }
    Box(Modifier.size(36.dp).clip(shape)) {
        val url = app.imageURL
        if (url != null) {
            SubcomposeAsyncImage(
                model = url,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
                loading = { placeholder() },
                error = { placeholder() },
            )
        } else {
            placeholder()
        }
    }
}

/**
 * "Create custom template": a name and the prompt the app runs on each conversation, private unless
 * made public. Omi picks the description and icon; the app is installed right away.
 */
@Composable
fun CreateTemplateForm(templates: SummaryTemplatesStore, onBack: () -> Unit, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var draft by remember { mutableStateOf(SummaryTemplateDraft("", "")) }
    var tried by remember { mutableStateOf(false) }

    fun create() {
        tried = true
        if (draft.problem != null) return
        scope.launch { if (templates.create(draft, CreateTemplateForm::icon) != null) onDone() }
    }

    val problemText = when (draft.problem) {
        SummaryTemplateDraft.Problem.NameMissing -> L("pleaseEnterAppName")
        SummaryTemplateDraft.Problem.NameTooShort -> L("nameMustBeAtLeast3Characters")
        SummaryTemplateDraft.Problem.PromptMissing -> L("pleaseEnterAppPrompt")
        SummaryTemplateDraft.Problem.PromptTooShort -> L("promptMustBeAtLeast10Characters")
        null -> null
    }
    val stepText = when (templates.creationStep) {
        SummaryTemplatesStore.CreationStep.Describing -> L("generatingDescription")
        SummaryTemplatesStore.CreationStep.Creating -> L("creatingYourApp")
        SummaryTemplatesStore.CreationStep.Installing -> L("installingApp")
        null -> null
    }
    SheetBar(
        L("createCustomTemplate"),
        leading = { SheetBarIcon("chevron.left", onClick = onBack) },
        trailing = {
            if (stepText != null) {
                HStack(spacing = DS.Spacing.xs) {
                    OmiProgress()
                    Text(stepText, style = DS.Typography.caption, color = DS.Palette.ink)
                }
            } else {
                SheetBarButton(L("createApp"), prominent = true, onClick = ::create)
            }
        },
    )
    val nameHint = L("templateNameHint")
    val promptHint = L("conversationPromptHint")
    val makePublic = L("makePublic")
    val publicFooter = if (draft.isPublic) L("anyoneCanDiscoverTemplate") else L("onlyYouCanUseTemplate")
    val problem = draft.problem
    val nameProblem = if (tried && (problem == SummaryTemplateDraft.Problem.NameMissing || problem == SummaryTemplateDraft.Problem.NameTooShort)) problemText else null
    val promptProblem = if (tried && (problem == SummaryTemplateDraft.Problem.PromptMissing || problem == SummaryTemplateDraft.Problem.PromptTooShort)) problemText else null
    OmiGroupedList {
        section(
            header = L("templateName"),
            footerContent = nameProblem?.let { text -> { Text(text, style = TextStyles.footnote, color = DS.Palette.live) } },
        ) {
            row { FormField(draft.name, nameHint, singleLine = true) { draft = draft.copy(name = it) } }
        }
        section(
            header = L("conversationPrompt"),
            footerContent = promptProblem?.let { text -> { Text(text, style = TextStyles.footnote, color = DS.Palette.live) } },
        ) {
            row { FormField(draft.prompt, promptHint, singleLine = false) { draft = draft.copy(prompt = it) } }
        }
        section {
            row {
                OmiToggleRow(draft.isPublic, { draft = draft.copy(isPublic = it) }) {
                    Column {
                        Text(makePublic, style = DS.Typography.body, color = DS.Palette.ink)
                        Text(publicFooter, style = DS.Typography.caption, color = DS.Palette.inkSecondary, modifier = Modifier.padding(top = DS.Spacing.xxs))
                    }
                }
            }
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.FormField(value: String, hint: String, singleLine: Boolean, onChange: (String) -> Unit) {
    Box(Modifier.weight(1f)) {
        if (value.isEmpty()) Text(hint, style = DS.Typography.body, color = DS.Palette.inkTertiary)
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = singleLine,
            minLines = if (singleLine) 1 else 4,
            maxLines = if (singleLine) 1 else 8,
            textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
            cursorBrush = SolidColor(DS.Palette.agent),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

object CreateTemplateForm {
    /** The emoji on white, 256 px square, as the app's icon PNG (Flutter draws the same). */
    fun icon(emoji: String): ByteArray? = runCatching {
        val bitmap = Bitmap.createBitmap(256, 256, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(AndroidColor.WHITE)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = 160f
            textAlign = Paint.Align.CENTER
        }
        val metrics = paint.fontMetrics
        canvas.drawText(emoji, 128f, 128f - (metrics.ascent + metrics.descent) / 2, paint)
        ByteArrayOutputStream().use { out ->
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
            bitmap.recycle()
            out.toByteArray()
        }
    }.getOrNull()
}
