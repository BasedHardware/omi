package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.network.APIClientProtocol

/**
 * Port of `DiagnosticsReportStore.swift`: My Devices › Diagnostics › Share / Send to support
 * (Flutter `_exportDiagnostics`, `_sendToSupport`): the bundle shared as a JSON file, or uploaded
 * for a support ticket.
 */
class DiagnosticsReportStore(
    private val api: APIClientProtocol,
    private val devices: DeviceStore,
    private val environment: DeviceDiagnosticsLog.Environment,
) {
    sealed interface Phase {
        data object Idle : Phase
        data object Sending : Phase
        data class Sent(val ticket: String) : Phase
        data object Failed : Phase
    }

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set

    /** The bundle as shown before sending, and as shared. */
    fun bundle(): ByteArray = devices.diagnostics.bundle(
        device = devices.paired,
        battery = if (devices.connection == DeviceStore.Connection.Connected) devices.battery else null,
        charging = devices.isCharging,
        environment = environment,
    )

    suspend fun send() {
        if (phase == Phase.Sending) return
        phase = Phase.Sending
        phase = try {
            Phase.Sent(api.uploadDeviceDiagnostics(bundle()))
        } catch (e: Exception) {
            Phase.Failed
        }
    }

    fun dismiss() {
        if (phase != Phase.Sending) phase = Phase.Idle
    }
}
