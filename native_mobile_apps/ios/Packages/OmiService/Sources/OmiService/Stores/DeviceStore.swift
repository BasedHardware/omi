import Foundation
import Observation
import OmiDevice
import OmiPersistence

/// The Omi wearable: pairing, connection, battery, codec. Mirrors `device_provider.dart`.
/// The paired device lives in the Flutter app's `btDevice` preference, so a device paired in the
/// Flutter build reconnects after the update.
///
/// Reconnecting lives here, not in the driver: the paired Omi is connected once Bluetooth is
/// ready and again after every disconnect. A CoreBluetooth connect waits until the device is in
/// range, so the attempt shows as `.connecting` for `connectTimeout` and then quietly keeps
/// waiting as `.disconnected`. Attempts that fail outright are retried a few times, spaced out.
@MainActor
@Observable
public final class DeviceStore {
    public enum Connection: Equatable, Sendable { case disconnected, connecting, connected }

    public private(set) var bluetooth: OmiDeviceManager.BluetoothState = .unknown
    public private(set) var paired: PairedDevice?
    public private(set) var connection: Connection = .disconnected
    public private(set) var battery: Int?
    public private(set) var codec: OmiGATT.Codec?
    public private(set) var discovered: [OmiDeviceManager.Discovery] = []
    public private(set) var isScanning = false
    /// The firmware revision read on this connection (`nil` until read, and while disconnected).
    /// `paired.firmwareRevision` is the last one known.
    public private(set) var liveFirmware: String?
    /// A firmware update owns the Omi: no connects until it hands the device back.
    public private(set) var isUpdatingFirmware = false
    /// On the charger (settings service; `nil` until read, and on firmware without it).
    public private(set) var isCharging: Bool?
    /// What the connected firmware supports; `nil` until read (old firmware never reports it).
    public private(set) var features: OmiGATT.Features?
    /// LED brightness 0…100 and mic gain level 0…8, as read from (or last written to) the Omi.
    public private(set) var ledBrightness: Int?
    public private(set) var micGain: Int?
    /// Find my Omi is buzzing.
    public private(set) var isFinding = false
    /// Drops, failed connects, battery and signal for My Devices › Diagnostics.
    public let diagnostics: DeviceDiagnosticsLog
    public var doubleTapAction: DoubleTapAction {
        didSet { preferences.set(doubleTapAction.rawValue, for: .doubleTapAction) }
    }

    /// Single press asks Omi and double tap runs `doubleTapAction` (Flutter "Omi Button Actions").
    public var buttonActionsEnabled: Bool {
        didSet { preferences.set(buttonActionsEnabled, for: .omiButtonActionsEnabled) }
    }

    /// Audio frames while connected (wired to the capture store by the app shell).
    @ObservationIgnored public var onAudio: ((Data) -> Void)?
    /// Called once the codec is known after a connect: capture can start.
    @ObservationIgnored public var onReady: ((OmiGATT.Codec) -> Void)?
    @ObservationIgnored public var onDisconnect: (() -> Void)?
    /// A second listener for the Omi's audio (onboarding's voice sample), next to capture.
    @ObservationIgnored public var audioTap: ((Data) -> Void)?
    /// A double tap on the Omi's button while it is set to end the conversation.
    @ObservationIgnored public var onDoubleTap: (() -> Void)?
    /// Every routed button action (`ButtonAction.route`), the end-conversation tap included.
    @ObservationIgnored public var onButtonAction: ((ButtonAction) -> Void)?
    /// Sees every raw button event first (the button lessons in onboarding); true keeps it from
    /// `ButtonAction.route`, so a practice press does not end or star anything.
    @ObservationIgnored public var buttonInterceptor: ((OmiGATT.ButtonEvent) -> Bool)?
    /// Model or firmware read from the connected Omi (the firmware check runs from here).
    @ObservationIgnored public var onDeviceInfo: (() -> Void)?
    /// The Omi's battery dropped below `LowBatteryAlert.low`; once per discharge.
    @ObservationIgnored public var onLowBattery: ((Int) -> Void)?
    /// Offline storage replies (wired to the sync store by the app shell).
    @ObservationIgnored public var onStorage: ((OmiStorage.Event) -> Void)?

    private let makeDriver: () -> any DeviceDriving
    /// Created on first use (`driver`); nil until then. Internal for the controls extension.
    var driverInstance: (any DeviceDriving)?
    private let preferences: Preferences
    private let connectTimeout: Duration
    private let retryDelay: Duration
    private var eventTask: Task<Void, Never>?
    private var storageTask: Task<Void, Never>?
    private var timeoutTask: Task<Void, Never>?
    private var retryTask: Task<Void, Never>?
    /// Whether the link was up before the last disconnect (otherwise the attempt failed).
    private var wasConnected = false
    private var failedAttempts = 0
    @ObservationIgnored private var lowBattery = LowBatteryAlert()
    private let findPulseGap: Duration
    private static let maxFailedAttempts = 3

