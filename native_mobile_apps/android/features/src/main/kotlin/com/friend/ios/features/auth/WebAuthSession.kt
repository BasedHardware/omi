package com.friend.ios.features.auth

import android.content.Context
import android.net.Uri
import android.util.Base64
import androidx.browser.customtabs.CustomTabsIntent
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * Sign in with Apple on Android: the backend's web flow (`/v1/auth/authorize`) in a Custom Tab,
 * back through `omi://auth/callback` (Flutter `AuthService.authenticateWithProvider`). A
 * connection's login (`CapabilitiesList.connect`, iOS's `ASWebAuthenticationSession` with the
 * `omi` callback scheme) comes back the same way, through `omi://<key>/callback?success=`.
 *
 * The app's deep-link entry hands every incoming URI to [handle] first.
 */
object WebAuthSession {
    /** The authorization code and state the callback carried, or why it did not. */
    sealed interface Result {
        data class Code(val code: String, val state: String?) : Result
        data class Failed(val reason: String) : Result
        data object Cancelled : Result
    }

    private var pending: CompletableDeferred<Result>? = null

    /** A browser sign-in is open and waiting for its callback. */
    val isWaiting: Boolean get() = pending?.isActive == true

    /** How a connection's login ended. */
    enum class Connection { Succeeded, Failed, Cancelled }

    private var pendingConnection: CompletableDeferred<Connection>? = null

    /** A connection's login is open and waiting for its callback. */
    val isConnecting: Boolean get() = pendingConnection?.isActive == true

    /** True when [uri] was the auth callback or a connection's callback (consumed here). */
    fun handle(uri: Uri): Boolean {
        if (uri.scheme == "omi" && uri.host != "auth" && uri.path == "/callback") {
            // The backend's callback page redirects to omi://<key>/callback?success=true.
            pendingConnection?.complete(if (uri.getQueryParameter("success") == "false") Connection.Failed else Connection.Succeeded)
            return true
        }
        if (uri.host != "auth" || uri.path != "/callback" || uri.scheme !in setOf("omi", "omi-dev", "omi-beta")) return false
        val code = uri.getQueryParameter("code")
        val result = if (code != null) {
            Result.Code(code, uri.getQueryParameter("state"))
        } else {
            Result.Failed(uri.getQueryParameter("error_description") ?: uri.getQueryParameter("error") ?: "No authorization code received")
        }
        pending?.complete(result)
        return true
    }

    /** The user came back to the app without the callback (closed the tab). */
    fun cancel() {
        pending?.complete(Result.Cancelled)
        pendingConnection?.complete(Connection.Cancelled)
    }

    /**
     * A connection's login: opens [url] in a Custom Tab and waits for `omi://<key>/callback`, or
     * [cancel] when the user comes back without it.
     */
    suspend fun connect(context: Context, url: String): Connection {
        pendingConnection?.complete(Connection.Cancelled)
        val deferred = CompletableDeferred<Connection>()
        pendingConnection = deferred
        try {
            CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, Uri.parse(url))
        } catch (e: Exception) {
            pendingConnection = null
            return Connection.Failed
        }
        val result = withTimeoutOrNull(5 * 60 * 1000L) { deferred.await() } ?: Connection.Failed
        if (pendingConnection === deferred) pendingConnection = null
        return result
    }

    /**
     * Opens [url] in a Custom Tab and waits up to five minutes for the callback (Flutter's
     * timeout). The state is checked against [state].
     */
    suspend fun authorize(context: Context, url: String, state: String): Result {
        pending?.complete(Result.Cancelled)
        val deferred = CompletableDeferred<Result>()
        pending = deferred
        try {
            CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, Uri.parse(url))
        } catch (e: Exception) {
            pending = null
            return Result.Failed("Failed to launch authentication URL")
        }
        val result = withTimeoutOrNull(5 * 60 * 1000L) { deferred.await() } ?: Result.Failed("Authentication timeout")
        if (pending === deferred) pending = null
        if (result is Result.Code && result.state != state) return Result.Failed("Invalid state parameter")
        return result
    }

    // PKCE, as Flutter's `_generateState` / `_generateCodeVerifier` / `_codeChallengeForVerifier`.

    fun randomToken(bytes: Int = 32): String {
        val data = ByteArray(bytes).also { SecureRandom().nextBytes(it) }
        return Base64.encodeToString(data, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    }

    fun codeChallenge(verifier: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII))
        return Base64.encodeToString(digest, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    }
}
