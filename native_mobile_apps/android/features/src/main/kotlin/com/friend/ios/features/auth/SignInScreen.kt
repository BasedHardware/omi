package com.friend.ios.features.auth

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiColorScheme
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiSurface
import com.friend.ios.design.pressable
import com.friend.ios.features.R
import com.friend.ios.features.settings.OmiSegmentedPicker
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.ProviderCredential
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `SignInScreen.swift`: first screen for signed-out users. Sign in with Apple runs the
 * backend's web flow in a Custom Tab (as the Flutter Android app); Google uses Credential Manager
 * when the build has a web client id ([googleSignIn] null hides it). The local harness signs in
 * through the backend's custom-token endpoint, like the Flutter dev flavor.
 */
@Composable
fun SignInScreen(googleSignIn: (suspend () -> ProviderCredential?)?) {
    val session = LocalSessionStore.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var devUserID by remember { mutableStateOf("local-dev-user") }

    // Back from the Custom Tab without the callback: the user closed it.
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && WebAuthSession.isWaiting) {
                scope.launch {
                    delay(800)
                    WebAuthSession.cancel()
                }
            }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }

    fun signInWithApple() {
        scope.launch {
            val state = WebAuthSession.randomToken()
            val verifier = WebAuthSession.randomToken(48)
            val url = session.webAuthorizeURL("apple", state, WebAuthSession.codeChallenge(verifier))
            when (val result = WebAuthSession.authorize(context, url, state)) {
                is WebAuthSession.Result.Code -> session.signInWithAuthorizationCode(result.code, verifier)
                is WebAuthSession.Result.Failed -> session.signInFailed(result.reason)
                WebAuthSession.Result.Cancelled -> Unit
            }
        }
    }

    OmiColorScheme(dark = true) {
        Box(Modifier.fillMaxSize().background(DS.Palette.background), contentAlignment = Alignment.BottomCenter) {
            PhotoReel()
            Column(
                Modifier.navigationBarsPadding().padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.md),
                verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl),
            ) {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    Text("omi", style = TextStyles.system(64, FontWeight.Bold), color = DS.Palette.ink)
                    Text(L("captureEveryMoment"), style = DS.Typography.body, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
                }
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    AppleButton(onClick = ::signInWithApple)
                    if (googleSignIn != null) {
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = DS.Size.primaryButtonHeight)
                                .pressable(pressedScale = 0.98f, pressedAlpha = 0.85f) {
                                    scope.launch {
                                        val credential = runCatching { googleSignIn() }.getOrNull() ?: return@launch
                                        session.signIn(credential)
                                    }
                                }
                                .omiSurface(CircleShape),
                            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm, Alignment.CenterHorizontally),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            SFImage("g.circle.fill", tint = DS.Palette.ink)
                            Text(L("signInWithGoogle"), style = DS.Typography.button, color = DS.Palette.ink)
                        }
                    }
                    if (session.canUseLocalDevSignIn) {
                        LocalDevSignIn(devUserID, onSelect = { devUserID = it }) { scope.launch { session.signInLocalDev(devUserID) } }
                    }
                    session.errorMessage?.let {
                        Text(it, style = DS.Typography.caption, color = DS.Palette.live, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                    }
                    Text(
                        legalText(L("byContinuingAgree"), L("privacyPolicy"), L("and"), L("termsOfUse")),
                        style = DS.Typography.micro.copy(textAlign = TextAlign.Center),
                        color = DS.Palette.inkTertiary,
                        modifier = Modifier.fillMaxWidth().padding(top = DS.Spacing.xs),
                    )
                }
            }
        }
    }
}

/** `L("byContinuingAgree") + [privacy](…) + L("and") + [terms](…) + "."`, links tinted. */
@Composable
internal fun legalText(lead: String, privacy: String, and: String, terms: String, linkColor: Color = DS.Palette.inkSecondary): AnnotatedString {
    val styles = TextLinkStyles(SpanStyle(color = linkColor))
    return buildAnnotatedString {
        append(lead)
        withLink(LinkAnnotation.Url("https://www.omi.me/pages/privacy", styles)) { append(privacy) }
        append(and)
        withLink(LinkAnnotation.Url("https://www.omi.me/pages/terms-of-service", styles)) { append(terms) }
        append(".")
    }
}

