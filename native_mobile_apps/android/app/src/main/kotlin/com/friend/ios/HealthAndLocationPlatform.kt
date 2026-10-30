package com.friend.ios

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.core.content.ContextCompat
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateGroupByPeriodRequest
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.friend.ios.core.models.GeolocationSnapshot
import com.friend.ios.core.models.HealthSummary
import com.friend.ios.service.stores.HealthDataReading
import com.friend.ios.service.stores.LocationAccess
import com.friend.ios.service.stores.LocationProviding
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeoutOrNull
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.Period
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * The Health Connect permission screen, asked through the visible activity (iOS shows the
 * HealthKit sheet from `requestAuthorization`). Attached in `MainActivity.onCreate`.
 */
class HealthConnectPermission {
    private var launcher: ActivityResultLauncher<Set<String>>? = null
    private var pending: CompletableDeferred<Set<String>>? = null

    fun attach(activity: ComponentActivity) {
        launcher = activity.registerForActivityResult(PermissionController.createRequestPermissionResultContract()) { granted ->
            pending?.complete(granted)
            pending = null
        }
    }

    suspend fun request(permissions: Set<String>): Set<String> {
        val launcher = launcher ?: return emptySet()
        pending?.let { return it.await() }
        val deferred = CompletableDeferred<Set<String>>()
        pending = deferred
        launcher.launch(permissions)
        return deferred.await()
    }
}

/**
 * Port of `HealthKitReader.swift` on Health Connect: the same metrics (steps, active energy,
 * distance, heart rate, resting heart rate, sleep, workouts) in the summary Flutter's
 * `AppleHealthService.swift` builds, so the backend and the chat read them the same way.
 */
class HealthConnectReader(private val context: Context, private val permission: HealthConnectPermission) : HealthDataReading {
    private val client: HealthConnectClient? by lazy {
        if (isAvailable) runCatching { HealthConnectClient.getOrCreate(context) }.getOrNull() else null
    }

    override val isAvailable: Boolean
        get() = HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE

    private val readPermissions: Set<String> = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(RestingHeartRateRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
    )

    override suspend fun requestAuthorization(): Boolean {
        val client = client ?: return false
        val granted = runCatching { client.permissionController.getGrantedPermissions() }.getOrDefault(emptySet())
        if (granted.containsAll(readPermissions)) return true
        return permission.request(readPermissions).isNotEmpty() || granted.isNotEmpty()
    }

    override suspend fun probeAccess(): Boolean {
        val client = client ?: return false
        return runCatching { client.permissionController.getGrantedPermissions() }.getOrDefault(emptySet()).any { it in readPermissions }
    }

