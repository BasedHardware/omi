import XCTest

@testable import Omi_Computer

private final class PowerProbeCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0

    func next() -> Int {
        lock.withLock {
            count += 1
            return count
        }
    }
}

@MainActor
final class PowerMonitorTests: XCTestCase {

    func testStalePowerProbeCannotOverwriteNewerPowerState() async {
        let probeCounter = PowerProbeCounter()
        let firstChangeStarted = DispatchSemaphore(value: 0)
        let secondChangeStarted = DispatchSemaphore(value: 0)
        let releaseFirstChange = DispatchSemaphore(value: 0)
        let releaseSecondChange = DispatchSemaphore(value: 0)

        let monitor = PowerMonitor(
            batteryStateProbe: {
                let call = probeCounter.next()

                switch call {
                case 1:
                    return false
                case 2:
                    firstChangeStarted.signal()
                    _ = releaseFirstChange.wait(timeout: .now() + 2)
                    return false
                default:
                    secondChangeStarted.signal()
                    _ = releaseSecondChange.wait(timeout: .now() + 2)
                    return true
                }
            },
            startMonitoring: false
        )
        var changes: [Bool] = []
        var acReconnects = 0
        let powerChangeApplied = expectation(description: "latest power change applied")
        let unexpectedACReconnect = DispatchSemaphore(value: 0)
        monitor.onPowerSourceChanged = {
            changes.append($0)
            powerChangeApplied.fulfill()
        }
        monitor.onACReconnected = {
            acReconnects += 1
            unexpectedACReconnect.signal()
        }

        monitor.handlePowerSourceChanged()
        XCTAssertEqual(firstChangeStarted.wait(timeout: .now() + 2), .success)
        monitor.handlePowerSourceChanged()
        XCTAssertEqual(secondChangeStarted.wait(timeout: .now() + 2), .success)

        releaseSecondChange.signal()
        await fulfillment(of: [powerChangeApplied], timeout: 2)
        releaseFirstChange.signal()
        await Task.yield()

        XCTAssertTrue(monitor.isOnBattery)
        XCTAssertEqual(changes, [true])
        XCTAssertEqual(acReconnects, 0)
        XCTAssertEqual(unexpectedACReconnect.wait(timeout: .now()), .timedOut)
    }
}
