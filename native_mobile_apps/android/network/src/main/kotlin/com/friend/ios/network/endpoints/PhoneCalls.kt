package com.friend.ios.network.endpoints

import com.friend.ios.core.models.Conversation
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.generated.OmiAPI
import com.friend.ios.network.listen.PhoneCallSocket
import com.friend.ios.network.listen.PhoneCallTranscriptChannel
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant
import java.time.OffsetDateTime

/** A verified caller ID (`GET v1/phone/numbers`): the number people you call see. */
data class VerifiedPhoneNumber(
    val id: String,
    /** E.164, e.g. `+15551234567`. */
    val phoneNumber: String,
    val verifiedAt: Instant?,
    val isPrimary: Boolean,
)

/** `POST v1/phone/numbers/verify`: Twilio calls the number; the person types `validationCode`. */
data class PhoneVerification(
    val phoneNumber: String,
    val validationCode: String?,
    /** Twilio's status; `verified` when the number already was. */
    val status: String,
)

/** `POST v1/phone/token`: a Twilio Voice access token for one call. */
data class PhoneCallToken(val accessToken: String, val ttl: Int, val identity: String)

/** `phone_call_quota` of `GET v1/users/me/subscription` (backend `models/users.py` `PhoneCallQuota`). */
data class PhoneCallQuota(
    val hasAccess: Boolean,
    val isPaid: Boolean,
    /** `null` unlimited, `0` calling is off for the plan. */
    val monthlyLimit: Int?,
    val monthlyUsed: Int,
    val remaining: Int?,
    val maxDurationSeconds: Int?,
)

/**
 * The reason in a FastAPI error body. Phone endpoints answer with a string, the quota error with a
 * map (`check_call_access` in `backend/utils/phone_calls.py`); Flutter `errorDetailMessage`.
 */
sealed interface PhoneCallErrorDetail {
    data class Message(val text: String) : PhoneCallErrorDetail
    data class QuotaExceeded(val monthlyLimit: Int?) : PhoneCallErrorDetail

    companion object {
        /** `init?(body:)`: null when the body carries no reason. */
        fun from(body: String): PhoneCallErrorDetail? {
            val root = JsonAccess.parse(body) as? JsonObject ?: return null
            val detail = root["detail"]
            if (detail is JsonPrimitive && detail.isString) {
                val trimmed = detail.content.trim()
                return if (trimmed.isEmpty()) null else Message(trimmed)
            }
            val map = detail as? JsonObject ?: return null
            val code = map.string("error") ?: return null
            return if (code == "phone_call_quota_exceeded") QuotaExceeded(map.int("monthly_limit")) else Message(code)
        }
    }
}

/**
 * Port of `APIClient+PhoneCalls.swift`: phone calls through Omi's Twilio number service. Contract:
 * `backend/routers/phone_calls.py`, Flutter `app/lib/backend/http/api/phone_calls.dart`.
 */
interface PhoneCallsAPI {
    /** `GET v1/phone/numbers`. */
    suspend fun verifiedPhoneNumbers(): List<VerifiedPhoneNumber>

    /** `POST v1/phone/numbers/verify` (rate limited: 5 an hour). */
    suspend fun startPhoneVerification(phoneNumber: String): PhoneVerification

    /** `POST v1/phone/numbers/verify/check`: `true` once the code was entered on the call (poll it). */
    suspend fun checkPhoneVerification(phoneNumber: String): Boolean

    /** `DELETE v1/phone/numbers/{id}`. */
    suspend fun deletePhoneNumber(id: String)

    /** `POST v1/phone/token`. */
    suspend fun phoneCallToken(): PhoneCallToken

    /** The `phone_call_quota` of `GET v1/users/me/subscription`. */
    suspend fun phoneCallQuota(): PhoneCallQuota?

    /** Past calls: the conversations the call transcripts became (`GET v1/conversations?sources=phone_call`). */
    suspend fun phoneCallConversations(limit: Int, offset: Int): List<Conversation>

