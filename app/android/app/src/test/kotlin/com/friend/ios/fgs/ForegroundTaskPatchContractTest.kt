package com.friend.ios.fgs

import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertTrue
import org.junit.Test

/** Checks the Kotlin service that the Gradle hook generates from the pinned plugin. */
class ForegroundTaskPatchContractTest {
    private val stockService = """
        class ForegroundService : Service() {
            private var isTimeout: Boolean = false

            override fun onCreate() {
                super.onCreate()
                registerBroadcastReceiver()
            }

            override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
                isTimeout = false
                loadDataFromPreferences()
                if (intent == null) {
                    restartFromPreferences()
                }
                if (action == ForegroundServiceAction.API_STOP) {
                    stopForegroundService()
                    return START_NOT_STICKY
                }
                try {
                    when (action) {
                        ForegroundServiceAction.API_UPDATE -> {
                            updateNotification()
                        }
                    }
                } catch (e: Exception) {
                    stopForegroundService()
                }
                throw IllegalStateException("body failed")
            }

            override fun onTaskRemoved(rootIntent: Intent?) {
                super.onTaskRemoved(rootIntent)
                stopSelf()
            }

            private fun stopForegroundService() {
                RestartReceiver.cancelRestartAlarm(this)
                stopForeground(true)
                stopSelf()

                _isRunningServiceState.update { false }
            }

            private fun startForegroundService() {
                val serviceId = notificationOptions.serviceId
                val notification = createNotification()
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    startForeground(serviceId, notification, foregroundServiceTypes.value)
                } else {
                    startForeground(serviceId, notification)
                }
            }
        }
    """.trimIndent()

    private fun patchedService(): String {
        val relativePath = "app/scripts/patch_flutter_foreground_task.py"
        val script = generateSequence(File(System.getProperty("user.dir") ?: ".").absoluteFile) { it.parentFile }
            .map { File(it, relativePath) }
            .firstOrNull { it.isFile } ?: error("Could not locate $relativePath")
        val fixture = Files.createTempFile("omi-fgs-contract-", ".kt").toFile()
        try {
            fixture.writeText(stockService)
            val process = ProcessBuilder("python3", script.absolutePath, fixture.absolutePath)
                .redirectErrorStream(true)
                .start()
            val output = process.inputStream.bufferedReader().readText()
            check(process.waitFor() == 0) { "Foreground service patch failed: $output" }
            return fixture.readText()
        } finally {
            fixture.delete()
        }
    }

    @Test
    fun `sticky restart with null intent promotes before preference reads`() {
        val source = patchedService()
        val start = source.substringAfter("override fun onStartCommand").substringBefore("override fun onTaskRemoved")
        assertTrue(start.indexOf("promoteColdStart()") < start.indexOf("loadDataFromPreferences()"))
        assertTrue(start.indexOf("promoteColdStart()") < start.indexOf("if (intent == null)"))
    }

    @Test
    fun `body exception and stop still follow successful promotion`() {
        val source = patchedService()
        val start = source.substringAfter("override fun onStartCommand").substringBefore("override fun onTaskRemoved")
        assertTrue(start.indexOf("promoteColdStart()") < start.indexOf("body failed"))
        val stop = source.substringAfter("private fun stopForegroundService()").substringBefore("private fun promoteForeground(")
        assertTrue(stop.indexOf("promoteColdStart()") < stop.indexOf("stopForeground(true)"))
        val update = source.substringAfter("ForegroundServiceAction.API_UPDATE -> {").substringBefore("body failed")
        assertTrue(update.indexOf("startForegroundService()") < update.indexOf("updateNotification()"))
        assertTrue(source.contains("throw IllegalStateException(\"cold-start foreground promotion failed\", e)"))
    }

    @Test
    fun `first promotion precedes notification and receiver work`() {
        val source = patchedService()
        val create = source.substringAfter("override fun onCreate()").substringBefore("override fun onStartCommand")
        assertTrue(create.indexOf("promoteColdStart()") < create.indexOf("registerBroadcastReceiver()"))
        val start = source.substringAfter("override fun onStartCommand").substringBefore("override fun onTaskRemoved")
        assertTrue(start.indexOf("promoteColdStart()") < start.indexOf("loadDataFromPreferences()"))
        val coldStart = source.substringAfter("private fun promoteColdStart()").substringBefore("private fun startForegroundService()")
        assertTrue(coldStart.indexOf("fallbackContractNotification()") < coldStart.indexOf("startForeground("))
        assertTrue(!coldStart.contains("notificationOptions"))
    }

    @Test
    fun `stop preserves a newer pending foreground start`() {
        val source = patchedService()
        val start = source.substringAfter("override fun onStartCommand").substringBefore("override fun onTaskRemoved")
        assertTrue(start.indexOf("promoteColdStart()") < start.indexOf("lastDeliveredStartId = startId"))
        val stop = source.substringAfter("private fun stopForegroundService()").substringBefore("private fun promoteForeground(")
        assertTrue(stop.contains("stopSelf(lastDeliveredStartId)"))
        assertTrue(!stop.contains("\n        stopSelf()"))
    }
}
