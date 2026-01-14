Pod::Spec.new do |s|
  s.name             = 'flutter_sound'
  s.version          = '9.11.2'
  s.summary          = 'Flutter Sound - macOS stub'
  s.description      = <<-DESC
Flutter Sound stub for macOS - the plugin does not support macOS natively.
                       DESC
  s.homepage         = 'https://github.com/Canardoux/flutter_sound'
  s.license          = { :type => 'MIT' }
  s.author           = { 'Stub' => 'stub@example.com' }
  s.source           = { :path => '.' }
  s.source_files = 'Classes/**/*'
  s.dependency 'FlutterMacOS'
  s.platform = :osx, '10.13'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES' }
  s.swift_version = '5.0'
end
