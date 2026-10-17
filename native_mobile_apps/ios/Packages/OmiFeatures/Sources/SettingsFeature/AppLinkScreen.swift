import OmiDesign
import OmiService
import SwiftUI

/// An app opened from a link (`h.omi.me/apps/<id>`, Flutter `openAppLink`): its page once it
/// loads, or Flutter's "not available" when the backend does not know it.
public struct AppLinkScreen: View {
    @Environment(AppCatalogStore.self) private var catalog
    @Environment(\.dismiss) private var dismiss
    let appID: String
    @State private var notFound = false

    public init(appID: String) {
        self.appID = appID
    }

    public var body: some View {
        NavigationStack {
            Group {
                if let detail = catalog.details[appID] {
                    AppDetailScreen(appID: appID, preview: detail.app)
                } else if notFound {
                    ContentUnavailableView(L("appNotAvailable"), systemImage: "square.grid.2x2")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(DS.Palette.background)
                        .accessibilityIdentifier("appLink.unavailable")
                } else {
                    ProgressView()
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(L("close")) { dismiss() }
                }
            }
        }
        .task {
            await catalog.loadDetail(appID)
            notFound = catalog.details[appID] == nil
        }
    }
}
