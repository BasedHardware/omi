# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

# Regression: a dev-flavor debug build opened from the Home Screen (or relaunched
# by iOS in the background) after `flutter run` disconnected crashed inside
# SwiftAwesomeNotificationsPlugin.register, because AppDelegate registered
# plugins against a FlutterViewController whose engine never came up.
class FlutterLaunchEngineGuardTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  GUARD_SOURCE = File.join(IOS_ROOT, 'Runner', 'FlutterLaunchEngineGuard.swift')

  def test_plugin_registration_requires_a_live_engine
    Dir.mktmpdir('omi-launch-engine-guard') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-launch-engine-guard-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct FlutterLaunchEngineGuardTestHarness {
            static func main() {
                // The storyboard controller exists but FlutterEngine init returned
                // nil (debug JIT refused without tooling): never hand plugins a
                // nil registrar.
                precondition(!FlutterLaunchEngineGuard.canRegisterPlugins(
                    hasFlutterRootViewController: true,
                    hasEngine: false
                ))
                // No Flutter root controller at all (window not built yet).
                precondition(!FlutterLaunchEngineGuard.canRegisterPlugins(
                    hasFlutterRootViewController: false,
                    hasEngine: false
                ))
                // Normal tooled or AOT launch.
                precondition(FlutterLaunchEngineGuard.canRegisterPlugins(
                    hasFlutterRootViewController: true,
                    hasEngine: true
                ))

                let debugNotice = FlutterLaunchEngineGuard.unavailableNotice(
                    debugBuild: true,
                    bundleDisplayName: "Omi Dev"
                )
                precondition(debugNotice.contains("Omi Dev"))
                precondition(debugNotice.contains("flutter run"))
                precondition(debugNotice.contains("OMI_MOBILE_BUILD_MODE=profile"))

                let releaseNotice = FlutterLaunchEngineGuard.unavailableNotice(
                    debugBuild: false,
                    bundleDisplayName: "Omi"
                )
                precondition(releaseNotice.contains("Omi"))
                precondition(!releaseNotice.contains("OMI_MOBILE_BUILD_MODE"))
            }
        }
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        GUARD_SOURCE,
        harness,
        '-o',
        binary,
      )
      assert compile_status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"

      stdout, stderr, run_status = Open3.capture3(binary)
      assert run_status.success?, "guard assertions failed:\n#{stdout}\n#{stderr}"
    end
  end
end
