import Foundation

@main
enum Tests {
    static var checks = 0
    static func check(_ condition: @autoclosure () -> Bool, _ message: String) {
        checks += 1
        if !condition() { fatalError(message) }
    }
    static func rejected(_ args: [String]) {
        do { _ = try Options.parse(args); fatalError("Accepted unsafe arguments: \(args)") }
        catch { checks += 1 }
    }
    static func main() throws {
        let base = ["--seconds", "2", "--output", "receipt.json"]
        let expected = ["--expect-serial", "synthetic-bench"]
        let options = try Options.parse(["audio"] + base + expected)
        check(options.seconds == 2 && options.deadlineSeconds == 34, "Audio bounds")
        check(options.prefix == "Omi" && options.keepAudio == nil, "Safe defaults")
        check(options.expectSerial == "synthetic-bench", "Audio retains expected serial")
        let baselineOptions = try Options.parse(["session"] + base)
        let identifiedOptions = try Options.parse(["session"] + base + expected)
        check(baselineOptions.expectSerial == nil, "Baseline session has no serial requirement")
        check(identifiedOptions.expectSerial == "synthetic-bench", "Session accepts expected serial")
        for value in ["0", "-1", "3.0001", "nan", "inf", "1e999", "garbage"] {
            rejected(["audio", "--seconds", value, "--output", "new.json"] + expected)
        }
        for value in ["0", "121", "nan", "-inf"] {
            rejected(["session", "--seconds", value, "--output", "new.json"])
        }
        check(tryParse(["audio", "--seconds", "3", "--output", "new.json"] + expected), "Allow exactly three seconds")
        rejected([]); rejected(["dfu"] + base); rejected(["scan"] + base + ["--seconds", "1"])
        rejected(["scan"] + base + ["--keep-audio", "new.bin"])
        rejected(["audio"] + base + expected + ["--keep-audio", "./receipt.json"])
        rejected(["audio"] + base)
        rejected(["audio"] + base + ["--expect-serial", ""])
        rejected(["session"] + base + ["--expect-serial"])
        rejected(["session"] + base + ["--expect-serial", "bad\nvalue"])
        rejected(["session"] + base + expected + expected)
        rejected(["scan"] + base + expected)
        rejected(["scan"] + base + ["--name-prefix", ""])
        rejected(["scan"] + base + ["--write", "1"])
        rejected(["scan", "--seconds", "1"])
        rejected(["scan"] + base + ["--output"])
        check(matches(name: "oMi bench", prefix: "Omi"), "Case-insensitive prefix")
        check(!matches(name: "other Omi", prefix: "Omi") && !matches(name: nil, prefix: "Omi"), "Reject unrelated/nameless")

        let baselineReads = try FirstConnectionReads(discovered: [UUIDs.firmware])
        check(baselineReads.ordered == [UUIDs.firmware], "Baseline missing serial still has a valid read plan")
        check(baselineReads.absentOptional == [UUIDs.serial, UUIDs.features, UUIDs.diagnostics, UUIDs.recovery], "Serial absence recorded alongside other optionals")
        let allReads = try FirstConnectionReads(discovered: [UUIDs.recovery, UUIDs.diagnostics, UUIDs.serial, UUIDs.features, UUIDs.firmware])
        check(allReads.ordered == [UUIDs.firmware, UUIDs.serial, UUIDs.features, UUIDs.diagnostics, UUIDs.recovery], "DIS precedes optional reads regardless of discovery order")
        check(allReads.absentOptional.isEmpty, "Present serial not marked absent")
        do { _ = try FirstConnectionReads(discovered: [UUIDs.serial]); fatalError("Accepted absent firmware") }
        catch { checks += 1 }
        var unchecked = IdentityCheck(expectedSerial: nil)
        unchecked.evaluate(serial: nil)
        check(!unchecked.checked && unchecked.status == .notRequested && unchecked.allowsContinuation, "Baseline identity explicitly unchecked")
        for observed in [nil, "", "synthetic-other", "SYNTHETIC-BENCH", "synthetic-bench ", "synthetic-bench"] as [String?] {
            var identity = IdentityCheck(expectedSerial: "synthetic-bench")
            check(!identity.checked && identity.status == .pending && !identity.allowsContinuation, "Pending identity cannot advance")
            identity.evaluate(serial: observed)
            check(identity.checked, "Attempted identity comparison recorded")
            if observed == "synthetic-bench" {
                check(identity.status == .matched && identity.allowsContinuation && identity.failureDetail == nil, "Matching serial allows reconnect/audio")
            } else {
                check(!identity.allowsContinuation, "Absent or wrong serial blocks reconnect/audio")
                check(identity.failureDetail?.contains(observed == nil || observed == "" ? "absent" : "wrong") == true, "Identity failure detail states absent/wrong")
                check(Progress(command: .audio).outcome(.gatt) == .gattFailed, "Identity failures are GATT failures even for audio")
            }
        }

        // Synthetic diagnostics bytes, distinct values at every offset. No device capture/identifier.
        let diagnostic = Data([1, 0x78, 0x56, 0x34, 0x12, 4, 3, 2, 1, 0x74, 0x0e, 1, 0,
                               8, 7, 6, 5, 12, 11, 10, 9, 16, 15, 14, 13])
        let fields = decodeDiagnostics(diagnostic).fields
        check(fields["reset_cause"] == 0x12345678 && fields["uptime_s"] == 0x01020304, "Diagnostic u32 endian")
        check(fields["battery_mv"] == 3700 && fields["charging"] == 1, "Battery offsets")
        check(fields["mic_overrun_count"] == 0x05060708 && fields["ble_tx_drop_count"] == 0x090a0b0c && fields["storage_error_count"] == 0x0d0e0f10, "Counter offsets")
        for length in 0..<25 { check(decodeDiagnostics(diagnostic.prefix(length)).fields.isEmpty, "Reject truncated diagnostics") }
        var unknown = diagnostic; unknown[0] = 2
        check(decodeDiagnostics(unknown).fields.isEmpty && decodeDiagnostics(unknown).rawHex == hex(unknown), "Unknown version raw")
        unknown = diagnostic; unknown[12] = 1
        check(decodeDiagnostics(unknown).fields.isEmpty, "Reserved flags unknown")
        check(decodeDiagnostics(diagnostic + Data([0])).fields.isEmpty, "Oversized diagnostics raw")
        check(decodeFeatures(Data([0x80, 0x05, 0, 0])).fields["bitmask"] == 0x580, "Features endian")
        for length in [0, 1, 3, 5] { check(decodeFeatures(Data(repeating: 0, count: length)).fields.isEmpty, "Unknown features size") }
        check(decodeText(Data([0xff])).text == nil, "Reject invalid DIS UTF-8")

        var audio = AudioStats()
        audio.consume(Data([0xfe, 0xff, 0, 10]))
        audio.consume(Data([0xff, 0xff, 1, 11, 12]))
        audio.consume(Data([0, 0, 0, 13]))
        check(audio.valid && audio.notifications == 3 && audio.frameStarts == 2, "Wrap and fragment boundaries")
        check(audio.bytes == 13 && audio.payloadBytes == 4 && audio.firstSequence == 65534 && audio.lastSequence == 0, "Counts exclude three-byte headers")
        audio.consume(Data([2, 0, 2, 14]))
        check(!audio.valid && audio.sequenceBreaks == 1 && audio.fragmentBreaks == 1, "Gap and fragment loss")
        audio.consume(Data([2, 0, 0, 15]))
        check(audio.sequenceBreaks == 2, "Duplicate sequence")
        for length in 0...3 {
            var short = AudioStats(); short.consume(Data(repeating: 0, count: length))
            check(short.malformed == 1 && !short.valid, "Truncated/empty audio payload")
        }
        var midFrame = AudioStats(); midFrame.consume(Data([1, 0, 2, 1]))
        check(midFrame.valid && midFrame.frameStarts == 0, "First packet may be mid-frame")
        midFrame.consume(Data([2, 0, 1, 1]))
        check(!midFrame.valid, "Fragment regression")
        var fragmentWrap = AudioStats(); fragmentWrap.consume(Data([1, 0, 255, 1])); fragmentWrap.consume(Data([2, 0, 1, 1]))
        check(!fragmentWrap.valid, "No invented fragment wrap")

        for command in [Command.scan, .session, .audio] {
            var progress = Progress(command: command)
            check(progress.outcome(.deadline) == .bluetoothOff, "Adapter never became ready")
            progress.permissionPending = true
            check(progress.outcome(.deadline) == .permissionDenied, "Consent wait bounded")
            progress.permissionPending = false
            progress.phase = .scanning
            check(progress.outcome(.deadline) == .noAdvertisement, "No advertisement stays distinct")
            check(progress.outcome(.permission) == .permissionDenied && progress.outcome(.bluetooth) == .bluetoothOff, "Permission/power priority")
            progress.matched = true; progress.phase = .connecting
            if command != .scan {
                check(progress.outcome(.deadline) == .connectFailed, "Connect deadline")
                progress.phase = .gatt
                check(progress.outcome(.deadline) == .gattFailed, "GATT deadline")
                progress.phase = .reconnecting
                check(progress.outcome(.deadline) == .connectFailed, "Reconnect deadline")
            } else {
                check(progress.outcome(.deadline) == .passed, "Matching scan completes at deadline")
                check(progress.outcome(.interrupted) != .passed, "Interrupted scan cannot pass")
            }
            check(progress.outcome(.connection) == .connectFailed && progress.outcome(.gatt) == .gattFailed, "Explicit failure categories")
        }
        var session = Progress(command: .session); session.matched = true; session.sessionComplete = true
        check(session.outcome(.complete) == .passed, "Completed session")
        var capture = Progress(command: .audio); capture.matched = true; capture.sessionComplete = true; capture.phase = .audio
        check(capture.outcome(.deadline) == .audioFailed && capture.outcome(.complete) == .audioFailed, "No audio cannot pass")
        capture.audio.consume(Data([7, 0, 0, 1])); capture.audioComplete = true
        check(capture.outcome(.complete) == .passed, "Complete capture")
        capture.audio.consume(Data([9, 0, 0, 1]))
        check(capture.outcome(.complete) == .audioFailed, "Sequence breaks fail receipt")
        check(Set(Outcome.allCases.map { $0.rawValue }) == Set(["permission_denied", "bluetooth_off", "no_advertisement", "connect_failed", "gatt_failed", "interrupted", "audio_failed", "passed"]), "Exact outcome vocabulary")
        let receipt = Receipt(startedAt: "synthetic", requestedSeconds: 1, deadlineSeconds: 1, progress: session)
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(receipt)) as! [String: Any]
        check(json["schema"] as? Int == 1 && json["limitations"] != nil, "Receipt serializes with limitations")
        let identityJSON = json["identity"] as! [String: Any]
        check(identityJSON["checked"] as? Bool == false && identityJSON["status"] as? String == "not_requested", "Unchecked identity visible in receipt")
        var checkedReceipt = receipt
        checkedReceipt.identity = IdentityCheck(expectedSerial: "synthetic-bench")
        checkedReceipt.identity.evaluate(serial: "synthetic-bench")
        let checkedJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(checkedReceipt)) as! [String: Any]
        let checkedIdentity = checkedJSON["identity"] as! [String: Any]
        check(checkedIdentity["checked"] as? Bool == true && checkedIdentity["status"] as? String == "matched", "Checked identity visible in receipt")
        print("PASS: \(checks) pure Swift checks; no CoreBluetooth linked or initialized")
    }
    static func tryParse(_ args: [String]) -> Bool { (try? Options.parse(args)) != nil }
}
