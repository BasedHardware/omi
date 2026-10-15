#!/usr/bin/env ruby
# Generates an isolated simulator-only UI test project outside the checkout.
require 'xcodeproj'
require 'fileutils'

output = ARGV.fetch(0)
abort "Output already exists: #{output}" if File.exist?(output)
FileUtils.mkdir_p(output)
source = File.expand_path(__dir__)
%w[Host.swift SpotlightTests.swift].each { |name| FileUtils.cp(File.join(source, name), output) }

project = Xcodeproj::Project.new(File.join(output, 'SpotlightProbe.xcodeproj'))
group = project.main_group.new_group('Sources')
host = project.new_target(:application, 'SpotlightHost', :ios, '27.0')
tests = project.new_target(:ui_test_bundle, 'SpotlightTests', :ios, '27.0')
tests.add_dependency(host)
{ 'Host.swift' => host, 'SpotlightTests.swift' => tests }.each do |name, target|
  target.source_build_phase.add_file_reference(group.new_file(name))
end
host.build_configurations.each do |configuration|
  configuration.build_settings.merge!({
    'PRODUCT_BUNDLE_IDENTIFIER' => 'com.omi.spotlightprobe.host',
    'SWIFT_VERSION' => '5.0',
    'GENERATE_INFOPLIST_FILE' => 'YES',
    'TARGETED_DEVICE_FAMILY' => '1',
    'CODE_SIGNING_ALLOWED' => 'NO'
  })
end
tests.build_configurations.each do |configuration|
  configuration.build_settings.merge!({
    'PRODUCT_BUNDLE_IDENTIFIER' => 'com.omi.spotlightprobe.tests',
    'SWIFT_VERSION' => '5.0',
    'GENERATE_INFOPLIST_FILE' => 'YES',
    'TARGETED_DEVICE_FAMILY' => '1',
    'CODE_SIGNING_ALLOWED' => 'NO',
    'TEST_TARGET_NAME' => 'SpotlightHost'
  })
end
project.save

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(host)
scheme.add_test_target(tests)
scheme.save_as(project.path, 'SpotlightProbe')
