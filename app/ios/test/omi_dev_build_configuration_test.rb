# frozen_string_literal: true

require 'minitest/autorun'

class OmiDevBuildConfigurationTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  PROJECT_FILE = File.join(IOS_ROOT, 'Runner.xcodeproj', 'project.pbxproj')
  DEV_BUNDLE_ID = 'com.friend-app-with-wearable.ios12.development'

  DEV_CONFIGS = {
    'Profile-dev' => ['devProfile.xcconfig', 'Pods-Runner.profile-dev.xcconfig'],
    'Release-dev' => ['devRelease.xcconfig', 'Pods-Runner.release-dev.xcconfig'],
  }.freeze

  def setup
    @project = File.binread(PROJECT_FILE)
  end

  def test_profile_and_release_use_the_dev_identity_and_matching_pod_configuration
    DEV_CONFIGS.each do |config_name, (file_name, pods_file)|
      config = File.binread(File.join(IOS_ROOT, 'Flutter', file_name))

      assert_includes config, %(Pods/Target Support Files/Pods-Runner/#{pods_file})
      assert_includes config, "APP_BUNDLE_IDENTIFIER=#{DEV_BUNDLE_ID}"
      refute_includes config, 'FRAMEWORK_SEARCH_PATHS=', 'CocoaPods owns the framework search paths'
    end
  end

  def test_watch_signing_keeps_simulator_debug_account_free_and_device_builds_installable
    configs = dev_extension_configurations('omiWatchApp-Info.plist')

    assert_includes configs.fetch('Debug-dev'), 'CODE_SIGNING_ALLOWED = NO;'
    refute_includes configs.fetch('Profile-dev'), 'CODE_SIGNING_ALLOWED = NO;'
    refute_includes configs.fetch('Release-dev'), 'CODE_SIGNING_ALLOWED = NO;'
  end

  def test_dev_widget_derives_its_identifier_from_the_dev_app_once
    configs = dev_extension_configurations('BatteryWidget-Info.plist')

    %w[Debug-dev Profile-dev Release-dev].each do |config_name|
      config = configs.fetch(config_name)
      assert_includes config, 'PRODUCT_BUNDLE_IDENTIFIER = "$(APP_BUNDLE_IDENTIFIER).widget";'
      refute_includes config, '$(APP_BUNDLE_IDENTIFIER).development.widget'
    end
  end

  private

  def dev_extension_configurations(info_plist)
    blocks = @project.scan(
      /^\t\t[A-Z0-9]+ \/\* (?:Debug|Profile|Release)-dev \*\/ = \{\n\t\t\tisa = XCBuildConfiguration;.*?^\t\t\};/m,
    )
    matching = blocks.select { |block| block.include?(%(INFOPLIST_FILE = "#{info_plist}";)) }
    configs = matching.to_h do |block|
      name = block.match(/^\t\t\tname = "?([^";]+)"?;$/)&.captures&.first
      refute_nil name, "missing configuration name for #{info_plist}"
      [name, block]
    end

    assert_equal %w[Debug-dev Profile-dev Release-dev], configs.keys.sort
    configs
  end
end
