# frozen_string_literal: true

require "minitest/autorun"

class BleGattProjectGraphTest < Minitest::Test
  PROJECT = File.expand_path("../Runner.xcodeproj/project.pbxproj", __dir__)
  MANAGER = File.expand_path("../Runner/Ble/OmiBleManager.swift", __dir__)
  SCHEDULER = File.expand_path("../Runner/Ble/BleGattOperationScheduler.swift", __dir__)
  ROUTER = File.expand_path("../Runner/Ble/BleNotificationRouter.swift", __dir__)
  FILE_REF = "C0D3B1E00000000000000001"
  RUNNER_BUILD_REF = "C0D3B1E00000000000000002"
  RAYBAN_BUILD_REF = "C0D3B1E00000000000000003"
  ROUTER_FILE_REF = "C0D3B1E10000000000000001"
  ROUTER_RUNNER_BUILD_REF = "C0D3B1E10000000000000002"
  ROUTER_RAYBAN_BUILD_REF = "C0D3B1E10000000000000003"

  def setup
    @project = File.read(PROJECT)
    @manager = File.read(MANAGER)
    @scheduler = File.read(SCHEDULER)
    @router = File.read(ROUTER)
  end

  def test_scheduler_has_one_file_reference_and_two_target_build_references
    assert_equal 1, @project.scan(/#{FILE_REF} .* = \{isa = PBXFileReference;/).length
    assert_equal 2, @project.scan(/fileRef = #{FILE_REF}/).length
    assert_equal 2, @project.scan(/#{RUNNER_BUILD_REF} \/\* BleGattOperationScheduler\.swift in Sources \*\//).length
    assert_equal 2, @project.scan(/#{RAYBAN_BUILD_REF} \/\* BleGattOperationScheduler\.swift in Sources \*\//).length
  end

  def test_scheduler_is_compiled_by_both_phone_targets
    runner_sources = source_phase("97C146EA1CF9000F007C117D")
    rayban_sources = source_phase("A39438EBCDB909113855E505")

    assert_includes runner_sources, RUNNER_BUILD_REF
    refute_includes runner_sources, RAYBAN_BUILD_REF
    assert_includes rayban_sources, RAYBAN_BUILD_REF
    refute_includes rayban_sources, RUNNER_BUILD_REF
  end

  def test_notification_router_is_compiled_by_both_phone_targets
    assert_equal 1, @project.scan(/#{ROUTER_FILE_REF} .* = \{isa = PBXFileReference;/).length
    assert_equal 2, @project.scan(/fileRef = #{ROUTER_FILE_REF}/).length

    runner_sources = source_phase("97C146EA1CF9000F007C117D")
    rayban_sources = source_phase("A39438EBCDB909113855E505")
    assert_includes runner_sources, ROUTER_RUNNER_BUILD_REF
    refute_includes runner_sources, ROUTER_RAYBAN_BUILD_REF
    assert_includes rayban_sources, ROUTER_RAYBAN_BUILD_REF
    refute_includes rayban_sources, ROUTER_RUNNER_BUILD_REF
  end

  # Static integration tripwires complement the behavioral scheduler tests.
  # They make sure the manager does not bypass the tested ownership boundary.
  def test_manager_does_not_restore_characteristic_keyed_completion_ownership
    refute_includes @manager, "readCompletions"
    refute_includes @manager, "writeCompletions"
    assert_includes @manager, "operationScheduler(for:"
    assert_includes @manager, "completeExpected("
  end

  def test_manager_does_not_restore_rssi_keepalive_or_fixed_reconnect_spin
    refute_includes @manager, "startRssiKeepAlive"
    refute_includes @manager, ".milliseconds(200)"
    assert_includes @manager, "BleReconnectLifecycle"
    assert_includes @manager, "nextReconnectDelay()"
    assert_includes @manager, "deviceReady()"
    assert_includes @scheduler, "BleReconnectBackoff.delay"
  end

  def test_manager_routes_before_native_batch_policy
    assert_includes @manager, "BleNotificationRouter.route("
    assert_includes @router, "case limitlessFlash"
    assert_includes @router, "case batchAudio"
  end

  private

  def source_phase(identifier)
    match = @project.match(
      /^\t\t#{identifier} \/\* Sources \*\/ = \{\n(?<body>.*?)^\t\t\};$/m
    )
    refute_nil match, "missing PBXSourcesBuildPhase #{identifier}"
    match[:body]
  end
end
