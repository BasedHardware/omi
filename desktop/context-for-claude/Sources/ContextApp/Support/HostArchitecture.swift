import ContextCore
import Foundation

/// Runtime host facts for Context for Claude.
///
/// Detection matches Omi desktop (`AppState.isAppleSilicon`): `hw.optional.arm64` via sysctl.
/// Policy decisions live in `CaptureHostPolicy` so tests can inject Silicon vs Intel without
/// needing both machines.
enum HostArchitecture {
    static let isAppleSilicon: Bool = {
        var value: Int32 = 0
        var size = MemoryLayout<Int32>.size
        if sysctlbyname("hw.optional.arm64", &value, &size, nil, 0) == 0 {
            return value == 1
        }
        return false
    }()

    static var policy: CaptureHostPolicy {
        CaptureHostPolicy(isAppleSilicon: isAppleSilicon)
    }

    static var usesLocalSTT: Bool { policy.usesLocalSTT }

    static var screenCaptureInterval: TimeInterval { policy.screenCaptureInterval }
}
