import Foundation

// Hardware-free effects for executing the production capture class on the host.
public enum RayBanAudioProbe {
    public enum Fault: String, Error, Hashable { case category, preferredInput, activation, format, converter, engine, deactivation }
    public static var faults: Set<Fault> = []
    public static var taps = 0
    public static var installs = 0
    public static var removals = 0
    public static var activations = 0
    public static var deactivations = 0
    public static var starts = 0
    public static var stops = 0
    public static var sessionActive = false
    public static var engineRunning = false
    public static func reset() {
        faults = []; taps = 0; installs = 0; removals = 0
        activations = 0; deactivations = 0; starts = 0; stops = 0
        sessionActive = false; engineRunning = false
        AVAudioSession.sharedInstance().availableInputs = [AVAudioSessionPortDescription()]
    }
}

public final class AVAudioSessionPortDescription {
    public let portType = AVAudioSession.Port.bluetoothHFP
    public let uid = "fixture-glasses"
    public let portName = "Fixture glasses"
    public init() {}
}
public struct AVAudioSessionRouteDescription { public var inputs: [AVAudioSessionPortDescription] = [] }
public final class AVAudioSession {
    public enum Port { case bluetoothHFP }
    public enum Category { case playAndRecord }
    public enum Mode { case `default` }
    public enum InterruptionType: UInt { case ended = 0, began = 1 }
    public struct CategoryOptions: OptionSet {
        public let rawValue: Int
        public init(rawValue: Int) { self.rawValue = rawValue }
        public static let allowBluetoothHFP = Self(rawValue: 1)
    }
    public struct SetActiveOptions: OptionSet {
        public let rawValue: Int
        public init(rawValue: Int) { self.rawValue = rawValue }
        public static let notifyOthersOnDeactivation = Self(rawValue: 1)
    }
    public static let routeChangeNotification = Notification.Name("fixture-route-change")
    public static let interruptionNotification = Notification.Name("fixture-interruption")
    private static let shared = AVAudioSession()
    public static func sharedInstance() -> AVAudioSession { shared }
    public var availableInputs: [AVAudioSessionPortDescription]? = [AVAudioSessionPortDescription()]
    public var currentRoute = AVAudioSessionRouteDescription()
    public func setCategory(_ category: Category, mode: Mode, options: CategoryOptions) throws {
        if RayBanAudioProbe.faults.contains(.category) { throw RayBanAudioProbe.Fault.category }
    }
    public func setPreferredInput(_ input: AVAudioSessionPortDescription) throws {
        if RayBanAudioProbe.faults.contains(.preferredInput) { throw RayBanAudioProbe.Fault.preferredInput }
        currentRoute.inputs = [input]
    }
    public func setActive(_ active: Bool, options: SetActiveOptions) throws {
        RayBanAudioProbe.sessionActive = active
        if active {
            RayBanAudioProbe.activations += 1
            // An activation attempt may fail after changing native state.
            if RayBanAudioProbe.faults.contains(.activation) { throw RayBanAudioProbe.Fault.activation }
        } else {
            RayBanAudioProbe.deactivations += 1
            if RayBanAudioProbe.faults.contains(.deactivation) { throw RayBanAudioProbe.Fault.deactivation }
        }
    }
}
public let AVAudioSessionInterruptionTypeKey = "fixture-interruption-type"
extension Notification.Name {
    public static let AVAudioEngineConfigurationChange = Notification.Name("fixture-engine-change")
}

public typealias AVAudioFrameCount = UInt32
public enum AVAudioCommonFormat { case pcmFormatInt16 }
public final class AVAudioFormat {
    public let sampleRate: Double
    public init(sampleRate: Double) { self.sampleRate = sampleRate }
    public init?(commonFormat: AVAudioCommonFormat, sampleRate: Double, channels: UInt32, interleaved: Bool) {
        self.sampleRate = sampleRate
    }
}
public final class AVAudioPCMBuffer {
    public let format: AVAudioFormat
    public var frameLength: AVAudioFrameCount = 0
    public var int16ChannelData: UnsafePointer<UnsafeMutablePointer<Int16>>? { nil }
    public init?(pcmFormat: AVAudioFormat, frameCapacity: AVAudioFrameCount) { format = pcmFormat }
}
public enum AVAudioConverterInputStatus { case noDataNow, haveData }
public enum AVAudioConverterOutputStatus { case haveData }
public final class AVAudioConverter {
    public init?(from: AVAudioFormat, to: AVAudioFormat) {
        if RayBanAudioProbe.faults.contains(.converter) { return nil }
    }
    @discardableResult
    public func convert(to: AVAudioPCMBuffer, error: UnsafeMutablePointer<NSError?>?,
                        withInputFrom: (AVAudioFrameCount, UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioPCMBuffer?) -> AVAudioConverterOutputStatus {
        .haveData
    }
}
public final class AVAudioInputNode {
    public func inputFormat(forBus: Int) -> AVAudioFormat {
        AVAudioFormat(sampleRate: RayBanAudioProbe.faults.contains(.format) ? 0 : 48000)
    }
    public func installTap(onBus: Int, bufferSize: UInt32, format: AVAudioFormat,
                           block: @escaping (AVAudioPCMBuffer, Any?) -> Void) {
        precondition(RayBanAudioProbe.taps == 0, "duplicate input tap")
        RayBanAudioProbe.taps += 1
        RayBanAudioProbe.installs += 1
    }
    public func removeTap(onBus: Int) {
        precondition(RayBanAudioProbe.taps == 1, "removing an unowned tap")
        RayBanAudioProbe.taps -= 1
        RayBanAudioProbe.removals += 1
    }
}
public final class AVAudioEngine {
    public let inputNode = AVAudioInputNode()
    public init() {}
    public func prepare() {}
    public func start() throws {
        RayBanAudioProbe.starts += 1
        if RayBanAudioProbe.faults.contains(.engine) { throw RayBanAudioProbe.Fault.engine }
        RayBanAudioProbe.engineRunning = true
    }
    public func stop() {
        RayBanAudioProbe.stops += 1
        RayBanAudioProbe.engineRunning = false
    }
}
