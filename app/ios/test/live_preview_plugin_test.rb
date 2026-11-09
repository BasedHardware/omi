# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

# The on-device live preview's engine policy (pure Swift, run on the host) and
# the plugin itself type-checked against the real iOS Speech/AVFAudio SDK with
# a minimal Flutter stand-in, so API drift fails here rather than in an archive.
class LivePreviewPluginTest < Minitest::Test
  RUNNER = File.expand_path('../Runner', __dir__)
  SELECTION = File.join(RUNNER, 'LivePreviewSelection.swift')
  PLUGIN = File.join(RUNNER, 'LivePreviewPlugin.swift')

  def test_engine_order_reasons_and_segment_ids
    Dir.mktmpdir('omi-live-preview-selection') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'live-preview-selection-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct Harness {
            static func main() {
                typealias S = LivePreviewSelection
                // Engine order: SpeechTranscriber, then SFSpeech, never anything else.
                precondition(S.choose(analyzer: .ready, sfSpeech: .ready, bundledInstalled: false).engine == "speech_transcriber")
                let legacy = S.choose(analyzer: .unavailable("locale_asset_missing"), sfSpeech: .ready, bundledInstalled: true)
                precondition(legacy == LivePreviewChoice(engine: "sf_speech", reason: "ok", bundledInstalled: true))
                // iOS < 26: the SFSpeech refusal is the reason.
                let old = S.choose(analyzer: .unavailable("os_too_old"), sfSpeech: .unavailable("speech_permission_denied"), bundledInstalled: false)
                precondition(old == LivePreviewChoice(engine: "none", reason: "speech_permission_denied", bundledInstalled: false))
                // iOS 26+: the analyzer's refusal is the reason; an installed Omi model is reported, not used.
                let none = S.choose(analyzer: .unavailable("locale_asset_missing"), sfSpeech: .unavailable("os_engine_unavailable"), bundledInstalled: true)
                precondition(none == LivePreviewChoice(engine: "none", reason: "locale_asset_missing", bundledInstalled: true))
                // Unknown reasons never leak onto the closed wire set.
                precondition(S.choose(analyzer: .unavailable("weird"), sfSpeech: .unavailable("x"), bundledInstalled: false).reason == "engine_error")

                precondition(S.languageCode("multi", deviceLanguage: "de") == "de")
                precondition(S.languageCode("", deviceLanguage: nil) == "en")
                precondition(S.languageCode("en-US", deviceLanguage: "de") == "en")
                precondition(S.languageCode("pt_BR", deviceLanguage: nil) == "pt")

                // Installed beats supported; the device locale wins among installed; never a download.
                let pick = S.pickLocale(code: "en", installed: ["en-GB", "en-US", "fr-FR"], supported: ["en-AU"], device: "en-US")
                precondition(pick.locale == "en-US" && pick.reason == "ok")
                precondition(S.pickLocale(code: "en", installed: ["en-GB"], supported: [], device: "de-DE").locale == "en-GB")
                let missing = S.pickLocale(code: "de", installed: ["en-US"], supported: ["de-DE"], device: "de-DE")
                precondition(missing.locale == nil && missing.reason == "locale_asset_missing")
                precondition(S.pickLocale(code: "xx", installed: [], supported: ["en-US"], device: "en-US").reason == "locale_unsupported")

                var ids = LivePreviewSegmentIds(prefix: "a")
                precondition(ids.id(isFinal: false) == "a0")
                precondition(ids.id(isFinal: false) == "a0")
                precondition(ids.id(isFinal: true) == "a0")
                precondition(ids.id(isFinal: false) == "a1")
                print("live preview selection: order, reasons, locales and segment ids passed")
            }
        }
      SWIFT
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', SELECTION, harness, '-o', binary)
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "selection behavior failed:\n#{stdout}\n#{stderr}"
    end
  end

  FLUTTER_STUB = <<~SWIFT
    import Foundation
    public typealias FlutterResult = (Any?) -> Void
    public typealias FlutterEventSink = (Any?) -> Void
    public let FlutterMethodNotImplemented: NSObject = NSObject()
    public protocol FlutterBinaryMessenger: AnyObject {}
    open class FlutterMethodCall: NSObject { public var method: String = ""; public var arguments: Any? }
    open class FlutterError: NSObject { public init(code: String, message: String?, details: Any?) {} }
    open class FlutterStandardTypedData: NSObject { public var data: Data = Data() }
    @objc public protocol FlutterStreamHandler {
      func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError?
      func onCancel(withArguments arguments: Any?) -> FlutterError?
    }
    open class FlutterMethodChannel: NSObject {
      public init(name: String, binaryMessenger: FlutterBinaryMessenger) {}
      public func setMethodCallHandler(_ handler: ((FlutterMethodCall, @escaping FlutterResult) -> Void)?) {}
    }
    open class FlutterEventChannel: NSObject {
      public init(name: String, binaryMessenger: FlutterBinaryMessenger) {}
      public func setStreamHandler(_ handler: (NSObjectProtocol & FlutterStreamHandler)?) {}
    }
  SWIFT

  def test_plugin_type_checks_against_the_ios_sdk
    sdk, _, status = Open3.capture3('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
    skip 'iOS simulator SDK unavailable' unless status.success?
    sdk = sdk.strip
    Dir.mktmpdir('omi-live-preview-plugin') do |directory|
      stub = File.join(directory, 'Flutter.swift')
      File.write(stub, FLUTTER_STUB)
      handler = File.join(directory, 'Handler.swift')
      # The plugin reuses AppDelegate's on-device recognizer lookup.
      File.write(handler, "import Speech\nclass SpeechRecognitionHandler: NSObject { " \
                          "static func onDeviceRecognizer(for language: String) -> SFSpeechRecognizer? { nil } }\n")
      target = 'arm64-apple-ios15.1-simulator'
      stdout, stderr, status = Open3.capture3('xcrun', 'swiftc', '-emit-module', '-module-name', 'Flutter',
                                              '-parse-as-library', '-sdk', sdk, '-target', target, stub,
                                              '-emit-module-path', File.join(directory, 'Flutter.swiftmodule'))
      assert status.success?, "stub module failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3('xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
                                              '-target', target, '-I', directory, PLUGIN, SELECTION, handler)
      assert status.success?, "plugin type-check failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_plugin_is_registered_retained_and_built
    delegate = File.read(File.join(RUNNER, 'AppDelegate.swift'))
    assert_includes delegate, 'private var livePreviewPlugin: LivePreviewPlugin?'
    assert_includes delegate, 'livePreviewPlugin = LivePreviewPlugin(messenger: messenger)'
    project = File.read(File.expand_path('../Runner.xcodeproj/project.pbxproj', __dir__))
    %w[LivePreviewPlugin.swift LivePreviewSelection.swift].each do |name|
      assert_equal 2, project.scan(%r{/\* #{Regexp.escape(name)} in Sources \*/ = \{isa = PBXBuildFile}).length,
                   "#{name} must compile in both app targets"
    end
    plugin = File.read(PLUGIN)
    assert_includes plugin, '"com.omi/live_preview"'
    assert_includes plugin, '"com.omi/live_preview/events"'
    refute_includes plugin, 'name: "com.omi/on_device"', 'must not share the single-flight overflow channel'
    refute_includes plugin, 'downloadAndInstall', 'the preview never downloads speech assets'
    refute_includes plugin, 'requestAuthorization', 'the preview never prompts from the capture path'
    assert_includes plugin, 'await analyzer.cancelAndFinishNow()', 'stop replies only after the analyzer let go'
    assert_includes plugin, 'await retired.value', 'start and stop wait for the previous session cleanup'
    assert_includes plugin, '"failure": "engine_error"', 'runtime failures reach Dart with the closed reason'
  end
end
