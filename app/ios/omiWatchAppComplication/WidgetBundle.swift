// Created by Barrett Jacobsen

import WidgetKit
import SwiftUI

@main
struct OmiComplicationBundle: WidgetBundle {
    var body: some Widget {
        OmiDeviceMonitorWidget()
        QuickRecordWidget()
        AskOmiWidget()
    }
}
