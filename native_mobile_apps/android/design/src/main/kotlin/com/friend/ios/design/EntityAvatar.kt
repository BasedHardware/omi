package com.friend.ios.design

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest

/** What an [EntityAvatar] draws (mirrors the service's `EntityVisual`, without depending on it). */
sealed interface AvatarContent {
    /** A brand logo: bundled (`logo_<key>` drawable) or loaded by domain. */
    data class Logo(val domain: String, val bundled: String? = null) : AvatarContent
    data class Monogram(val name: String) : AvatarContent
    data class Emoji(val emoji: String, val category: String?) : AvatarContent
    data class Symbol(val systemName: String) : AvatarContent
}

/**
 * The picture at the start of a row: a brand logo on a white plate (rounded square), a person's
 * monogram (circle), the conversation's emoji on a soft category tint, or a glyph. A logo that
 * fails to load falls back to [fallback] (a wrong or blank logo is worse than a neutral tile).
 */
@Composable
fun EntityAvatar(content: AvatarContent, modifier: Modifier = Modifier, size: Dp = 40.dp, fallback: AvatarContent? = null) {
    val square = ContinuousRoundedShape(size * 0.28f)
    when (content) {
        is AvatarContent.Logo -> {
            val bundled = content.bundled?.let { bundledLogo(it) }
            var failed by remember(content.domain) { mutableStateOf(false) }
            if (failed && fallback != null) {
                EntityAvatar(fallback, modifier, size)
                return
            }
            Box(
                modifier.size(size).background(Color.White, square).border(DS.Stroke.hairline, DS.Palette.hairline, square).padding(size * 0.16f),
                contentAlignment = Alignment.Center,
            ) {
                if (bundled != null) {
                    Image(painterResource(bundled), null, contentScale = ContentScale.Fit)
                } else {
                    AsyncImage(
                        model = ImageRequest.Builder(LocalContext.current).data(LogoURL.forDomain(content.domain)).crossfade(true).build(),
                        contentDescription = null,
                        contentScale = ContentScale.Fit,
                        onError = { failed = true },
                    )
                }
            }
        }
        is AvatarContent.Monogram -> {
            val initials = content.name.split(" ").filter { it.isNotEmpty() }.take(2).joinToString("") { it.take(1).uppercase() }
            val hue = monogramColors[(content.name.lowercase().hashCode() and 0x7fffffff) % monogramColors.size]
            Box(
                modifier.size(size).background(Brush.linearGradient(listOf(hue.first, hue.second)), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Text(initials, style = TextStyles.system((size.value * 0.38f).toInt(), FontWeight.SemiBold), color = Color.White)
            }
        }
        is AvatarContent.Emoji -> Box(
            modifier.size(size).background(categoryTint(content.category).copy(alpha = if (LocalOmiDark.current) 0.18f else 0.12f), square),
            contentAlignment = Alignment.Center,
        ) {
            Text(content.emoji, style = TextStyles.system((size.value * 0.5f).toInt()).copy(letterSpacing = 0.sp))
        }
        is AvatarContent.Symbol -> Box(modifier.size(size).background(DS.Palette.fill, square), contentAlignment = Alignment.Center) {
            SFImage(content.systemName, size = (size.value * 0.42f).sp, tint = DS.Palette.inkSecondary)
        }
    }
}

/** Brand logos by domain: logo.dev, 404 for unknown domains so the fallback shows (never its placeholder). */
object LogoURL {
    /** logo.dev publishable key (safe to embed; the same kind Iris ships). */
    var token: String = "pk_X-1ZO13GSgeOoUrIuJ6GMQ"

    fun forDomain(domain: String): String = "https://img.logo.dev/$domain?token=$token&size=128&format=png&fallback=404"
}

@Composable
private fun bundledLogo(key: String): Int? {
    val context = LocalContext.current
    @Suppress("DiscouragedApi")
    val id = remember(key) { context.resources.getIdentifier("logo_$key", "drawable", context.packageName) }
    return id.takeIf { it != 0 }
}

/** A soft hue per conversation category, so emoji tiles don't all read the same. */
@Composable
private fun categoryTint(category: String?): Color = when (category) {
    "health" -> DS.Palette.live
    "finance", "economics", "business" -> DS.Palette.success
    "work", "technology", "education" -> DS.Palette.agent
    "travel", "personal", "family" -> DS.Palette.amber
    "social" -> hex(0xA855F7)
    else -> DS.Palette.inkTertiary
}

private val monogramColors = listOf(
    hex(0x60A5FA) to hex(0x2563EB),
    hex(0xF472B6) to hex(0xDB2777),
    hex(0x34D399) to hex(0x059669),
    hex(0xFBBF24) to hex(0xD97706),
    hex(0xA78BFA) to hex(0x7C3AED),
    hex(0x22D3EE) to hex(0x0891B2),
)
