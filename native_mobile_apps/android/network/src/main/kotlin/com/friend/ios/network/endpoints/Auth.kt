package com.friend.ios.network.endpoints

import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/** Port of `APIClient+Auth.swift`. */
interface AuthAPI {
    /** Local dev harness only: a Firebase custom token for one of the seeded users. */
    suspend fun localDevCustomToken(uid: String): String

    /**
     * Android only (Flutter `_exchangeCodeForOAuthCredentials`): `POST v1/auth/token` exchanges the
     * code from the backend's web sign-in (`v1/auth/authorize`, PKCE) for the provider's tokens,
     * or a Firebase custom token when [useCustomToken].
     */
    suspend fun exchangeAuthorizationCode(code: String, redirectURI: String, codeVerifier: String, useCustomToken: Boolean): WebAuthTokens
}

/** What `v1/auth/token` returns: `provider` plus a custom token or the provider's tokens. */
data class WebAuthTokens(val provider: String?, val customToken: String?, val idToken: String?, val accessToken: String?)

internal class AuthEndpoints(private val http: HttpCore) : AuthAPI {
    @Serializable
    private data class CustomTokenResponse(@SerialName("custom_token") val customToken: String)

    override suspend fun localDevCustomToken(uid: String): String {
        val text = http.data(Method.POST, "v1/auth/local-dev/custom-token", body = Body.Form(mapOf("uid" to uid)), authenticated = false)
        return http.decode(CustomTokenResponse.serializer(), text).customToken
    }

    override suspend fun exchangeAuthorizationCode(code: String, redirectURI: String, codeVerifier: String, useCustomToken: Boolean): WebAuthTokens {
        val form = mapOf(
            "grant_type" to "authorization_code",
            "code" to code,
            "redirect_uri" to redirectURI,
            "use_custom_token" to useCustomToken.toString(),
            "code_verifier" to codeVerifier,
        )
        val text = http.data(Method.POST, "v1/auth/token", body = Body.Form(form), authenticated = false)
        val o = http.decode(JsonObject.serializer(), text)
        return WebAuthTokens(o.string("provider"), o.string("custom_token"), o.string("id_token"), o.string("access_token"))
    }
}
