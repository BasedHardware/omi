import WidgetKit
import SwiftUI

@main
struct BatteryWidgetBundle: WidgetBundle {
    var body: some Widget {
        OmiBatteryWidget()
        OmiUpNextWidget()
        OmiLatestWidget()
        if #available(iOS 16.1, *) {
            OmiCaptureLiveActivity()
        }
    }
}
