package com.friend.ios

import com.friend.ios.network.APIError
import com.friend.ios.network.AuthTokenProviding
import com.friend.ios.service.AuthServicing
import com.friend.ios.service.AuthenticatedUser
import com.friend.ios.service.ProviderCredential
import com.google.firebase.auth.AuthCredential
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.auth.OAuthProvider
import com.google.firebase.auth.FirebaseUser
import com.google.firebase.auth.userProfileChangeRequest
import kotlinx.coroutines.tasks.await

/**
 * Port of `FirebaseAuthService.swift`. The Firebase Android SDK persists the session per app, so
 * a user signed in on the Flutter build (same package, same Firebase project) stays signed in
 * after the native update.
 */
class FirebaseAuthService(private val auth: FirebaseAuth = FirebaseAuth.getInstance()) : AuthServicing {
    override val currentUserID: String? get() = auth.currentUser?.uid

    override suspend fun signIn(customToken: String): AuthenticatedUser = user(auth.signInWithCustomToken(customToken).await().user!!)

    override suspend fun signIn(credential: ProviderCredential): AuthenticatedUser {
        val firebaseCredential: AuthCredential = when (credential) {
            is ProviderCredential.Apple -> OAuthProvider.newCredentialBuilder("apple.com").apply {
                if (credential.rawNonce != null) setIdTokenWithRawNonce(credential.idToken, credential.rawNonce) else setIdToken(credential.idToken)
                credential.accessToken?.let { setAccessToken(it) }
            }.build()
            is ProviderCredential.Google -> GoogleAuthProvider.getCredential(credential.idToken, credential.accessToken)
            is ProviderCredential.CustomToken -> return signIn(credential.token)
        }
        return user(auth.signInWithCredential(firebaseCredential).await().user!!)
    }

    override suspend fun updateDisplayName(name: String) {
        val user = auth.currentUser ?: return
        if (name.isEmpty()) return
        user.updateProfile(userProfileChangeRequest { displayName = name }).await()
    }

    override fun signOut() = auth.signOut()

    private fun user(user: FirebaseUser) = AuthenticatedUser(user.uid, user.email, user.displayName)
}

/** ID tokens for `Authorization: Bearer`. Firebase refreshes them transparently. */
class FirebaseTokenProvider(private val auth: FirebaseAuth = FirebaseAuth.getInstance()) : AuthTokenProviding {
    override suspend fun idToken(forceRefresh: Boolean): String {
        val user = auth.currentUser ?: throw APIError.NotSignedIn
        return user.getIdToken(forceRefresh).await().token ?: throw APIError.NotSignedIn
    }
}
