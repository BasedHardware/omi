# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'
require 'json'

class OmiCapturePresentationTest < Minitest::Test
  ROOT = File.expand_path('..', __dir__)

  def test_presentation_policy_ignores_confirmed_quiet_and_warns_only_on_real_failures
    Dir.mktmpdir('omi-capture-presentation') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'presentation-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct PresentationTest {
            static func main() throws {
                let policy = CapturePresentationPolicy.self

                // Healthy pendant capture is the default and shows nothing: listening
                // (a flowing lease or a confirmed-subscription quiet) and reconnecting
                // transcription never warn.
                for status in ["listening", "recording", "reconnecting", "unverified", "connecting"] {
                    precondition(policy.decide(status: status, source: "pendant", statusAge: 0, battery: nil) == .hidden)
                }
                // A wait inside the grace period stays quiet, whatever the battery says.
                precondition(policy.decide(status: "connecting", source: "pendant",
                                    statusAge: policy.unheardGrace - 1, battery: nil) == .hidden)
                precondition(policy.decide(status: "unverified", source: "pendant",
                                    statusAge: policy.unheardGrace - 1, battery: nil) == .hidden)
                // The same wait past the grace period is a real failure.
                precondition(policy.decide(status: "unverified", source: "pendant",
                                    statusAge: policy.unheardGrace, battery: nil) == .notice(.unheard))
                precondition(policy.decide(status: "connecting", source: "pendant",
                                    statusAge: policy.unheardGrace + 30, battery: nil) == .notice(.unheard))

                // An exhausted recovery (actionRequired) is not a wait: it warns at once.
                precondition(policy.decide(status: "noAudio", source: "pendant", statusAge: 0, battery: nil)
                    == .notice(.unheard))
                precondition(policy.decide(status: "noAudio", source: "pendant", statusAge: 0, battery: 80)
                    == .notice(.unheard))

                // Paused leads, ended hides, a phone recording keeps its card.
                precondition(policy.decide(status: "paused", source: "pendant", statusAge: 0, battery: nil)
                    == .notice(.muted))
                precondition(policy.decide(status: "noAudio", source: "phone", statusAge: 0, battery: nil) == .recording)
                precondition(policy.decide(status: "ended", source: "pendant", statusAge: 0, battery: nil) == .hidden)

                // Battery only when nothing about the audio needs the user.
                precondition(policy.decide(status: "listening", source: "pendant", statusAge: 0, battery: 10)
                    == .notice(.battery))
                precondition(policy.decide(status: "listening", source: "pendant", statusAge: 0, battery: 16) == .hidden)

                print("presentation policy assertions passed")
            }
        }
      SWIFT
      stdout, stderr, status = Open3.capture3(
        'swiftc', '-parse-as-library',
        File.join(ROOT, 'LiveActivity/OmiCapturePresentationPolicy.swift'), harness, '-o', binary,
      )
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "presentation assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_live_activity_sources_typecheck_against_the_ios_sdk
    sdk = Open3.capture3('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path').first.strip
    skip 'iphonesimulator SDK unavailable' if sdk.empty?
    stdout, stderr, status = Open3.capture3(
      'swiftc', '-parse-as-library', '-typecheck',
      '-sdk', sdk, '-target', 'arm64-apple-ios16.1-simulator',
      File.join(ROOT, 'LiveActivity/OmiCapturePresentationPolicy.swift'),
      File.join(ROOT, 'LiveActivity/OmiCaptureAttributes.swift'),
      File.join(ROOT, 'LiveActivity/OmiCaptureIntents.swift'),
      File.join(ROOT, 'BatteryWidget/OmiCaptureLiveActivity.swift'),
    )
    assert status.success?, "live activity typecheck failed:\n#{stdout}\n#{stderr}"
  end

  def test_unheard_notice_strings_exist_in_every_widget_locale
    catalog = JSON.parse(File.binread(File.join(ROOT, 'BatteryWidget/Localizable.xcstrings')))
    strings = catalog.fetch('strings')
    ['No audio from pendant', 'Reconnect', 'Pendant connected, but no audio is reaching your phone'].each do |key|
      localizations = strings.fetch(key).fetch('localizations')
      refute_empty localizations.fetch('en').fetch('stringUnit').fetch('value'), key
      localizations.each do |locale, entry|
        refute_empty entry.fetch('stringUnit').fetch('value'), "#{key} must have a #{locale} translation"
      end
    end
  end
end
