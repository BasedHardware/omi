# frozen_string_literal: true

require 'json'
require 'minitest/autorun'
require 'rexml/document'

class RayBanDatXcodeGraphTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  PROJECT_FILE = File.join(IOS_ROOT, 'Runner.xcodeproj', 'project.pbxproj')
  PODFILE = File.join(IOS_ROOT, 'Podfile')
  SCHEME_FILE = File.join(
    IOS_ROOT,
    'Runner.xcodeproj',
    'xcshareddata',
    'xcschemes',
    'raybanDat.xcscheme',
  )
  PACKAGE_LOCK = File.join(
    IOS_ROOT,
    'Runner.xcodeproj',
    'project.xcworkspace',
    'xcshareddata',
    'swiftpm',
    'Package.resolved',
  )

  DAT_CONFIGS = {
    'Debug-raybanDat' => 'raybanDatDebug.xcconfig',
    'Profile-raybanDat' => 'raybanDatProfile.xcconfig',
    'Release-raybanDat' => 'raybanDatRelease.xcconfig',
  }.freeze
  COCOAPODS_FALLBACK_CONFIGS = %w[Debug Profile Release].freeze

  TEAM = '9536L8KLMP'
  BUNDLE_ID = 'com.friend-app-with-wearable.ios12.development'
  PACKAGE_URL = 'https://github.com/facebook/meta-wearables-dat-ios'
  PACKAGE_VERSION = '0.8.0'
  PACKAGE_REVISION = '2e30f1253ab76ee3c448a29dce39114ab09763c3'

  def setup
    @project = File.binread(PROJECT_FILE)
  end

  def test_default_runner_has_no_meta_package_products
    runner = native_target('Runner')

    refute_includes runner, 'MWDATCore'
    refute_includes runner, 'MWDATCamera'
  end

  def test_separate_dat_target_owns_only_the_required_meta_products
    dat = native_target('RunnerRayBanDat')
    product_names = package_product_names(dat)

    assert_equal %w[MWDATCamera MWDATCore], product_names.sort
    assert_package_product('MWDATCore')
    assert_package_product('MWDATCamera')
  end

  def test_meta_package_is_pinned_to_exact_0_8_0
    package = object_with_comment('XCRemoteSwiftPackageReference "meta-wearables-dat-ios"')

    assert_includes package, %(repositoryURL = "#{PACKAGE_URL}";)
    assert_match(/requirement = \{\s*kind = exactVersion;\s*version = #{Regexp.escape(PACKAGE_VERSION)};\s*\};/m,
                 package)

    lock = JSON.parse(read_required(PACKAGE_LOCK))
    pin = lock.fetch('pins').find { |candidate| candidate.fetch('identity') == 'meta-wearables-dat-ios' }
    refute_nil pin
    assert_equal PACKAGE_URL, pin.fetch('location')
    assert_equal PACKAGE_VERSION, pin.fetch('state').fetch('version')
    assert_equal PACKAGE_REVISION, pin.fetch('state').fetch('revision')
  end

  def test_dat_target_has_dedicated_configs_and_exact_signing_contract
    dat = native_target('RunnerRayBanDat')
    config_list_id = capture!(dat, /buildConfigurationList = ([A-Z0-9]+) /, 'DAT config list')
    config_list = object_with_id(config_list_id)

    DAT_CONFIGS.each do |config_name, xcconfig_name|
      config_id = capture!(config_list,
                           /([A-Z0-9]+) \/\* #{Regexp.escape(config_name)} \*\//,
                           config_name)
      config = object_with_id(config_id)

      assert_match(/name = \"?#{Regexp.escape(config_name)}\"?;/, config)
      assert_includes config, "/* #{xcconfig_name} */"
      assert_includes config, "DEVELOPMENT_TEAM = #{TEAM};"
      assert_includes config, 'IPHONEOS_DEPLOYMENT_TARGET = 15.2;'
      assert_match(/PRODUCT_BUNDLE_IDENTIFIER = \"?#{Regexp.escape(BUNDLE_ID)}\"?;/, config)
      assert_includes config, 'SWIFT_VERSION = 5.0;'

      xcconfig_reference = object_with_comment(xcconfig_name)
      assert_includes xcconfig_reference, "path = Flutter/#{xcconfig_name};"

      xcconfig = read_required(File.join(IOS_ROOT, 'Flutter', xcconfig_name))
      assert_includes xcconfig, "APP_BUNDLE_IDENTIFIER=#{BUNDLE_ID}"
      assert_match(%r{Pods-RunnerRayBanDat/Pods-RunnerRayBanDat\.(debug|profile|release)-raybandat\.xcconfig},
                   xcconfig)
    end
  end

  def test_dat_target_fallback_configs_keep_cocoapods_analysis_on_the_same_swift_version
    dat = native_target('RunnerRayBanDat')
    config_list_id = capture!(dat, /buildConfigurationList = ([A-Z0-9]+) /, 'DAT config list')
    config_list = object_with_id(config_list_id)

    COCOAPODS_FALLBACK_CONFIGS.each do |config_name|
      config_id = capture!(config_list,
                           /([A-Z0-9]+) \/\* #{Regexp.escape(config_name)} \*\//,
                           "CocoaPods fallback #{config_name}")
      config = object_with_id(config_id)

      assert_includes config, "name = #{config_name};"
      assert_includes config, "DEVELOPMENT_TEAM = #{TEAM};"
      assert_includes config, 'IPHONEOS_DEPLOYMENT_TARGET = 15.2;'
      assert_includes config, "PRODUCT_BUNDLE_IDENTIFIER = \"#{BUNDLE_ID}\";"
      assert_includes config, 'SWIFT_VERSION = 5.0;'
    end
  end

  def test_dat_target_compiles_the_same_sources_and_resources_as_runner
    runner = native_target('Runner')
    dat = native_target('RunnerRayBanDat')

    assert_equal phase_file_reference_ids(runner, 'Sources'), phase_file_reference_ids(dat, 'Sources')
    assert_equal phase_file_reference_ids(runner, 'Resources'), phase_file_reference_ids(dat, 'Resources')
  end

  def test_dat_target_has_only_required_non_pod_frameworks
    dat = native_target('RunnerRayBanDat')
    framework_phase_id = capture!(dat, /([A-Z0-9]+) \/\* Frameworks \*\//, 'DAT frameworks phase')
    frameworks = object_with_id(framework_phase_id)

    assert_includes frameworks, 'WatchConnectivity.framework in Frameworks'
    assert_includes frameworks, 'MWDATCore in Frameworks'
    assert_includes frameworks, 'MWDATCamera in Frameworks'
    refute_includes frameworks, 'Foundation.framework in Frameworks'
    refute_includes frameworks, 'Pods_Runner.framework in Frameworks'
  end

  def test_shared_flutter_scheme_builds_only_the_dat_target
    document = REXML::Document.new(read_required(SCHEME_FILE))
    references = REXML::XPath.match(document, '//BuildableReference')

    refute_empty references
    assert references.all? { |reference| reference.attributes['BlueprintName'] == 'RunnerRayBanDat' }
    assert references.all? { |reference| reference.attributes['BuildableName'] == 'Runner.app' }
    assert_equal ['Debug-raybanDat'], action_configs(document, '//TestAction | //LaunchAction | //AnalyzeAction').uniq
    assert_equal ['Profile-raybanDat'], action_configs(document, '//ProfileAction').uniq
    assert_equal ['Release-raybanDat'], action_configs(document, '//ArchiveAction').uniq
  end

  def test_cocoapods_declares_a_separate_dat_aggregate_target
    podfile = File.binread(PODFILE)

    DAT_CONFIGS.each_key do |config_name|
      assert_match(/['"]#{Regexp.escape(config_name)}['"]\s*=>/, podfile)
    end
    assert_match(/^\s*target ['"]RunnerRayBanDat['"] do$/m, podfile)
  end

  private

  def native_target(name)
    object_with_comment_and_isa(name, 'PBXNativeTarget')
  end

  def object_with_comment(comment)
    object = object_blocks.find { |candidate| candidate.fetch(:comment) == comment }
    refute_nil object, "missing Xcode object #{comment.inspect}"
    object.fetch(:text)
  end

  def object_with_comment_and_isa(comment, isa)
    object = object_blocks.find do |candidate|
      candidate.fetch(:comment) == comment && candidate.fetch(:text).include?("isa = #{isa};")
    end
    refute_nil object, "missing #{isa} Xcode object #{comment.inspect}"
    object.fetch(:text)
  end

  def object_with_id(id)
    object = object_blocks.find { |candidate| candidate.fetch(:id) == id }
    refute_nil object, "missing Xcode object #{id}"
    object.fetch(:text)
  end

  def package_product_names(target)
    list = target[/packageProductDependencies = \((.*?)\);/m, 1]
    refute_nil list, 'DAT target must declare packageProductDependencies'
    list.scan(%r{/\* (MWDAT(?:Core|Camera)) \*/}).flatten
  end

  def assert_package_product(name)
    dependency = object_with_comment_and_isa(name, 'XCSwiftPackageProductDependency')
    assert_includes dependency, "productName = #{name};"
    assert_includes dependency, '/* XCRemoteSwiftPackageReference "meta-wearables-dat-ios" */'
  end

  def action_configs(document, xpath)
    REXML::XPath.match(document, xpath).map { |action| action.attributes['buildConfiguration'] }
  end

  def phase_file_reference_ids(target, phase_name)
    phase_id = capture!(target,
                        /([A-Z0-9]+) \/\* #{Regexp.escape(phase_name)} \*\//,
                        "#{phase_name} phase")
    phase = object_with_id(phase_id)
    build_file_ids = phase.scan(/^\s*([A-Z0-9]+) \/\* .* in #{Regexp.escape(phase_name)} \*\/,/).flatten
    build_file_ids.map do |build_file_id|
      capture!(object_with_id(build_file_id),
               /fileRef = ([A-Z0-9]+) /,
               "#{phase_name} file reference for build file #{build_file_id}")
    end.sort
  end

  def capture!(text, pattern, description)
    match = text.match(pattern)
    refute_nil match, "missing #{description}"
    match[1]
  end

  def read_required(path)
    assert File.file?(path), "missing required file #{path}"
    File.binread(path)
  end

  def object_blocks
    @object_blocks ||= begin
      lines = @project.lines
      blocks = []
      index = 0
      while index < lines.length
        header = lines[index].match(/^\s*([A-Z0-9]+) \/\* (.*?) \*\/ = \{/)
        unless header
          index += 1
          next
        end

        start = index
        depth = 0
        loop do
          depth += lines[index].count('{') - lines[index].count('}')
          index += 1
          break if depth.zero?
        end
        blocks << {id: header[1], comment: header[2], text: lines[start...index].join}
      end
      blocks
    end
  end
end
