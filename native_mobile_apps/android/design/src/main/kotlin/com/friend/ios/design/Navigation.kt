package com.friend.ios.design

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * `NavigationStack(path:)`: a stack of routes over a root. `push` = `path.append`, `pop` =
 * dismiss; the system back gesture pops. Screens slide like UIKit pushes.
 */
@Stable
class NavPath<Route : Any> {
    internal val routes = mutableStateListOf<Route>()
    val isEmpty: Boolean get() = routes.isEmpty()
    val last: Route? get() = routes.lastOrNull()
    fun push(route: Route) { routes.add(route) }
    fun pop() { if (routes.isNotEmpty()) routes.removeAt(routes.lastIndex) }
    fun popToRoot() = routes.clear()
}

@Composable
fun <Route : Any> rememberNavPath(): NavPath<Route> = remember { NavPath() }

@Composable
fun <Route : Any> OmiNavigationStack(
    path: NavPath<Route>,
    modifier: Modifier = Modifier,
    root: @Composable () -> Unit,
    destination: @Composable (Route) -> Unit,
) {
    val holder = rememberSaveableStateHolder()
    BackHandler(enabled = !path.isEmpty) { path.pop() }
    val depth = path.routes.size
    AnimatedContent(
        targetState = depth to path.last,
        modifier = modifier,
        transitionSpec = {
            val forward = targetState.first > initialState.first
            val spec = tween<androidx.compose.ui.unit.IntOffset>(350, easing = androidx.compose.animation.core.CubicBezierEasing(0.2f, 0.9f, 0.1f, 1f))
            if (forward) slideInHorizontally(spec) { it } togetherWith slideOutHorizontally(spec) { -it / 3 }
            else slideInHorizontally(spec) { -it / 3 } togetherWith slideOutHorizontally(spec) { it }
        },
        label = "nav",
    ) { (level, route) ->
        holder.SaveableStateProvider(level) {
            if (route == null) root() else destination(route)
        }
    }
}

/**
 * A pushed screen with the inline navigation bar (`.navigationTitle` + `.navigationBarTitleDisplayMode(.inline)`):
 * back chevron, centered 17 pt semibold title, optional trailing items, on the page color.
 */
@Composable
fun OmiPushedScreen(
    title: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    trailing: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(modifier.fillMaxSize().background(DS.Palette.background)) {
        OmiNavBar(title, onBack, Modifier.statusBarsPadding(), trailing)
        content()
    }
}

@Composable
fun OmiNavBar(title: String, onBack: (() -> Unit)?, modifier: Modifier = Modifier, trailing: @Composable RowScope.() -> Unit = {}) {
    Box(modifier.fillMaxWidth().height(52.dp).padding(horizontal = DS.Spacing.sm)) {
        if (onBack != null) {
            Box(Modifier.align(Alignment.CenterStart).plainButton(onClick = onBack)) { OmiCircleIcon("chevron.left") }
        }
        Text(
            title,
            style = TextStyles.headline,
            color = DS.Palette.ink,
            textAlign = TextAlign.Center,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.align(Alignment.Center).padding(horizontal = 56.dp),
        )
        Row(Modifier.align(Alignment.CenterEnd), verticalAlignment = Alignment.CenterVertically, content = trailing)
    }
}
