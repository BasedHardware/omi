# frozen_string_literal: true

require 'minitest/autorun'

# Crashlytics 6c17570d and 84b41824: BGTaskScheduler raises on a second registration of an identifier
# and on any registration after launch finished. With UIScene the storyboard engine (and the plugins it
# registers) appears after didFinishLaunching, and Flutter's scene fallback can send plugins
# didFinishLaunching twice. Every launch handler is registered exactly once, from didFinishLaunching.
class BGTaskLaunchRegistrationTest < Minitest::Test
  APP_ROOT = File.expand_path('../..', __dir__)
  RUNNER = File.join(APP_ROOT, 'ios', 'Runner')
  APP_DELEGATE = File.read(File.join(RUNNER, 'AppDelegate.swift'))
  OVERFLOW = File.read(File.join(RUNNER, 'OnDeviceOverflowPlugin.swift'))
  VENDORED = File.join(APP_ROOT, 'packages', 'flutter_background_service_ios')
  BACKGROUND_SERVICE = File.read(File.join(VENDORED, 'ios', 'Classes', 'SwiftFlutterBackgroundServicePlugin.swift'))

  def did_finish_launching_body
    start = APP_DELEGATE.index('didFinishLaunchingWithOptions launchOptions')
    refute_nil start
    APP_DELEGATE[start...APP_DELEGATE.index('let launched = super.application', start)]
  end

  def test_overflow_handler_is_registered_before_launch_finishes
    assert_includes did_finish_launching_body, 'OnDeviceOverflowPlugin.registerBackgroundTask()'
    init = OVERFLOW[OVERFLOW.index('init(messenger: FlutterBinaryMessenger)')..]
    init = init[0...init.index("\n    }\n")]
    refute_includes init, 'register(forTaskWithIdentifier', 'plugin init runs after launch (awakeFromNib)'
  end

  def test_each_runner_identifier_has_one_registration_site
    sites = Dir[File.join(RUNNER, '**', '*.swift')].sum { |f| File.read(f).scan('register(forTaskWithIdentifier').size }
    assert_equal 2, sites, 'periodic sync + on-device overflow, both from didFinishLaunching'
  end

  def test_background_service_handler_is_registered_before_launch_finishes
    assert_includes did_finish_launching_body,
                    'SwiftFlutterBackgroundServicePlugin.registerTaskIdentifier(' \
                    "\n      taskIdentifier: SwiftFlutterBackgroundServicePlugin.taskIdentifier"
  end

  def test_foreground_task_handler_is_registered_before_launch_finishes
    assert_includes did_finish_launching_body, 'SwiftFlutterForegroundTaskPlugin.registerAppRefreshForBackgroundLaunch()'
  end

  def test_background_service_registration_is_once_per_process
    body = BACKGROUND_SERVICE[BACKGROUND_SERVICE.index('public static func registerTaskIdentifier')..]
    guard = body.index('registeredTaskIdentifiers.insert(taskIdentifier).inserted else { return }')
    register = body.index('BGTaskScheduler.shared.register(forTaskWithIdentifier')
    refute_nil guard
    assert_operator guard, :<, register
  end

  def test_app_uses_the_vendored_background_service
    pubspec = File.read(File.join(APP_ROOT, 'pubspec.yaml'))
    overrides = pubspec[pubspec.index("\ndependency_overrides:")..]
    assert_match(%r{flutter_background_service_ios:\n\s+path: packages/flutter_background_service_ios}, overrides)
  end
end
