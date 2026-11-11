# frozen_string_literal: true

require 'json'
require 'minitest/autorun'
require 'open3'
require 'rbconfig'
require 'tmpdir'

class RayBanDatPluginBoundaryTest < Minitest::Test
  HELPER = File.expand_path('../rayban_dat_plugin_boundary.rb', __dir__)
  PODFILE = File.expand_path('../Podfile', __dir__)
  PODFILE_LOCK = File.expand_path('../Podfile.lock', __dir__)

  MCUMGR_IMPORT_BLOCK = <<~OBJC.freeze
    #if __has_include(<mcumgr_flutter/McumgrFlutterPlugin.h>)
    #import <mcumgr_flutter/McumgrFlutterPlugin.h>
    #else
    @import mcumgr_flutter;
    #endif

  OBJC

  MCUMGR_REGISTRATION =
    '  [McumgrFlutterPlugin registerWithRegistrar:[registry registrarForPlugin:@"McumgrFlutterPlugin"]];'

  def test_prepare_is_a_byte_for_byte_no_op_without_the_exact_dat_flag
    [nil, '', '0', 'true', '01'].each do |flag|
      with_fixture do |app_root, metadata_path, registrant_path|
        metadata_before = File.binread(metadata_path)
        registrant_before = File.binread(registrant_path)

        stdout, stderr, status = run_helper('prepare', app_root, flag: flag)

        assert status.success?, "flag=#{flag.inspect}\nstdout:\n#{stdout}\nstderr:\n#{stderr}"
        assert_equal metadata_before, File.binread(metadata_path), "flag=#{flag.inspect} changed plugin metadata"
        assert_equal registrant_before, File.binread(registrant_path), "flag=#{flag.inspect} changed registrant"
        refute Dir.exist?(backup_dir(app_root)), "flag=#{flag.inspect} created a backup"
      end
    end
  end

  def test_prepare_removes_only_the_ios_mcumgr_plugin_and_its_registration
    with_fixture do |app_root, metadata_path, registrant_path|
      original_metadata = JSON.parse(File.binread(metadata_path))

      stdout, stderr, status = run_helper('prepare', app_root, flag: '1')

      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      transformed_metadata = JSON.parse(File.binread(metadata_path))
      assert_equal ['other_plugin'], transformed_metadata.fetch('plugins').fetch('ios').map { |plugin| plugin.fetch('name') }
      assert_equal original_metadata.fetch('plugins').fetch('android'),
                   transformed_metadata.fetch('plugins').fetch('android')
      assert_equal original_metadata.fetch('dependencyGraph'), transformed_metadata.fetch('dependencyGraph')

      transformed_registrant = File.binread(registrant_path)
      refute_includes transformed_registrant, 'mcumgr_flutter'
      refute_includes transformed_registrant, 'McumgrFlutterPlugin'
      assert_includes transformed_registrant, 'OtherPlugin'
      assert Dir.exist?(backup_dir(app_root))
    end
  end

  def test_prepare_is_idempotent_and_restore_recovers_the_exact_original_bytes
    with_fixture do |app_root, metadata_path, registrant_path|
      metadata_before = File.binread(metadata_path)
      registrant_before = File.binread(registrant_path)

      first_stdout, first_stderr, first_status = run_helper('prepare', app_root, flag: '1')
      assert first_status.success?, "stdout:\n#{first_stdout}\nstderr:\n#{first_stderr}"
      metadata_after_first_prepare = File.binread(metadata_path)
      registrant_after_first_prepare = File.binread(registrant_path)

      second_stdout, second_stderr, second_status = run_helper('prepare', app_root, flag: '1')
      assert second_status.success?, "stdout:\n#{second_stdout}\nstderr:\n#{second_stderr}"
      assert_equal metadata_after_first_prepare, File.binread(metadata_path)
      assert_equal registrant_after_first_prepare, File.binread(registrant_path)

      restore_stdout, restore_stderr, restore_status = run_helper('restore', app_root)
      assert restore_status.success?, "stdout:\n#{restore_stdout}\nstderr:\n#{restore_stderr}"
      assert_equal metadata_before, File.binread(metadata_path)
      assert_equal registrant_before, File.binread(registrant_path)
      refute Dir.exist?(backup_dir(app_root))
    end
  end

  def test_prepare_accepts_flutter_regeneration_that_only_changes_date_created
    with_fixture do |app_root, metadata_path, registrant_path|
      metadata_before = File.binread(metadata_path)
      registrant_before = File.binread(registrant_path)

      first_stdout, first_stderr, first_status = run_helper('prepare', app_root, flag: '1')
      assert first_status.success?, "stdout:\n#{first_stdout}\nstderr:\n#{first_stderr}"

      regenerated_metadata = JSON.parse(metadata_before)
      regenerated_metadata['date_created'] = '2026-07-20 00:00:01.000000'
      File.binwrite(metadata_path, JSON.generate(regenerated_metadata))
      File.binwrite(registrant_path, registrant_before)

      second_stdout, second_stderr, second_status = run_helper('prepare', app_root, flag: '1')

      assert second_status.success?, "stdout:\n#{second_stdout}\nstderr:\n#{second_stderr}"
      prepared_metadata = JSON.parse(File.binread(metadata_path))
      assert_equal regenerated_metadata.fetch('date_created'), prepared_metadata.fetch('date_created')
      refute_includes prepared_metadata.fetch('plugins').fetch('ios').map { |plugin| plugin.fetch('name') },
                      'mcumgr_flutter'
      assert_equal registrant_before.gsub(MCUMGR_IMPORT_BLOCK, '').gsub(MCUMGR_REGISTRATION, ''),
                   File.binread(registrant_path)

      restore_stdout, restore_stderr, restore_status = run_helper('restore', app_root)
      assert restore_status.success?, "stdout:\n#{restore_stdout}\nstderr:\n#{restore_stderr}"
      assert_equal metadata_before, File.binread(metadata_path)
      assert_equal registrant_before, File.binread(registrant_path)
    end
  end

  def test_prepare_fails_closed_when_ios_metadata_does_not_have_exactly_one_mcumgr_entry
    [0, 2].each do |count|
      with_fixture(ios_mcumgr_count: count) do |app_root, metadata_path, registrant_path|
        metadata_before = File.binread(metadata_path)
        registrant_before = File.binread(registrant_path)

        _stdout, stderr, status = run_helper('prepare', app_root, flag: '1')

        refute status.success?
        assert_includes stderr, 'expected exactly one mcumgr_flutter iOS plugin entry'
        assert_equal metadata_before, File.binread(metadata_path)
        assert_equal registrant_before, File.binread(registrant_path)
        refute Dir.exist?(backup_dir(app_root))
      end
    end
  end

  def test_prepare_fails_closed_when_the_generated_registration_shape_drifts
    with_fixture(registration_count: 0) do |app_root, metadata_path, registrant_path|
      metadata_before = File.binread(metadata_path)
      registrant_before = File.binread(registrant_path)

      _stdout, stderr, status = run_helper('prepare', app_root, flag: '1')

      refute status.success?
      assert_includes stderr, 'expected exactly one mcumgr_flutter registration call'
      assert_equal metadata_before, File.binread(metadata_path)
      assert_equal registrant_before, File.binread(registrant_path)
      refute Dir.exist?(backup_dir(app_root))
    end
  end

  def test_restore_refuses_to_overwrite_generated_files_changed_after_prepare
    with_fixture do |app_root, metadata_path, _registrant_path|
      stdout, stderr, status = run_helper('prepare', app_root, flag: '1')
      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      File.binwrite(metadata_path, "externally changed\n")

      _restore_stdout, restore_stderr, restore_status = run_helper('restore', app_root)

      refute restore_status.success?
      assert_includes restore_stderr, 'refusing to overwrite changed generated file'
      assert_equal "externally changed\n", File.binread(metadata_path)
      assert Dir.exist?(backup_dir(app_root))
    end
  end

  def test_podfile_resolves_mutually_exclusive_default_and_dat_target_graphs
    podfile = File.read(PODFILE)
    runner_target_index = podfile.index("target 'Runner' do")
    resolution_indexes = podfile.enum_for(:scan, /flutter_install_all_ios_pods/).map { Regexp.last_match.begin(0) }
    prepare_index = podfile.index('RayBanDatPluginBoundary.prepare!')
    dat_flag_index = podfile.index("if ENV['OMI_RAYBAN_DAT'] == '1'")
    dat_target_index = podfile.index("target 'RunnerRayBanDat' do")
    branch_else_index = podfile.index("\nelse\n", dat_target_index)

    refute_nil runner_target_index
    assert_equal 2, resolution_indexes.length, 'both native app targets must have an explicit pod graph'
    refute_nil prepare_index, 'Podfile must invoke the Ray-Ban DAT plugin boundary'
    refute_nil dat_flag_index, 'DAT pod integration must require the exact build flag'
    refute_nil dat_target_index
    refute_nil branch_else_index, 'default and DAT targets must be mutually exclusive branches'
    assert_operator dat_flag_index, :<, prepare_index
    assert_operator prepare_index, :<, dat_target_index
    assert_operator dat_target_index, :<, resolution_indexes.fetch(0)
    assert_operator resolution_indexes.fetch(0), :<, branch_else_index
    assert_operator branch_else_index, :<, runner_target_index
    assert_operator runner_target_index, :<, resolution_indexes.fetch(1)
  end

  def test_committed_default_pod_lock_keeps_mcumgr_and_swiftprotobuf_linkage
    lockfile = File.read(PODFILE_LOCK)
    mcumgr_stanza = lockfile[/^  - mcumgr_flutter \([^\n]+\):\n(?:    - [^\n]+\n)+/]

    refute_nil mcumgr_stanza, 'default Podfile.lock must include the mcumgr_flutter pod'
    assert_includes mcumgr_stanza, 'iOSMcuManagerLibrary'
    assert_includes mcumgr_stanza, 'SwiftProtobuf'
    assert_match(/^  - iOSMcuManagerLibrary \([^\n]+\):/m, lockfile)
    assert_match(/^  - SwiftProtobuf \([^\n]+\)$/m, lockfile)
  end

  private

  def with_fixture(ios_mcumgr_count: 1, registration_count: 1)
    Dir.mktmpdir('rayban-dat-boundary-test') do |app_root|
      ios_dir = File.join(app_root, 'ios')
      runner_dir = File.join(ios_dir, 'Runner')
      FileUtils.mkdir_p(runner_dir)

      metadata_path = File.join(app_root, '.flutter-plugins-dependencies')
      registrant_path = File.join(runner_dir, 'GeneratedPluginRegistrant.m')
      File.binwrite(metadata_path, JSON.generate(plugin_metadata(ios_mcumgr_count)))
      File.binwrite(registrant_path, generated_registrant(registration_count))

      yield app_root, metadata_path, registrant_path
    end
  end

  def plugin_metadata(ios_mcumgr_count)
    ios_plugins = [plugin('other_plugin')]
    ios_mcumgr_count.times { ios_plugins << plugin('mcumgr_flutter') }

    {
      'info' => 'This is a generated file; do not edit or check into version control.',
      'plugins' => {
        'ios' => ios_plugins,
        'android' => [plugin('mcumgr_flutter'), plugin('other_plugin')],
        'macos' => [],
        'linux' => [],
        'windows' => [],
        'web' => [],
      },
      'dependencyGraph' => [
        {'name' => 'mcumgr_flutter', 'dependencies' => []},
        {'name' => 'other_plugin', 'dependencies' => []},
      ],
      'date_created' => '2026-07-20 00:00:00.000000',
      'version' => '3.41.9',
      'swift_package_manager_enabled' => false,
    }
  end

  def plugin(name)
    {
      'name' => name,
      'path' => "/tmp/#{name}",
      'native_build' => true,
      'dependencies' => [],
      'dev_dependency' => false,
    }
  end

  def generated_registrant(registration_count)
    registrations = Array.new(registration_count, MCUMGR_REGISTRATION).join("\n")
    <<~OBJC
      // Generated file. Do not edit.

      #import "GeneratedPluginRegistrant.h"

      #if __has_include(<other_plugin/OtherPlugin.h>)
      #import <other_plugin/OtherPlugin.h>
      #else
      @import other_plugin;
      #endif

      #{MCUMGR_IMPORT_BLOCK}      @implementation GeneratedPluginRegistrant

      + (void)registerWithRegistry:(NSObject<FlutterPluginRegistry>*)registry {
        [OtherPlugin registerWithRegistrar:[registry registrarForPlugin:@"OtherPlugin"]];
      #{registrations}
      }

      @end
    OBJC
  end

  def run_helper(command, app_root, flag: nil)
    env = {'OMI_RAYBAN_DAT' => flag}
    Open3.capture3(env, RbConfig.ruby, HELPER, command, app_root)
  end

  def backup_dir(app_root)
    File.join(app_root, '.dart_tool', 'rayban_dat_plugin_boundary')
  end
end
