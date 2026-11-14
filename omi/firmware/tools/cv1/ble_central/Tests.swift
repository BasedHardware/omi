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

        for command in [Command.scan, .session, .audio, .imageState, .imageUpload] {
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
        try smpChecks()
        print("PASS: \(checks) pure Swift checks; no CoreBluetooth linked or initialized")
    }
    static func mustThrow(_ message: String, _ action: () throws -> Void) {
        do { try action(); fatalError(message) } catch { checks += 1 }
    }
    static func syntheticImage(protected: Bool = false) -> Data {
        var b = [UInt8](repeating: 0, count: 32)
        b.replaceSubrange(0..<4, with: [0x3d, 0xb8, 0xf3, 0x96])
        b[8] = 32; b[10] = protected ? 8 : 0; b[12] = 4
        b += [1, 2, 3, 4]
        if protected { b += [8, 0x69, 8, 0, 0x50, 0, 0, 0] }
        b += [7, 0x69, 40, 0, 0x10, 0, 32, 0] + Array(UInt8(0)..<UInt8(32))
        return Data(b)
    }
    static func smpChecks() throws {
        let h = SMPHeader(op: 2, length: 0x1234, group: 0x0102, sequence: 0xfe, id: 1)
        check(h.encoded() == Data([0x0a, 0, 0x12, 0x34, 1, 2, 0xfe, 1]), "SMP v2 header big endian")
        let decodedHeader = try SMPHeader.decode(h.encoded())
        check(decodedHeader == h, "SMP header decode")
        for bad in [Data(), Data([0, 0, 0, 0, 0, 1, 0, 0]), Data([0x08, 1, 0, 0, 0, 1, 0, 0]), Data([0x10, 0, 0, 0, 0, 1, 0, 0])] {
            mustThrow("Accepted invalid header") { _ = try SMPHeader.decode(bad) }
        }
        let hash = Data(UInt8(0)..<UInt8(32))
        let state: CBOR = .map(["images": .array([.map([
            "image": .uint(0), "slot": .uint(1), "version": .text("1.2.3.4"), "hash": .bytes(hash),
            "bootable": .bool(true), "pending": .bool(true), "confirmed": .bool(false),
            "active": .bool(false), "permanent": .bool(false),
        ])]), "splitStatus": .uint(0)])
        for v in [state, .map(["rc": .negative(-2)]), .map(["err": .map(["group": .uint(1), "rc": .uint(7)])]),
                  .map(["off": .uint(65536)]), .map(["bootloader": .text("MCUboot")]), .map(["r": .text("echo")]),
                  .array([.uint(23), .uint(24), .uint(255), .uint(256), .uint(65535), .uint(UInt64.max), .negative(Int64.min), .text("é"), .bytes(Data())])] {
            let decoded = try CBOR.decode(v.encoded())
            check(decoded == v, "McuMgr-shaped CBOR round trip")
        }
        // Zephyr's zcbor commonly emits indefinite containers, including nested image lists.
        let indefinite = Data([0xbf]) + CBOR.text("images").encoded() + Data([0x9f, 0xbf])
            + CBOR.text("slot").encoded() + Data([1, 0xff, 0xff, 0xff])
        let decodedIndefinite = try CBOR.decode(indefinite)
        check(decodedIndefinite == .map(["images": .array([.map(["slot": .uint(1)])])]), "Indefinite map/array response")
        for bad in [Data([0xbf]), Data([0x61, 0xff]), Data([0xa1, 0x61, 0x78]), Data([0x80, 0]), Data([0x5b, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff]), Data([0xa2, 0x61, 0x61, 0, 0x61, 0x61, 1])] {
            mustThrow("Accepted malformed CBOR") { _ = try CBOR.decode(bad) }
        }
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(state)) as! [String: Any]
        let slots = json["images"] as! [[String: Any]]
        check(slots[0]["hash"] as? String == hex(hash) && slots[0]["pending"] as? Bool == true, "Receipt retains hex hash and flags")
        for protected in [false, true] {
            let parsedHash = try imageHash(syntheticImage(protected: protected))
            check(parsedHash == hash, "Parse MCUboot SHA256 with optional protected TLVs")
        }
        for size in 0..<syntheticImage().count {
            mustThrow("Accepted truncated image") { _ = try imageHash(syntheticImage().prefix(size)) }
        }
        var badImage = syntheticImage(); badImage[40] = 0x11
        mustThrow("Accepted missing SHA256") { _ = try imageHash(badImage) }
        badImage = syntheticImage(); badImage[42] = 31
        mustThrow("Accepted short SHA256") { _ = try imageHash(badImage) }
        let image = try UploadImage(data: syntheticImage() + Data(repeating: 0xff, count: 12000))
        for maximum in [20, 64, 244, 247, 512, 2475, 3000] {
            for offset in [0, 24, 256, image.data.count - 1] {
                let chunk = try uploadChunk(image: image, sha: hash, offset: offset, maximumWrite: maximum)
                guard case .bytes(let bytes) = chunk["data"] else { fatalError("Missing chunk data") }
                let total = 8 + chunk.encoded().count
                check(total <= 2475 && !bytes.isEmpty, "Chunk fits netbuf including header")
                check(total <= (maximum > 2475 ? 2475 : (2475 / maximum) * maximum), "Chunk respects write-sized reassembly budget")
                check(bytes == image.data.subdata(in: offset..<(offset + bytes.count)), "Exact upload bytes")
                check((chunk["sha"] != nil) == (offset == 0) && (chunk["image"] != nil) == (offset == 0), "First chunk metadata only")
            }
        }
        mustThrow("Accepted zero write length") { _ = try uploadChunk(image: image, sha: hash, offset: 0, maximumWrite: 0) }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        let output = root.appendingPathComponent("new.json").path, input = root.appendingPathComponent("image.bin").path
        try image.data.write(to: URL(fileURLWithPath: input))
        let unreadable = root.appendingPathComponent("unreadable.bin")
        try image.data.write(to: unreadable)
        try FileManager.default.setAttributes([.posixPermissions: 0], ofItemAtPath: unreadable.path)
        let base = ["--seconds", "120", "--output", output]
        let upload = ["image-upload"] + base + ["--expect-serial", "synthetic-bench"]
        rejected(upload + ["--mode", "test"])
        rejected(upload + ["--file", input])
        rejected(upload + ["--file", root.appendingPathComponent("absent.bin").path, "--mode", "test"])
        rejected(upload + ["--file", root.path, "--mode", "test"])
        rejected(upload + ["--file", unreadable.path, "--mode", "test"])
        rejected(upload + ["--file", input, "--mode", "other"])
        rejected(upload + ["--file", input, "--mode", "test", "--no-reset", "--no-reset"])
        rejected(["image-state"] + base + ["--mode", "test"])
        rejected(["image-state"] + base + ["--no-reset"])
        check(tryParse(["image-state"] + base + ["--expect-serial", "synthetic-bench"]), "Image-state accepts optional identity")
        rejected(["image-upload"] + base + ["--file", input, "--mode", "test"])
        rejected(["image-upload"] + base + ["--file", input, "--mode", "test", "--expect-serial", ""])
        rejected(["image-upload"] + base + ["--file", input, "--mode", "test", "--expect-serial", "bad\nserial"])
        rejected(["scan"] + base + ["--file", input])
        // 3.0.21 has no DIS serial: a CoreBluetooth peripheral pin can stand in for it.
        let pinID = "8E3B7C1A-2F4D-4B6E-9A1C-0D2E3F405162", otherID = "00000000-0000-0000-0000-000000000000"
        let pinned = try Options.parse(["image-upload"] + base + ["--file", input, "--mode", "confirm", "--expect-peripheral", pinID.lowercased()])
        check(pinned.expectPeripheral == pinID && pinned.expectSerial == nil, "Peripheral pin normalizes and stands in for serial")
        rejected(["image-upload"] + base + ["--file", input, "--mode", "test", "--expect-peripheral", "not-a-uuid"])
        rejected(["image-upload"] + base + ["--file", input, "--mode", "test", "--expect-peripheral", ""])
        rejected(["scan"] + base + ["--expect-peripheral", pinID])
        var pinPlan = SMPPlan(options: pinned, sha: Data())
        mustThrow("Accepted another peripheral") { try pinPlan.beginConnection(discovered: [UUIDs.firmware], peripheral: otherID) }
        check(pinPlan.access == nil, "Wrong peripheral leaves no SMP access")
        try pinPlan.beginConnection(discovered: [UUIDs.firmware], peripheral: pinID)
        try pinPlan.consumeDIS(uuid: UUIDs.firmware, data: Data("3.0.21".utf8))
        check(pinPlan.access?.allowsSMP == true && pinPlan.access?.identity.status == .matched, "Pinned peripheral without serial allows SMP")
        var both = IdentityCheck(expectedSerial: "synthetic-bench", expectedPeripheral: pinID)
        both.connected(to: pinID)
        check(both.status == .pending && !both.allowsContinuation, "Peripheral pin alone does not satisfy an expected serial")
        both.evaluate(serial: "synthetic-other")
        check(both.status == .wrong && both.failureDetail?.contains("serial") == true, "Serial still checked with a pin")
        var wrongPin = IdentityCheck(expectedSerial: nil, expectedPeripheral: pinID)
        wrongPin.connected(to: otherID)
        wrongPin.evaluate(serial: "anything")
        check(wrongPin.status == .wrong && wrongPin.failureDetail?.contains("peripheral") == true, "Wrong peripheral cannot be rescued by later reads")
        let options = try Options.parse(upload + ["--file", input, "--mode", "test"])
        try gateChecks(options: options)
        try gateChecks(options: Options.parse(["image-state"] + base + ["--expect-serial", "synthetic-bench"]))
        for mode in ["test", "confirm"] {
            for noReset in [false, true] {
                let opts = try Options.parse(upload + ["--file", input, "--mode", mode] + (noReset ? ["--no-reset"] : []))
                var plan = SMPPlan(options: opts, sha: hash)
                try authorizeSMP(&plan)
                var names: [String] = [], mark: CBOR?
                while let request = try plan.request(maximumWrite: 244) {
                    names.append(request.name)
                    var body: CBOR = .map([:])
                    if plan.step == .upload {
                        guard case .bytes(let bytes) = request.body["data"] else { fatalError("Missing data") }
                        body = .map(["off": .uint(UInt64(plan.offset + bytes.count))])
                    }
                    if plan.step == .mark { mark = request.body }
                    let response = SMPHeader(op: request.header.op + 1, length: UInt16(body.encoded().count), group: request.header.group, sequence: request.header.sequence, id: request.header.id).encoded() + body.encoded()
                    let decoded = try request.response(response)
                    try request.checkError(decoded)
                    // Every byte boundary, including a split header, must reassemble exactly once.
                    for split in 1..<response.count {
                        var receiver = SMPReassembler()
                        let first = try receiver.consume(response.prefix(split))
                        let second = try receiver.consume(response.suffix(response.count - split))
                        check(first == nil && second == response, "Fragmented SMP response")
                    }
                    let wasReset = plan.step == .reset
                    try plan.accept(decoded)
                    if wasReset {
                        mustThrow("Reset must revoke SMP access") { _ = try plan.request(maximumWrite: 244) }
                        try authorizeSMP(&plan)
                    }
                }
                check(names.first == "initial-image-state" && names.contains("marked-image-state"), "State before upload and after mark")
                check(names.contains("reset") == !noReset && names.contains("post-reset-image-state") == !noReset, "Reset followed by state observation unless suppressed")
                check(mark?["hash"] == .bytes(image.hash) && mark?["confirm"] == .bool(mode == "confirm"), "Mark uses TLV hash and explicit mode")
            }
        }
        var plan = SMPPlan(options: options, sha: hash)
        try authorizeSMP(&plan)
        let request = try plan.request(maximumWrite: 244)!
        for body: CBOR in [.map(["rc": .negative(-1)]), .map(["err": .map(["group": .uint(1), "rc": .uint(9)])])] {
            do { try request.checkError(body); fatalError("Accepted SMP error") }
            catch { check(String(describing: error).contains("group=1 id=0 rc="), "Failure detail identifies request and rc") }
        }
        try request.checkError(.map(["rc": .uint(0)]))
        mustThrow("Accepted mismatched response") { _ = try request.response(h.encoded()) }
        try plan.accept(.map([:]))
        mustThrow("Accepted stalled offset") { try plan.accept(.map(["off": .uint(0)])) }
        mustThrow("Accepted missing offset") { try plan.accept(.map([:])) }
        mustThrow("Accepted unbounded offset") { try plan.accept(.map(["off": .uint(UInt64.max)])) }
        try plan.accept(.map(["off": .uint(10)]))
        let resumed = try plan.request(maximumWrite: 244)!
        check(resumed.body["off"] == .uint(10), "Next chunk uses server offset")
        var statePlan = SMPPlan(options: try Options.parse(["image-state"] + base), sha: Data())
        mustThrow("Ungated image-state request") { _ = try statePlan.request(maximumWrite: 20) }
        try statePlan.beginConnection(discovered: [UUIDs.firmware])
        mustThrow("Firmware must precede unverified image-state") { _ = try statePlan.request(maximumWrite: 20) }
        try statePlan.consumeDIS(uuid: UUIDs.firmware, data: Data("synthetic-1".utf8))
        check(statePlan.access?.identity.status == .notRequested && statePlan.access?.allowsSMP == true, "Optional image-state identity allows missing serial after firmware")
        var optionalPlan = SMPPlan(options: try Options.parse(["image-state"] + base), sha: Data())
        try optionalPlan.beginConnection(discovered: [UUIDs.firmware, UUIDs.serial])
        try optionalPlan.consumeDIS(uuid: UUIDs.firmware, data: Data("synthetic-1".utf8))
        mustThrow("Skipped available serial without --expect-serial") { _ = try optionalPlan.request(maximumWrite: 20) }
        try optionalPlan.consumeDIS(uuid: UUIDs.serial, data: Data("synthetic-bench".utf8))
        check(optionalPlan.access?.allowsSMP == true && optionalPlan.access?.identity.status == .notRequested, "Optional serial is read without claiming verified identity")
        var stateNames: [String] = []
        while let req = try statePlan.request(maximumWrite: 20) { stateNames.append(req.name); try statePlan.accept(.map([:])) }
        check(stateNames == ["bootloader-info", "initial-image-state", "echo"], "Image-state command order")
        try Data("preserve".utf8).write(to: URL(fileURLWithPath: output))
        rejected(upload + ["--file", input, "--mode", "confirm"])
        rejected(["image-state"] + base)
    }
    static func authorizeSMP(_ plan: inout SMPPlan) throws {
        try plan.beginConnection(discovered: [UUIDs.serial, UUIDs.firmware])
        try plan.consumeDIS(uuid: UUIDs.firmware, data: Data("synthetic-1".utf8))
        try plan.consumeDIS(uuid: UUIDs.serial, data: Data("synthetic-bench".utf8))
    }
    static func gateChecks(options: Options) throws {
        var plan = SMPPlan(options: options, sha: Data(repeating: 0, count: 32))
        mustThrow("Planned SMP before DIS discovery") { _ = try plan.request(maximumWrite: 244) }
        mustThrow("Accepted missing DIS firmware") { try plan.beginConnection(discovered: [UUIDs.serial]) }
        for serial in [nil, Data(), Data([0xff]), Data("synthetic-other".utf8), Data("SYNTHETIC-BENCH".utf8), Data("synthetic-bench ".utf8), Data("synthetic-bench".utf8)] as [Data?] {
            try plan.beginConnection(discovered: serial == nil ? [UUIDs.firmware] : [UUIDs.serial, UUIDs.firmware])
            check(plan.access?.nextRead == UUIDs.firmware && plan.access?.identity.status == .pending, "Firmware is first; identity starts pending")
            check(plan.access?.allowsSMP == false, "No SMP subscription before DIS")
            mustThrow("Planned SMP before firmware") { _ = try plan.request(maximumWrite: 244) }
            if let serial {
                try plan.consumeDIS(uuid: UUIDs.firmware, data: Data("synthetic-1".utf8))
                check(plan.access?.nextRead == UUIDs.serial && plan.access?.allowsSMP == false, "Serial follows firmware before subscription")
                mustThrow("Planned SMP before expected serial") { _ = try plan.request(maximumWrite: 244) }
                if serial == Data("synthetic-bench".utf8) {
                    try plan.consumeDIS(uuid: UUIDs.serial, data: serial)
                    check(plan.access?.identity.status == .matched && plan.access?.allowsSMP == true, "Only matched identity unlocks SMP")
                    let request = try plan.request(maximumWrite: 244)
                    check(request?.header.sequence == 0, "Blocked attempts did not plan a request or advance sequence")
                    check(plan.access?.firmware?.text == "synthetic-1", "DIS firmware retained")
                } else {
                    mustThrow("Accepted wrong, empty or non-UTF-8 serial") { try plan.consumeDIS(uuid: UUIDs.serial, data: serial) }
                    let absent = serial.isEmpty || String(data: serial, encoding: .utf8) == nil
                    check(plan.access?.identity.status == (absent ? .absent : .wrong), "Existing absent/wrong semantics")
                    check(Progress(command: options.command).outcome(.gatt) == .gattFailed, "Identity refusal is gatt_failed")
                    check(plan.access?.allowsSMP == false, "Failed identity forbids subscription")
                    mustThrow("Planned SMP after rejected serial") { _ = try plan.request(maximumWrite: 244) }
                }
            } else {
                mustThrow("Accepted missing expected serial") { try plan.consumeDIS(uuid: UUIDs.firmware, data: Data("synthetic-1".utf8)) }
                check(plan.access?.identity.status == .absent && plan.access?.allowsSMP == false, "Missing serial fails identity before subscription")
                mustThrow("Planned SMP with absent serial") { _ = try plan.request(maximumWrite: 244) }
            }
        }
        plan.endConnection()
        mustThrow("Reused old identity on reconnect") { _ = try plan.request(maximumWrite: 244) }
        try plan.beginConnection(discovered: [UUIDs.firmware, UUIDs.serial])
        mustThrow("Read serial before firmware") { try plan.consumeDIS(uuid: UUIDs.serial, data: Data("synthetic-bench".utf8)) }
        mustThrow("Recovered failed read order without a new connection") { _ = try plan.request(maximumWrite: 244) }
        try plan.beginConnection(discovered: [UUIDs.firmware, UUIDs.serial])
        mustThrow("Accepted non-UTF-8 firmware") { try plan.consumeDIS(uuid: UUIDs.firmware, data: Data([0xff])) }
        mustThrow("Planned SMP without valid firmware") { _ = try plan.request(maximumWrite: 244) }
        var receipt = Receipt(startedAt: "synthetic", requestedSeconds: 1, deadlineSeconds: 1, progress: Progress(command: options.command))
        receipt.postResetFirmware = decodeText(Data("synthetic-2".utf8))
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(receipt)) as! [String: Any]
        check((json["postResetFirmware"] as? [String: Any])?["text"] as? String == "synthetic-2", "Post-reset DIS firmware serialized in receipt")
    }
    static func tryParse(_ args: [String]) -> Bool { (try? Options.parse(args)) != nil }
}
