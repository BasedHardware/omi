import OmiKit
import SwiftUI

// ReadStatus ported from `react-native/src/ui/ReadStatus.tsx` — the page
// completeness footnote with its exact copy rules.

public struct ReadStatusView: View {
    public let label: String
    public let page: ReadPageState

    public init(label: String, page: ReadPageState) {
        self.label = label
        self.page = page
    }

    public var body: some View {
        if visible {
            Text(detail)
                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(Palette.textMuted)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 12)
        }
    }

    private var visible: Bool {
        if page.complete && page.completenessStatus == .complete { return false }
        if !page.hasMore && page.completenessStatus == .unknown { return false }
        return true
    }

    private var detail: String {
        let lower = label.lowercased()
        if page.hasMore {
            if page.nextCursor == nil {
                return "Showing the first 50 \(lower). More may be available."
            }
            return "More \(lower) are available."
        }
        if page.completenessStatus == .degraded {
            return "\(label) may be temporarily incomplete."
        }
        if page.completenessStatus == .partial {
            return "\(label) are a partial view."
        }
        return "\(label) are incomplete."
    }
}