    override suspend fun summary(days: Int): HealthSummary? {
        val client = client ?: return null
        if (days !in 1..365) return null
        val granted = runCatching { client.permissionController.getGrantedPermissions() }.getOrDefault(emptySet())
        fun allowed(type: kotlin.reflect.KClass<out androidx.health.connect.client.records.Record>) = HealthPermission.getReadPermission(type) in granted
        val zone = ZoneId.systemDefault()
        val end = Instant.now()
        val start = end.minus(Duration.ofDays(days.toLong()))
        val range = TimeRangeFilter.between(start, end)
        val localRange = TimeRangeFilter.between(
            LocalDateTime.ofInstant(start, zone).toLocalDate().atStartOfDay(),
            LocalDateTime.ofInstant(end, zone),
        )
        var summary = HealthSummary(periodDays = days)
        if (allowed(StepsRecord::class) || allowed(ActiveCaloriesBurnedRecord::class)) {
            val metrics = buildSet {
                if (allowed(StepsRecord::class)) add(StepsRecord.COUNT_TOTAL)
                if (allowed(ActiveCaloriesBurnedRecord::class)) add(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL)
            }
            val groups = runCatching {
                client.aggregateGroupByPeriod(AggregateGroupByPeriodRequest(metrics, localRange, Period.ofDays(1)))
            }.getOrDefault(emptyList())
            summary = summary.copy(
                dailySteps = if (allowed(StepsRecord::class)) {
                    groups.map { group ->
                        val day = group.startTime
                        HealthSummary.DailySteps(dayString(day), dayMillis(day, zone), (group.result[StepsRecord.COUNT_TOTAL] ?: 0L).toInt())
                    }
                } else {
                    emptyList()
                },
                dailyEnergy = if (allowed(ActiveCaloriesBurnedRecord::class)) {
                    groups.map { group ->
                        val day = group.startTime
                        HealthSummary.DailyEnergy(dayString(day), dayMillis(day, zone), group.result[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories ?: 0.0)
                    }
                } else {
                    emptyList()
                },
            )
        }
        if (allowed(HeartRateRecord::class)) {
            summary = summary.copy(heartRate = heartRate(client, range))
        }
        if (allowed(SleepSessionRecord::class)) summary = addSleep(client, range, zone, summary)
        if (allowed(ExerciseSessionRecord::class)) summary = summary.copy(workouts = workouts(client, range, granted))
        return summary
    }

    private suspend fun heartRate(client: HealthConnectClient, range: TimeRangeFilter): HealthSummary.HeartRate? {
        val result = runCatching {
            client.aggregate(AggregateRequest(setOf(HeartRateRecord.BPM_AVG, HeartRateRecord.BPM_MIN, HeartRateRecord.BPM_MAX), range))
        }.getOrNull() ?: return null
        val rate = HealthSummary.HeartRate(
            average = result[HeartRateRecord.BPM_AVG]?.toDouble(),
            minimum = result[HeartRateRecord.BPM_MIN]?.toDouble(),
            maximum = result[HeartRateRecord.BPM_MAX]?.toDouble(),
        )
        return if (rate.average == null && rate.minimum == null && rate.maximum == null) null else rate
    }

    /**
     * Every stage becomes a session with its type; asleep stages count toward the total and the
     * day the sleep ended (Flutter `fetchDailySleep`). A session without stages counts as asleep;
     * the session itself is the time in bed.
     */
    private suspend fun addSleep(client: HealthConnectClient, range: TimeRangeFilter, zone: ZoneId, summary: HealthSummary): HealthSummary {
        val records = runCatching { client.readRecords(ReadRecordsRequest(SleepSessionRecord::class, range)).records }.getOrNull() ?: return summary
        val asleep = setOf(SleepSessionRecord.STAGE_TYPE_LIGHT, SleepSessionRecord.STAGE_TYPE_DEEP, SleepSessionRecord.STAGE_TYPE_REM, SleepSessionRecord.STAGE_TYPE_SLEEPING)
        val byDay = sortedMapOf<String, Double>()
        var asleepSeconds = 0.0
        var inBedSeconds = 0.0
        val sessions = mutableListOf<HealthSummary.SleepSession>()
        for (record in records.sortedByDescending { it.endTime }) {
            inBedSeconds += Duration.between(record.startTime, record.endTime).seconds
            val stages = record.stages.ifEmpty { listOf(SleepSessionRecord.Stage(record.startTime, record.endTime, SleepSessionRecord.STAGE_TYPE_SLEEPING)) }
            for (stage in stages.sortedByDescending { it.endTime }) {
                val seconds = Duration.between(stage.startTime, stage.endTime).seconds.toDouble()
                if (stage.stage in asleep) {
                    asleepSeconds += seconds
                    val day = dayString(LocalDateTime.ofInstant(stage.endTime, zone))
                    byDay[day] = (byDay[day] ?: 0.0) + seconds
                }
                sessions += HealthSummary.SleepSession(
                    startDate = stage.startTime.toEpochMilli().toDouble(), endDate = stage.endTime.toEpochMilli().toDouble(),
                    durationMinutes = seconds / 60, type = sleepStage(stage.stage),
                )
            }
        }
        return summary.copy(
            sleepSessions = sessions,
            totalSleepHours = asleepSeconds / 3600,
            totalInBedHours = inBedSeconds / 3600,
            dailySleep = byDay.entries.map { HealthSummary.DailySleep(it.key, it.value / 3600) }.sortedByDescending { it.date },
        )
    }

    private suspend fun workouts(client: HealthConnectClient, range: TimeRangeFilter, granted: Set<String>): List<HealthSummary.Workout> {
        val records = runCatching { client.readRecords(ReadRecordsRequest(ExerciseSessionRecord::class, range)).records }.getOrNull() ?: return emptyList()
        val calories = HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class) in granted
        val distance = HealthPermission.getReadPermission(DistanceRecord::class) in granted
        return records.sortedByDescending { it.endTime }.map { workout ->
            val metrics = buildSet {
                if (calories) add(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL)
                if (distance) add(DistanceRecord.DISTANCE_TOTAL)
            }
            val totals = if (metrics.isEmpty()) null else runCatching {
                client.aggregate(AggregateRequest(metrics, TimeRangeFilter.between(workout.startTime, workout.endTime)))
            }.getOrNull()
            HealthSummary.Workout(
                type = workoutName(workout.exerciseType),
                startDate = workout.startTime.toEpochMilli().toDouble(),
                endDate = workout.endTime.toEpochMilli().toDouble(),
                durationMinutes = Duration.between(workout.startTime, workout.endTime).seconds / 60.0,
                caloriesBurned = totals?.get(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL)?.inKilocalories,
                distanceKm = totals?.get(DistanceRecord.DISTANCE_TOTAL)?.inKilometers,
            )
        }
    }

