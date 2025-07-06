import Cocoa
import AVFoundation
import CoreBluetooth
import CoreLocation
import UserNotifications
import ScreenCaptureKit

// MARK: - Permission Manager
class PermissionManager: NSObject, CBCentralManagerDelegate, CLLocationManagerDelegate {
    
    // MARK: - Singleton
    static let shared = PermissionManager()
    
    // MARK: - Private Properties
    private var bluetoothManager: CBCentralManager?
    private var locationManager: CLLocationManager?
    private var bluetoothPermissionCompletion: ((Bool) -> Void)?
    private var locationPermissionCompletion: ((Bool) -> Void)?
    private var notificationPermissionCompletion: ((Bool) -> Void)?
    
    // MARK: - Initialization
    private override init() {
        super.init()
    }
    
    // MARK: - Microphone Permission
    
    func checkMicrophonePermission() -> String {
        if #available(macOS 14.0, *) {
            switch AVAudioApplication.shared.recordPermission {
            case .granted:
                return "granted"
            case .denied:
                return "denied"
            case .undetermined:
                return "undetermined"
            @unknown default:
                return "unknown"
            }
        } else if #available(macOS 10.14, *) {
            // Fallback on earlier versions
            switch AVCaptureDevice.authorizationStatus(for: .audio) {
            case .authorized:
                return "granted"
            case .denied:
                return "denied"
            case .notDetermined:
                return "undetermined"
            case .restricted:
                return "restricted"
            @unknown default:
                return "unknown"
            }
        } else {
            // For macOS versions prior to 10.14, there was no explicit microphone permission.
            return "granted"
        }
    }
    
    func requestMicrophonePermission() async -> Bool {
        if #available(macOS 14.0, *) {
            guard AVAudioApplication.shared.recordPermission != .granted else {
                return true // Already granted
            }
            
            let granted = await AVAudioApplication.requestRecordPermission()
            print("Microphone permission request result: \(granted)")
            return granted
        } else if #available(macOS 10.14, *) {
            // Fallback on earlier versions
            guard AVCaptureDevice.authorizationStatus(for: .audio) != .authorized else {
                return true
            }
            return await withCheckedContinuation { continuation in
                AVCaptureDevice.requestAccess(for: .audio) { granted in
                    print("Microphone permission request result: \(granted)")
                    continuation.resume(returning: granted)
                }
            }
        } else {
            // For macOS versions prior to 10.14, there was no explicit microphone permission.
            return true
        }
    }
    
    // MARK: - Screen Capture Permission
    
    func checkScreenCapturePermission() async -> String {
        // First try the most reliable method - actually attempt to get content
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            if !content.displays.isEmpty {
                return "granted"
            } else {
                return "denied"
            }
        } catch {
            print("Error checking shareable content: \(error)")
            if case SCStreamError.userDeclined = error {
                return "denied"
            }
            // For any other error, it's likely undetermined
            return "undetermined"
        }
    }
    
    func requestScreenCapturePermission() async -> Bool {
        // First check if we can actually use the permission without triggering dialogs
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            if !content.displays.isEmpty {
                print("Screen capture permission is actually working despite status")
                return true
            }
        } catch {
            print("Initial screen capture test failed: \(error)")
        }
        
        // Only if the above fails, try the official request method
        if #available(macOS 11.0, *) {
            // Check TCC database first to avoid unnecessary prompts
            let hasAccess = CGPreflightScreenCaptureAccess()
            if hasAccess {
                print("TCC database shows screen capture access is granted")
                return true
            }
            
            print("Requesting screen capture permission via CGRequestScreenCaptureAccess")
            let granted = CGRequestScreenCaptureAccess()
            if granted {
                return true
            }
        }
        
        // As a last resort, open system preferences
        print("Opening System Preferences as last resort for screen capture permission")
        await MainActor.run {
            NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!)
        }
        return false
    }
    
    // MARK: - Bluetooth Permission
    
    func checkBluetoothPermission() -> String {
        if #available(macOS 10.15, *) {
            switch CBCentralManager.authorization {
            case .allowedAlways:
                return "granted"
            case .denied:
                return "denied"
            case .restricted:
                return "restricted"
            case .notDetermined:
                return "undetermined"
            @unknown default:
                return "unknown"
            }
        } else {
            // For older macOS versions, assume granted if Bluetooth is available
            return "granted"
        }
    }
    
    func requestBluetoothPermission() async -> Bool {
        if #available(macOS 10.15, *) {
            guard CBCentralManager.authorization != .allowedAlways else {
                return true
            }
            
            // If explicitly denied or restricted, can't request again
            if CBCentralManager.authorization == .denied || CBCentralManager.authorization == .restricted {
                print("Bluetooth permission is \(CBCentralManager.authorization.rawValue), cannot request again")
                return false
            }
            
            // Check if Bluetooth service is available first
            let tempManager = CBCentralManager()
            if tempManager.state == .poweredOff {
                print("Bluetooth is powered off. User needs to enable Bluetooth in System Settings.")
                await MainActor.run {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.bluetooth")!)
                }
                return false
            } else if tempManager.state == .unsupported {
                print("Bluetooth is not supported on this device.")
                return false
            }
            
            return await withCheckedContinuation { continuation in
                // Set up timeout to prevent continuation leak
                Task {
                    try? await Task.sleep(nanoseconds: 15_000_000_000) // 15 seconds timeout for Bluetooth
                    if bluetoothPermissionCompletion != nil {
                        print("Bluetooth permission request timed out")
                        bluetoothPermissionCompletion?(false)
                    }
                }
                
                bluetoothPermissionCompletion = { granted in
                    continuation.resume(returning: granted)
                    self.bluetoothPermissionCompletion = nil // Clear to prevent multiple calls
                }
                
                // Initialize CBCentralManager to trigger permission request
                if bluetoothManager == nil {
                    print("Initializing Bluetooth central manager...")
                    bluetoothManager = CBCentralManager(delegate: self, queue: nil)
                } else {
                    // If manager already exists, check current state
                    print("Bluetooth manager exists, checking current state...")
                    centralManagerDidUpdateState(bluetoothManager!)
                }
            }
        } else {
            print("Bluetooth permission handling not available on macOS < 10.15, assuming granted")
            return true
        }
    }
    
    // MARK: - Location Permission
    
    func checkLocationPermission() -> String {
        switch CLLocationManager.authorizationStatus() {
        case .authorizedAlways, .authorized:
            return "granted"
        case .denied:
            return "denied"
        case .restricted:
            return "restricted"
        case .notDetermined:
            return "undetermined"
        @unknown default:
            return "unknown"
        }
    }
    
    func requestLocationPermission() async -> Bool {
        let currentStatus = CLLocationManager.authorizationStatus()
        guard currentStatus != .authorizedAlways && currentStatus != .authorized else {
            return true // Already granted
        }
        
        guard currentStatus == .notDetermined else {
            // If denied or restricted, open system preferences
            print("Location permission is \(currentStatus.rawValue), opening System Preferences")
            await MainActor.run {
                NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices")!)
            }
            return false
        }
        
        // Check if location services are enabled before requesting
        guard CLLocationManager.locationServicesEnabled() else {
            print("Location services are disabled system-wide, opening System Preferences")
            await MainActor.run {
                NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices")!)
            }
            return false
        }
        
        return await withCheckedContinuation { continuation in
            // Set up timeout to prevent continuation leak
            Task {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10 seconds timeout
                if locationPermissionCompletion != nil {
                    print("Location permission request timed out")
                    locationPermissionCompletion?(false)
                }
            }
            
            locationPermissionCompletion = { granted in
                continuation.resume(returning: granted)
                self.locationPermissionCompletion = nil // Clear to prevent multiple calls
            }
            
            if locationManager == nil {
                locationManager = CLLocationManager()
                locationManager?.delegate = self
            }
            
            locationManager?.requestWhenInUseAuthorization()
        }
    }
    
    // MARK: - Notification Permission
    
    func checkNotificationPermission() async -> String {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        
        switch settings.authorizationStatus {
        case .authorized:
            return "granted"
        case .denied:
            return "denied"
        case .notDetermined:
            return "undetermined"
        case .provisional:
            return "provisional"
        case .ephemeral:
            return "ephemeral"
        @unknown default:
            return "unknown"
        }
    }
    
    func requestNotificationPermission() async -> Bool {
        let center = UNUserNotificationCenter.current()
        let currentSettings = await center.notificationSettings()
        
        guard currentSettings.authorizationStatus != .authorized else {
            print("Notification permission already granted")
            return true
        }
        
        if currentSettings.authorizationStatus == .notDetermined {
            // Only try to request if undetermined
            do {
                let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
                print("Notification permission request result: \(granted)")
                if !granted {
                    print("User denied notification permission request, opening System Preferences")
                    await MainActor.run {
                        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!)
                    }
                }
                return granted
            } catch {
                print("Error requesting notification permission: \(error.localizedDescription)")
                await MainActor.run {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!)
                }
                return false
            }
        } else {
            // If denied, restricted, or any other status, redirect to system preferences
            print("Notification permission is \(currentSettings.authorizationStatus.rawValue), opening System Preferences")
            await MainActor.run {
                NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!)
            }
            return false
        }
    }
    
    // MARK: - CBCentralManagerDelegate
    
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        print("Bluetooth central manager state updated to: \(central.state.rawValue)")
        
        // Handle different Bluetooth states
        switch central.state {
        case .poweredOff:
            print("Bluetooth is powered off. Permission cannot be granted until Bluetooth is enabled.")
            bluetoothPermissionCompletion?(false)
            bluetoothPermissionCompletion = nil
            return
        case .unsupported:
            print("Bluetooth is not supported on this device.")
            bluetoothPermissionCompletion?(false)
            bluetoothPermissionCompletion = nil
            return
        case .unauthorized:
            print("Bluetooth access is not authorized for this app.")
            bluetoothPermissionCompletion?(false)
            bluetoothPermissionCompletion = nil
            return
        case .poweredOn:
            break
        case .unknown, .resetting:
            print("Bluetooth state is \(central.state). Waiting for definitive state...")
            return
        @unknown default:
            print("Unknown Bluetooth state: \(central.state)")
            return
        }
        
        if #available(macOS 10.15, *) {
            let granted: Bool
            switch CBCentralManager.authorization {
            case .allowedAlways:
                granted = true
            case .denied, .restricted:
                granted = false
            case .notDetermined:
                granted = (central.state == .poweredOn)
            @unknown default:
                granted = false
            }
            
            print("Bluetooth permission resolved: granted=\(granted)")
            bluetoothPermissionCompletion?(granted)
            bluetoothPermissionCompletion = nil
        } else {
            let granted = (central.state == .poweredOn)
            bluetoothPermissionCompletion?(granted)
            bluetoothPermissionCompletion = nil
        }
    }
    
    // MARK: - CLLocationManagerDelegate
    
    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        print("Location authorization changed to: \(status.rawValue)")
        
        guard let completion = locationPermissionCompletion else {
            print("Location permission completion is nil, ignoring delegate call")
            return
        }
        
        let granted = (status == .authorizedAlways || status == .authorized)
        print("Location permission resolved: granted=\(granted)")
        completion(granted)
    }
    
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("Location manager failed with error: \(error.localizedDescription)")
        locationPermissionCompletion?(false)
    }
} 