    /// The driver is created lazily: creating a CBCentralManager shows the Bluetooth prompt, which
    /// only users with (or looking for) a wearable should see.
    public init(
        makeDriver: @escaping () -> any DeviceDriving,
        preferences: Preferences,
        connectTimeout: Duration = .seconds(15),
        retryDelay: Duration = .seconds(5),
        findPulseGap: Duration = OmiGATT.findPulseGap
    ) {
        self.makeDriver = makeDriver
        self.preferences = preferences
        self.connectTimeout = connectTimeout
        self.retryDelay = retryDelay
        self.findPulseGap = findPulseGap
        diagnostics = DeviceDiagnosticsLog(preferences: preferences)
        doubleTapAction = DoubleTapAction(rawValue: preferences.integer(.doubleTapAction, default: 0)) ?? .endConversation
        buttonActionsEnabled = preferences.bool(.omiButtonActionsEnabled, default: true)
        paired = PairedDevice.decode(preferences.string(.btDevice))
        lowBattery = LowBatteryAlert(alerted: preferences.bool(.lowBatteryAlerted, default: false))
    }

    private var driver: any DeviceDriving {
        if let driverInstance { return driverInstance }
        let driver = makeDriver()
        driverInstance = driver
        let events = driver.events
        eventTask = Task { [weak self] in
            for await event in events {
                self?.handle(event)
            }
        }
        let storage = driver.storageEvents
        storageTask = Task { [weak self] in
            for await event in storage {
                self?.onStorage?(event)
            }
        }
        return driver
    }

    /// Connects the paired device (no-op, and no Bluetooth prompt, without one). Also "Try again":
    /// starts over after failed attempts.
    public func start() {
        failedAttempts = 0
        connectPaired()
    }

    public func scan() {
        discovered = []
        isScanning = true
        driver.startScan()
    }

    public func stopScan() {
        isScanning = false
        driverInstance?.stopScan()
    }

    public func pair(_ discovery: OmiDeviceManager.Discovery) {
        stopScan()
        let device = PairedDevice(id: discovery.id.uuidString, name: discovery.name, rssi: discovery.rssi)
        persist(device)
        driver.connect(discovery.id)
    }

    public func forget() {
        diagnostics.reset()
        driverInstance?.disconnect()
        paired = nil
        preferences.set(nil as String?, for: .btDevice)
        connection = .disconnected
        battery = nil
        codec = nil
        liveFirmware = nil
        clearControls()
        timeoutTask?.cancel()
        retryTask?.cancel()
        wasConnected = false
        failedAttempts = 0
    }

    // MARK: Controls

    public func setLEDBrightness(_ percent: Int) {
        guard canDimLED else { return }
        let value = min(100, max(0, percent))
        ledBrightness = value
        driverInstance?.write(.ledBrightness, OmiGATT.ledBrightnessPayload(value))
    }

    public func setMicGain(_ level: Int) {
        guard canSetMicGain else { return }
        let value = min(OmiGATT.micGainLevels.upperBound, max(OmiGATT.micGainLevels.lowerBound, level))
        micGain = value
        driverInstance?.write(.micGain, OmiGATT.micGainPayload(value))
    }

    /// Find my Omi: three long buzzes. Calls while it buzzes are ignored.
    public func findDevice() async {
        guard canFind, !isFinding else { return }
        isFinding = true
        defer { isFinding = false }
        for (index, pulse) in OmiGATT.findPattern.enumerated() {
            guard connection == .connected else { return }
            driverInstance?.write(.haptic, pulse.payload)
            if index < OmiGATT.findPattern.count - 1 { try? await Task.sleep(for: findPulseGap) }
        }
    }

    private func clearControls() {
        isCharging = nil
        features = nil
        ledBrightness = nil
        micGain = nil
    }

    /// Writes a command to the Omi's storage (no-op while not connected).
    public func sendStorage(_ command: OmiStorage.Command) {
        guard connection == .connected else { return }
        driverInstance?.writeStorage(command.bytes)
    }

    private var pairedID: UUID? {
        paired.flatMap { UUID(uuidString: $0.id) }
    }

    private func connectPaired() {
        guard let id = pairedID, connection != .connected, !isUpdatingFirmware else { return }
        retryTask?.cancel()
        driver.connect(id)
    }

    private func bluetoothChanged(_ state: OmiDeviceManager.BluetoothState) {
        bluetooth = state
        // Connects made before Bluetooth reported ready (every cold start) went nowhere.
        if state == .ready {
            failedAttempts = 0
            connectPaired()
        } else if connection != .disconnected {
            // Bluetooth off drops the link without a disconnect callback.
            if connection == .connected { diagnostics.disconnected(reason: nil, wasConnected: true, manual: true) }
            connection = .disconnected
            wasConnected = false
            timeoutTask?.cancel()
            onDisconnect?()
        }
    }

    /// "Connecting…" for `connectTimeout`; after that the attempt keeps waiting as "Not connected".
    private func connecting() {
        connection = .connecting
        timeoutTask?.cancel()
        timeoutTask = Task { [weak self, connectTimeout] in
            try? await Task.sleep(for: connectTimeout)
            guard !Task.isCancelled, let self, connection == .connecting else { return }
            connection = .disconnected
        }
    }

