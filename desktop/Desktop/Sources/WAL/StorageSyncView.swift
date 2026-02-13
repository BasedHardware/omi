import SwiftUI

// MARK: - Storage Sync View

/// View for managing device storage sync operations
struct StorageSyncView: View {
    @ObservedObject var storageSyncService = StorageSyncService.shared
    @ObservedObject var wifiSyncService = WifiSyncService.shared
    @ObservedObject var walService = WALService.shared
    @ObservedObject var deviceProvider = DeviceProvider.shared

    @State private var showWifiSetup = false
    @State private var wifiSsid = ""
    @State private var wifiPassword = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 16))
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Storage Sync")
                    .font(.system(size: 14, weight: .semibold))

                Spacer()

                // Pending count badge
                if walService.pendingWals.count > 0 {
                    Text("\(walService.pendingWals.count) pending")
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(
                            Capsule()
                                .fill(OmiColors.backgroundTertiary)
                        )
                }
            }

            // Device status
            if deviceProvider.isConnected, let device = deviceProvider.connectedDevice {
                deviceStatusSection(device: device)
            } else {
                noDeviceView
            }

            // Sync progress
            if storageSyncService.isSyncing || wifiSyncService.isSyncing {
                syncProgressSection
            }

            // Error message
            if let error = storageSyncService.errorMessage ?? wifiSyncService.errorMessage {
                errorView(error)
            }

            // Action buttons
            if deviceProvider.isConnected {
                actionButtonsSection
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundSecondary)
        )
        .dismissableSheet(isPresented: $showWifiSetup) {
            wifiSetupSheet
        }
    }

    // MARK: - Subviews

    private func deviceStatusSection(device: BtDevice) -> some View {
        HStack(spacing: 12) {
            // Device icon
            Image(systemName: device.type.iconName)
                .font(.system(size: 24))
                .foregroundColor(OmiColors.purplePrimary)
                .frame(width: 40, height: 40)
                .background(
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.15))
                )

            VStack(alignment: .leading, spacing: 4) {
                Text(device.displayName)
                    .font(.system(size: 13, weight: .medium))

                HStack(spacing: 8) {
                    // Connection status
                    HStack(spacing: 4) {
                        Circle()
                            .fill(Color.green)
                            .frame(width: 6, height: 6)
                        Text("Connected")
                            .font(.system(size: 11))
                            .foregroundColor(OmiColors.textSecondary)
                    }

                    // Battery
                    if deviceProvider.batteryLevel >= 0 {
                        HStack(spacing: 2) {
                            Image(systemName: batteryIcon)
                                .font(.system(size: 10))
                            Text("\(deviceProvider.batteryLevel)%")
                                .font(.system(size: 11))
                        }
                        .foregroundColor(batteryColor)
                    }
                }
            }

            Spacer()
        }
    }

    private var noDeviceView: some View {
        HStack(spacing: 12) {
            Image(systemName: "waveform.slash")
                .font(.system(size: 20))
                .foregroundColor(OmiColors.textTertiary)

            Text("No device connected")
                .font(.system(size: 13))
                .foregroundColor(OmiColors.textSecondary)

            Spacer()
        }
        .padding(.vertical, 8)
    }

    private var syncProgressSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Progress bar
            let progress = storageSyncService.isSyncing ?
                storageSyncService.progress : wifiSyncService.progress

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(OmiColors.backgroundTertiary)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(OmiColors.purplePrimary)
                        .frame(width: geometry.size.width * CGFloat(progress.percentComplete / 100))
                }
            }
            .frame(height: 8)

            // Progress details
            HStack {
                Text(formatBytes(progress.downloadedBytes))
                    .font(.system(size: 11, weight: .medium))

                Text("of \(formatBytes(progress.totalBytes))")
                    .font(.system(size: 11))
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                // Speed
                if progress.bytesPerSecond > 0 {
                    Text("\(formatBytes(Int(progress.bytesPerSecond)))/s")
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textSecondary)
                }

                // ETA
                if let eta = progress.estimatedSecondsRemaining {
                    Text("~\(formatDuration(eta))")
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textSecondary)
                }
            }

            // WiFi status
            if wifiSyncService.isSyncing {
                HStack(spacing: 6) {
                    Image(systemName: "wifi")
                        .font(.system(size: 10))
                    Text(wifiSyncService.status.displayName)
                        .font(.system(size: 11))
                }
                .foregroundColor(OmiColors.textSecondary)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
    }

    private func errorView(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.orange)

            Text(message)
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textSecondary)

            Spacer()

            Button("Dismiss") {
                storageSyncService.errorMessage = nil
                wifiSyncService.errorMessage = nil
            }
            .font(.system(size: 11, weight: .medium))
            .foregroundColor(OmiColors.purplePrimary)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.orange.opacity(0.1))
        )
    }

    private var actionButtonsSection: some View {
        HStack(spacing: 12) {
            // BLE Sync button
            Button(action: {
                Task {
                    await startBleSync()
                }
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                    Text("BLE Sync")
                }
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.purplePrimary)
                )
                .foregroundColor(.white)
            }
            .buttonStyle(.plain)
            .disabled(storageSyncService.isSyncing || wifiSyncService.isSyncing)

            // WiFi Sync button
            Button(action: {
                showWifiSetup = true
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "wifi")
                    Text("WiFi Sync")
                }
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(OmiColors.purplePrimary, lineWidth: 1)
                )
                .foregroundColor(OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)
            .disabled(storageSyncService.isSyncing || wifiSyncService.isSyncing)

            Spacer()

            // Stop button
            if storageSyncService.isSyncing || wifiSyncService.isSyncing {
                Button(action: {
                    stopSync()
                }) {
                    Image(systemName: "stop.fill")
                        .font(.system(size: 12))
                        .foregroundColor(.red)
                        .padding(8)
                        .background(
                            Circle()
                                .fill(Color.red.opacity(0.15))
                        )
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var wifiSetupSheet: some View {
        VStack(spacing: 20) {
            // Header
            HStack {
                Text("WiFi Sync Setup")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: { showWifiSetup = false })
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Network Name (SSID)")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(OmiColors.textSecondary)

                TextField("Enter WiFi network name", text: $wifiSsid)
                    .textFieldStyle(.roundedBorder)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Password")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(OmiColors.textSecondary)

                SecureField("Enter WiFi password", text: $wifiPassword)
                    .textFieldStyle(.roundedBorder)
            }

            Spacer()

            HStack(spacing: 12) {
                Button("Cancel") {
                    showWifiSetup = false
                }
                .buttonStyle(.plain)
                .foregroundColor(OmiColors.textSecondary)

                Button("Start Sync") {
                    showWifiSetup = false
                    Task {
                        await startWifiSync()
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(wifiSsid.isEmpty || wifiPassword.count < 8)
            }
        }
        .padding(24)
        .frame(width: 360, height: 280)
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - Actions

    private func startBleSync() async {
        guard let device = deviceProvider.connectedDevice,
              let connection = deviceProvider.activeConnection else { return }

        let codec = await connection.getAudioCodec()

        do {
            try await storageSyncService.startSync(
                device: device,
                codec: codec.name
            )
        } catch {
            // Error is shown in UI
        }
    }

    private func startWifiSync() async {
        guard let device = deviceProvider.connectedDevice,
              let connection = deviceProvider.activeConnection else { return }

        let codec = await connection.getAudioCodec()

        do {
            try await wifiSyncService.startWifiSync(
                device: device,
                codec: codec.name,
                ssid: wifiSsid,
                password: wifiPassword
            )
        } catch {
            // Error is shown in UI
        }
    }

    private func stopSync() {
        if storageSyncService.isSyncing {
            storageSyncService.stopSync()
        }
        if wifiSyncService.isSyncing {
            wifiSyncService.stopSync()
        }
    }

    // MARK: - Helpers

    private var batteryIcon: String {
        let level = deviceProvider.batteryLevel
        switch level {
        case 0..<10: return "battery.0"
        case 10..<35: return "battery.25"
        case 35..<60: return "battery.50"
        case 60..<85: return "battery.75"
        default: return "battery.100"
        }
    }

    private var batteryColor: Color {
        let level = deviceProvider.batteryLevel
        switch level {
        case 0..<20: return .red
        case 20..<40: return .orange
        default: return .green
        }
    }

    private func formatBytes(_ bytes: Int) -> String {
        if bytes < 1024 {
            return "\(bytes) B"
        } else if bytes < 1024 * 1024 {
            return String(format: "%.1f KB", Double(bytes) / 1024)
        } else {
            return String(format: "%.1f MB", Double(bytes) / (1024 * 1024))
        }
    }

    private func formatDuration(_ seconds: Double) -> String {
        if seconds < 60 {
            return "\(Int(seconds))s"
        } else {
            let minutes = Int(seconds) / 60
            let secs = Int(seconds) % 60
            return "\(minutes)m \(secs)s"
        }
    }
}

// MARK: - Compact Sync Status Indicator

/// Compact indicator showing sync status in headers/toolbars
struct StorageSyncIndicator: View {
    @ObservedObject var storageSyncService = StorageSyncService.shared
    @ObservedObject var wifiSyncService = WifiSyncService.shared
    @ObservedObject var walService = WALService.shared

    var body: some View {
        if storageSyncService.isSyncing || wifiSyncService.isSyncing {
            // Syncing indicator
            HStack(spacing: 6) {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 12, height: 12)

                let progress = storageSyncService.isSyncing ?
                    storageSyncService.progress : wifiSyncService.progress

                Text("\(Int(progress.percentComplete))%")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(OmiColors.textSecondary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(OmiColors.purplePrimary.opacity(0.15))
            )
        } else if walService.pendingWals.count > 0 {
            // Pending indicator
            HStack(spacing: 4) {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 10))

                Text("\(walService.pendingWals.count)")
                    .font(.system(size: 11, weight: .medium))
            }
            .foregroundColor(OmiColors.textSecondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(OmiColors.backgroundTertiary)
            )
        }
    }
}

// MARK: - Preview

#Preview("Storage Sync View") {
    StorageSyncView()
        .frame(width: 360)
        .padding()
        .background(OmiColors.backgroundPrimary)
}