    companion object {
        private val dayFormat = DateTimeFormatter.ofPattern("yyyy-MM-dd")

        private fun dayString(date: LocalDateTime): String = dayFormat.format(date)

        private fun dayMillis(date: LocalDateTime, zone: ZoneId): Double = date.atZone(zone).toInstant().toEpochMilli().toDouble()

        /** HealthKit's stage names (Flutter's strings, kept for the backend and the chat). */
        internal fun sleepStage(stage: Int): String = when (stage) {
            SleepSessionRecord.STAGE_TYPE_LIGHT -> "core"
            SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
            SleepSessionRecord.STAGE_TYPE_REM -> "rem"
            SleepSessionRecord.STAGE_TYPE_SLEEPING -> "asleep"
            SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED -> "inBed"
            SleepSessionRecord.STAGE_TYPE_AWAKE, SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> "awake"
            else -> "unknown"
        }

        /** Flutter's workout names (`AppleHealthService.swift`). */
        internal fun workoutName(type: Int): String = when (type) {
            ExerciseSessionRecord.EXERCISE_TYPE_RUNNING, ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL -> "Running"
            ExerciseSessionRecord.EXERCISE_TYPE_WALKING -> "Walking"
            ExerciseSessionRecord.EXERCISE_TYPE_BIKING, ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY -> "Cycling"
            ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL, ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER -> "Swimming"
            ExerciseSessionRecord.EXERCISE_TYPE_HIKING -> "Hiking"
            ExerciseSessionRecord.EXERCISE_TYPE_YOGA -> "Yoga"
            ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING, ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING -> "Strength Training"
            ExerciseSessionRecord.EXERCISE_TYPE_ELLIPTICAL -> "Elliptical"
            ExerciseSessionRecord.EXERCISE_TYPE_ROWING, ExerciseSessionRecord.EXERCISE_TYPE_ROWING_MACHINE -> "Rowing"
            ExerciseSessionRecord.EXERCISE_TYPE_STAIR_CLIMBING, ExerciseSessionRecord.EXERCISE_TYPE_STAIR_CLIMBING_MACHINE -> "Stair Climbing"
            ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING -> "HIIT"
            ExerciseSessionRecord.EXERCISE_TYPE_DANCING -> "Dance"
            ExerciseSessionRecord.EXERCISE_TYPE_PILATES -> "Pilates"
            ExerciseSessionRecord.EXERCISE_TYPE_TENNIS -> "Tennis"
            ExerciseSessionRecord.EXERCISE_TYPE_BASKETBALL -> "Basketball"
            ExerciseSessionRecord.EXERCISE_TYPE_SOCCER -> "Soccer"
            ExerciseSessionRecord.EXERCISE_TYPE_GOLF -> "Golf"
            else -> "Other"
        }
    }
}

/**
 * Port of `CoreLocationProvider.swift` on the fused location provider: while-in-use access, the
 * provider's cached fix, and one fresh fix at balanced (about 100 m) accuracy, enough to name a
 * place, as in Flutter. The permission itself is asked by onboarding and Settings > Privacy.
 */
class FusedLocationProvider(private val context: Context) : LocationProviding {
    private val client by lazy { LocationServices.getFusedLocationProviderClient(context) }
    private val prefs = context.getSharedPreferences("omi.settings", Context.MODE_PRIVATE)

    override val access: LocationAccess
        get() {
            val granted = listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
                .any { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }
            return when {
                granted -> LocationAccess.Allowed
                // The Privacy screen and onboarding mark that they asked (`omi.location.asked`).
                prefs.getBoolean("omi.location.asked", false) -> LocationAccess.Denied
                else -> LocationAccess.NotDetermined
            }
        }

    /** Asked by the screens with their own launchers; here it only reports. */
    override suspend fun requestAccess(): LocationAccess = access

    @SuppressLint("MissingPermission")
    override suspend fun lastKnown(): GeolocationSnapshot? {
        if (access != LocationAccess.Allowed) return null
        return runCatching { client.lastLocation.await() }.getOrNull()?.let { snapshot(it, GeolocationSnapshot.Source.LastKnownPosition) }
    }

    @SuppressLint("MissingPermission")
    override suspend fun currentFix(timeoutMillis: Long): GeolocationSnapshot? {
        if (access != LocationAccess.Allowed) return null
        val cancel = CancellationTokenSource()
        return try {
            withTimeoutOrNull(timeoutMillis) {
                runCatching { client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, cancel.token).await() }.getOrNull()
            }?.let { snapshot(it, GeolocationSnapshot.Source.CurrentPosition) }
        } finally {
            cancel.cancel()
        }
    }

    companion object {
        fun snapshot(location: Location, source: GeolocationSnapshot.Source) = GeolocationSnapshot(
            latitude = location.latitude,
            longitude = location.longitude,
            altitude = if (location.hasAltitude()) location.altitude else null,
            accuracy = if (location.hasAccuracy()) location.accuracy.toDouble() else null,
            capturedAt = Instant.ofEpochMilli(location.time),
            source = source,
        )
    }
}
