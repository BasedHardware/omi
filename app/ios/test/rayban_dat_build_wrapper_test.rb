# frozen_string_literal: true

require 'fileutils'
require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class RayBanDatBuildWrapperTest < Minitest::Test
  APP_ROOT = File.expand_path('../..', __dir__)
  WRAPPER = File.join(APP_ROOT, 'scripts', 'rayban_dat.sh')

  DEFAULT_LOCK = <<~LOCK
    PODS:
      - mcumgr_flutter
      - SwiftProtobuf
  LOCK
  DEFAULT_METADATA = '{"plugins":{"ios":[{"name":"mcumgr_flutter"}],"android":[{"name":"mcumgr_flutter"}]}}'
  DEFAULT_GENERATED_XCCONFIG = "DART_DEFINES=default-defines\nFLAVOR=dev\n"
  DEFAULT_EXPORT_ENVIRONMENT = <<~SHELL
    #!/bin/sh
    export "DART_DEFINES=default-defines"
    export "FLAVOR=dev"
  SHELL

  def setup
    assert File.file?(WRAPPER), "missing DAT build wrapper: #{WRAPPER}"
  end

  def test_run_prepares_dat_graph_then_restores_default_graph_exactly
    in_fixture do |fixture|
      env = fixture.fetch(:env).merge('FLUTTER_ACTION_EXIT' => '0')
      stdout, stderr, status = Open3.capture3(
        env,
        fixture.fetch(:wrapper),
        'run',
        '-d',
        'physical-iphone',
        chdir: fixture.fetch(:app)
      )

      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      assert_equal expected_run_log, File.readlines(fixture.fetch(:log), chomp: true)
      assert_default_state_restored(fixture)
    end
  end

  def test_failed_flutter_run_preserves_exit_status_and_still_restores_default_graph
    in_fixture do |fixture|
      env = fixture.fetch(:env).merge('FLUTTER_ACTION_EXIT' => '42')
      _stdout, stderr, status = Open3.capture3(
        env,
        fixture.fetch(:wrapper),
        'run',
        chdir: fixture.fetch(:app)
      )

      assert_equal 42, status.exitstatus, stderr
      assert_includes File.readlines(fixture.fetch(:log), chomp: true), 'helper||restore'
      assert_includes File.readlines(fixture.fetch(:log), chomp: true), 'pod||install'
      assert_default_state_restored(fixture)
    end
  end

  def test_successful_action_reports_cleanup_failure_and_keeps_recovery_state
    in_fixture do |fixture|
      env = fixture.fetch(:env).merge('POD_DEFAULT_EXIT' => '53')
      _stdout, stderr, status = Open3.capture3(
        env,
        fixture.fetch(:wrapper),
        'run',
        chdir: fixture.fetch(:app)
      )

      refute status.success?, stderr
      assert_match(/restore incomplete/, stderr)
      assert File.exist?(
        File.join(fixture.fetch(:app), '.dart_tool', 'rayban_dat_build', 'default_Podfile.lock')
      )
      assert_equal DEFAULT_LOCK, File.binread(File.join(fixture.fetch(:app), 'ios', 'Podfile.lock'))
    end
  end

  def test_cleanup_refuses_to_mask_default_pod_resolution_drift
    in_fixture do |fixture|
      env = fixture.fetch(:env).merge('POD_DEFAULT_DRIFT' => '1')
      _stdout, stderr, status = Open3.capture3(
        env,
        fixture.fetch(:wrapper),
        'run',
        chdir: fixture.fetch(:app)
      )

      refute status.success?, stderr
      assert_match(/default Podfile.lock changed during pod install/, stderr)
      backup = File.join(fixture.fetch(:app), '.dart_tool', 'rayban_dat_build', 'default_Podfile.lock')
      assert_equal DEFAULT_LOCK, File.binread(backup)
      assert_includes File.binread(File.join(fixture.fetch(:app), 'ios', 'Podfile.lock')), 'resolution drift'
    end
  end

  def test_missing_dat_lock_fails_closed_before_flutter_launch
    in_fixture do |fixture|
      env = fixture.fetch(:env).merge('POD_DAT_SKIP_LOCK' => '1')
      _stdout, stderr, status = Open3.capture3(
        env,
        fixture.fetch(:wrapper),
        'run',
        chdir: fixture.fetch(:app)
      )

      refute status.success?
      assert_match(/DAT Podfile.lock is missing/, stderr)
      refute File.readlines(fixture.fetch(:log), chomp: true).any? { |line| line.start_with?('flutter|1|run|') }
      assert_default_state_restored(fixture)
    end
  end

  def test_build_uses_rayban_dat_flavor_define_and_no_pub
    in_fixture do |fixture|
      stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'build',
        'ipa',
        '--release',
        chdir: fixture.fetch(:app)
      )

      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      assert_includes(
        File.readlines(fixture.fetch(:log), chomp: true),
        'flutter|1|build|ipa|--flavor|raybanDat|--dart-define=OMI_RAYBAN_DAT=true|--no-pub|--release'
      )
      assert_default_state_restored(fixture)
    end
  end

  def test_wrapper_is_independent_of_the_callers_working_directory
    in_fixture do |fixture|
      stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'build',
        '--debug',
        chdir: fixture.fetch(:root)
      )

      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      assert_includes(
        File.readlines(fixture.fetch(:log), chomp: true),
        'flutter|1|build|ios|--flavor|raybanDat|--dart-define=OMI_RAYBAN_DAT=true|--no-pub|--debug'
      )
      assert_default_state_restored(fixture)
    end
  end

  def test_explicit_restore_recovers_a_stale_dat_transaction
    in_fixture do |fixture|
      app = fixture.fetch(:app)
      state_dir = File.join(app, '.dart_tool', 'rayban_dat_build')
      FileUtils.mkdir_p(state_dir)
      File.write(File.join(state_dir, 'default_Podfile.lock'), DEFAULT_LOCK)
      File.write(File.join(state_dir, 'default_Generated.xcconfig'), DEFAULT_GENERATED_XCCONFIG)
      File.write(
        File.join(state_dir, 'default_flutter_export_environment.sh'),
        DEFAULT_EXPORT_ENVIRONMENT
      )
      File.write(File.join(app, 'ios', 'Podfile.lock'), "PODS:\n  - MWDATCore\n")
      File.write(
        File.join(app, 'ios', 'Flutter', 'Generated.xcconfig'),
        "DART_DEFINES=T01JX1JBWUJBTl9EQVQ9dHJ1ZQ==\nFLAVOR=raybanDat\n"
      )
      File.write(
        File.join(app, 'ios', 'Flutter', 'flutter_export_environment.sh'),
        "#!/bin/sh\nexport \"DART_DEFINES=T01JX1JBWUJBTl9EQVQ9dHJ1ZQ==\"\nexport \"FLAVOR=raybanDat\"\n"
      )
      File.write(
        File.join(app, '.flutter-plugins-dependencies'),
        '{"plugins":{"ios":[],"android":[{"name":"mcumgr_flutter"}]}}'
      )
      File.write(File.join(app, 'ios', 'Runner', 'GeneratedPluginRegistrant.m'), 'dat registrant')

      stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'restore',
        chdir: app
      )

      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      assert_equal(
        ['helper||restore', 'flutter||pub|get|--enforce-lockfile', 'pod||install'],
        File.readlines(fixture.fetch(:log), chomp: true)
      )
      assert_default_state_restored(fixture)
    end
  end

  def test_missing_boundary_helper_fails_before_flutter_or_cocoapods_mutation
    in_fixture do |fixture|
      FileUtils.rm(File.join(fixture.fetch(:app), 'ios', 'rayban_dat_plugin_boundary.rb'))

      _stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'run',
        chdir: fixture.fetch(:app)
      )

      refute status.success?
      assert_match(/rayban_dat_plugin_boundary\.rb/, stderr)
      refute File.exist?(fixture.fetch(:log))
      assert_equal DEFAULT_LOCK, File.binread(File.join(fixture.fetch(:app), 'ios', 'Podfile.lock'))
    end
  end

  def test_invalid_build_artifact_fails_before_flutter_or_cocoapods_mutation
    in_fixture do |fixture|
      _stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'build',
        'macos',
        chdir: fixture.fetch(:app)
      )

      refute status.success?
      assert_match(/unsupported build artifact/, stderr)
      refute File.exist?(fixture.fetch(:log))
      assert_equal DEFAULT_LOCK, File.binread(File.join(fixture.fetch(:app), 'ios', 'Podfile.lock'))
    end
  end

  def test_rejects_a_preexisting_dat_flutter_environment_before_native_mutation
    in_fixture do |fixture|
      app = fixture.fetch(:app)
      File.write(
        File.join(app, 'ios', 'Flutter', 'Generated.xcconfig'),
        "DART_DEFINES=T01JX1JBWUJBTl9EQVQ9dHJ1ZQ==\nFLAVOR=raybanDat\n"
      )

      _stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'run',
        chdir: app
      )

      refute status.success?
      assert_match(/DAT flavor leaked/, stderr)
      assert_equal ['flutter||pub|get|--enforce-lockfile'], File.readlines(fixture.fetch(:log), chomp: true)
      refute Dir.exist?(File.join(app, '.dart_tool', 'rayban_dat_build'))
      assert_equal DEFAULT_LOCK, File.binread(File.join(app, 'ios', 'Podfile.lock'))
    end
  end

  def test_removes_generated_flutter_environment_that_was_absent_before_the_transaction
    in_fixture do |fixture|
      app = fixture.fetch(:app)
      FileUtils.rm(File.join(app, 'ios', 'Flutter', 'Generated.xcconfig'))
      FileUtils.rm(File.join(app, 'ios', 'Flutter', 'flutter_export_environment.sh'))

      stdout, stderr, status = Open3.capture3(
        fixture.fetch(:env),
        fixture.fetch(:wrapper),
        'run',
        chdir: app
      )

      assert status.success?, "stdout:\n#{stdout}\nstderr:\n#{stderr}"
      assert_default_state_restored(fixture, generated_environment: false)
    end
  end

  private

  def in_fixture
    Dir.mktmpdir('rayban-dat-wrapper-test') do |root|
      app = File.join(root, 'app')
      scripts = File.join(app, 'scripts')
      ios = File.join(app, 'ios')
      flutter = File.join(ios, 'Flutter')
      runner = File.join(ios, 'Runner')
      fake_bin = File.join(root, 'fake-bin')
      log = File.join(root, 'commands.log')

      [scripts, flutter, runner, fake_bin].each { |directory| FileUtils.mkdir_p(directory) }
      FileUtils.cp(WRAPPER, File.join(scripts, 'rayban_dat.sh'))
      FileUtils.chmod(0o755, File.join(scripts, 'rayban_dat.sh'))
      File.write(File.join(ios, 'Podfile.lock'), DEFAULT_LOCK)
      File.write(File.join(flutter, 'Generated.xcconfig'), DEFAULT_GENERATED_XCCONFIG)
      File.write(File.join(flutter, 'flutter_export_environment.sh'), DEFAULT_EXPORT_ENVIRONMENT)
      File.write(File.join(root, 'expected-default.lock'), DEFAULT_LOCK)
      File.write(File.join(app, '.dev.env'), "API_BASE_URL=http://192.168.1.196:8083/\n")
      File.write(File.join(ios, 'rayban_dat_plugin_boundary.rb'), fake_helper_source)
      File.write(File.join(fake_bin, 'flutter'), fake_flutter_source)
      File.write(File.join(fake_bin, 'pod'), fake_pod_source)
      FileUtils.chmod(0o755, [File.join(fake_bin, 'flutter'), File.join(fake_bin, 'pod')])

      fixture = {
        root: root,
        app: app,
        wrapper: File.join(scripts, 'rayban_dat.sh'),
        log: log,
        env: {
          'COMMAND_LOG' => log,
          'FIXTURE_APP' => app,
          'FLUTTER_BIN' => File.join(fake_bin, 'flutter'),
          'POD_BIN' => File.join(fake_bin, 'pod'),
          'EXPECTED_DEFAULT_LOCK' => File.join(root, 'expected-default.lock'),
        },
      }

      yield fixture
    end
  end

  def fake_helper_source
    <<~'RUBY'
      # frozen_string_literal: true

      app = File.expand_path('..', __dir__)
      File.open(ENV.fetch('COMMAND_LOG'), 'a') do |log|
        log.puts("helper|#{ENV.fetch('OMI_RAYBAN_DAT', '')}|#{ARGV.fetch(0)}")
      end

      case ARGV.fetch(0)
      when 'prepare'
        abort 'prepare requires exact DAT flag' unless ENV['OMI_RAYBAN_DAT'] == '1'
        File.write(
          File.join(app, '.flutter-plugins-dependencies'),
          '{"plugins":{"ios":[],"android":[{"name":"mcumgr_flutter"}]}}'
        )
        File.write(File.join(__dir__, 'Runner', 'GeneratedPluginRegistrant.m'), 'dat registrant without firmware')
      when 'restore'
        File.write(
          File.join(app, '.flutter-plugins-dependencies'),
          '{"plugins":{"ios":[{"name":"mcumgr_flutter"}],"android":[{"name":"mcumgr_flutter"}]}}'
        )
        File.write(File.join(__dir__, 'Runner', 'GeneratedPluginRegistrant.m'), 'default registrant: McumgrFlutterPlugin')
      else
        abort 'unexpected helper action'
      end
    RUBY
  end

  def fake_flutter_source
    <<~'BASH'
      #!/usr/bin/env bash
      set -euo pipefail

      {
        printf 'flutter|%s' "${OMI_RAYBAN_DAT-}"
        for argument in "$@"; do
          printf '|%s' "$argument"
        done
        printf '\n'
      } >> "$COMMAND_LOG"

      [[ "$(pwd -P)" == "$FIXTURE_APP" ]]

      if [[ "${1-}" == "pub" && "${2-}" == "get" ]]; then
        printf '%s' '{"plugins":{"ios":[{"name":"mcumgr_flutter"}],"android":[{"name":"mcumgr_flutter"}]}}' > "$FIXTURE_APP/.flutter-plugins-dependencies"
        printf '%s' 'default registrant: McumgrFlutterPlugin' > "$FIXTURE_APP/ios/Runner/GeneratedPluginRegistrant.m"
      elif [[ "${1-}" == "run" || "${1-}" == "build" ]]; then
        printf '%s\n' 'DART_DEFINES=T01JX1JBWUJBTl9EQVQ9dHJ1ZQ==' 'FLAVOR=raybanDat' > "$FIXTURE_APP/ios/Flutter/Generated.xcconfig"
        printf '%s\n' '#!/bin/sh' 'export "DART_DEFINES=T01JX1JBWUJBTl9EQVQ9dHJ1ZQ=="' 'export "FLAVOR=raybanDat"' > "$FIXTURE_APP/ios/Flutter/flutter_export_environment.sh"
        exit "${FLUTTER_ACTION_EXIT:-0}"
      fi
    BASH
  end

  def fake_pod_source
    <<~'BASH'
      #!/usr/bin/env bash
      set -euo pipefail

      {
        printf 'pod|%s' "${OMI_RAYBAN_DAT-}"
        for argument in "$@"; do
          printf '|%s' "$argument"
        done
        printf '\n'
      } >> "$COMMAND_LOG"

      [[ "$PWD" == "$FIXTURE_APP/ios" ]]
      mkdir -p Pods

      if [[ "${OMI_RAYBAN_DAT-}" == "1" ]]; then
        ! grep -q '"ios":\[{"name":"mcumgr_flutter"}' ../.flutter-plugins-dependencies
        grep -q '"android":\[{"name":"mcumgr_flutter"}' ../.flutter-plugins-dependencies
        ! grep -q 'McumgrFlutterPlugin' Runner/GeneratedPluginRegistrant.m
        printf 'PODS:\n  - MWDATCore\n' > Podfile.lock
        cp Podfile.lock Pods/Manifest.lock
        printf 'dat' > Pods/graph
        if [[ -n "${POD_DAT_SKIP_LOCK-}" ]]; then
          rm -f Podfile.lock Pods/Manifest.lock
        fi
      else
        cmp -s Podfile.lock "$EXPECTED_DEFAULT_LOCK"
        grep -q 'mcumgr_flutter' ../.flutter-plugins-dependencies
        grep -q 'McumgrFlutterPlugin' Runner/GeneratedPluginRegistrant.m
        cp Podfile.lock Pods/Manifest.lock
        printf 'default' > Pods/graph
        if [[ -n "${POD_DEFAULT_DRIFT-}" ]]; then
          printf '# resolution drift\n' >> Podfile.lock
          cp Podfile.lock Pods/Manifest.lock
        fi
      fi

      if [[ "${OMI_RAYBAN_DAT-}" != "1" && -n "${POD_DEFAULT_EXIT-}" ]]; then
        exit "$POD_DEFAULT_EXIT"
      fi
    BASH
  end

  def expected_run_log
    [
      'flutter||pub|get|--enforce-lockfile',
      'helper|1|prepare',
      'pod|1|install',
      'flutter|1|run|--flavor|raybanDat|--dart-define=OMI_RAYBAN_DAT=true|--no-pub|-d|physical-iphone',
      'helper||restore',
      'flutter||pub|get|--enforce-lockfile',
      'pod||install',
    ]
  end

  def assert_default_state_restored(fixture, generated_environment: true)
    app = fixture.fetch(:app)
    assert_equal DEFAULT_LOCK, File.binread(File.join(app, 'ios', 'Podfile.lock'))
    assert_equal DEFAULT_LOCK, File.binread(File.join(app, 'ios', 'Pods', 'Manifest.lock'))
    assert_equal 'default', File.binread(File.join(app, 'ios', 'Pods', 'graph'))
    assert_equal DEFAULT_METADATA, File.binread(File.join(app, '.flutter-plugins-dependencies'))
    assert_includes File.binread(File.join(app, 'ios', 'Runner', 'GeneratedPluginRegistrant.m')), 'McumgrFlutterPlugin'
    if generated_environment
      assert_equal DEFAULT_GENERATED_XCCONFIG,
                   File.binread(File.join(app, 'ios', 'Flutter', 'Generated.xcconfig'))
      assert_equal DEFAULT_EXPORT_ENVIRONMENT,
                   File.binread(File.join(app, 'ios', 'Flutter', 'flutter_export_environment.sh'))
    else
      refute File.exist?(File.join(app, 'ios', 'Flutter', 'Generated.xcconfig'))
      refute File.exist?(File.join(app, 'ios', 'Flutter', 'flutter_export_environment.sh'))
    end
    assert_equal "API_BASE_URL=http://192.168.1.196:8083/\n", File.binread(File.join(app, '.dev.env'))
    refute Dir.exist?(File.join(app, '.dart_tool', 'rayban_dat_build'))
  end
end
