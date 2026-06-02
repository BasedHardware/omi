import Flutter
import UIKit

/// Bridges Pigeon BleHostApi calls to OmiBleManager.
final class BleHostApiImpl: BleHostApi {
    private let bleManager: OmiBleManager

    init(bleManager: OmiBleManager) {
        self.bleManager = bleManager
    }

    func startScan(timeout timeoutSeconds: Int64, serviceUuids: [String]) throws {
        bleManager.startScan(timeout: Int(timeoutSeconds), serviceUuids: serviceUuids)
    }

    func stopScan() throws {
        bleManager.stopScan()
    }

    func manageDevice(uuid: String, requiresBond: Bool) throws {
        bleManager.connectPeripheral(uuid: uuid)
    }

    func unmanageDevice(uuid: String) throws {
        bleManager.disconnectPeripheral(uuid: uuid)
    }

    func requestBond(uuid: String, completion: @escaping (Result<Bool, Error>) -> Void) {
        // iOS handles bonding automatically at the OS level
        completion(.success(true))
    }

    func readCharacteristic(
        peripheralUuid: String,
        serviceUuid: String,
        characteristicUuid: String,
        completion: @escaping (Result<FlutterStandardTypedData, Error>) -> Void
    ) {
        bleManager.readCharacteristic(
            peripheralUuid: peripheralUuid,
            serviceUuid: serviceUuid,
            characteristicUuid: characteristicUuid,
            completion: completion
        )
    }

    func writeCharacteristic(
        peripheralUuid: String,
        serviceUuid: String,
        characteristicUuid: String,
        data: FlutterStandardTypedData,
        completion: @escaping (Result<Void, Error>) -> Void
    ) {
        bleManager.writeCharacteristic(
            peripheralUuid: peripheralUuid,
            serviceUuid: serviceUuid,
            characteristicUuid: characteristicUuid,
            data: data,
            completion: completion
        )
    }

    func subscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) throws {
        bleManager.subscribeCharacteristic(peripheralUuid: peripheralUuid, serviceUuid: serviceUuid, characteristicUuid: characteristicUuid)
    }

    func unsubscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) throws {
        bleManager.unsubscribeCharacteristic(peripheralUuid: peripheralUuid, serviceUuid: serviceUuid, characteristicUuid: characteristicUuid)
    }

    func getBluetoothState() throws -> String {
        return bleManager.getBluetoothState()
    }

    func isPeripheralConnected(uuid: String) throws -> Bool {
        return bleManager.isPeripheralConnected(uuid: uuid)
    }

    // ── Diagnostics ──

    func startRssiStreaming(uuid: String) throws {
        bleManager.isRssiStreamingEnabled = true
    }

    func stopRssiStreaming(uuid: String) throws {
        bleManager.isRssiStreamingEnabled = false
    }

    func getDeviceDiagnostics(uuid: String, completion: @escaping (Result<BleDeviceDiagnostics, Error>) -> Void) {
        completion(.success(bleManager.getDeviceDiagnostics(uuid: uuid)))
    }

    func getBatteryHistory(uuid: String, completion: @escaping (Result<[BleBatteryPoint], Error>) -> Void) {
        completion(.success(bleManager.getBatteryHistory(uuid: uuid)))
    }

    func hasCompanionDeviceAssociation() throws -> Bool {
        return true // iOS uses state restoration
    }

    func requestCompanionDeviceAssociation(deviceAddress: String, completion: @escaping (Result<String, Error>) -> Void) {
        // No-op on iOS — state restoration handles background reconnection
        completion(.success(""))
    }

    func openBluetoothSettings() throws {
        // Try the Bluetooth-specific deep-link first; Apple has restricted this URL
        // on newer iOS versions. canOpenURL would always return false here without
        // an LSApplicationQueriesSchemes entry for App-Prefs (a non-public scheme),
        // so check the open() completion handler's success flag instead — that
        // reflects what actually happened. Fall back to the app's settings page
        // (UIApplication.openSettingsURLString) which is guaranteed to open and at
        // least gets the user into Settings.
        let bluetoothUrl = URL(string: "App-Prefs:root=Bluetooth")
        let appSettingsUrl = URL(string: UIApplication.openSettingsURLString)
        DispatchQueue.main.async {
            if let url = bluetoothUrl {
                UIApplication.shared.open(url, options: [:]) { success in
                    if !success, let settingsUrl = appSettingsUrl {
                        UIApplication.shared.open(settingsUrl, options: [:], completionHandler: nil)
                    }
                }
            } else if let url = appSettingsUrl {
                UIApplication.shared.open(url, options: [:], completionHandler: nil)
            }
        }
    }
}
