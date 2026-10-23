# frozen_string_literal: true

# Manual SDK/simulator probe; not a hardware or paired-Watch acceptance test.
# Run in the CocoaPods Ruby environment, with --device <booted Watch UUID>.
require 'fileutils'
require 'json'
require 'open3'
require 'optparse'
require 'tmpdir'
require 'xcodeproj'

options = { output: Dir.mktmpdir('omi-watch-controls') }
OptionParser.new do |parser|
  parser.on('--device UUID') { |value| options[:device] = value }
  parser.on('--output PATH') { |value| options[:output] = File.expand_path(value) }
end.parse!
abort 'Specify --device <booted Watch simulator UUID>' unless options[:device]

root = File.expand_path('../../..', __dir__)
output = options[:output]
FileUtils.mkdir_p(output)
project_path = File.join(output, 'Controls.xcodeproj')
project = Xcodeproj::Project.new(project_path)
target = project.new_target(:application, 'Controls', :watchos, '11.0')
%w[
  app/ios/omiWatchApp/ContentView.swift
  app/ios/omiWatchApp/RecordingPresentation.swift
  app/ios/omiWatchApp/WatchRecorderControlling.swift
  app/ios/omiWatchApp/WatchAudioRecorderViewModel.swift
  app/ios/omiWatchApp/BatteryManager.swift
  app/ios/Runner/WatchRecordingStore.swift
  app/ios/Runner/SafeFoundationSinks.swift
  app/ios/test/fixtures/watch_recording_controls_app.swift
].each do |source|
  target.source_build_phase.add_file_reference(project.main_group.new_file(File.join(root, source)))
end
%w[app/ios/omiWatchApp/Assets.xcassets app/ios/omiWatchApp/Localizable.xcstrings].each do |resource|
  target.resources_build_phase.add_file_reference(project.main_group.new_file(File.join(root, resource)))
end
bundle = 'com.omi.watchcontrols.qa'
target.build_configurations.each do |configuration|
  configuration.build_settings.merge!(
    'PRODUCT_BUNDLE_IDENTIFIER' => bundle, 'GENERATE_INFOPLIST_FILE' => 'YES',
    'INFOPLIST_KEY_WKApplication' => 'YES', 'INFOPLIST_KEY_WKWatchOnly' => 'YES',
    'INFOPLIST_KEY_CFBundleDisplayName' => 'Omi Controls QA', 'SWIFT_VERSION' => '5.0',
    'TARGETED_DEVICE_FAMILY' => '4', 'CODE_SIGNING_ALLOWED' => 'NO'
  )
end
project.save

log = File.join(output, 'probe.log')
def run_logged!(log, *command)
  File.open(log, 'a') do |file|
    abort "Command failed; see #{log}" unless system(*command, out: file, err: file)
  end
end
run_logged!(log, 'xcodebuild', '-project', project_path, '-scheme', 'Controls', '-configuration', 'Debug',
            '-sdk', 'watchsimulator', '-derivedDataPath', File.join(output, 'build'), 'CODE_SIGNING_ALLOWED=NO', 'build')
run_logged!(log, 'xcrun', 'simctl', 'install', options[:device],
            File.join(output, 'build/Build/Products/Debug-watchsimulator/Controls.app'))
container, error, status = Open3.capture3('xcrun', 'simctl', 'get_app_container', options[:device], bundle, 'data')
abort error unless status.success?
result_path = File.join(container.strip, 'Documents/watch-controls-result.json')
FileUtils.rm_f(result_path) # disposable probe result in this fixture's sandbox only
run_logged!(log, 'xcrun', 'simctl', 'launch', '--terminate-running-process', options[:device], bundle, '--verify-lifecycle')
deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 15
until File.exist?(result_path)
  abort "Probe produced no result; see #{log}" if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
  sleep 0.2
end
result = JSON.parse(File.read(result_path))
abort "Probe failed: #{result}" unless result['passed'] == true && result['cases'] == 7
File.write(File.join(output, 'result.json'), JSON.pretty_generate(result) + "\n")
puts JSON.generate(result)
