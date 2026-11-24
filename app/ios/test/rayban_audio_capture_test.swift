import AVFoundation
import Darwin
import Foundation

@main
struct RayBanAudioCaptureTest {
    enum Failure: Error { case assertion(String) }

    static func require(_ condition: Bool, _ message: String = "capture invariant failed") throws {
        if !condition { throw Failure.assertion(message) }
    }

    static func clean(_ capture: RayBanMetaAudioCapture) throws {
        try require(!capture.running && !RayBanAudioProbe.engineRunning, "failed start retained the engine")
        try require(RayBanAudioProbe.taps == 0 && !RayBanAudioProbe.sessionActive, "failed start retained tap/session")
        let effects = [RayBanAudioProbe.removals, RayBanAudioProbe.deactivations, RayBanAudioProbe.stops]
        capture.stop()
        capture.stop()
        try require(effects == [RayBanAudioProbe.removals, RayBanAudioProbe.deactivations, RayBanAudioProbe.stops],
                    "cleanup must be idempotent")
    }

    static func retry(_ capture: RayBanMetaAudioCapture) throws {
        RayBanAudioProbe.faults = []
        try capture.start(targetUid: nil)
        try require(capture.running && RayBanAudioProbe.engineRunning && RayBanAudioProbe.sessionActive)
        try require(RayBanAudioProbe.taps == 1)
        let starts = RayBanAudioProbe.starts
        let installs = RayBanAudioProbe.installs
        try capture.start(targetUid: nil)
        try require(starts == RayBanAudioProbe.starts && installs == RayBanAudioProbe.installs)
        capture.stop()
        try clean(capture)
    }

    static func main() {
        do { try scenarios() }
        catch {
            fputs("Ray-Ban native capture test failed: \(error)\n", stderr)
            exit(1)
        }
    }

    static func scenarios() throws {
        for fault in [RayBanAudioProbe.Fault.engine, .activation, .format, .converter, .category, .preferredInput] {
            RayBanAudioProbe.reset()
            RayBanAudioProbe.faults = [fault]
            let capture = RayBanMetaAudioCapture()
            do {
                try capture.start(targetUid: nil)
                throw Failure.assertion("setup should have failed at \(fault)")
            } catch {
                if fault == .format || fault == .converter {
                    try require((error as NSError).code == (fault == .format ? 1 : 2))
                } else {
                    try require(error as? RayBanAudioProbe.Fault == fault, "preserve the original error")
                }
            }
            try clean(capture)
            let early = fault == .category || fault == .preferredInput
            try require(RayBanAudioProbe.deactivations == (early ? 0 : 1))
            try require(RayBanAudioProbe.removals == (fault == .engine ? 1 : 0))
            try retry(capture)
        }

        // Cleanup failure must never replace the setup error sent to Dart.
        RayBanAudioProbe.reset()
        RayBanAudioProbe.faults = [.engine, .deactivation]
        let cleanupFailure = RayBanMetaAudioCapture()
        do {
            try cleanupFailure.start(targetUid: nil)
            throw Failure.assertion("engine failure expected")
        } catch {
            try require(error as? RayBanAudioProbe.Fault == .engine)
        }
        try clean(cleanupFailure)
        try retry(cleanupFailure)

        // Refusal before activation must not deactivate another audio owner.
        RayBanAudioProbe.reset()
        AVAudioSession.sharedInstance().availableInputs = []
        let missing = RayBanMetaAudioCapture()
        do {
            try missing.start(targetUid: "unavailable-fixture-port")
            throw Failure.assertion("missing input must refuse")
        } catch {
            try require((error as NSError).code == 3)
        }
        try clean(missing)
        try require(RayBanAudioProbe.activations == 0 && RayBanAudioProbe.deactivations == 0)
        AVAudioSession.sharedInstance().availableInputs = [AVAudioSessionPortDescription()]
        try retry(missing)
        print("Ray-Ban native capture: 8 failure/retry scenarios passed")
    }
}
