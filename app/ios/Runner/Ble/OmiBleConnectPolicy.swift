import Foundation

/// What a connect request does for a peripheral's current link state
/// (FC-already-satisfied-request-as-noop). A state-restored peripheral is often
/// already connected before Flutter listens, so "already connected" must
/// re-deliver the readiness event the caller waits for, never return silently.
enum OmiBleConnectPolicy {
    enum Link: Equatable {
        case disconnected
        case connecting
        case connected
    }

    enum Action: Equatable {
        /// Ask CoreBluetooth to connect; didConnect then discovers and announces.
        case connect
        /// Services are known: replay the ready event to the caller now.
        case announceReady
        /// Connected but not fully discovered: discovery ends in the ready event.
        case discoverServices
    }

    static func action(link: Link, servicesDiscovered: Bool) -> Action {
        switch link {
        case .connected:
            return servicesDiscovered ? .announceReady : .discoverServices
        case .connecting, .disconnected:
            return .connect
        }
    }
}
