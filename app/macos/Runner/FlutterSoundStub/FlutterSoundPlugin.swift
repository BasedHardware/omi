import FlutterMacOS

public class FlutterSoundPlugin: NSObject, FlutterPlugin {
    public static func register(with registrar: FlutterPluginRegistrar) {
        // Stub implementation for macOS - flutter_sound is not fully supported on macOS
        let channel = FlutterMethodChannel(name: "com.dooboolab.flutter_sound", binaryMessenger: registrar.messenger)
        let instance = FlutterSoundPlugin()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }
    
    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        result(FlutterMethodNotImplemented)
    }
}
