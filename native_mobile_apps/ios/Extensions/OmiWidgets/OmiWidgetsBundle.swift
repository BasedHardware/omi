import SwiftUI
import WidgetKit

/// Everything Omi shows outside the app: the Omi's battery, the next tasks, the latest
/// conversation, and the Live Activity for a recording or a task Omi works on.
@main
struct OmiWidgetsBundle: WidgetBundle {
    var body: some Widget {
        OmiBatteryWidget()
        OmiUpNextWidget()
        OmiLatestWidget()
        OmiLiveActivity()
    }
}
