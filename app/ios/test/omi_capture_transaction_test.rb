# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'
require 'json'

class OmiCaptureTransactionTest < Minitest::Test
  def test_terminal_recovery_storage_progress_and_cross_language_incident_trace
    root = File.expand_path('../Runner/Ble', __dir__)
    manager = File.read(File.join(root, 'OmiBleManager.swift'))
    assert_includes manager, 'captureSession(uuid).reconnectTransaction('
    assert_includes manager, 'recovery.settleResume(true)'
    assert_includes manager, 'captureSession(uuid).ready(fresh: fresh, recovery: captureReconnects[uuid])'
    refute_includes manager, 'resumeAfterCaptureReset'
    refute_includes manager, 'captureLinkTransfers'
    fixture = File.expand_path('../../test/fixtures/capture_recovery_trace.json', __dir__)
    Dir.mktmpdir('omi-capture-transaction') do |directory|
      binary = File.join(directory, 'transaction')
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library',
        File.join(root, 'OmiCaptureHealth.swift'), File.join(root, 'OmiBleCaptureSession.swift'),
        File.join(__dir__, 'omi_capture_transaction_test.swift'), '-o', binary)
      assert status.success?, "compile failed:
#{stdout}
#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "transaction failed:
#{stdout}
#{stderr}"
      trace = JSON.parse(stdout)
      File.write(fixture, JSON.pretty_generate(trace) + "
") if ENV['UPDATE_CAPTURE_TRACE'] == '1'
      assert_equal JSON.parse(File.read(fixture)), trace, 'native recovery contract changed; review Dart replay'
      assert_equal 1, trace.count { |row| row['event'] == 'connect' }
    end
  end
end
