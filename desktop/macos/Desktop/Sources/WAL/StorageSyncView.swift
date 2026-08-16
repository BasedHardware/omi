import OmiTheme
import OmiWAL
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
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      // Header
      HStack {
        Image(systemName: "arrow.triangle.2.circlepath")
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(Ink.primary)

        Text("Storage Sync")
          .scaledFont(size: OmiType.body, weight: .semibold)

        Spacer()

        // Pending count badge
        if walService.pendingWals.count > 0 {
          Text("\(walService.pendingWals.count) pending")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.hairline)
            .background(
              Capsule()
                .fill(Ink.rowFill)
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
    .padding(OmiSpacing.lg)
    .background(
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
        .fill(Ink.wash)
    )
    .dismissableSheet(isPresented: $showWifiSetup) {
      wifiSetupSheet
    }
  }

  // MARK: - Subviews

  private func deviceStatusSection(device: BtDevice) -> some View {
    HStack(spacing: OmiSpacing.md) {
      // Device icon
      Image(systemName: device.type.iconName)
        .scaledFont(size: 24)
        .foregroundColor(Ink.accent)
        .frame(width: 40, height: 40)
        .background(
          Circle()
            .fill(Ink.accent.opacity(0.15))
        )

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(device.displayName)
          .scaledFont(size: OmiType.body, weight: .medium)

        HStack(spacing: OmiSpacing.sm) {
          // Connection status
          HStack(spacing: OmiSpacing.xxs) {
            Circle()
              .fill(Ink.listeningGreen)
              .frame(width: 6, height: 6)
            Text("Connected")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }

          // Battery
          if deviceProvider.batteryLevel >= 0 {
            HStack(spacing: OmiSpacing.hairline) {
              Image(systemName: batteryIcon)
                .scaledFont(size: OmiType.micro)
              Text("\(deviceProvider.batteryLevel)%")
                .scaledFont(size: OmiType.caption)
            }
            .foregroundColor(batteryColor)
          }
        }
      }

      Spacer()
    }
  }

  private var noDeviceView: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: "waveform.slash")
        .scaledFont(size: OmiType.heading)
        .foregroundColor(Ink.secondary)

      Text("No device connected")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      Spacer()
    }
    .padding(.vertical, OmiSpacing.sm)
  }

  private var syncProgressSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      // Progress bar
      let progress = storageSyncService.isSyncing ? storageSyncService.progress : wifiSyncService.progress

      GeometryReader { geometry in
        ZStack(alignment: .leading) {
          RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
            .fill(Ink.rowFill)

          RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
            .fill(Ink.primary)
            .frame(width: geometry.size.width * CGFloat(progress.percentComplete / 100))
        }
      }
      .frame(height: 8)

      // Progress details
      HStack {
        Text(formatBytes(progress.downloadedBytes))
          .scaledFont(size: OmiType.caption, weight: .medium)

        Text("of \(formatBytes(progress.totalBytes))")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)

        Spacer()

        // Speed
        if progress.bytesPerSecond > 0 {
          Text("\(formatBytes(Int(progress.bytesPerSecond)))/s")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }

        // ETA
        if let eta = progress.estimatedSecondsRemaining {
          Text("~\(formatDuration(eta))")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }

      // WiFi status
      if wifiSyncService.isSyncing {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "wifi")
            .scaledFont(size: OmiType.micro)
          Text(wifiSyncService.status.displayName)
            .scaledFont(size: OmiType.caption)
        }
        .foregroundColor(Ink.secondary)
      }
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
        .fill(Ink.rowFill)
    )
  }

  private func errorView(_: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.triangle.fill")
        .foregroundColor(SettingsInk.notice)

      Text("Storage sync couldn't finish. Try again.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Spacer()

      Button("Dismiss") {
        storageSyncService.errorMessage = nil
        wifiSyncService.errorMessage = nil
      }
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(Ink.primary)
    }
    .padding(OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
        .fill(SettingsInk.notice.opacity(0.1))
    )
  }

  private var actionButtonsSection: some View {
    HStack(spacing: OmiSpacing.md) {
      // BLE Sync button
      Button(action: {
        Task {
          await startBleSync()
        }
      }) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "antenna.radiowaves.left.and.right")
          Text("BLE Sync")
        }
        .scaledFont(size: OmiType.caption, weight: .medium)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
            .fill(Ink.primary)
        )
        .foregroundColor(Ink.surface)
      }
      .buttonStyle(.plain)
      .disabled(storageSyncService.isSyncing || wifiSyncService.isSyncing)

      // WiFi Sync button
      Button(action: {
        showWifiSetup = true
      }) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "wifi")
          Text("WiFi Sync")
        }
        .scaledFont(size: OmiType.caption, weight: .medium)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
            .stroke(Ink.hairline, lineWidth: 1)
        )
        .foregroundColor(Ink.primary)
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
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.errorRed)
            .padding(OmiSpacing.sm)
            .background(
              Circle()
                .fill(Ink.errorRed.opacity(0.15))
            )
        }
        .buttonStyle(.plain)
      }
    }
  }

  private var wifiSetupSheet: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Header
      HStack {
        Text("WiFi Sync Setup")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        DismissButton(action: { showWifiSetup = false })
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Network Name (SSID)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)

        TextField("Enter WiFi network name", text: $wifiSsid)
          .textFieldStyle(.roundedBorder)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Password")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)

        SecureField("Enter WiFi password", text: $wifiPassword)
          .textFieldStyle(.roundedBorder)
      }

      Spacer()

      HStack(spacing: OmiSpacing.md) {
        Button("Cancel") {
          showWifiSetup = false
        }
        .buttonStyle(.plain)
        .foregroundColor(Ink.secondary)

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
    .padding(OmiSpacing.xxl)
    .frame(width: 360, height: 280)
    .background(Ink.wash)
  }

  // MARK: - Actions

  private func startBleSync() async {
    guard let device = deviceProvider.connectedDevice,
      let connection = deviceProvider.activeConnection
    else { return }

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
      let connection = deviceProvider.activeConnection
    else { return }

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
    case 0..<20: return Ink.errorRed
    case 20..<40: return SettingsInk.notice
    default: return Ink.listeningGreen
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
      HStack(spacing: OmiSpacing.xs) {
        ProgressView()
          .scaleEffect(0.6)
          .frame(width: 12, height: 12)

        let progress = storageSyncService.isSyncing ? storageSyncService.progress : wifiSyncService.progress

        Text("\(Int(progress.percentComplete))%")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(
        Capsule()
          .fill(Ink.accent.opacity(0.15))
      )
    } else if walService.pendingWals.count > 0 {
      // Pending indicator
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: "arrow.triangle.2.circlepath")
          .scaledFont(size: OmiType.micro)

        Text("\(walService.pendingWals.count)")
          .scaledFont(size: OmiType.caption, weight: .medium)
      }
      .foregroundColor(Ink.secondary)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(
        Capsule()
          .fill(Ink.rowFill)
      )
    }
  }
}

// MARK: - Preview

#if canImport(PreviewsMacros)
  #Preview("Storage Sync View") {
    StorageSyncView()
      .frame(width: 360)
      .padding()
      .background(Ink.surface)
  }
#endif
