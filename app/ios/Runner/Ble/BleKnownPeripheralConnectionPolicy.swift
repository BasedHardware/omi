enum BleKnownPeripheralConnectionAction: Equatable {
  case rediscoverServices
  case connect
}

/// Chooses how a Dart connection request repairs a CoreBluetooth peripheral.
///
/// CoreBluetooth can preserve a physical connection across process relaunch
/// without replaying `didConnect`. Treating that state as "nothing to do"
/// strands Dart before `onDeviceReady`; rediscovering services republishes the
/// GATT boundary and lets the storage-first stream resume.
enum BleKnownPeripheralConnectionPolicy {
  static func action(isConnected: Bool) -> BleKnownPeripheralConnectionAction {
    isConnected ? .rediscoverServices : .connect
  }
}
