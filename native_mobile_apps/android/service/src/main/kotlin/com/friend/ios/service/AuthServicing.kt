package com.friend.ios.service

/** A credential from a native sign-in sheet, handed to the identity provider. */
sealed interface ProviderCredential {
    /**
     * Sign in with Apple: identity token + the raw nonce whose SHA-256 was sent to Apple. On
     * Android the backend's web flow returns the token (and an access token, no nonce).
     */
    data class Apple(
        val idToken: String,
        val rawNonce: String?,
        val givenName: String?,
        val familyName: String?,
        val accessToken: String? = null,
    ) : ProviderCredential

    /** Google: from Credential Manager (id token only) or the backend's web flow. */
    data class Google(val idToken: String, val accessToken: String?) : ProviderCredential

    /**
     * The backend's web flow can mint a Firebase custom token instead (Flutter
     * `use_custom_token`). Android only: iOS signs in with Apple natively.
     */
    data class CustomToken(val token: String) : ProviderCredential
}

/** Port of `AuthServicing.swift`: identity, implemented by the app module (Firebase). */
data class AuthenticatedUser(val uid: String, val email: String?, val displayName: String?)

interface AuthServicing {
    /** The signed-in user's uid, if any. Restored by Firebase on launch. */
    val currentUserID: String?
    suspend fun signIn(customToken: String): AuthenticatedUser
    suspend fun signIn(credential: ProviderCredential): AuthenticatedUser
    suspend fun updateDisplayName(name: String)
    fun signOut()
}
