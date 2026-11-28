package com.friend.ios.service.stores

import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.PhoneCallErrorDetail
import com.friend.ios.service.phonecalls.PhoneCallFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/*
 * Port of `PhoneCallStore+Numbers.swift`. The caller ID: verifying a number by a Twilio call with a
 * code, deleting it, past calls, quota. Flutter `phone_setup_number_page.dart`,
 * `phone_setup_verify_page.dart`, `phone_call_settings_page.dart`.
 */

/** Numbers, then quota and past calls. */
suspend fun PhoneCallStore.load() {
    loadNumbers()
    if (unavailable != null) return
    coroutineScope {
        val quota = async { loadQuota() }
        val history = async { loadHistory() }
        quota.await()
        history.await()
    }
}

suspend fun PhoneCallStore.loadNumbers() {
    try {
        numbers = api.verifiedPhoneNumbers()
        unavailable = null
    } catch (error: CancellationException) {
        throw error
    } catch (error: APIError.Http) {
        if (error.status == 402 || error.status == 403) {
            unavailable = PhoneCallErrorDetail.from(error.body) ?: PhoneCallErrorDetail.Message("HTTP ${error.status}")
            numbers = emptyList()
        }
    } catch (error: Exception) {
        // Offline: keep what is shown.
    }
    numbersLoaded = true
}

suspend fun PhoneCallStore.loadQuota() {
    try {
        api.phoneCallQuota()?.let { quota = it }
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        // Keep what is shown.
    }
}

suspend fun PhoneCallStore.loadHistory() {
    try {
        history = api.phoneCallConversations(limit = 20, offset = 0)
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        // Keep what is shown.
    }
}

/** `false` when the number is still there (`deletePhoneNumber` refused). */
suspend fun PhoneCallStore.deleteNumber(id: String): Boolean = try {
    api.deletePhoneNumber(id)
    numbers = numbers.filter { it.id != id }
    true
} catch (error: CancellationException) {
    throw error
} catch (error: Exception) {
    false
}

/**
 * Asks Twilio to call [phoneNumber] (E.164). `true`: the call is on its way (or the number was
 * verified already); poll with [pollVerification].
 */
suspend fun PhoneCallStore.startVerification(phoneNumber: String): Boolean {
    isStartingVerification = true
    verificationFailure = null
    try {
        val started = api.startPhoneVerification(phoneNumber)
        val alreadyVerified = started.status == "verified"
        verification = PhoneCallStore.Verification(
            phoneNumber, started.validationCode,
            if (alreadyVerified) PhoneCallStore.Verification.Status.Verified else PhoneCallStore.Verification.Status.Calling,
        )
        if (alreadyVerified) loadNumbers()
        return true
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        verificationFailure = PhoneCallFailure.Server(PhoneCallStore.detail(error))
        return false
    } finally {
        isStartingVerification = false
    }
}

/**
 * Every 2 s for 60 s (the verify screen's effect; leaving the screen cancels it). After two polls
 * the call is in progress, after fifteen it counts as missed, after thirty it timed out.
 */
suspend fun PhoneCallStore.pollVerification() {
    val started = verification ?: return
    if (started.status == PhoneCallStore.Verification.Status.Verified) return
    setVerification(PhoneCallStore.Verification.Status.Calling)
    for (poll in 1..31) {
        delay(timing.verificationPoll)
        if (!currentCoroutineContext().isActive || verification?.phoneNumber != started.phoneNumber) return
        if (poll > 30) {
            setVerification(PhoneCallStore.Verification.Status.TimedOut)
            return
        }
        if (poll == 2 && verification?.status == PhoneCallStore.Verification.Status.Calling) setVerification(PhoneCallStore.Verification.Status.InProgress)
        if (poll == 15 && verification?.status == PhoneCallStore.Verification.Status.InProgress) setVerification(PhoneCallStore.Verification.Status.Missed)
        val verified = try {
            api.checkPhoneVerification(started.phoneNumber)
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            false
        }
        if (verified) {
            setVerification(PhoneCallStore.Verification.Status.Verified)
            loadNumbers()
            return
        }
    }
}

/** Try again after a missed call or a timeout: a new Twilio call, then polling. */
suspend fun PhoneCallStore.retryVerification() {
    val number = verification?.phoneNumber ?: return
    if (startVerification(number)) {
        pollVerification()
    } else {
        setVerification(PhoneCallStore.Verification.Status.TimedOut)
    }
}

fun PhoneCallStore.cancelVerification() {
    verification = null
    verificationFailure = null
}

private fun PhoneCallStore.setVerification(status: PhoneCallStore.Verification.Status) {
    verification = verification?.copy(status = status)
}
