package com.rnruntime

import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableMap
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.nio.charset.StandardCharsets
import java.util.Locale
import java.util.concurrent.Executors

private const val CONTRACT_VERSION = "1.0.0"
private const val CLOUD_ORIGIN = "https://api.omi.me"
private const val LOCAL_ORIGIN = "http://127.0.0.1:8787"
private const val EXAMPLE_ORIGIN = "http://127.0.0.1:4851"
private const val DEVELOPMENT_UNSUPPORTED_BODY =
  "{\"error\":{\"code\":\"development_backend_unsupported\",\"retryable\":false,\"action\":\"none\"}}"

private enum class CredentialKind { Cloud, Local, ExamplePlatform }

private data class BackendPolicy(
  val url: URI,
  val token: String,
  val clientId: String,
  val kind: CredentialKind,
  val captureUrl: URI? = null,
  val captureOriginRequired: Boolean = false,
)

class OmiBackendModule(context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  private val executor = Executors.newCachedThreadPool()

  override fun getName() = "OmiBackend"

  @ReactMethod
  fun request(value: ReadableMap, promise: Promise) {
    executor.execute {
      try {
        promise.resolve(performRequest(value))
      } catch (error: TransportException) {
        promise.reject(error.code, error.message)
      } catch (_: Exception) {
        promise.reject("OMI_HTTP_TRANSPORT", "Native HTTP transport failed")
      }
    }
  }

  @ReactMethod
  fun generationEvents(generationId: String, lastEventId: String?, promise: Promise) {
    promise.reject("OMI_HTTP_UNCONFIGURED", "Android generation streaming is unavailable")
  }

  @ReactMethod
  fun cancelGenerationEvents(generationId: String, promise: Promise) {
    promise.resolve(null)
  }

  private fun performRequest(value: ReadableMap): com.facebook.react.bridge.WritableMap {
    val policy = resolvedPolicy() ?: throw TransportException(
      "OMI_HTTP_UNCONFIGURED",
      "Native HTTP configuration is unavailable",
    )
    val requestId = value.getString("id").orEmpty()
    val method = value.getString("method").orEmpty()
    val path = value.getString("path").orEmpty()
    val body = if (value.hasKey("body")) value.getString("body") else null
    val methods = setOf("GET", "POST", "PATCH", "DELETE")
    if (requestId.isEmpty() || method !in methods || !path.startsWith("/") || path.startsWith("//") || path.contains("://")) {
      throw TransportException("OMI_HTTP_INVALID_REQUEST", "Native HTTP request is invalid")
    }
    if (policy.kind == CredentialKind.ExamplePlatform && !examplePlatformSupported(method, path)) {
      return Arguments.createMap().apply {
        putString("id", requestId)
        putInt("status", 503)
        putString("body", DEVELOPMENT_UNSUPPORTED_BODY)
        putNull("retryAfterSeconds")
      }
    }
    val base = requestBaseURL(policy, path)
      ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Native HTTP configuration is unavailable")
    val url = URL(base.toURL(), path)
    if (!sameOrigin(url, base.toURL())) {
      throw TransportException("OMI_HTTP_INVALID_REQUEST", "Native HTTP request is unavailable or invalid")
    }
    val connection = (url.openConnection() as HttpURLConnection).apply {
      requestMethod = method
      connectTimeout = 15_000
      readTimeout = 30_000
      doInput = true
      setRequestProperty("authorization", "Bearer ${policy.token}")
      setRequestProperty("x-omi-contract-version", CONTRACT_VERSION)
      if (policy.kind != CredentialKind.Cloud || !isCloudHost(url.host)) {
        setRequestProperty("x-omi-client-id", policy.clientId)
      }
      if (body != null) {
        doOutput = true
        setRequestProperty("content-type", "application/json")
        outputStream.use { stream -> stream.write(body.toByteArray(StandardCharsets.UTF_8)) }
      }
    }
    try {
      val status = connection.responseCode
      val responseBytes = (if (status >= 400) connection.errorStream else connection.inputStream)?.readBytes()
      val responseBody = responseBytes?.toString(StandardCharsets.UTF_8)
      val retryAfter = connection.getHeaderField("Retry-After")?.toIntOrNull()
      return Arguments.createMap().apply {
        putString("id", requestId)
        putInt("status", status)
        if (responseBody == null) putNull("body") else putString("body", responseBody)
        if (retryAfter != null && retryAfter in 1..3600) {
          putInt("retryAfterSeconds", retryAfter)
        } else {
          putNull("retryAfterSeconds")
        }
      }
    } finally {
      connection.disconnect()
    }
  }

  private fun resolvedPolicy(): BackendPolicy? {
    val environment = System.getenv()
    val developmentBackend = environment["OMI_DEV_BACKEND"].orEmpty()
    val localURL = environment["OMI_LOCAL_BACKEND_URL"].orEmpty()
    val localToken = environment["OMI_LOCAL_API_TOKEN"].orEmpty()
    val localClient = environment["OMI_LOCAL_API_CLIENT_ID"].orEmpty()
    val localSelected = developmentBackend.isNotEmpty() || localURL.isNotEmpty() ||
      localToken.isNotEmpty() || localClient.isNotEmpty()
    if (localSelected) {
      if (localToken.isEmpty() || localClient.isEmpty()) return null
      val url = localBaseURL(localURL, developmentBackend) ?: return null
      return BackendPolicy(
        url = url,
        token = localToken,
        clientId = localClient,
        kind = if (developmentBackend.isNotEmpty()) CredentialKind.ExamplePlatform else CredentialKind.Local,
      )
    }
    val cloud = environment["OMI_CLOUD_API_TOKEN"].orEmpty().ifEmpty { environment["OMI_API_TOKEN"].orEmpty() }
    if (cloud.isEmpty()) return null
    val v5URL = environment["OMI_V5_BACKEND_URL"].orEmpty()
    return BackendPolicy(
      url = URI(CLOUD_ORIGIN),
      token = cloud,
      clientId = "omi-android",
      kind = CredentialKind.Cloud,
      captureOriginRequired = v5URL.isNotEmpty(),
      captureUrl = if (v5URL.isNotEmpty()) validatedV5URL(v5URL) else null,
    )
  }

  private fun isCloudHost(host: String?): Boolean {
    return host?.lowercase(Locale.US) == "api.omi.me"
  }

  private fun isAllowedV5Host(host: String): Boolean {
    val normalized = host.lowercase(Locale.US)
    val loopback = normalized == "localhost" || normalized == "127.0.0.1" || normalized == "::1"
    if (loopback || isCloudHost(normalized)) return true
    return normalized.endsWith(".workers.dev") && normalized.length > ".workers.dev".length
  }

  private fun isCaptureBackendPath(path: String): Boolean {
    val route = runCatching { URI(path).path }.getOrNull() ?: path
    return route == "/v1/device-sessions" || route.startsWith("/v1/device-sessions/")
  }

  private fun requestBaseURL(policy: BackendPolicy, path: String): URI? {
    if (isCaptureBackendPath(path) && policy.captureOriginRequired) {
      return policy.captureUrl
    }
    return policy.url
  }

  private fun validatedV5URL(value: String): URI? {
    val url = runCatching { URI(value) }.getOrNull() ?: return null
    if (url.scheme?.lowercase(Locale.US) != "https") return null
    val host = url.host?.lowercase(Locale.US) ?: return null
    if (url.userInfo != null || !url.query.isNullOrEmpty() || !url.fragment.isNullOrEmpty()) return null
    if (url.path.isNotEmpty() && url.path != "/") return null
    if (!isAllowedV5Host(host)) return null
    val loopback = host == "localhost" || host == "127.0.0.1" || host == "::1"
    if (!loopback && url.port != -1 && url.port != 443) return null
    return url
  }

  private fun localBaseURL(value: String, developmentBackend: String): URI? {
    if (developmentBackend.isNotEmpty()) {
      if (!BuildConfig.DEBUG) return null
      if (value.isNotEmpty() || developmentBackend != "example-platform") return null
      return URI(EXAMPLE_ORIGIN)
    }
    return validatedURL(value.ifEmpty { LOCAL_ORIGIN }, requireLoopback = true)
  }

  private fun validatedURL(value: String, requireLoopback: Boolean): URI? {
    val url = runCatching { URI(value) }.getOrNull() ?: return null
    val scheme = url.scheme?.lowercase(Locale.US) ?: return null
    if (scheme != "http" && scheme != "https") return null
    val host = url.host?.lowercase(Locale.US) ?: return null
    if (url.userInfo != null || !url.query.isNullOrEmpty() || !url.fragment.isNullOrEmpty()) return null
    if (url.path.isNotEmpty() && url.path != "/") return null
    val loopback = host == "localhost" || host == "127.0.0.1" || host == "::1"
    if (requireLoopback && !loopback) return null
    if (!requireLoopback && host != "api.omi.me" && !loopback) return null
    return url
  }

  private fun sameOrigin(left: URL, right: URL): Boolean {
    val leftPort = if (left.port == -1) left.defaultPort else left.port
    val rightPort = if (right.port == -1) right.defaultPort else right.port
    return left.protocol.equals(right.protocol, ignoreCase = true) &&
      left.host.equals(right.host, ignoreCase = true) &&
      leftPort == rightPort
  }

  private fun examplePlatformSupported(method: String, path: String): Boolean {
    if (method != "GET") return false
    val route = runCatching { URI(path).path }.getOrNull() ?: path
    return route == "/v1/conversations" || route == "/v1/memories"
  }

  private class TransportException(val code: String, message: String) : Exception(message)
}
