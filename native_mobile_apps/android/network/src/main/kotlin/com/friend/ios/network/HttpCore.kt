package com.friend.ios.network

import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.generated.OmiJson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.DeserializationStrategy
import okhttp3.Call
import okhttp3.Callback
import okhttp3.FormBody
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Supplies the Firebase ID token for `Authorization: Bearer`; implemented by the app module. */
fun interface AuthTokenProviding {
    suspend fun idToken(forceRefresh: Boolean): String
}

/** Port of `APIError`. */
sealed class APIError(message: String) : Exception(message) {
    data object NotSignedIn : APIError("notSignedIn")
    data class Http(val status: Int, val body: String) : APIError("http($status): $body")
    data class Decoding(val detail: String) : APIError("decoding: $detail")
    data class Transport(val detail: String) : APIError("transport: $detail")
}

/**
 * The request/decoding half of `APIClient.swift`. The header contract mirrors the Flutter app's
 * `buildHeaders` (`app/lib/backend/http/shared.dart`).
 */
class HttpCore(
    val configuration: AppConfiguration,
    private val tokens: AuthTokenProviding,
    val client: OkHttpClient = defaultClient,
) {
    enum class Method { GET, POST, PATCH, PUT, DELETE }

    sealed interface Body {
        data object None : Body
        class Json(val text: String) : Body
        class Form(val fields: Map<String, String>) : Body
        /** One file part (`multipart/form-data`), as FastAPI's `UploadFile` expects. */
        class File(val field: String, val filename: String, val mimeType: String, val data: ByteArray) : Body
    }

    fun url(path: String, query: List<Pair<String, String>> = emptyList()): HttpUrl {
        val builder = configuration.apiBaseURL.toString().toHttpUrl().newBuilder().addPathSegments(path.trimStart('/'))
        query.forEach { (name, value) -> builder.addQueryParameter(name, value) }
        return builder.build()
    }

    suspend fun request(
        method: Method,
        path: String,
        query: List<Pair<String, String>> = emptyList(),
        body: Body = Body.None,
        headers: Map<String, String> = emptyMap(),
        authenticated: Boolean = true,
    ): Request {
        val builder = Request.Builder()
            .url(url(path, query))
            .header("X-App-Platform", "android")
            .header("X-App-Version", configuration.appVersion)
            .header("X-App-Build", configuration.appBuild)
        val requestBody: RequestBody? = when (body) {
            Body.None -> if (method == Method.GET || method == Method.DELETE) null else ByteArray(0).toRequestBody()
            is Body.Json -> body.text.toRequestBody("application/json".toMediaType())
            is Body.Form -> FormBody.Builder().apply { body.fields.forEach { (k, v) -> add(k, v) } }.build()
            is Body.File -> MultipartBody.Builder("omi-${UUID.randomUUID()}")
                .setType(MultipartBody.FORM)
                .addFormDataPart(body.field, body.filename, body.data.toRequestBody(body.mimeType.toMediaType()))
                .build()
        }
        builder.method(method.name, requestBody)
        headers.forEach { (name, value) -> builder.header(name, value) }
        if (authenticated) {
            // Authenticated requests never degrade into anonymous traffic.
            builder.header("Authorization", "Bearer ${tokens.idToken(forceRefresh = false)}")
        }
        return builder.build()
    }

    suspend fun data(
        method: Method,
        path: String,
        query: List<Pair<String, String>> = emptyList(),
        body: Body = Body.None,
        headers: Map<String, String> = emptyMap(),
        authenticated: Boolean = true,
    ): String {
        val request = request(method, path, query, body, headers, authenticated)
        val response = try {
            client.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        return response.use {
            val text = withContext(Dispatchers.IO) { it.body?.string().orEmpty() }
            if (it.code !in 200..299) throw APIError.Http(it.code, text.take(500))
            text
        }
    }

    fun <T> decode(deserializer: DeserializationStrategy<T>, text: String): T = try {
        OmiJson.decodeFromString(deserializer, text)
    } catch (e: Exception) {
        throw APIError.Decoding(e.message ?: e.toString())
    }

    companion object {
        val defaultClient: OkHttpClient = OkHttpClient.Builder()
            .callTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()
    }
}

/** Suspends on an OkHttp call; cancelling the coroutine cancels the call. */
suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: Response) = cont.resume(response)
        override fun onFailure(call: Call, e: IOException) = cont.resumeWithException(e)
    })
    cont.invokeOnCancellation { runCatching { cancel() } }
}
