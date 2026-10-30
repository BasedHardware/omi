package com.friend.ios.service.stores

import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.endpoints.OnboardingState
import com.friend.ios.network.endpoints.WebAuthTokens
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.AuthServicing
import com.friend.ios.service.AuthenticatedUser
import com.friend.ios.service.ProviderCredential
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.URI

/** Sign-in paths of `SessionStore` (Apple / Google credentials and the Android web flow). */
class SessionStoreSignInTest {
    private class FakeAuth : AuthServicing {
        val credentials = mutableListOf<ProviderCredential>()
        var customTokens = mutableListOf<String>()
        var names = mutableListOf<String>()
        override var currentUserID: String? = null
        override suspend fun signIn(customToken: String): AuthenticatedUser {
            customTokens += customToken
            currentUserID = "u1"
            return AuthenticatedUser("u1", "a@b.c", "Ada Lovelace")
        }
        override suspend fun signIn(credential: ProviderCredential): AuthenticatedUser {
            if (credential is ProviderCredential.CustomToken) return signIn(credential.token)
            credentials += credential
            currentUserID = "u1"
            return AuthenticatedUser("u1", "a@b.c", null)
        }
        override suspend fun updateDisplayName(name: String) {
            names += name
        }
        override fun signOut() {
            currentUserID = null
        }
    }

    private fun config(profile: AppConfiguration.Profile) =
        AppConfiguration(profile, URI("http://127.0.0.1:8000/"), null, "1", "1")

    private val api = fakeAPI {
        "onboardingState" returns OnboardingState(completed = true, acquisitionSource = "friend")
        "primaryLanguage" returns "de"
        "setTimeZone" returns Unit
    }

    private fun store(auth: FakeAuth, profile: AppConfiguration.Profile = AppConfiguration.Profile.Production) =
        SessionStore(auth, api.client, config(profile), freshPreferences(), CoroutineScope(Dispatchers.Unconfined))

    @Test
    fun appleCredentialSavesTheNameAndRestoresOnboarding() = runBlocking {
        val auth = FakeAuth()
        val session = store(auth)
        session.signIn(ProviderCredential.Apple("id", "nonce", "Ada", "Lovelace"))
        assertEquals(listOf("Ada Lovelace"), auth.names)
        assertEquals("Ada", session.preferences.string(Key.GivenName))
        assertEquals("friend", session.preferences.string(Key.FoundOmiSource))
        assertEquals("de", session.preferences.string(Key.UserPrimaryLanguage))
        // Consent is local: asked again after every sign-in.
        assertEquals(SessionStore.Phase.Consent("u1"), session.phase)
        session.giveConsent()
        assertEquals(SessionStore.Phase.Ready("u1"), session.phase)
    }

    @Test
    fun webFlowUsesTheProfileSchemeAndPKCE() {
        val local = store(FakeAuth(), AppConfiguration.Profile.LocalDev)
        assertEquals("omi-dev://auth/callback", local.webAuthRedirectURI)
        val url = store(FakeAuth()).webAuthorizeURL("apple", "s1", "c1")
        assertTrue(url.startsWith("http://127.0.0.1:8000/v1/auth/authorize?provider=apple&redirect_uri=omi%3A%2F%2Fauth%2Fcallback"))
        assertTrue(url.endsWith("state=s1&code_challenge=c1&code_challenge_method=S256"))
    }

    @Test
    fun webFlowSignsInWithTheCustomTokenOrTheAppleToken() = runBlocking {
        val auth = FakeAuth()
        api.apply { "exchangeAuthorizationCode" returns WebAuthTokens("apple", "custom", null, null) }
        store(auth, AppConfiguration.Profile.LocalDev).signInWithAuthorizationCode("code", "verifier")
        assertEquals(listOf("custom"), auth.customTokens)
        assertEquals(listOf("code", "omi-dev://auth/callback", "verifier", true), api.called("exchangeAuthorizationCode").last())

        api.apply { "exchangeAuthorizationCode" returns WebAuthTokens("apple", null, "idt", "at") }
        store(auth).signInWithAuthorizationCode("code", "verifier")
        assertEquals(ProviderCredential.Apple("idt", null, null, null, "at"), auth.credentials.last())
    }
}
