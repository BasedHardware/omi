import CoreBluetooth
import Foundation

/// Pure helpers for classifying CoreBluetooth pairing failures (testable without a live radio).
enum OmiBlePairingPolicy {
    private static let peerRemovedPairingInformationCode = CBError.Code.peerRemovedPairingInformation.rawValue

    static func isPairingLost(_ error: Error?) -> Bool {
        var current: Error? = error
        while let err = current {
            if isPeerRemovedPairingInformation(err) {
                return true
            }
            current = (err as NSError).userInfo[NSUnderlyingErrorKey] as? Error
        }
        return false
    }

    private static func isPeerRemovedPairingInformation(_ error: Error) -> Bool {
        if let cbError = error as? CBError, cbError.code == .peerRemovedPairingInformation {
            return true
        }
        let nsError = error as NSError
        if nsError.domain == CBError.errorDomain, nsError.code == peerRemovedPairingInformationCode {
            return true
        }
        // Some iOS builds surface CB errors only as the string domain + numeric code.
        if nsError.domain == "CBErrorDomain", nsError.code == peerRemovedPairingInformationCode {
            return true
        }
        return false
    }
}
