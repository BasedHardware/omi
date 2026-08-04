import CoreBluetooth
import Foundation

struct CharacteristicConfig: Decodable {
    let uuid: String
    let properties: [String]
    let value: [UInt8]
}

struct ServiceConfig: Decodable {
    let uuid: String
    let primary: Bool
    let characteristics: [CharacteristicConfig]
}

struct PeripheralConfig: Decodable {
    let name: String
    let advertisedServices: [String]
    let services: [ServiceConfig]
}

struct Update: Decodable {
    let uuid: String
    let value: [UInt8]
}

final class Peripheral: NSObject, CBPeripheralManagerDelegate {
    private let config: PeripheralConfig
    private var manager: CBPeripheralManager?
    private var characteristics: [CBUUID: CBMutableCharacteristic] = [:]
    private var values: [CBUUID: Data] = [:]
    private var services: [CBMutableService] = []

    init(config: PeripheralConfig) {
        self.config = config
    }

    func start() {
        for serviceConfig in config.services {
            let service = CBMutableService(type: CBUUID(string: serviceConfig.uuid), primary: serviceConfig.primary)
            service.characteristics = serviceConfig.characteristics.map { item in
                let characteristic = CBMutableCharacteristic(
                    type: CBUUID(string: item.uuid),
                    properties: properties(item.properties),
                    value: nil,
                    permissions: item.properties.contains("read") ? [.readable] : []
                )
                characteristics[characteristic.uuid] = characteristic
                values[characteristic.uuid] = Data(item.value)
                return characteristic
            }
            services.append(service)
        }
        manager = CBPeripheralManager(delegate: self, queue: nil)
    }

    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        guard peripheral.state == .poweredOn else {
            emit(["state": stateName(peripheral.state)])
            return
        }
        for service in services {
            peripheral.add(service)
        }
        peripheral.startAdvertising([
            CBAdvertisementDataLocalNameKey: config.name,
            CBAdvertisementDataServiceUUIDsKey: config.advertisedServices.map(CBUUID.init(string:))
        ])
    }

    func peripheralManagerDidStartAdvertising(_ peripheral: CBPeripheralManager, error: Error?) {
        if let error {
            emit(["state": "error", "error": error.localizedDescription])
            exit(1)
        }
        emit(["state": "advertising", "name": config.name])
    }

    func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveRead request: CBATTRequest) {
        guard characteristics[request.characteristic.uuid] != nil,
              let value = values[request.characteristic.uuid],
              request.offset <= value.count else {
            peripheral.respond(to: request, withResult: .invalidOffset)
            return
        }
        request.value = value.subdata(in: request.offset..<value.count)
        peripheral.respond(to: request, withResult: .success)
    }

    func update(_ update: Update) {
        let uuid = CBUUID(string: update.uuid)
        guard let characteristic = characteristics[uuid] else {
            emit(["state": "error", "error": "unknown characteristic \(update.uuid)"])
            return
        }
        let value = Data(update.value)
        values[uuid] = value
        let notified = manager?.updateValue(value, for: characteristic, onSubscribedCentrals: nil) ?? false
        emit(["state": "updated", "uuid": update.uuid, "notified": notified])
    }

    private func properties(_ values: [String]) -> CBCharacteristicProperties {
        values.reduce(into: CBCharacteristicProperties()) { result, value in
            if value == "read" { result.insert(.read) }
            if value == "notify" { result.insert(.notify) }
        }
    }

    private func stateName(_ state: CBManagerState) -> String {
        switch state {
        case .poweredOn: return "powered_on"
        case .poweredOff: return "powered_off"
        case .resetting: return "resetting"
        case .unauthorized: return "unauthorized"
        case .unsupported: return "unsupported"
        case .unknown: return "unknown"
        @unknown default: return "unknown"
        }
    }
}

func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value),
       let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
}

guard let first = readLine(),
      let configData = first.data(using: .utf8),
      let config = try? JSONDecoder().decode(PeripheralConfig.self, from: configData) else {
    emit(["state": "error", "error": "missing or invalid peripheral config"])
    exit(2)
}

let peripheral = Peripheral(config: config)
DispatchQueue.global().async {
    while let line = readLine() {
        guard let data = line.data(using: .utf8),
              let update = try? JSONDecoder().decode(Update.self, from: data) else {
            emit(["state": "error", "error": "invalid update"])
            continue
        }
        DispatchQueue.main.async {
            peripheral.update(update)
        }
    }
    DispatchQueue.main.async {
        exit(0)
    }
}
peripheral.start()
RunLoop.main.run()
