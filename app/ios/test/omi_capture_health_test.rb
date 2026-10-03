# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class OmiCaptureHealthTest < Minitest::Test
  def test_native_ingress_recovery_and_restart_budget
    root = File.expand_path('../Runner/Ble', __dir__)
    Dir.mktmpdir('omi-capture-health') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'capture-health-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct CaptureHealthTest {
            static func main() throws {
                let directory = URL(fileURLWithPath: CommandLine.arguments[1])
                let uuid = "D99C1693-A366-48AD-AEF5-F74A6F248722"
                var disk = OmiCaptureHealthStore.load(uuid, directory: directory)
                var writes = 0
                func launch() -> OmiCaptureHealth {
                    OmiCaptureHealth(record: OmiCaptureHealthStore.load(uuid, directory: directory)) {
                        disk = $0
                        writes += 1
                        return OmiCaptureHealthStore.save($0, uuid: uuid, directory: directory)
                    }
                }
                let first = launch()
                first.ready(fresh: false, now: 0) // cached services; reads are not an input to health
                first.authorize(true, now: 0)
                first.subscribed(true, now: 1)
                precondition(first.phase == .unverified)
                // Replayed ready callbacks cannot reset the 30-second deadline.
                for t in 1...29 {
                    first.ready(fresh: false, now: Double(t))
                    first.subscribed(true, now: Double(t))
                }
                precondition(first.tick(now: 30) == .repairSubscription)
                precondition(disk.spent && !disk.reconnectSpent && writes > 0)
                first.ready(fresh: false, now: 31)
                first.subscribed(true, now: 31)
                first.repairCompleted(success: true, now: 32)
                precondition(first.phase == .repairing)
                // Host dies between stages. Relaunch can finish, but not repeat, the reset.
                let second = launch()
                second.ready(fresh: false, now: 40)
                second.authorize(true, now: 40)
                second.subscribed(true, now: 41)
                precondition(second.tick(now: 70) == .reconnect)
                precondition(disk.reconnectSpent)
                second.disconnected(recovering: true, now: 71)
                second.ready(fresh: true, now: 72)
                second.subscribed(true, now: 73)
                second.reconnectCompleted(success: true, now: 73)
                precondition(second.tick(now: 103) == nil && second.phase == .quiet)
                for i in 1...20 {
                    let relaunched = launch()
                    let t = Double(i * 1000)
                    relaunched.ready(fresh: false, now: t)
                    relaunched.authorize(true, now: t)
                    relaunched.subscribed(true, now: t)
                    precondition(relaunched.tick(now: t + 30) == nil)
                    precondition(relaunched.phase == .quiet)
                    precondition(relaunched.lastAudioAt == nil)
                }

                // Repeated short launches cannot perpetually renew the initial grace period.
                var earlyRecord = OmiCaptureHealth.Record()
                for t in [0.0, 10, 20, 30] {
                    let early = OmiCaptureHealth(record: earlyRecord) { earlyRecord = $0; return true }
                    early.ready(fresh: false, now: t)
                    early.authorize(true, now: t)
                    early.subscribed(true, now: t)
                    precondition(early.tick(now: t) == (t == 30 ? .repairSubscription : nil))
                }

                // A killed or failed reset cannot become quiet success on another cached link.
                for outcome in ["fresh_connection_requested", "fresh_connection_failed"] {
                    let interrupted = OmiCaptureHealth(
                        record: .init(spent: true, reconnectSpent: true, outcome: outcome), persist: { _ in true }
                    )
                    interrupted.ready(fresh: false, now: 0)
                    interrupted.authorize(true, now: 0)
                    interrupted.subscribed(true, now: 1)
                    precondition(interrupted.tick(now: 30) == nil)
                    precondition(interrupted.phase == .actionRequired)
                    interrupted.ready(fresh: true, now: 40) // manual Bluetooth toggle
                    interrupted.subscribed(true, now: 41)
                    precondition(interrupted.tick(now: 70) == nil && interrupted.phase == .quiet)
                    interrupted.ready(fresh: false, now: 80)
                    interrupted.subscribed(true, now: 81)
                    precondition(interrupted.tick(now: 110) == nil && interrupted.phase == .quiet)
                }

                // Fresh confirmed silence (released firmware AAD sleep) costs zero reconnects.
                let quiet = OmiCaptureHealth { _ in true }
                quiet.authorize(true, now: 0)
                quiet.ready(fresh: true, now: 0)
                quiet.subscribed(true, now: 1)
                precondition(quiet.tick(now: 30) == nil && quiet.phase == .quiet)
                precondition(!quiet.record.spent)
                quiet.audio(now: 40)
                precondition(quiet.phase == .flowing)
                precondition(quiet.tick(now: 70) == .repairSubscription)
                quiet.subscribed(false, now: 71) // repair's disable confirmation is not a new episode
                quiet.repairCompleted(success: false, now: 72)
                precondition(quiet.tick(now: 72) == .reconnect)
                quiet.recoveryFailed("timeout", now: 117)
                precondition(quiet.phase == .actionRequired)
                quiet.audio(now: 118) // no confirmed subscription: cannot clear the banner
                precondition(quiet.phase == .actionRequired)
                quiet.subscribed(true, now: 119)
                quiet.audio(now: 120)
                precondition(quiet.phase == .flowing)
                quiet.ready(fresh: false, now: 121)
                precondition(quiet.phase == .unverified && quiet.lastAudioAt == nil)
                precondition(!quiet.subscriptionConfirmed)

                // Durable budget failure refuses all automatic radio work.
                let unwritable = OmiCaptureHealth { _ in false }
                unwritable.authorize(true, now: 0)
                unwritable.ready(fresh: false, now: 0)
                precondition(unwritable.tick(now: 30) == nil)
                precondition(unwritable.phase == .actionRequired)

                // Rearm needs BOTH sustained audio and the six-hour battery cooldown.
                let rearm = launch()
                rearm.authorize(true, now: 100)
                rearm.ready(fresh: true, now: 100)
                rearm.subscribed(true, now: 100)
                for t in stride(from: 100.0, through: 200.0, by: 5) { rearm.audio(now: t) }
                precondition(rearm.record.spent)
                for t in stride(from: 22000.0, through: 22060.0, by: 5) { rearm.audio(now: t) }
                precondition(!rearm.record.spent && !rearm.record.reconnectSpent)

                // Exercise the real session effect owner: silence -> repair -> reconnect.
                var time = 0.0
                var repairDone: ((Bool) -> Void)?
                var reconnects = 0
                var permitted = true
                var snapshots: [[String: Any]] = []
                let session = OmiBleCaptureSession(
                    health: OmiCaptureHealth { _ in true }, now: { time }, permitted: { permitted },
                    repair: { repairDone = $0 }, reconnect: { reconnects += 1; $0(false) },
                    publish: { snapshots.append($0) }
                )
                session.ready(fresh: false)
                session.authorize(true)
                session.subscribed(true)
                time = 30
                session.tick()
                precondition(repairDone != nil && reconnects == 0)
                repairDone?(true)
                time = 40
                session.tick()
                precondition(reconnects == 1 && session.health.phase == .actionRequired)
                precondition(snapshots.contains { $0["phase"] as? String == "repairing" })
                session.authorize(false)
                repairDone?(true) // retired callback cannot revive capture
                session.subscribed(true)
                session.audio()
                precondition(session.health.phase == .inactive)
                permitted = false
                session.authorize(true)
                time = 500
                session.tick()
                precondition(reconnects == 1 && session.health.phase == .inactive)
                session.authorize(false)
                // The real store fails closed on corrupt persisted data.
                try Data("broken".utf8).write(to: OmiCaptureHealthStore.url(uuid, directory: directory)!)
                let corrupt = OmiCaptureHealthStore.load(uuid, directory: directory)
                precondition(corrupt.spent && corrupt.reconnectSpent && corrupt.attemptedAt != nil)
                let again = OmiCaptureHealthStore.load(uuid, directory: directory)
                precondition(again.attemptedAt == corrupt.attemptedAt)
                let healed = OmiCaptureHealth(record: again) { _ in true }
                let afterCooldown = corrupt.attemptedAt! + OmiCaptureHealth.Policy.minimumRecoveryInterval
                healed.ready(fresh: true, now: afterCooldown)
                healed.authorize(true, now: afterCooldown)
                healed.subscribed(true, now: afterCooldown)
                for t in stride(from: afterCooldown, through: afterCooldown + 60, by: 5) { healed.audio(now: t) }
                precondition(!healed.record.spent && !healed.record.reconnectSpent)
                print("native capture health assertions passed")
            }
        }
      SWIFT
      stdout, stderr, status = Open3.capture3(
        'swiftc', '-parse-as-library', File.join(root, 'OmiCaptureHealth.swift'),
        File.join(root, 'OmiBleCaptureSession.swift'), harness, '-o', binary,
      )
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary, directory)
      assert status.success?, "capture assertions failed:\n#{stdout}\n#{stderr}"
    end
  end
end
