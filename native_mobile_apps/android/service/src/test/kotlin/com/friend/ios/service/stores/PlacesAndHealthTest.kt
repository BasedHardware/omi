package com.friend.ios.service.stores

import com.friend.ios.core.models.GeolocationSnapshot
import com.friend.ios.core.models.HealthSummary
import com.friend.ios.core.models.Integration
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant

/** Port of `PlacesAndHealthTests.swift`: the recording's place and the health connection. */
@OptIn(ExperimentalCoroutinesApi::class)
class PlacesAndHealthTest {
    private val now = Instant.parse("2026-10-09T08:00:00Z")

    private fun fix(minutesAgo: Long, source: GeolocationSnapshot.Source) =
        GeolocationSnapshot(52.52, 13.405, 34.0, 12.0, now.minus(Duration.ofMinutes(minutesAgo)), source)

    private class FakeLocation(
        override var access: LocationAccess,
        var last: GeolocationSnapshot? = null,
        var fresh: GeolocationSnapshot? = null,
    ) : LocationProviding {
        var requests = 0
        var fixes = 0

        override suspend fun requestAccess(): LocationAccess {
            requests += 1
            return access
        }

        override suspend fun lastKnown(): GeolocationSnapshot? = last

        override suspend fun currentFix(timeoutMillis: Long): GeolocationSnapshot? {
            fixes += 1
            return fresh
        }
    }

