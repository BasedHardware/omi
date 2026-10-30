package com.friend.ios.features.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.Memory
import com.friend.ios.design.DS
import com.friend.ios.design.Formatted
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.service.LocalPreferences

/** Labels for Flutter's three memory kinds; any other (older) category shows as written. */
object MemoryKind {
    @Composable
    @ReadOnlyComposable
    fun title(category: String): String = when (category) {
        "system" -> L("nativeMemoryKindAboutYou")
        "interesting" -> L("filterInteresting")
        "manual" -> L("filterManual")
        else -> category.replaceFirstChar { it.uppercase() }
    }

    /** Where it was captured: this phone, an iPhone, a Mac or an Android phone. Null when unknown. */
    @Composable
    @ReadOnlyComposable
    fun device(captureDevice: String?): Pair<String, String>? {
        if (captureDevice == null) return null
        val hash = LocalPreferences.current.deviceIdHash
        if (hash != null && captureDevice == "android_$hash") return L("memoryThisPhone") to "smartphone"
        return when (captureDevice.substringBefore("_")) {
            "ios" -> L("memoryProvenanceIphone") to "iphone"
            "macos" -> L("memoryProvenanceMac") to "laptopcomputer"
            "android" -> L("memoryProvenanceAndroid") to "smartphone"
            else -> null
        }
    }
}

/**
 * Port of `MemoryCard.swift`: one memory as a quiet row, its text, then kind and date (pin and
 * visibility marks).
 */
@Composable
fun MemoryCard(memory: Memory, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(vertical = DS.Spacing.md), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.Top) {
            Text(memory.content, style = DS.Typography.cardTitle, color = DS.Palette.ink, modifier = Modifier.weight(1f))
            if (memory.isBaseline) {
                SFImage("pin", size = TextStyles.caption1.fontSize, tint = DS.Palette.inkSecondary, modifier = Modifier.padding(top = 4.dp), contentDescription = L("baselineMemory"))
            }
        }
        HStack(spacing = DS.Spacing.xs) {
            val meta = "${MemoryKind.title(memory.category)} · ${Formatted.abbreviatedDate(memory.createdAt)}"
            Text(meta, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (memory.visibility == Memory.Visibility.Public) {
                SFImage("globe", size = DS.Typography.caption.fontSize, tint = DS.Palette.inkSecondary, contentDescription = L("nativeMemoryPublic"))
            }
            MemoryKind.device(memory.captureDevice)?.let { (title, symbol) ->
                Text("·", style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                SFImage(symbol, size = DS.Typography.caption.fontSize, tint = DS.Palette.inkSecondary)
                Text(title, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1)
            }
        }
    }
}
