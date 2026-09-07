package com.rnruntime

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.net.URL
import java.net.URLEncoder
import java.security.KeyStore
import java.util.concurrent.atomic.AtomicLong
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

object OmiCloudSession {
  private const val KEY = "omi-v5-cloud-session"
  private const val FIREBASE_KEY = "AIzaSyA88gHcmiAxjN_aE23tHRWXOgFfapyO6dk"
  private val revision = AtomicLong()
  private val attemptLock = Any()

  private fun preferences(context: Context) = context.getSharedPreferences(KEY, Context.MODE_PRIVATE)

  private fun key(): SecretKey {
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    (store.getKey(KEY, null) as? SecretKey)?.let { return it }
    return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
      init(KeyGenParameterSpec.Builder(KEY, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
    }.generateKey()
  }

  private fun read(context: Context): JSONObject? {
    val stored = preferences(context).getString("session", null) ?: return null
    return JSONObject(String(OmiAuthPolicy.decrypt(key(), Base64.decode(stored, Base64.NO_WRAP)), Charsets.UTF_8))
  }

  private fun save(context: Context, session: JSONObject) {
    val bytes = OmiAuthPolicy.encrypt(key(), session.toString().toByteArray(Charsets.UTF_8))
    check(preferences(context).edit().putString("session", Base64.encodeToString(bytes, Base64.NO_WRAP))
      .putBoolean("signedOut", false).commit())
  }

  fun currentRevision() = revision.get()

  @Synchronized fun journalLogin(context: Context): String? {
    val session = read(context) ?: return null
    val existing = session.optString("journalLogin")
    if (existing.isNotEmpty()) return existing
    val generated = java.util.UUID.randomUUID().toString()
    session.put("journalLogin", generated)
    save(context, session)
    return generated
  }

  @Synchronized internal fun cachedToken(context: Context): String? = read(context)?.optString("idToken")?.ifEmpty { null }

  @Synchronized internal fun recordingOwner(context: Context, origin: String): OmiRecordingOwner? {
    val session = read(context) ?: return null
    val owner = session.optJSONObject("recordingOwner") ?: return null
    if (owner.optString("origin") != origin || owner.optString("login") != session.optString("journalLogin")) return null
    return OmiRecordingOwner(owner.getString("ownerKey"), owner.getString("receipt"), origin, owner.getString("login"))
  }

  @Synchronized internal fun storeRecordingOwner(context: Context, owner: OmiRecordingOwner) {
    val session = read(context) ?: error("Recording login is unavailable")
    check(owner.login == session.optString("journalLogin"))
    session.put("recordingOwner", JSONObject().put("ownerKey", owner.ownerKey).put("receipt", owner.receipt).put("origin", owner.origin).put("login", owner.login))
    save(context, session)
  }

  fun cancelAttempt(expectedRevision: Long) {
    synchronized(attemptLock) { revision.compareAndSet(expectedRevision, expectedRevision + 1) }
  }

  @Synchronized fun signOut(context: Context) {
    revision.incrementAndGet()
    check(preferences(context).edit().remove("session").putBoolean("signedOut", true).commit())
  }

  @Synchronized fun hasSession(context: Context): Boolean = read(context) != null || token(context) != null

  @Synchronized fun invalidateToken(context: Context, failedToken: String): Boolean {
    val session = read(context)
    val current = session?.getString("idToken") ?: if (preferences(context).getBoolean("signedOut", false)) null
      else System.getenv("OMI_CLOUD_API_TOKEN").orEmpty().ifEmpty { System.getenv("OMI_API_TOKEN").orEmpty() }
    if (current != failedToken) return false
    signOut(context)
    return true
  }

  @Synchronized fun token(context: Context): String? {
    val session = read(context) ?: return if (preferences(context).getBoolean("signedOut", false)) null
      else System.getenv("OMI_CLOUD_API_TOKEN").orEmpty().ifEmpty { System.getenv("OMI_API_TOKEN").orEmpty() }.ifEmpty { null }
    if (session.getLong("expiresAt") > System.currentTimeMillis() + 60_000) return session.getString("idToken")
    val refreshed = try {
      post("https://securetoken.googleapis.com/v1/token?key=$FIREBASE_KEY",
        form(mapOf("grant_type" to "refresh_token", "refresh_token" to session.getString("refreshToken"))),
        "application/x-www-form-urlencoded")
    } catch (error: HttpFailure) {
      if (error.status == 400 || error.status == 401 || error.status == 403) {
        signOut(context)
        return null
      }
      throw error
    }
    val next = session(refreshed.getString("id_token"), refreshed.getString("refresh_token"), refreshed.getString("expires_in"))
    next.put("journalLogin", session.optString("journalLogin").ifEmpty { java.util.UUID.randomUUID().toString() })
    session.optJSONObject("recordingOwner")?.let { next.put("recordingOwner", it) }
    save(context, next)
    return next.getString("idToken")
  }

  fun exchange(context: Context, code: String, verifier: String, expectedRevision: Long) {
    val custom = post("https://api.omi.me/v1/auth/token", form(mapOf(
      "grant_type" to "authorization_code", "code" to code, "redirect_uri" to OmiAuthPolicy.REDIRECT,
      "use_custom_token" to "true", "code_verifier" to verifier)), "application/x-www-form-urlencoded")
    val firebase = post("https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=$FIREBASE_KEY",
      JSONObject().put("token", custom.getString("custom_token")).put("returnSecureToken", true).toString(), "application/json")
    val next = session(firebase.getString("idToken"), firebase.getString("refreshToken"), firebase.getString("expiresIn"))
    synchronized(this) {
      synchronized(attemptLock) {
        check(revision.get() == expectedRevision)
        save(context, next)
        revision.incrementAndGet()
      }
    }
  }

  private fun session(token: String, refresh: String, expires: String): JSONObject {
    require(token.isNotEmpty() && refresh.isNotEmpty())
    val seconds = expires.toLong()
    require(seconds in 1..86_400)
    return JSONObject().put("idToken", token).put("refreshToken", refresh)
      .put("expiresAt", System.currentTimeMillis() + seconds * 1000)
      .put("journalLogin", java.util.UUID.randomUUID().toString())
  }

  fun form(values: Map<String, String>) = values.entries.joinToString("&") {
    URLEncoder.encode(it.key, "UTF-8") + "=" + URLEncoder.encode(it.value, "UTF-8")
  }

  private fun post(url: String, body: String, contentType: String): JSONObject {
    val connection = OmiBackendTransport.openConnection(URL(url))
    try {
      connection.requestMethod = "POST"
      connection.connectTimeout = 15_000
      connection.readTimeout = 30_000
      connection.doOutput = true
      connection.setRequestProperty("Content-Type", contentType)
      connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
      val status = connection.responseCode
      if (status !in 200..299) throw HttpFailure(status)
      return connection.inputStream.use { JSONObject(it.bufferedReader().readText()) }
    } finally {
      connection.disconnect()
    }
  }

  private class HttpFailure(val status: Int) : Exception("Native authentication request failed")
}