    /// Reconnects right away when the link dropped (the connect waits for the device); spaced out
    /// and capped when the attempt itself failed, so a broken bond does not spin.
    private func disconnected(_ id: UUID, error: String?) {
        onDisconnect?()
        // A previous device let go while switching: not ours to reconnect.
        guard id == pairedID else { return }
        // A firmware update let go on purpose (recorded when it did).
        if !isUpdatingFirmware { diagnostics.disconnected(reason: error, wasConnected: wasConnected) }
        connection = .disconnected
        liveFirmware = nil
        timeoutTask?.cancel()
        if wasConnected {
            wasConnected = false
            failedAttempts = 0
            connectPaired()
            return
        }
        failedAttempts += 1
        guard failedAttempts <= Self.maxFailedAttempts else { return }
        retryTask?.cancel()
        retryTask = Task { [weak self, retryDelay] in
            try? await Task.sleep(for: retryDelay)
            guard !Task.isCancelled else { return }
            self?.connectPaired()
        }
    }

    /// Lets go of the Omi for a firmware update, which connects on its own: live audio stops and
    /// nothing reconnects until `resumeAfterFirmwareUpdate()`.
    public func suspendForFirmwareUpdate() {
        isUpdatingFirmware = true
        if connection == .connected { diagnostics.disconnected(reason: nil, wasConnected: true, manual: true) }
        timeoutTask?.cancel()
        retryTask?.cancel()
        driverInstance?.disconnect()
        if connection != .disconnected { onDisconnect?() }
        connection = .disconnected
        wasConnected = false
        liveFirmware = nil
    }

    /// The update is over (either way): reconnect, waiting for the Omi to finish restarting.
    public func resumeAfterFirmwareUpdate() {
        guard isUpdatingFirmware else { return }
        isUpdatingFirmware = false
        failedAttempts = 0
        connectPaired()
    }

    private func batteryChanged(_ level: Int) {
        battery = level
        diagnostics.batteryRead(level, charging: isCharging)
        let wasAlerted = lowBattery.alerted
        if lowBattery.update(level) { onLowBattery?(level) }
        if lowBattery.alerted != wasAlerted { preferences.set(lowBattery.alerted, for: .lowBatteryAlerted) }
    }

    private func persist(_ device: PairedDevice) {
        paired = device
        preferences.set(device.encoded, for: .btDevice)
    }

    func handle(_ event: OmiDeviceManager.Event) {
        switch event {
        case let .bluetooth(state):
            bluetoothChanged(state)
        case let .discovered(discovery):
            if let index = discovered.firstIndex(where: { $0.id == discovery.id }) {
                discovered[index] = discovery
            } else {
                discovered.append(discovery)
            }
        case .connecting:
            connecting()
        case let .connected(id, name):
            connection = .connected
            liveFirmware = nil
            clearControls()
            wasConnected = true
            diagnostics.connected()
            failedAttempts = 0
            timeoutTask?.cancel()
            if paired?.id != id.uuidString { persist(PairedDevice(id: id.uuidString, name: name)) }
        case let .disconnected(id, error):
            disconnected(id, error: error)
        case let .battery(level):
            batteryChanged(level)
        case let .codec(codec):
            self.codec = codec
            onReady?(codec)
        case let .info(model, firmware, manufacturer, hardware):
            guard var device = paired else { return }
            device.modelNumber = model ?? device.modelNumber
            device.firmwareRevision = firmware ?? device.firmwareRevision
            device.manufacturerName = manufacturer ?? device.manufacturerName
            device.hardwareRevision = hardware ?? device.hardwareRevision
            persist(device)
            if let firmware { liveFirmware = firmware }
            onDeviceInfo?()
        case let .audio(frame):
            onAudio?(frame)
            audioTap?(frame)
        case let .button(value):
            guard let event = OmiGATT.ButtonEvent(value) else { return }
            if buttonInterceptor?(event) == true { return }
            guard let action = ButtonAction.route(event, doubleTap: doubleTapAction, actionsEnabled: buttonActionsEnabled) else { return }
            if action == .endConversation { onDoubleTap?() }
            onButtonAction?(action)
        case let .rssi(level):
            diagnostics.signalRead(level)
        case .features, .charging, .ledBrightness, .micGain, .serialNumber:
            handleControl(event)
        }
    }

    /// Settings, features and Device Information read from the Omi.
    private func handleControl(_ event: OmiDeviceManager.Event) {
        switch event {
        case let .features(features):
            self.features = features
        case let .charging(charging):
            isCharging = charging
        case let .ledBrightness(level):
            ledBrightness = level
        case let .micGain(level):
            micGain = level
        case let .serialNumber(serial):
            guard var device = paired, device.serialNumber != serial else { return }
            device.serialNumber = serial
            persist(device)
        default:
            break
        }
    }
}

extension DeviceStore: StorageLink {
    public var storageDeviceID: String? {
        connection == .connected ? paired?.id : nil
    }
}