    private fun TestScope.scope() = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[kotlinx.coroutines.Job]!!)

    private fun locationAPI(): FakeAPI = fakeAPI { "updateUserGeolocation" returns Unit }

    @Test
    fun aFreshLastKnownFixIsUsedAtOnce() = runTest(UnconfinedTestDispatcher()) {
        val api = locationAPI()
        val last = fix(1, GeolocationSnapshot.Source.LastKnownPosition)
        val provider = FakeLocation(LocationAccess.Allowed, last = last)
        val store = LocationStore(provider, api.client, scope(), now = { now })
        assertEquals(last, store.snapshotForRecording())
        assertEquals(0, provider.fixes)
        assertEquals(listOf(listOf<Any?>(last)), api.called("updateUserGeolocation"))
    }

    @Test
    fun aStaleLastKnownFixWaitsForAFreshOne() = runTest(UnconfinedTestDispatcher()) {
        val fresh = fix(0, GeolocationSnapshot.Source.CurrentPosition)
        val provider = FakeLocation(LocationAccess.Allowed, last = fix(30, GeolocationSnapshot.Source.LastKnownPosition), fresh = fresh)
        val store = LocationStore(provider, locationAPI().client, scope(), now = { now })
        assertEquals(fresh, store.snapshotForRecording())
        assertEquals(1, provider.fixes)
    }

    @Test
    fun neverAskedOrDeniedGivesNoPlaceAndNoPrompt() = runTest(UnconfinedTestDispatcher()) {
        for (access in listOf(LocationAccess.NotDetermined, LocationAccess.Denied)) {
            val api = locationAPI()
            val provider = FakeLocation(access, last = fix(1, GeolocationSnapshot.Source.LastKnownPosition))
            val store = LocationStore(provider, api.client, scope(), now = { now })
            assertNull(store.snapshotForRecording())
            assertEquals(0, provider.requests)
            assertTrue(api.called("updateUserGeolocation").isEmpty())
        }
    }

    @Test
    fun theHeaderIsFlutterGeolocationJson() {
        val snapshot = GeolocationSnapshot(1.5, 2.5, null, -1.0, Instant.parse("2026-10-09T08:00:00.250Z"), GeolocationSnapshot.Source.CurrentPosition)
        assertEquals(
            """{"capture_source":"current_position","captured_at":"2026-10-09T08:00:00.250Z","latitude":1.5,"longitude":2.5}""",
            snapshot.headerValue,
        )
    }

    // MARK: Health

    private class FakeHealthReader : HealthDataReading {
        override var isAvailable = true
        var shown = true
        var readable = true
        var summary: HealthSummary? = HealthSummary(7, dailySteps = listOf(HealthSummary.DailySteps("2026-10-07", 1_791_331_200_000.0, 8400)))
        var requests = 0

        override suspend fun requestAuthorization(): Boolean {
            requests += 1
            return shown
        }

        override suspend fun probeAccess(): Boolean = readable

        override suspend fun summary(days: Int): HealthSummary? = summary
    }

    private val syncedAt = Instant.parse("2026-10-09T07:59:00Z")

    private fun healthAPI(connected: MutableSet<String> = mutableSetOf()): FakeAPI = fakeAPI {
        "syncAppleHealth" returns syncedAt
        "markAppleHealthConnected" does { connected += "apple_health" }
        "integrationConnected" does { args -> (args[0] as String) in connected }
        "disconnectIntegration" does { args -> connected -= (args[0] as Integration).id }
    }

    private fun make(api: FakeAPI, reader: FakeHealthReader, clock: () -> Instant = { now }) =
        AppleHealthStore(api.client, reader, freshPreferences(), now = clock)

    @Test
    fun connectSyncsThenMarksConnected() = runTest {
        val api = healthAPI()
        val store = make(api, FakeHealthReader())
        store.connect()
        assertTrue(store.isConnected)
        assertEquals(AppleHealthStore.Notice.Connected, store.notice)
        assertEquals(listOf(8400), api.called("syncAppleHealth").map { (it[0] as HealthSummary).totalSteps })
        assertEquals(1, api.called("markAppleHealthConnected").size)
        assertEquals(syncedAt, store.lastSync)
        assertEquals(AppleHealthStore.Phase.Idle, store.phase)
    }

    @Test
    fun nothingReadableIsADenial() = runTest {
        val api = healthAPI()
        val reader = FakeHealthReader().apply { readable = false }
        val store = make(api, reader)
        store.connect()
        assertFalse(store.isConnected)
        assertEquals(AppleHealthStore.Notice.Denied, store.notice)
        assertTrue(api.called("syncAppleHealth").isEmpty())
    }

    @Test
    fun unavailableNeverPrompts() = runTest {
        val reader = FakeHealthReader().apply { isAvailable = false }
        val store = make(healthAPI(), reader)
        store.connect()
        assertEquals(AppleHealthStore.Notice.Unavailable, store.notice)
        assertEquals(0, reader.requests)
    }

    @Test
    fun disconnectDeletesTheIntegration() = runTest {
        val connected = mutableSetOf<String>()
        val store = make(healthAPI(connected), FakeHealthReader())
        store.connect()
        assertTrue("apple_health" in connected)
        store.disconnect()
        assertFalse(store.isConnected)
        assertEquals(AppleHealthStore.Notice.Disconnected, store.notice)
        assertFalse("apple_health" in connected)
    }

    @Test
    fun returningToTheAppSyncsAtMostHourly() = runTest {
        val api = healthAPI(mutableSetOf("apple_health"))
        val store = make(api, FakeHealthReader(), clock = { Instant.parse("2026-10-09T10:00:00Z") })
        store.syncIfConnected()
        store.syncIfConnected()
        assertEquals(1, api.called("syncAppleHealth").size)
        assertTrue(store.isConnected)
    }

    @Test
    fun syncBodyUsesTheBackendFields() {
        val summary = HealthSummary(
            7,
            dailySteps = listOf(HealthSummary.DailySteps("2026-10-07", 1.0, 7000)),
            heartRate = HealthSummary.HeartRate(average = 64.0, minimum = 50.0, maximum = null),
        )
        val body = summary.syncBody
        assertEquals(7000, body["total_steps"]!!.jsonPrimitive.int)
        assertEquals(1000, body["average_steps_per_day"]!!.jsonPrimitive.int)
        assertEquals("64.0", body["heart_rate_average"]!!.jsonPrimitive.content)
        assertNull(body["heart_rate_max"])
        assertEquals("1.0", body["daily_steps"]!!.jsonArray[0].jsonObject["dateMs"]!!.jsonPrimitive.content)
    }
}