/** `SignInWithAppleButton(.signIn)` in `.white` style: white capsule, black logo and label. */
@Composable
private fun AppleButton(onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(DS.Size.primaryButtonHeight)
            .pressable(pressedScale = 0.98f, pressedAlpha = 0.85f, onClick = onClick)
            .background(Color.White, CircleShape),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Image(painterResource(R.drawable.ic_apple_logo), contentDescription = null, modifier = Modifier.size(18.dp))
        Box(Modifier.width(6.dp))
        Text(L("signInWithApple"), style = TextStyles.system(19, FontWeight.Medium), color = Color.Black)
    }
}

/** The local harness: pick a seeded user, sign in with the backend's custom token. */
@Composable
private fun LocalDevSignIn(devUserID: String, onSelect: (String) -> Unit, onSignIn: () -> Unit) {
    val session = LocalSessionStore.current
    val users = listOf("local-dev-user", "alice", "bob")
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        val pickerLabel = L("nativeLocalUser")
        Box(Modifier.semantics { contentDescription = pickerLabel }) {
            OmiSegmentedPicker(users, users.indexOf(devUserID).coerceAtLeast(0), textStyle = TextStyles.footnote) { onSelect(users[it]) }
        }
        Row(
            Modifier.fillMaxWidth().heightIn(min = DS.Size.primaryButtonHeight)
                .pressable(enabled = !session.isWorking, pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onSignIn)
                .background(DS.Palette.card, com.friend.ios.design.ContinuousRoundedShape(DS.Radius.md)),
            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (session.isWorking) OmiProgress()
            Text(L("nativeLocalSignIn"), style = DS.Typography.button, color = if (session.isWorking) DS.Palette.inkDisabled else DS.Palette.ink)
        }
    }
}

/** Omi's onboarding photos, slowly drifting and cross-fading, darkened toward the bottom. */
@Composable
internal fun PhotoReel() {
    val photos = OnboardingPhotos
    var index by remember { mutableIntStateOf(0) }
    var drift by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        drift = true
        while (true) {
            delay(5000)
            drift = false
            index = (index + 1) % photos.size
            delay(16)
            drift = true
        }
    }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val photoHeight = maxHeight * 0.75f
        photos.forEachIndexed { offset, photo ->
            val alpha by animateFloatAsState(if (offset == index) 1f else 0f, tween(1200), label = "photo")
            val scale by animateFloatAsState(
                if (drift && offset == index) 1.08f else 1f,
                if (drift) tween(6000, easing = LinearEasing) else tween(0),
                label = "drift",
            )
            if (alpha > 0f) {
                Image(
                    painterResource(photo),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    alignment = Alignment.TopCenter,
                    modifier = Modifier.fillMaxWidth().height(photoHeight).clipToBounds()
                        .graphicsLayer {
                            this.alpha = alpha
                            scaleX = scale
                            scaleY = scale
                            transformOrigin = TransformOrigin(0.5f, 0f)
                        },
                )
            }
        }
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    0f to Color.Black.copy(alpha = 0.3f),
                    0.2f to Color.Transparent,
                    0.55f to Color.Black.copy(alpha = 0.75f),
                    0.72f to Color.Black,
                ),
            ),
        )
    }
}

/** `OmiMedia.Background.allCases`. */
internal val OnboardingPhotos = listOf(
    com.friend.ios.design.R.drawable.onboarding_bg_1,
    com.friend.ios.design.R.drawable.onboarding_bg_2,
    com.friend.ios.design.R.drawable.onboarding_bg_3,
    com.friend.ios.design.R.drawable.onboarding_bg_4,
    com.friend.ios.design.R.drawable.onboarding_bg_6,
)
