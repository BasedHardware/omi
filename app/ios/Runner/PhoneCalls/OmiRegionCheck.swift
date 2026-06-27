import Foundation
import CoreTelephony

/// Detects whether CallKit should be disabled based on device region.
/// Apple requires CallKit to be deactivated for apps available in China.
struct OmiRegionCheck {
    /// Returns true if CallKit usage is restricted (currently: China).
    static var isCallKitRestricted: Bool {
        // Primary: device locale region
        let region: String
        if #available(iOS 16, *) {
            region = Locale.current.region?.identifier ?? ""
        } else {
            region = Locale.current.regionCode ?? ""
        }
        if region == "CN" {
            print("OmiRegionCheck: CallKit restricted (locale region: CN)")
            return true
        }

        // Fallback: carrier Mobile Country Code (MCC 460 = China)
        let networkInfo = CTTelephonyNetworkInfo()
        if let carriers = networkInfo.serviceSubscriberCellularProviders {
            for (_, carrier) in carriers {
                if carrier.mobileCountryCode == "460" {
                    print("OmiRegionCheck: CallKit restricted (carrier MCC: 460)")
                    return true
                }
            }
        }

        return false
    }
}
