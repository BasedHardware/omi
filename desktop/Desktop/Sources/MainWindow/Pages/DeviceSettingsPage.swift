import SwiftUI

/// Settings page for Bluetooth device management
struct DeviceSettingsPage: View {
    @ObservedObject private var deviceProvider = DeviceProvider.shared

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Header
                headerSection

                // Content
                VStack(spacing: 24) {
                    // Connected Device Section
                    if deviceProvider.isConnected, let device = deviceProvider.connectedDevice {
                        connectedDeviceSection(device: device)
                    } else if let pairedDevice = deviceProvider.pairedDevice {
                        pairedDeviceSection(device: pairedDevice)
                    }

                    // Discovery Section
                    discoverySection

                    // Device List
                    if !deviceProvider.discoveredDevices.isEmpty {
                        discoveredDevicesSection
                    }

                    Spacer()
                }
                .padding(.horizontal, 32)
            }
        }
        .background(OmiColors.backgroundSecondary.opacity(0.3))
    }

    // MARK: - Header

    private var headerSection: some View {
        HStack {
            Text("Device")
                .scaledFont(size: 28, weight: .bold)
                .foregroundColor(OmiColors.textPrimary)

            Spacer()

            // Bluetooth status indicator
            HStack(spacing: 8) {
                Circle()
                    .fill(bluetoothStatusColor)
                    .frame(width: 8, height: 8)

                Text(bluetoothStatusText)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(.horizontal, 32)
        .padding(.top, 32)
        .padding(.bottom, 24)
    }

    private var bluetoothStatusColor: Color {
        switch deviceProvider.bluetoothState {
        case .poweredOn:
            return deviceProvider.isConnected ? .green : .blue
        case .poweredOff:
            return .red
        default:
            return .gray
        }
    }

    private var bluetoothStatusText: String {
        switch deviceProvider.bluetoothState {
        case .poweredOn:
            return deviceProvider.isConnected ? "Connected" : "Ready"
        case .poweredOff:
            return "Bluetooth Off"
        case .unauthorized:
            return "Not Authorized"
        case .unsupported:
            return "Not Supported"
        default:
            return "Unknown"
        }
    }

    // MARK: - Connected Device Section

    private func connectedDeviceSection(device: BtDevice) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            // Section header
            Text("Connected Device")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .textCase(.uppercase)

            // Device card
            VStack(spacing: 16) {
                // Device info row
                HStack(spacing: 16) {
                    // Device icon
                    deviceIcon(for: device.type)

                    // Device info
                    VStack(alignment: .leading, spacing: 4) {
                        Text(device.displayName)
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(device.type.displayName)
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    // Battery indicator
                    if deviceProvider.batteryLevel >= 0 {
                        batteryIndicator(level: deviceProvider.batteryLevel)
                    }
                }

                Divider()
                    .background(OmiColors.backgroundQuaternary)

                // Device details
                VStack(spacing: 12) {
                    if let firmware = device.firmwareRevision {
                        detailRow(label: "Firmware", value: firmware)
                    }
                    if let model = device.modelNumber {
                        detailRow(label: "Model", value: model)
                    }
                    if let hardware = device.hardwareRevision {
                        detailRow(label: "Hardware", value: hardware)
                    }
                }

                Divider()
                    .background(OmiColors.backgroundQuaternary)

                // Actions
                HStack(spacing: 12) {
                    // Disconnect button
                    Button(action: {
                        Task {
                            await deviceProvider.disconnect()
                        }
                    }) {
                        Text("Disconnect")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(OmiColors.backgroundTertiary)
                            )
                    }
                    .buttonStyle(.plain)

                    // Unpair button
                    Button(action: {
                        Task {
                            await deviceProvider.unpair()
                        }
                    }) {
                        Text("Unpair")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.red.opacity(0.5), lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                    )
            )
        }
    }

    // MARK: - Paired Device Section (when disconnected)

    private func pairedDeviceSection(device: BtDevice) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            // Section header
            Text("Paired Device")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .textCase(.uppercase)

            // Device card
            HStack(spacing: 16) {
                // Device icon
                deviceIcon(for: device.type)
                    .opacity(0.5)

                // Device info
                VStack(alignment: .leading, spacing: 4) {
                    Text(device.displayName)
                        .scaledFont(size: 16, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)

                    HStack(spacing: 6) {
                        Circle()
                            .fill(Color.orange)
                            .frame(width: 6, height: 6)
                        Text("Disconnected")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }

                Spacer()

                // Reconnect button
                if deviceProvider.isConnecting {
                    ProgressView()
                        .scaleEffect(0.8)
                        .frame(width: 80)
                } else {
                    Button(action: {
                        Task {
                            await deviceProvider.connect(to: device)
                        }
                    }) {
                        Text("Connect")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(.white)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(OmiColors.purplePrimary)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                    )
            )
        }
    }

    // MARK: - Discovery Section

    private var discoverySection: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Section header
            HStack {
                Text("Find Devices")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textTertiary)
                    .textCase(.uppercase)

                Spacer()

                if deviceProvider.isScanning {
                    HStack(spacing: 8) {
                        ProgressView()
                            .scaleEffect(0.6)
                        Text("Scanning...")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
            }

            // Scan button
            Button(action: {
                if deviceProvider.isScanning {
                    deviceProvider.stopDiscovery()
                } else {
                    deviceProvider.startDiscovery()
                }
            }) {
                HStack {
                    Image(systemName: deviceProvider.isScanning ? "stop.fill" : "antenna.radiowaves.left.and.right")
                        .scaledFont(size: 16)

                    Text(deviceProvider.isScanning ? "Stop Scanning" : "Scan for Devices")
                        .scaledFont(size: 14, weight: .medium)
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(deviceProvider.isScanning ? Color.orange : OmiColors.purplePrimary)
                )
            }
            .buttonStyle(.plain)
            .disabled(deviceProvider.bluetoothState != .poweredOn)
        }
    }

    // MARK: - Discovered Devices Section

    private var discoveredDevicesSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Section header
            Text("Available Devices (\(deviceProvider.discoveredDevices.count))")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .textCase(.uppercase)

            // Device list
            VStack(spacing: 2) {
                ForEach(deviceProvider.discoveredDevices, id: \.id) { device in
                    discoveredDeviceRow(device: device)
                }
            }
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
            )
        }
    }

    private func discoveredDeviceRow(device: BtDevice) -> some View {
        HStack(spacing: 12) {
            // Device icon
            deviceIcon(for: device.type, size: 32)

            // Device info
            VStack(alignment: .leading, spacing: 2) {
                Text(device.displayName)
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 8) {
                    Text(device.type.displayName)
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)

                    // Signal strength
                    signalIndicator(rssi: device.rssi)
                }
            }

            Spacer()

            // Connect button
            if deviceProvider.isConnecting && deviceProvider.pairedDevice?.id == device.id {
                ProgressView()
                    .scaleEffect(0.7)
            } else if deviceProvider.connectedDevice?.id == device.id {
                Text("Connected")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.green)
            } else {
                Button(action: {
                    Task {
                        await deviceProvider.connect(to: device)
                    }
                }) {
                    Text("Connect")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.clear)
        )
        .contentShape(Rectangle())
    }

    // MARK: - Helper Views

    private func deviceIcon(for type: DeviceType, size: CGFloat = 48) -> some View {
        ZStack {
            Circle()
                .fill(OmiColors.purplePrimary.opacity(0.15))
                .frame(width: size, height: size)

            Image(systemName: deviceIconName(for: type))
                .scaledFont(size: size * 0.4)
                .foregroundColor(OmiColors.purplePrimary)
        }
    }

    private func deviceIconName(for type: DeviceType) -> String {
        switch type {
        case .omi, .openglass:
            return "wave.3.right.circle.fill"
        case .frame:
            return "eyeglasses"
        case .appleWatch:
            return "applewatch"
        case .plaud:
            return "waveform.circle.fill"
        case .bee:
            return "antenna.radiowaves.left.and.right.circle.fill"
        default:
            return "circle.dotted"
        }
    }

    private func batteryIndicator(level: Int) -> some View {
        HStack(spacing: 4) {
            Image(systemName: batteryIconName(level: level))
                .scaledFont(size: 16)
                .foregroundColor(batteryColor(level: level))

            Text("\(level)%")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(batteryColor(level: level))
        }
    }

    private func batteryIconName(level: Int) -> String {
        switch level {
        case 0..<10: return "battery.0"
        case 10..<35: return "battery.25"
        case 35..<60: return "battery.50"
        case 60..<85: return "battery.75"
        default: return "battery.100"
        }
    }

    private func batteryColor(level: Int) -> Color {
        switch level {
        case 0..<20: return .red
        case 20..<40: return .orange
        default: return .green
        }
    }

    private func signalIndicator(rssi: Int) -> some View {
        HStack(spacing: 2) {
            ForEach(0..<4) { bar in
                RoundedRectangle(cornerRadius: 1)
                    .fill(signalBarColor(bar: bar, rssi: rssi))
                    .frame(width: 3, height: CGFloat(4 + bar * 2))
            }
        }
    }

    private func signalBarColor(bar: Int, rssi: Int) -> Color {
        // RSSI typically ranges from -30 (excellent) to -100 (poor)
        let threshold: Int
        switch bar {
        case 0: threshold = -90
        case 1: threshold = -75
        case 2: threshold = -60
        default: threshold = -45
        }

        return rssi >= threshold ? OmiColors.purplePrimary : OmiColors.backgroundQuaternary
    }

    private func detailRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)

            Spacer()

            Text(value)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
        }
    }
}

// MARK: - Preview

#Preview {
    DeviceSettingsPage()
        .frame(width: 600, height: 800)
        .background(OmiColors.backgroundPrimary)
}
