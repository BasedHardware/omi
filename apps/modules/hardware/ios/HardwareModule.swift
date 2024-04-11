import ExpoModulesCore
import CoreBluetooth

public class HardwareModule: Module {

    var manager: L2CAPManager? = nil

    public func definition() -> ModuleDefinition {
        Name("Hardware")
        AsyncFunction("startAsync") {
            if self.manager == nil {
                self.manager = L2CAPManager()
            }
        }
        AsyncFunction("stopAsync") {
            self.manager = nil // Should deallocate everything
        }
        AsyncFunction("connectAsync") { (device: String, psm: UInt16) in
            self.manager?.connect(device: device, psm: psm)
        }
        AsyncFunction("disconnectAsync") {
            self.manager?.disconnect()
        }
    }
    
    //
    // Lifecycle
    //

    func onCreate() {
        
    }
    
    func onDestroy() {
        
    }
}

class L2CAPManager: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate, StreamDelegate {
    
    private var managerQueue = DispatchQueue.global(qos: .utility)
    private var central: CBCentralManager!
    private var connected: CBPeripheral? = nil
    private var connectedPSM: UInt16? = nil
    private var channel: CBL2CAPChannel? = nil
    
    override init() {
        super.init()
        self.central = CBCentralManager(delegate: self, queue: nil)
    }

    func connect(device: String, psm: UInt16) {

        // Check if already connected
        if (self.connected != nil) {
            print("Already connected to \(String(describing: self.connected))")
            return;
        }
        
        // Find device and persist
        let p = self.central.retrievePeripherals(withIdentifiers: [UUID(uuidString: device)!])
        if p.count == 0 {
            print("Unable to find pheripial \(device)")
        }
        let d = p[0]
        self.connected = d
        self.connectedPSM = psm
        d.delegate = self
        
        // Connect
        self.central.connect(d)
    }

    private func onConnected(channel: CBL2CAPChannel) {
        self.channel = channel
        channel.inputStream.delegate = self
        channel.outputStream.delegate = self
        channel.inputStream.schedule(in: RunLoop.main, forMode: .default)
        channel.outputStream.schedule(in: RunLoop.main, forMode: .default)
        channel.inputStream.open()
        channel.outputStream.open()
    }

    func disconnect() {
        if (self.connected != nil) {
            print("Disconnecting from \(self.connected!.identifier.uuidString)")
            
            // Channel
            self.channel?.outputStream.close()
            self.channel?.inputStream.close()
            self.channel?.inputStream.remove(from: .main, forMode: .default)
            self.channel?.outputStream.remove(from: .main, forMode: .default)
        
            self.channel?.inputStream.delegate = nil
            self.channel?.outputStream.delegate = nil
            self.channel = nil
            
            // Device
            self.central.cancelPeripheralConnection(self.connected!)
            self.connected = nil
        } else {
            print("Not connected to any device" )
        }
    }
    
    //
    // Lifecycle
    //

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        print("\(central.state)")
    }
    
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        print("didConnected to \(peripheral.identifier.uuidString)")
        if peripheral == self.connected {
            peripheral.openL2CAPChannel(CBL2CAPPSM(self.connectedPSM!))
        }
    }
    
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: (any Error)?) {
        print("didDisconnectPeripheral to \(peripheral.identifier.uuidString)")
    }
    
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: (any Error)?) {
        print("didFailToConnect to \(peripheral.identifier.uuidString)")
    }

    func peripheral(_ peripheral: CBPeripheral, didOpen channel: CBL2CAPChannel?, error: (any Error)?) {
        if error != nil {
            print("Channel open failed \(String(describing: error))")
        } else {
            print("Channel open \(String(describing: channel))")
        }
    }

    func stream(_ aStream: Stream, handle eventCode: Stream.Event) {
        switch eventCode {
        case Stream.Event.openCompleted:
            print("Stream is open")
        case Stream.Event.endEncountered:
            print("End Encountered")
        case Stream.Event.hasBytesAvailable:
            print("Bytes are available")
            // self.readBytes(from: aStream as! InputStream)
        case Stream.Event.hasSpaceAvailable:
            print("Space is available")
            // self.send()
        case Stream.Event.errorOccurred:
            print("Stream error")
        default:
            print("Unknown stream event")
        }
        // self.stateChangeCallback?(self,eventCode)
    }
}
