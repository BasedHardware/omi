# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

# The on-device live notes policy (pure Swift, run on the host) and the plugin
# itself type-checked against the real iOS FoundationModels SDK with a minimal
# Flutter stand-in, so API drift fails here rather than in an archive. The
# bounded shape is the point: at most 4 bullets of at most 12 words, whatever
# the model returns; nothing about the prompt or the bullets is ever logged.
class LivePreviewNotesPluginTest < Minitest::Test
  RUNNER = File.expand_path('../Runner', __dir__)
  PLUGIN = File.join(RUNNER, 'LivePreviewNotesPlugin.swift')

  def test_clamp_bounds_the_schema_and_never_empties_in
    Dir.mktmpdir('omi-live-preview-notes') do |directory|
      stub = File.join(directory, 'Flutter.swift')
      File.write(stub, FLUTTER_STUB)
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'live-preview-notes-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct Harness {
            static func main() {
                if #available(macOS 26, *) {
                  let policy = LivePreviewNotesPolicy.self
                  precondition(policy.maxBullets == 4)
                  precondition(policy.maxBulletWords == 12)
                  // Six long bullets clamp to four twelve-word bullets.
                  let clamped = policy.clamp((0..<6).map { i in (0..<20).map { "w\\(i)-\\($0)" }.joined(separator: " ") })
                  precondition(clamped.count == 4, "clamped to \\(clamped.count)")
                  for bullet in clamped { precondition(bullet.split(separator: " ").count == 12) }
                  // Empties and whitespace drop out.
                  precondition(policy.clamp(["   ", "", "ok"]) == ["ok"])
                  precondition(policy.clamp([]) == [])
                  precondition(policy.clamp(["one\\ntwo\\tthree"]) == ["one two three"])
                  precondition(policy.boundedInput(String(repeating: "word ", count: 2000)).count <= policy.maxInputCharacters)
                  precondition(policy.boundedInput(String(repeating: "x", count: 20000)).count == policy.maxInputCharacters)
                  // Keep the same unspaced-script and mixed-script budgets as Dart.
                  for unit in ["漢字", "かな", "カナ", "한글", "ภาษา", "ที่นี่", "𠀀𠀁"] {
                    let long = String(repeating: unit, count: 1601)
                    let bullet = policy.clamp([long])[0]
                    precondition(policy.wordRanges(bullet).count == 12)
                    precondition(bullet.count == 24)
                    precondition(long.hasPrefix(bullet))
                    let input = policy.boundedInput(long)
                    precondition(policy.wordRanges(input).count == 1500)
                    precondition(input.count == 3000)
                    precondition(long.hasSuffix(input))
                  }
                  precondition(policy.wordRanges("hello漢字かなworld ภาษา").count == 6)
                  let mixed = policy.clamp(["hello" + String(repeating: "漢字", count: 30) + "world"])[0]
                  precondition(mixed == "hello" + String(repeating: "漢字", count: 11))
                  precondition(policy.instructions.contains("invented speaker labels"))
                  // The prompt stays inside AFM's shared prompt+completion budget.
                  precondition(!policy.instructions.isEmpty)
                  print("live preview notes: bounds and clamp passed")
                } else {
                  print("live preview notes: AFM unavailable on this host; bounds constants only")
                }
            }
        }
      SWIFT
      stdout, stderr, status = Open3.capture3('xcrun', 'swiftc', '-parse-as-library', stub, '-emit-module',
                                              '-module-name', 'Flutter',
                                              '-emit-module-path', File.join(directory, 'Flutter.swiftmodule'),
                                              '-emit-library', '-o', File.join(directory, 'libFlutter.dylib'))
      assert status.success?, "stub module failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3('xcrun', 'swiftc', '-parse-as-library', PLUGIN, harness,
                                              '-I', directory, '-L', directory, '-lFlutter', '-o', binary)
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3({ 'DYLD_LIBRARY_PATH' => directory }, binary)
      assert status.success?, "policy behavior failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_plugin_type_checks_against_the_ios_sdk
    sdk, _, status = Open3.capture3('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
    skip 'iOS simulator SDK unavailable' unless status.success?
    sdk = sdk.strip
    Dir.mktmpdir('omi-live-preview-notes-ios') do |directory|
      stub = File.join(directory, 'Flutter.swift')
      File.write(stub, FLUTTER_STUB)
      target = 'arm64-apple-ios15.1-simulator'
      stdout, stderr, status = Open3.capture3('xcrun', 'swiftc', '-emit-module', '-module-name', 'Flutter',
                                              '-parse-as-library', '-sdk', sdk, '-target', target, stub,
                                              '-emit-module-path', File.join(directory, 'Flutter.swiftmodule'))
      assert status.success?, "stub module failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3('xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
                                              '-target', target, '-I', directory, PLUGIN)
      assert status.success?, "plugin type-check failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_plugin_is_registered_bounded_and_text_free
    delegate = File.read(File.join(RUNNER, 'AppDelegate.swift'))
    assert_includes delegate, 'private var livePreviewNotesPlugin: LivePreviewNotesPlugin?'
    assert_includes delegate, 'livePreviewNotesPlugin = LivePreviewNotesPlugin(messenger: messenger)'
    project = File.read(File.expand_path('../Runner.xcodeproj/project.pbxproj', __dir__))
    assert_equal 2, project.scan(%r{/\* LivePreviewNotesPlugin\.swift in Sources \*/ = \{isa = PBXBuildFile}).length,
                 'must compile in both app targets'
    plugin = File.read(PLUGIN)
    # The channel and privacy refutes look at code only: doc comments may name
    # the channels this one deliberately stays separate from.
    code = plugin.lines.reject { |line| line.strip.start_with?('///') }.join
    assert_includes plugin, '"com.omi/live_preview_notes"'
    assert_includes code, 'maximumElements: maxBullets', 'the schema enforces maxItems at generation time'
    assert_includes code, 'SystemLanguageModel.default.availability == .available', 'AFM availability is checked'
    assert_includes code, 'code: "UNAVAILABLE"', 'unavailability reaches Dart as a typed error'
    assert_includes code, 'code: "BUSY"', 'a busy draft is dropped, reported to Dart'
    assert_includes code, 'Task.detached', 'generation runs off the main thread'
    assert_includes code, 'type(of: error)', 'failures carry the error type only'
    refute_includes code, 'NSLog', 'no preview or notes text is ever logged'
    refute_includes code, 'URLSession', 'the notes never leave the phone'
    refute_includes code, 'FileManager', 'the notes are never written anywhere'
    refute_includes code, 'UserDefaults', 'the notes are never stored'
    refute_includes code, 'com.omi/on_device', 'must not couple to the single-flight overflow channel'
    refute_includes code, '"com.omi/live_preview"', 'must not share the preview engine channel'
  end

  FLUTTER_STUB = <<~SWIFT
    import Foundation
    public typealias FlutterResult = (Any?) -> Void
    public let FlutterMethodNotImplemented: NSObject = NSObject()
    open class FlutterMethodCall: NSObject { public var method: String = ""; public var arguments: Any? }
    open class FlutterError: NSObject { public init(code: String, message: String?, details: Any?) {} }
    public protocol FlutterBinaryMessenger: AnyObject {}
    open class FlutterMethodChannel: NSObject {
      public init(name: String, binaryMessenger: FlutterBinaryMessenger) {}
      public func setMethodCallHandler(_ handler: ((FlutterMethodCall, @escaping FlutterResult) -> Void)?) {}
    }
  SWIFT
end
