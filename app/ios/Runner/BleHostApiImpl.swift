import Flutter

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

    func connectPeripheral(uuid: String) throws {
        bleManager.connectPeripheral(uuid: uuid)
    }

    func disconnectPeripheral(uuid: String) throws {
        bleManager.disconnectPeripheral(uuid: uuid)
    }

    func reconnectKnownPeripheral(uuid: String) throws {
        bleManager.reconnectKnownPeripheral(uuid: uuid)
    }

    func discoverServices(peripheralUuid: String) throws {
        bleManager.discoverServices(peripheralUuid: peripheralUuid)
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

    func setAudioBatchingEnabled(enabled: Bool) throws {
        bleManager.setAudioBatchingEnabled(enabled)
    }

    func registerAudioCharacteristic(characteristicUuid: String) throws {
        bleManager.registerAudioCharacteristic(characteristicUuid)
    }
}
