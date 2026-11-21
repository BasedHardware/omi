package com.friend.ios

import android.annotation.SuppressLint
import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import com.friend.ios.service.ProviderCredential
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential

/**
 * Android counterpart of `FirebaseAuthService.googleCredential()` (GoogleSignIn sheet on iOS):
 * Credential Manager's "Sign in with Google". Offered only when the build has a Google web
 * client id (`default_web_client_id`, generated from google-services.json), like iOS checks the
 * Firebase config's client id.
 */
object GoogleSignIn {
    @SuppressLint("DiscouragedApi")
    fun webClientID(context: Context): String? {
        val id = context.resources.getIdentifier("default_web_client_id", "string", context.packageName)
        return if (id == 0) null else context.getString(id).takeIf { it.isNotBlank() }
    }

    fun supportsGoogle(context: Context): Boolean = webClientID(context) != null

    /** Shows Google's sheet; null when the user dismissed it or no account was picked. */
    suspend fun credential(activityContext: Context): ProviderCredential? {
        val clientID = webClientID(activityContext) ?: return null
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(GetSignInWithGoogleOption.Builder(clientID).build())
            .build()
        val result = CredentialManager.create(activityContext).getCredential(activityContext, request)
        val credential = result.credential
        if (credential !is CustomCredential || credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) return null
        val google = GoogleIdTokenCredential.createFrom(credential.data)
        return ProviderCredential.Google(idToken = google.idToken, accessToken = null)
    }
}
