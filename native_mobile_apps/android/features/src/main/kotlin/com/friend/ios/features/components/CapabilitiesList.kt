package com.friend.ios.features.components

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.friend.ios.core.models.Integration
import com.friend.ios.features.auth.WebAuthSession
import com.friend.ios.service.LocalCapabilitiesStore
import kotlinx.coroutines.launch

/**
 * Port of `CapabilitiesList.connect` (`CapabilitiesList.swift`): the sign-in for one connection
 * (Settings > Apps & integrations, Home's "Connect …" card): the backend's OAuth page in a Custom
 * Tab, back through `omi://<key>/callback` (`WebAuthSession`), then a fresh state. Coming back
 * without the callback counts as cancelled; without a URL the store has recorded why.
 */
@Composable
fun rememberConnectIntegration(): (Integration) -> Unit {
    val store = LocalCapabilitiesStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        // The callback intent arrives before the resume; a resume without it means the tab was closed.
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && WebAuthSession.isConnecting) WebAuthSession.cancel()
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    return { integration ->
        scope.launch {
            val url = store.authorizationURL(integration) ?: return@launch
            when (WebAuthSession.connect(context, url)) {
                WebAuthSession.Connection.Succeeded -> Unit
                WebAuthSession.Connection.Failed -> store.loginEnded(integration, cancelled = false)
                WebAuthSession.Connection.Cancelled -> store.loginEnded(integration, cancelled = true)
            }
            store.load()
        }
    }
}
