#
# Podspec for meta_wearables_dat_flutter.
#
# This plugin is *Swift Package Manager first*. Meta's official iOS DAT SDK
# (`MWDATCore`, `MWDATCamera`, `MWDATMockDevice`) is consumed via SPM in
# `meta_wearables_dat_flutter/Package.swift` and is **not** vendored as
# `xcframework`s here.
#
# Consumers must run `flutter config --enable-swift-package-manager` and use
# Xcode 15.4+. See `doc/troubleshooting.md` for setup details. The Swift
# sources include a `#if !canImport(MWDATCore)` guard that emits a clear
# `#error` when SPM has not been enabled.
#
Pod::Spec.new do |s|
  s.name             = 'meta_wearables_dat_flutter'
  s.version          = '0.7.1'
  s.summary          = 'Unofficial Flutter plugin for Meta\'s Wearables Device Access Toolkit.'
  s.description      = <<-DESC
Unofficial Flutter plugin bridging Meta's iOS and Android Wearables Device
Access Toolkit (DAT) SDKs. iOS dependencies are linked via Swift Package
Manager; this podspec only declares the Flutter dependency and Apple system
frameworks.
                       DESC
  s.homepage         = 'https://github.com/iSee-Labs/meta-wearables-dat-flutter'
  s.license          = { :file => '../LICENSE' }
  s.author           = { 'iSee Labs' => 'https://github.com/iSee-Labs' }
  s.source           = { :path => '.' }
  s.source_files     = 'meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/**/*.swift'

  s.dependency 'Flutter'

  s.platform         = :ios, '17.0'
  s.swift_version    = '5.9'

  s.frameworks = 'CoreBluetooth', 'Network', 'AVFoundation', 'ExternalAccessory'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'EXCLUDED_ARCHS[sdk=iphonesimulator*]' => 'i386',
  }
end
