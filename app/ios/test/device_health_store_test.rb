require 'minitest/autorun'
require 'tmpdir'
require 'open3'
class DeviceHealthStoreTest < Minitest::Test
  def test_persisted_session_restart_consent_and_sign_out
    Dir.mktmpdir('device-health-store') do |dir|
      root = File.expand_path('..', __dir__)
      binary = File.join(dir, 'test')
      output, status = Open3.capture2e('swiftc', File.join(root, 'Runner/SafeFoundationSinks.swift'), File.join(root, 'Runner/Ble/OmiDeviceHealthStore.swift'), File.join(__dir__, 'device_health_store_test.swift'), '-o', binary)
      assert status.success?, output
      output, status = Open3.capture2e(binary)
      assert status.success?, output
    end
  end
  def test_manual_and_callback_persistence_precedes_cleanup
    root = File.expand_path('..', __dir__)
    source = File.read(File.join(root, 'Runner/Ble/OmiBleManager.swift'))
    manual = source.split('func disconnectPeripheral(uuid: String) {').last.split('func disconnectAllPeripherals').first
    assert_operator manual.index('persistDisconnectEvent'), :<, manual.index('setCaptureAuthorized')
    callback = source.split('didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {').last.split('func peripheral(').first
    assert_operator callback.index('persistDisconnectEvent'), :<, callback.index('cleanupPeripheral')
  end
end
