package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.AuthServicing
import com.friend.ios.service.AuthenticatedUser
import com.friend.ios.service.ProviderCredential
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.TimeZone

/** Port of `SessionStore.swift`: who is signed in, and which root screen shows. */
class SessionStore(
    internal val auth: AuthServicing,
    private val api: APIClientProtocol,
    private val configuration: AppConfiguration,
    internal val preferences: Preferences,
    /** Fire-and-forget calls (`Task { }` on iOS). */
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
) {
    sealed interface Phase {
        data object Launching : Phase
        data object SignedOut : Phase
        /** Signed in, AI-processing consent not given on this install yet. */
        data class Consent(val userID: String) : Phase
        /** Signed in, onboarding not finished. */
        data class Onboarding(val userID: String) : Phase
        data class Ready(val userID: String) : Phase
    }

    var phase: Phase by mutableStateOf(Phase.Launching)
        private set
    var isWorking: Boolean by mutableStateOf(false)
        private set
    var errorMessage: String? by mutableStateOf(null)
        private set

    val displayName: String? get() = preferences.displayName
    val canUseLocalDevSignIn: Boolean get() = configuration.isLocalDev

    /** Resolves the launch phase from the persisted session (no network). */
    fun restore() {
        val userID = auth.currentUserID
        phase = if (userID == null) Phase.SignedOut else signedInPhase(userID)
    }

    val userID: String?
        get() = when (val p = phase) {
            is Phase.Consent -> p.userID
            is Phase.Onboarding -> p.userID
            is Phase.Ready -> p.userID
            else -> null
        }

    fun giveConsent() {
        preferences.set(Key.AiConsentGiven, true)
        (phase as? Phase.Consent)?.let { phase = signedInPhase(it.userID) }
    }

    fun completeOnboarding() {
        saveOnboardingCompleted()
        (phase as? Phase.Onboarding)?.let { phase = Phase.Ready(it.userID) }
    }

    /**
     * Setup is done while "You're ready" and the introduction still show: an app closed during
     * them opens on Home next time.
     */
    fun saveOnboardingCompleted() {
        if (preferences.bool(Key.OnboardingCompleted)) return
        preferences.set(Key.OnboardingCompleted, true)
        preferences.set(Key.PermissionsCompleted, true)
        scope.launch { runCatching { api.updateOnboarding(completed = true, acquisitionSource = null) } }
    }

    /** A Settings section to open once Home shows (the introduction's "Choose how often"). */
    var settingsAfterIntroduction: String? by mutableStateOf(null)

    /** Sign in with Apple / Google (Credential Manager, or the backend's web flow in a Custom Tab). */
    suspend fun signIn(credential: ProviderCredential) {
        if (isWorking) return
        isWorking = true
        errorMessage = null
        try {
            val user = auth.signIn(credential)
            var given: String? = null
            var family: String? = null
            if (credential is ProviderCredential.Apple && !credential.givenName.isNullOrEmpty()) {
                // Apple shares the name only on the first sign-in.
                given = credential.givenName
                family = credential.familyName
                runCatching { auth.updateDisplayName(listOfNotNull(given, family).joinToString(" ")) }
            }
            didSignIn(user, givenName = given, familyName = family)
        } catch (e: Exception) {
            errorMessage = describe(e)
        } finally {
            isWorking = false
        }
    }

    /** A sign-in that failed outside the store (the browser flow broke). */
    fun signInFailed(message: String) {
        errorMessage = message
    }

    // Android: Sign in with Apple through the backend's web flow (Flutter `authenticateWithProvider`).

    /** Flutter's `authRedirectUri`: `omi-dev` for the local harness, `omi-beta`, else `omi`. */
    val webAuthRedirectURI: String
        get() = when (configuration.profile) {
            AppConfiguration.Profile.LocalDev -> "omi-dev"
            AppConfiguration.Profile.Beta -> "omi-beta"
            AppConfiguration.Profile.Production -> "omi"
        } + "://auth/callback"

    /** Flutter's `authApiBaseUrl`: OAuth stays on the production identity plane for Beta. */
    private val authBaseURL: String
        get() = if (configuration.profile == AppConfiguration.Profile.Beta) "https://api.omi.me/" else configuration.apiBaseURL.toString()

    /** `v1/auth/authorize` for [provider] (`apple`, `google`) with PKCE (S256). */
    fun webAuthorizeURL(provider: String, state: String, codeChallenge: String): String {
        fun encode(value: String) = java.net.URLEncoder.encode(value, "UTF-8")
        val query = listOf(
            "provider" to provider, "redirect_uri" to webAuthRedirectURI, "state" to state,
            "code_challenge" to codeChallenge, "code_challenge_method" to "S256",
        ).joinToString("&") { (k, v) -> "$k=${encode(v)}" }
        return authBaseURL.trimEnd('/') + "/v1/auth/authorize?" + query
    }

    /** The callback's code, exchanged at `v1/auth/token`, then signed in like a native credential. */
    suspend fun signInWithAuthorizationCode(code: String, codeVerifier: String) {
        if (isWorking) return
        isWorking = true
        errorMessage = null
        val tokens = try {
            api.exchangeAuthorizationCode(code, webAuthRedirectURI, codeVerifier, useCustomToken = configuration.isLocalDev)
        } catch (e: Exception) {
            errorMessage = describe(e)
            isWorking = false
            return
        }
        isWorking = false
        val customToken = tokens.customToken
        val idToken = tokens.idToken
        val credential = when {
            customToken != null -> ProviderCredential.CustomToken(customToken)
            idToken == null -> {
                errorMessage = "Sign-in failed (no token)."
                return
            }
            tokens.provider == "google" -> ProviderCredential.Google(idToken, tokens.accessToken)
            else -> ProviderCredential.Apple(idToken, rawNonce = null, givenName = null, familyName = null, accessToken = tokens.accessToken)
        }
        signIn(credential)
    }

    private fun signedInPhase(userID: String): Phase = when {
        !preferences.bool(Key.AiConsentGiven) -> Phase.Consent(userID)
        preferences.bool(Key.OnboardingCompleted) -> Phase.Ready(userID)
        else -> Phase.Onboarding(userID)
    }

    /** Mirrors Flutter's `_updateUserPreferences` + `_restoreOnboardingState` after any sign-in. */
    internal suspend fun didSignIn(user: AuthenticatedUser, givenName: String? = null, familyName: String? = null) {
        if (preferences.string(Key.Uid) != user.uid) preferences.clearUser()
        preferences.set(Key.Uid, user.uid)
        user.email?.takeIf { it.isNotEmpty() }?.let { preferences.set(Key.Email, it) }
        val parts = user.displayName?.split(" ", limit = 2).orEmpty()
        (givenName ?: parts.firstOrNull())?.takeIf { it.isNotEmpty() }?.let { preferences.set(Key.GivenName, it) }
        (familyName ?: parts.getOrNull(1))?.takeIf { it.isNotEmpty() }?.let { preferences.set(Key.FamilyName, it) }
        runCatching { api.onboardingState() }.getOrNull()?.let { state ->
            if (state.completed) preferences.set(Key.OnboardingCompleted, true)
            state.acquisitionSource?.let { preferences.set(Key.FoundOmiSource, it) }
        }
        runCatching { api.primaryLanguage() }.getOrNull()?.let { language ->
            preferences.set(Key.UserPrimaryLanguage, language)
            preferences.set(Key.HasSetPrimaryLanguage, true)
        }
        runCatching { api.setTimeZone(TimeZone.getDefault().id) }
        phase = signedInPhase(user.uid)
    }

    /** Local harness sign-in: the backend mints a custom token for [uid], Firebase signs in with it. */
    suspend fun signInLocalDev(uid: String = "local-dev-user") {
        if (!canUseLocalDevSignIn || isWorking) return
        isWorking = true
        errorMessage = null
        try {
            val token = api.localDevCustomToken(uid)
            didSignIn(auth.signIn(token))
        } catch (e: Exception) {
            errorMessage = describe(e)
        } finally {
            isWorking = false
        }
    }

    // Settings (port-settings): Account > Set up again, Help > Replay introduction, Delete account.

    /** Account > Set up again: the whole onboarding over Home (closes Settings). */
    fun replayOnboarding() {
        (phase as? Phase.Ready)?.let { phase = Phase.Onboarding(it.userID) }
    }

    /** The short introduction to the app on its own (Help > Replay introduction), over Home. */
    var showsIntroduction: Boolean by mutableStateOf(false)
        private set

    fun replayIntroduction() {
        if (phase is Phase.Ready) showsIntroduction = true
    }

    fun introductionFinished() {
        showsIntroduction = false
    }

    /** `DELETE v1/users/delete-account`, then signed out on this phone. Returns whether it worked. */
    suspend fun deleteAccount(reason: String?): Boolean = try {
        api.deleteAccount(reason)
        runCatching { auth.signOut() }
        preferences.clearUser()
        preferences.set(Key.BtDevice, null as String?)
        phase = Phase.SignedOut
        true
    } catch (e: Exception) {
        errorMessage = describe(e)
        false
    }

    fun signOut() {
        try {
            auth.signOut()
            preferences.clearUser()
            phase = Phase.SignedOut
        } catch (e: Exception) {
            errorMessage = describe(e)
        }
    }

    companion object {
        fun describe(error: Exception): String = when (error) {
            is APIError.Http -> if (error.status == 404) "This backend has no local sign-in. Start the harness with make dev-up." else "Sign-in failed (HTTP ${error.status})."
            is APIError.Transport -> "Cannot reach the backend. Is the local harness running?"
            else -> error.message ?: error.toString()
        }
    }
}
