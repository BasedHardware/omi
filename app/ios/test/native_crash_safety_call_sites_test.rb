# frozen_string_literal: true

require 'minitest/autorun'

class NativeCrashSafetyCallSitesTest < Minitest::Test
  IOS = File.expand_path('..', __dir__)

  def source(path)
    File.read(File.join(IOS, path))
  end

  def test_health_days_are_bounded_before_negation_and_date_arithmetic
    health = source('Runner/AppleHealthService.swift')
    assert_match(/guard \(1\.\.\.365\)\.contains\(days\),\s+let startDate = Calendar\.current\.date\(byAdding: \.day, value: -days/, health)
    assert_match(/invalid_days/, health)
  end

  def test_empty_audio_buffer_list_returns_before_first_buffer_access
    callback = source('Runner/PhoneCalls/OmiRecordingAudioDevice.swift')
    assert_match(/let buf = UnsafeMutableAudioBufferListPointer\(ioData\)\s+guard !buf\.isEmpty else \{ return noErr \}\s+if let data = buf\[0\]\.mData/m, callback)
  end

  def test_siri_due_date_conversion_is_checked
    snapshot = source('Runner/SiriIntegration/SiriSnapshotStore.swift')
    assert_match(/dueAt\.flatMap \{ CheckedIntegerConversion\.int64\(/, snapshot)
  end

  def test_snapshot_rebuild_uses_deterministic_duplicate_handling
    snapshot = source('Runner/SiriIntegration/SiriSnapshotStore.swift')
    assert_equal 2, snapshot.scan(/Dictionary\(\w+\.map \{ \(\$0\.id, \$0\) \}, uniquingKeysWith: \{ first, _ in first \}\)/).length
  end

  def test_optional_plugin_registrar_is_reported_without_unwrapping
    app_delegate = source('Runner/AppDelegate.swift')
    assert_match(/if let registrar = engineBridge\.pluginRegistry\.registrar\(forPlugin: "OmiPhoneCallsPlugin"\)/, app_delegate)
    refute_match(/registrar\(forPlugin: "OmiPhoneCallsPlugin"\)!/, app_delegate)
  end

  def test_siri_probe_runtime_optionals_have_fallbacks
    probe = source('Runner/SiriIntegration/SiriDebugProbe.swift')
    refute_match(/UserDefaults\(suiteName: "group\.com\.friend-app-with-wearable\.ios12"\)!/, probe)
    refute_match(/class_conformsToProtocol\(quickActionsClass!, sceneProtocol!\)/, probe)
    refute_match(/URL\(string: rawURL\)!/, probe)
    refute_match(/currentConfig\(\)!|currentUser!/, probe)
    refute_match(/request\.url!|HTTPURLResponse\([^\n]*\)!/, probe)
  end
end