    /** The call's two-channel transcription stream (`/v4/listen?source=phone_call&channels=2`). */
    suspend fun openPhoneCallSocket(uid: String, callID: String, language: String): PhoneCallTranscriptChannel
}

internal class PhoneCallsEndpoints(private val http: HttpCore) : PhoneCallsAPI {
    private val socketClient by lazy { PhoneCallSocket.socketClient(http.client) }

    override suspend fun verifiedPhoneNumbers(): List<VerifiedPhoneNumber> =
        http.jsonObject(Method.GET, "v1/phone/numbers").objects("numbers").mapNotNull { item ->
            val id = item.string("id") ?: return@mapNotNull null
            val number = item.string("phone_number") ?: return@mapNotNull null
            VerifiedPhoneNumber(id, number, item.string("verified_at")?.let(::parsePhoneDate), item.bool("is_primary") ?: false)
        }

    override suspend fun startPhoneVerification(phoneNumber: String): PhoneVerification {
        val body = JsonObject(mapOf("phone_number" to JsonPrimitive(phoneNumber)))
        val item = http.jsonObject(Method.POST, "v1/phone/numbers/verify", json = body)
        return PhoneVerification(
            phoneNumber = item.string("phone_number") ?: phoneNumber,
            validationCode = item.string("validation_code")?.takeIf { it.isNotEmpty() },
            status = item.string("status").orEmpty(),
        )
    }

    override suspend fun checkPhoneVerification(phoneNumber: String): Boolean {
        val body = JsonObject(mapOf("phone_number" to JsonPrimitive(phoneNumber)))
        return http.jsonObject(Method.POST, "v1/phone/numbers/verify/check", json = body).bool("verified") ?: false
    }

    override suspend fun deletePhoneNumber(id: String) {
        http.jsonObject(Method.DELETE, "v1/phone/numbers/$id")
    }

    override suspend fun phoneCallToken(): PhoneCallToken {
        val item = http.jsonObject(Method.POST, "v1/phone/token")
        val token = item.string("access_token") ?: throw APIError.Decoding("phone token without access_token")
        return PhoneCallToken(token, item.int("ttl") ?: 3600, item.string("identity").orEmpty())
    }

    override suspend fun phoneCallQuota(): PhoneCallQuota? {
        val quota = http.jsonObject(Method.GET, "v1/users/me/subscription").obj("phone_call_quota") ?: return null
        return PhoneCallQuota(
            hasAccess = quota.bool("has_access") ?: false,
            isPaid = quota.bool("is_paid") ?: false,
            monthlyLimit = quota.int("monthly_limit"),
            monthlyUsed = quota.int("monthly_used") ?: 0,
            remaining = quota.int("remaining"),
            maxDurationSeconds = quota.int("max_duration_seconds"),
        )
    }

    override suspend fun phoneCallConversations(limit: Int, offset: Int): List<Conversation> {
        val query = listOf(
            "include_discarded" to "false",
            "limit" to "$limit",
            "offset" to "$offset",
            "statuses" to "processing,completed",
            "sources" to "phone_call",
        )
        val text = http.data(Method.GET, "v1/conversations", query = query)
        return http.decode(ListSerializer(OmiAPI.Conversation.serializer()), text).map(ConversationMapper::map)
    }

    override suspend fun openPhoneCallSocket(uid: String, callID: String, language: String): PhoneCallTranscriptChannel {
        val request = http.request(Method.GET, "v4/listen", PhoneCallSocket.query(uid, callID, language))
        return PhoneCallSocket(request, socketClient).also { it.open() }
    }
}

/** `verified_at` is Python `isoformat()`: `2026-10-01T10:00:00.123456+00:00`. */
internal fun parsePhoneDate(text: String): Instant? =
    runCatching { OffsetDateTime.parse(text).toInstant() }.getOrNull()
        ?: runCatching { Instant.parse(text) }.getOrNull()
