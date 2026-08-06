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

enum BleRestoredPeripheralAction: Equatable {
  case restoreConnection
  case releaseConnection
}

/// Prevents an OS-restored iOS process from silently taking the pendant away
/// from another companion host.
///
/// A foreground Flutter session always calls `manageDevice` and can reconnect.
/// Process-level CoreBluetooth restoration is only justified when the user
/// explicitly enabled Background Mode.
enum BleRestoredPeripheralPolicy {
  static func action(backgroundModeEnabled: Bool) -> BleRestoredPeripheralAction {
    backgroundModeEnabled ? .restoreConnection : .releaseConnection
  }

  static func shouldDeferConnect(requiresForegroundActivation: Bool) -> Bool {
    requiresForegroundActivation
  }

  static func shouldResumeDeferredConnect(
    requiresForegroundActivation: Bool,
    applicationIsActive: Bool
  ) -> Bool {
    requiresForegroundActivation && applicationIsActive
  }
}
