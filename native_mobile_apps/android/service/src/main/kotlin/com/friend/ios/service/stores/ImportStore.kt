package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ImportJob
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Port of `ImportStore.swift`: importing history from another device (Flutter
 * `import_history_page`). A Limitless export zip is uploaded, the backend turns it into
 * conversations; the list refreshes every few seconds while a job runs.
 */
class ImportStore(
    private val api: APIClientProtocol,
    private val scope: CoroutineScope,
    private val pollIntervalMillis: Long = 3_000,
) {
    enum class Phase { Idle, Loading, Loaded, Failed }

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    var jobs: List<ImportJob> by mutableStateOf(emptyList())
        private set
    var isUploading: Boolean by mutableStateOf(false)
        private set
    var lastError: String? by mutableStateOf(null)
        private set
    private var polling: Job? = null

    val hasRunningJob: Boolean get() = jobs.any { it.isRunning }

    suspend fun load() {
        if (jobs.isEmpty()) phase = Phase.Loading
        try {
            jobs = api.importJobs()
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            phase = if (jobs.isEmpty()) Phase.Failed else Phase.Loaded
        }
        if (hasRunningJob) startPolling()
    }

    /** Uploads a picked zip ([bytes] null: unreadable). Returns whether the import started. */
    suspend fun importZip(bytes: ByteArray?, filename: String, language: String): Boolean {
        lastError = null
        if (!filename.lowercase().endsWith(".zip") || bytes == null) {
            lastError = "unreadable"
            return false
        }
        if (bytes.size > MAX_BYTES) {
            lastError = "tooLarge"
            return false
        }
        isUploading = true
        return try {
            val job = api.importLimitless(bytes, filename, language)
            jobs = listOf(job) + jobs.filter { it.id != job.id }
            startPolling()
            true
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            lastError = e.toString()
            false
        } finally {
            isUploading = false
        }
    }

    suspend fun cancel(id: String) {
        try {
            api.cancelImportJob(id)
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            lastError = e.toString()
        }
        load()
    }

    /** Removes a finished job from the history (its conversations stay). */
    suspend fun delete(id: String) {
        val index = jobs.indexOfFirst { it.id == id }
        if (index < 0) return
        val removed = jobs[index]
        jobs = jobs.filterIndexed { i, _ -> i != index }
        try {
            api.deleteImportJob(id)
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            lastError = e.toString()
            jobs = jobs.toMutableList().apply { add(minOf(index, size), removed) }
        }
    }

    fun stopPolling() {
        polling?.cancel()
        polling = null
    }

    private fun startPolling() {
        if (polling != null) return
        polling = scope.launch {
            while (isActive) {
                delay(pollIntervalMillis)
                runCatching { api.importJobs() }.getOrNull()?.let { jobs = it }
                if (!hasRunningJob) break
            }
            polling = null
        }
    }

    companion object {
        /** The backend refuses anything larger. */
        const val MAX_BYTES = 100 * 1024 * 1024
    }
}
