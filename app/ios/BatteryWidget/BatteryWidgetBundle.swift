import WidgetKit
import SwiftUI

@main
struct BatteryWidgetBundle: WidgetBundle {
    var body: some Widget {
        OmiBatteryWidget()
        if #available(iOS 16.1, *) {
            OmiCaptureLiveActivity()
        }
    }
}
