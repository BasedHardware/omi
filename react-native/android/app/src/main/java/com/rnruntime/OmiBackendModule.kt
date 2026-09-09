package com.rnruntime

import android.content.Context
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableMap
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.util.concurrent.atomic.AtomicInteger
import java.net.URI
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject
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
  private val retirement = Any()
  @Volatile private var disposed = false
  private val connections = mutableSetOf<java.net.HttpURLConnection>()
  private fun requireActive() {
    if (disposed) throw TransportException("OMI_HTTP_CANCELLED", "Native backend is disposed")
  }
  private fun submit(promise: Promise, operation: () -> Unit) {
    if (disposed) { promise.reject("OMI_HTTP_CANCELLED", "Native backend is disposed"); return }
    try {
      executor.execute {
        if (disposed) promise.reject("OMI_HTTP_CANCELLED", "Native backend is disposed") else operation()
      }
    } catch (_: java.util.concurrent.RejectedExecutionException) {
      promise.reject("OMI_HTTP_CANCELLED", "Native backend is disposed")
    }
  }
  private val listeners = AtomicInteger()
  private val recordingJournals = OmiRecordingJournals(context) { OmiCloudSession.journalLogin(context) }
  private data class ActiveGeneration(val stream: OmiGenerationStream, val promise: Promise,
    val finished: AtomicBoolean = AtomicBoolean())
  private val generations = ConcurrentHashMap<String, ActiveGeneration>()

  override fun getName() = "OmiBackend"

  @ReactMethod
  fun addListener(eventName: String) {
    listeners.incrementAndGet()
  }

  @ReactMethod
  fun removeListeners(count: Double) {
    listeners.updateAndGet { (it - count.toInt()).coerceAtLeast(0) }
  }

  private fun emitSessionInvalidated() {
    if (disposed) return
    cancelAllGenerations()
    recordingJournals.close()
    if (listeners.get() > 0) reactApplicationContext
      .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
      .emit("omiBackendSessionInvalidated", Arguments.createMap())
  }

  private fun emitGenerationFrame(streamId: String, frame: String) {
    if (disposed || listeners.get() <= 0 || streamId.isEmpty() || frame.isEmpty()) return
    reactApplicationContext
      .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
      .emit("omiGenerationFrame", Arguments.createMap().apply {
        putString("streamId", streamId)
        putString("frame", frame)
      })
  }

  @ReactMethod
  fun createWriteId(promise: Promise) {
    try {
      val bytes = ByteArray(32)
      java.security.SecureRandom().nextBytes(bytes)
      promise.resolve(bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) })
    } catch (_: Exception) {
      promise.reject("OMI_WRITE_ENTROPY", "Native write identity is unavailable")
    }
  }

  @ReactMethod
  fun getApiContract(promise: Promise) {
    submit(promise) {
      try {
        val policy = resolvedPolicy(false) ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Native HTTP configuration is unavailable")
        promise.resolve(if (policy.kind == CredentialKind.Cloud && !policy.captureOriginRequired) "omi" else "canonical")
      } catch (error: TransportException) { promise.reject(error.code, error.message) }
      catch (_: Exception) { promise.reject("OMI_HTTP_UNCONFIGURED", "Native HTTP configuration is unavailable") }
    }
  }

  @ReactMethod
  fun getSoftwarePlane(promise: Promise) {
    promise.resolve(resolvedSoftwarePlane())
  }

  @ReactMethod
  fun setSoftwarePlane(plane: String, promise: Promise) {
    val value = if (plane == "new") "new" else "old"
    if (!softwarePlaneStore().edit().putString(OmiBackendTransport.SOFTWARE_PLANE_KEY, value).commit()) {
      promise.reject("OMI_HTTP_UNCONFIGURED", "Native backend selection could not be saved")
      return
    }
    promise.resolve(value)
  }

  @ReactMethod
  fun stampedV5BackendOrigin(promise: Promise) {
    promise.resolve(validatedV5URL(System.getenv()["OMI_V5_BACKEND_URL"].orEmpty())?.toString())
  }

  @ReactMethod
  fun createRecordingId(promise: Promise) {
    promise.resolve(java.util.UUID.randomUUID().toString())
  }

  private val rememberedLock = Any()
  private var rememberedGeneration = 0L

  internal fun rememberedDevice(action: String, id: String?, name: String?, current: () -> Boolean, promise: Promise) {
    val ticket = synchronized(rememberedLock) { ++rememberedGeneration }
    val login = OmiCloudSession.journalLogin(reactApplicationContext)
    submit(promise) {
      try {
        if (login == null) {
          if (action == "get" || action == "forget") { promise.resolve(null); return@submit }
          error("Native login is unavailable")
        }
        val saved = OmiCloudSession.rememberedDevice(reactApplicationContext)
        val owner = if (action == "save" || (action == "get" && saved != null)) recordingOwner() else null
        synchronized(OmiCloudSession) {
        synchronized(retirement) {
        synchronized(rememberedLock) {
          requireActive()
          check(OmiRecordingPolicy.rememberedCurrent(ticket, rememberedGeneration, login, OmiCloudSession.journalLogin(reactApplicationContext), current()))
          if (owner != null) check(owner.origin == resolvedPolicy(false)?.let { requestBaseURL(it, "/v1/device-sessions/ownership")?.toString() })
          if (action == "forget") { OmiCloudSession.updateRememberedDevice(reactApplicationContext, login, null); promise.resolve(null) }
          else {
            val selected = if (action == "save") {
              check(OmiRecordingPolicy.rememberedIdentity(id, name) && owner != null)
              JSONObject().put("id", id).put("name", name).put("origin", owner.origin).put("login", owner.login).put("ownerKey", owner.ownerKey)
            } else saved?.takeIf { OmiRecordingPolicy.rememberedIdentity(it.opt("id") as? String, it.opt("name") as? String) && owner != null && it.optString("origin") == owner.origin && it.optString("login") == owner.login && it.optString("ownerKey") == owner.ownerKey }
            if (action == "save") OmiCloudSession.updateRememberedDevice(reactApplicationContext, login, selected)
            promise.resolve(selected?.let { Arguments.createMap().apply { putString("id", it.getString("id")); putString("name", it.getString("name")) } })
          }
        }
        }
        }
      } catch (_: Exception) { promise.reject("OMI_REMEMBERED_DEVICE", "Remembered device is unavailable. Check your connection and try again.") }
    }
  }

  private fun recordingOwner(allowCached: Boolean = false): OmiRecordingOwner {
    requireActive()
    val configured = resolvedPolicy(false) ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Recording ownership is unavailable")
    val login = OmiCloudSession.journalLogin(reactApplicationContext)
      ?: throw TransportException("OMI_RECORDING_OWNERSHIP", "A persistent native login is required for recording")
    val origin = requestBaseURL(configured, "/v1/device-sessions/ownership")?.toString()
      ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Recording ownership is unavailable")
    try {
      val policy = resolvedPolicy() ?: throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording login is unavailable")
      val response = performRequest(Arguments.createMap().apply {
        putString("id", "recording-ownership"); putString("method", "GET"); putString("path", "/v1/device-sessions/ownership")
      }, policy)
      if (response.getInt("status") == 503 && runCatching { JSONObject(response.getString("body").orEmpty()).optJSONObject("error")?.optString("code") }.getOrNull() == "capture_ownership_unavailable")
        throw TransportException("OMI_CAPTURE_OWNERSHIP_UNAVAILABLE", "Recording ownership is unavailable from this backend")
      if (OmiRecordingPolicy.retryableOwnershipStatus(response.getInt("status"))) throw TransportException("OMI_HTTP_TRANSPORT", "Recording ownership could not be refreshed")
      if (response.getInt("status") != 200) throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording ownership is unavailable from this backend")
      val ownership = JSONObject(response.getString("body").orEmpty()).getJSONObject("ownership")
      if (login != OmiCloudSession.journalLogin(reactApplicationContext)) throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording login changed")
      val owner = OmiRecordingOwner(ownership.getString("ownerKey"), ownership.getString("receipt"), origin, login)
      require(Regex("capture-owner-v1:[0-9a-f]{64}").matches(owner.ownerKey) && Regex("capture1\\.[0-9a-f]{64}\\.[0-9a-f]{64}").matches(owner.receipt))
      synchronized(OmiCloudSession) {
        synchronized(retirement) { requireActive(); OmiCloudSession.storeRecordingOwner(reactApplicationContext, owner) }
      }
      return owner
    } catch (failure: java.io.IOException) {
      if (allowCached && OmiRecordingPolicy.offline(failure) && OmiRecordingPolicy.sameContext(login,
          OmiCloudSession.journalLogin(reactApplicationContext), origin,
          resolvedPolicy(false)?.let { requestBaseURL(it, "/v1/device-sessions/ownership")?.toString() }))
        OmiCloudSession.recordingOwner(reactApplicationContext, origin)?.takeIf { it.login == login }?.let { return it }
      throw TransportException("OMI_HTTP_TRANSPORT", "Recording ownership could not be refreshed")
    }
  }

  private fun journalOperation(promise: Promise, operation: () -> Any?) {
    submit(promise) {
      try { requireActive(); val result = operation(); requireActive(); promise.resolve(result) }
      catch (error: TransportException) { promise.reject(error.code, error.message) }
      catch (_: Exception) { promise.reject("OMI_RECORDING_JOURNAL", "Recording journal operation failed; saved audio was retained") }
    }
  }

  @ReactMethod fun createRecordingJournal(input: ReadableMap, promise: Promise) = journalOperation(promise) {
    recordingJournals.create(recordingOwner(true), input)
  }
  @ReactMethod fun listRecordingJournals(promise: Promise) = journalOperation(promise) {
    recordingJournals.list(recordingOwner(true))
  }
  @ReactMethod fun readRecordingJournal(handle: String, promise: Promise) = journalOperation(promise) {
    recordingJournals.read(handle)
  }
  @ReactMethod fun appendRecordingJournal(handle: String, entry: String, promise: Promise) = journalOperation(promise) {
    recordingJournals.append(handle, entry)
  }
  @ReactMethod fun removeRecordingJournal(handle: String, promise: Promise) = journalOperation(promise) {
    recordingJournals.remove(handle); null
  }
  @ReactMethod fun requestRecordingJournal(handle: String, request: ReadableMap, promise: Promise) = journalOperation(promise) {
    val boundOwner = recordingJournals.ownerForRequest(handle, request)
    val owner = recordingOwner()
    if (owner.ownerKey != boundOwner.ownerKey || owner.login != boundOwner.login || owner.origin != boundOwner.origin) {
      recordingJournals.close()
      throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording ownership changed; saved audio was retained")
    }
    val policy = resolvedPolicy() ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Recording transport is unavailable")
    if (owner.login != OmiCloudSession.journalLogin(reactApplicationContext)
      || owner.origin != requestBaseURL(policy, request.getString("path").orEmpty())?.toString())
      throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording ownership changed")
    val response = performRequest(request, policy, owner.receipt)
    if (response.getInt("status") == 409 && JSONObject(response.getString("body").orEmpty()).optJSONObject("error")?.optString("code") == "capture_ownership_changed") {
      recordingJournals.close()
      throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording ownership changed; saved audio was retained")
    }
    recordingJournals.acknowledgeOpen(handle, request, response)
    response
  }

  @ReactMethod
  fun request(value: ReadableMap, promise: Promise) {
    submit(promise) {
      try {
        val path = value.getString("path").orEmpty()
        val method = value.getString("method").orEmpty()
        val transcribe = method == "POST" && Regex("^/v1/device-sessions/[0-9a-f-]{36}/transcribe$").matches(path)
        if (transcribe) {
          val owner = try { recordingOwner() } catch (failure: TransportException) {
            if (failure.code != "OMI_CAPTURE_OWNERSHIP_UNAVAILABLE") throw failure
            promise.resolve(performRequest(value))
            return@submit
          }
          val policy = resolvedPolicy() ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Recording backend is unavailable")
          if (owner.login != OmiCloudSession.journalLogin(reactApplicationContext) || owner.origin != requestBaseURL(policy, path)?.toString())
            throw TransportException("OMI_RECORDING_OWNERSHIP", "Recording ownership changed")
          promise.resolve(performRequest(value, policy, owner.receipt))
        } else promise.resolve(performRequest(value))
      } catch (error: TransportException) {
        promise.reject(error.code, error.message)
      } catch (_: Exception) {
        promise.reject("OMI_HTTP_TRANSPORT", "Native HTTP transport failed")
      }
    }
  }

  @ReactMethod
  fun sendOmiChat(requestId: String, text: String, promise: Promise) {
    if (!Regex("^[A-Za-z0-9._:-]{1,128}$").matches(requestId) || text.isBlank() || text.toByteArray(Charsets.UTF_8).size > 65_536) {
      promise.reject("OMI_HTTP_INVALID_REQUEST", "Omi chat request is invalid"); return
    }
    val key = "omi-chat:$requestId"
    val stream = OmiGenerationStream(null, true)
    stream.setFrameListener { frame -> emitGenerationFrame(requestId, frame) }
    val active = ActiveGeneration(stream, promise)
    synchronized(retirement) {
      if (disposed) { promise.reject("OMI_HTTP_CANCELLED", "Native backend is disposed"); return }
      if (generations.putIfAbsent(key, active) != null) { promise.reject("OMI_HTTP_INVALID_REQUEST", "Omi chat request is already active"); return }
    }
    submit(promise) {
      try {
        var policy: BackendPolicy? = null
        val body = JSONObject().put("text", text).put("file_ids", org.json.JSONArray()).toString().toByteArray(Charsets.UTF_8)
        val result = stream.run({ _ ->
          val selected = resolvedPolicy() ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Omi chat is unavailable")
          if (selected.kind != CredentialKind.Cloud || selected.captureOriginRequired) throw TransportException("OMI_HTTP_BACKEND_CHANGED", "The selected backend changed")
          policy = selected
          val base = requestBaseURL(selected, "/v2/messages") ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Omi chat is unavailable")
          OmiBackendTransport.openConnection(URL(base.toURL(), "/v2/messages")).apply {
            requestMethod = "POST"; connectTimeout = 15_000; readTimeout = 150_000; doOutput = true
            setRequestProperty("authorization", "Bearer ${selected.token}")
            setRequestProperty("content-type", "application/json")
            setRequestProperty("accept", "text/event-stream")
            setFixedLengthStreamingMode(body.size)
          }
        }, { data -> runCatching { JSONObject(data); true }.getOrDefault(false) }, { status ->
          policy?.let { if (status == 401 && OmiCloudSession.invalidateToken(reactApplicationContext, it.token, retirement) { !disposed }) emitSessionInvalidated() }
        }, { connection -> requireActive(); connection.outputStream.use { it.write(body) } })
        if (active.finished.compareAndSet(false, true)) promise.resolve(Arguments.createMap().apply {
          putString("id", requestId); putInt("status", result.status); putString("body", result.body)
          if (result.retryAfterSeconds == null) putNull("retryAfterSeconds") else putInt("retryAfterSeconds", result.retryAfterSeconds)
        })
      } catch (error: Exception) {
        if (active.finished.compareAndSet(false, true)) {
          if (error is TransportException) promise.reject(error.code, error.message)
          else promise.reject("OMI_HTTP_TRANSPORT", "Omi chat transport failed")
        }
      } finally { generations.remove(key, active) }
    }
  }

  @ReactMethod
  fun cancelOmiChat(requestId: String, promise: Promise) {
    if (!Regex("^[A-Za-z0-9._:-]{1,128}$").matches(requestId)) { promise.reject("OMI_HTTP_INVALID_REQUEST", "Omi chat request is invalid"); return }
    generations.remove("omi-chat:$requestId")?.let { cancelGeneration(it) }
    promise.resolve(null)
  }

  @ReactMethod
  fun generationEvents(generationId: String, lastEventId: String?, promise: Promise) {
    val path = generationPath(generationId)
    if (path == null) {
      promise.reject("OMI_HTTP_INVALID_REQUEST", "Native generation request is invalid")
      return
    }
    val stream = try { OmiGenerationStream(lastEventId) } catch (_: IllegalArgumentException) {
      promise.reject("OMI_HTTP_INVALID_REQUEST", "Native generation cursor is invalid")
      return
    }
    stream.setFrameListener { frame -> emitGenerationFrame(generationId, frame) }
    val active = ActiveGeneration(stream, promise)
    synchronized(retirement) {
    if (disposed) { promise.reject("OMI_HTTP_CANCELLED", "Native backend is disposed"); return }
    if (generations.putIfAbsent("canonical:$generationId", active) != null) {
      promise.reject("OMI_HTTP_INVALID_REQUEST", "Generation request is already active")
      return
    }
    }
    submit(promise) {
      try {
        var currentPolicy: BackendPolicy? = null
        val result = stream.run({ cursor ->
          val policy = resolvedPolicy() ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Native generation session is unavailable")
          if (policy.kind == CredentialKind.ExamplePlatform) throw TransportException("OMI_DEV_BACKEND_UNSUPPORTED", "Generation is unsupported by the selected development backend")
          val base = requestBaseURL(policy, path) ?: throw TransportException("OMI_HTTP_UNCONFIGURED", "Native generation origin is unavailable")
          val url = URL(base.toURL(), "$path/events")
          if (!sameOrigin(url, base.toURL())) throw TransportException("OMI_HTTP_INVALID_REQUEST", "Native generation origin is invalid")
          currentPolicy = policy
          OmiBackendTransport.openConnection(url).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 30_000
            setRequestProperty("authorization", "Bearer ${policy.token}")
            setRequestProperty("x-omi-contract-version", CONTRACT_VERSION)
            setRequestProperty("accept", "text/event-stream")
            setRequestProperty("cache-control", "no-cache")
            if (policy.kind != CredentialKind.Cloud || !isCloudHost(url.host)) setRequestProperty("x-omi-client-id", policy.clientId)
            if (cursor != null) setRequestProperty("last-event-id", cursor)
          }
        }, { data -> JSONObject(data).optString("kind") in setOf("done", "failed", "cancelled") }, { status ->
          val policy = currentPolicy
          if (status == 401 && policy?.kind == CredentialKind.Cloud &&
            OmiCloudSession.invalidateToken(reactApplicationContext, policy.token, retirement) { !disposed }) emitSessionInvalidated()
        })
        if (active.finished.compareAndSet(false, true)) promise.resolve(Arguments.createMap().apply {
          putString("id", generationId)
          putInt("status", result.status)
          putString("body", result.body)
          if (result.retryAfterSeconds == null) putNull("retryAfterSeconds") else putInt("retryAfterSeconds", result.retryAfterSeconds)
        })
      } catch (error: Exception) {
        if (active.finished.compareAndSet(false, true)) {
          if (error is TransportException) promise.reject(error.code, error.message)
          else promise.reject("OMI_HTTP_TRANSPORT", "Native generation transport failed")
        }
      } finally {
        generations.remove("canonical:$generationId", active)
      }
    }
  }

  @ReactMethod
  fun cancelGenerationEvents(generationId: String, promise: Promise) {
    val path = generationPath(generationId)
    if (path == null) {
      promise.reject("OMI_HTTP_INVALID_REQUEST", "Native generation request is invalid")
      return
    }
    val active = generations["canonical:$generationId"]
    submit(promise) {
      try {
        val response = performRequest(Arguments.createMap().apply {
          putString("id", generationId)
          putString("method", "DELETE")
          putString("path", path)
        })
        if (response.getInt("status") !in setOf(202, 204)) throw TransportException("OMI_HTTP_TRANSPORT", "Generation cancellation was not accepted")
        if (active != null && generations.remove("canonical:$generationId", active)) cancelGeneration(active)
        promise.resolve(null)
      } catch (error: Exception) {
        if (error is TransportException) promise.reject(error.code, error.message)
        else promise.reject("OMI_HTTP_TRANSPORT", "Native generation cancellation failed")
      }
    }
  }

  private fun generationPath(id: String): String? = if (id.isEmpty() || id.length > 256) null
    else "/v1/chat-generations/" + URLEncoder.encode(id, "UTF-8").replace("+", "%20")

  private fun cancelGeneration(active: ActiveGeneration) {
    if (active.finished.compareAndSet(false, true)) active.promise.reject("OMI_HTTP_CANCELLED", "Native generation request was cancelled")
    active.stream.cancel()
  }

  fun cancelAllGenerations() {
    generations.entries.toList().forEach { (id, active) ->
      if (generations.remove(id, active)) cancelGeneration(active)
    }
  }

  override fun invalidate() {
    val pending = synchronized(retirement) {
      disposed = true
      connections.toList().also { connections.clear() }
    }
    pending.forEach { runCatching { it.disconnect() } }
    recordingJournals.dispose()
    cancelAllGenerations()
    executor.shutdown()
    super.invalidate()
  }

  private fun performRequest(value: ReadableMap, resolved: BackendPolicy? = null, receipt: String? = null): com.facebook.react.bridge.WritableMap {
    requireActive()
    val policy = resolved ?: resolvedPolicy() ?: throw TransportException(
      "OMI_HTTP_UNCONFIGURED",
      "Native HTTP configuration is unavailable",
    )
    if (value.hasKey("expectedApiContract")) {
      if (value.getType("expectedApiContract") != com.facebook.react.bridge.ReadableType.String) throw TransportException("OMI_HTTP_INVALID_REQUEST", "Native API contract is invalid")
      val expected = value.getString("expectedApiContract")
      if (expected !in setOf("omi", "canonical")) throw TransportException("OMI_HTTP_INVALID_REQUEST", "Native API contract is invalid")
      val actual = if (policy.kind == CredentialKind.Cloud && !policy.captureOriginRequired) "omi" else "canonical"
      if (expected != actual) throw TransportException("OMI_HTTP_BACKEND_CHANGED", "The selected backend changed")
    }
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
    val connection = synchronized(retirement) {
      requireActive()
      OmiBackendTransport.openConnection(url).also { connections.add(it) }
    }
    try {
      requireActive()
      connection.apply {
      requestMethod = method
      connectTimeout = 15_000
      readTimeout = OmiBackendTransport.readTimeoutMillis(method, path)
      doInput = true
      setRequestProperty("authorization", "Bearer ${policy.token}")
      setRequestProperty("x-omi-contract-version", CONTRACT_VERSION)
      if (receipt != null) setRequestProperty("x-omi-capture-ownership", receipt)
      if (policy.kind != CredentialKind.Cloud || !isCloudHost(url.host)) {
        setRequestProperty("x-omi-client-id", policy.clientId)
      }
      if (body != null) {
        doOutput = true
        setRequestProperty("content-type", "application/json")
      }
      }
      requireActive()
      connection.connect()
      requireActive()
      if (body != null) connection.outputStream.use { stream -> stream.write(body.toByteArray(StandardCharsets.UTF_8)) }
      val status = connection.responseCode
      requireActive()
      if (status == 401 && policy.kind == CredentialKind.Cloud &&
        OmiCloudSession.invalidateToken(reactApplicationContext, policy.token, retirement) { !disposed }) emitSessionInvalidated()
      val responseBytes = (if (status >= 400) connection.errorStream else connection.inputStream)?.readBytes()
      val responseBody = responseBytes?.toString(StandardCharsets.UTF_8)
      val retryAfter = connection.getHeaderField("Retry-After")?.toIntOrNull()
      requireActive()
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
      synchronized(retirement) { connections.remove(connection) }
      connection.disconnect()
    }
  }

  private fun resolvedPolicy(refresh: Boolean = true): BackendPolicy? {
    requireActive()
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
    val cloud = (if (refresh) OmiCloudSession.token(reactApplicationContext, retirement) { !disposed } else OmiCloudSession.cachedToken(reactApplicationContext)).orEmpty()
    requireActive()
    if (cloud.isEmpty()) {
      emitSessionInvalidated()
      return null
    }
    val stamp = validatedV5URL(environment["OMI_V5_BACKEND_URL"].orEmpty())
    val plane = resolvedSoftwarePlane(stamp != null)
    if (OmiBackendTransport.softwarePlaneIsNew(plane) && stamp == null) return null
    return BackendPolicy(
      url = URI(CLOUD_ORIGIN),
      token = cloud,
      clientId = "omi-android",
      kind = CredentialKind.Cloud,
      captureOriginRequired = OmiBackendTransport.softwarePlaneIsNew(plane),
      captureUrl = stamp,
    )
  }

  private fun softwarePlaneStore() =
    reactApplicationContext.getSharedPreferences(OmiBackendTransport.SOFTWARE_PLANE_PREFERENCES, Context.MODE_PRIVATE)

  private fun resolvedSoftwarePlane(stampedValid: Boolean = validatedV5URL(System.getenv()["OMI_V5_BACKEND_URL"].orEmpty()) != null) =
    OmiBackendTransport.resolvedSoftwarePlane(
      softwarePlaneStore().getString(OmiBackendTransport.SOFTWARE_PLANE_KEY, null),
      stampedValid,
    )

  private fun isCloudHost(host: String?): Boolean {
    return host?.lowercase(Locale.US) == "api.omi.me"
  }

  private fun isAllowedV5Host(host: String): Boolean {
    val normalized = host.lowercase(Locale.US)
    val loopback = normalized == "localhost" || normalized == "127.0.0.1" || normalized == "::1"
    if (loopback || isCloudHost(normalized)) return true
    return normalized.endsWith(".workers.dev") && normalized.length > ".workers.dev".length
  }

  private fun requestBaseURL(policy: BackendPolicy, path: String): URI? {
    if (OmiBackendTransport.isV5BackendPath(path) && policy.captureOriginRequired) {
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
    return OmiBackendTransport.examplePlatformSupported(method, path)
  }

  private class TransportException(val code: String, message: String) : Exception(message)
}
