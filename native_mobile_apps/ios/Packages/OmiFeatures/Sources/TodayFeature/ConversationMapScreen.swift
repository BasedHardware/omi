import MapKit
import OmiComponents
import OmiCore
import OmiDesign
import SwiftUI

/// The loaded conversations by place (Flutter `conversation_map_page`): one pin per place (~100 m),
/// a single conversation opens directly, a place with several lists them first.
struct ConversationMapScreen: View {
    let conversations: [Conversation]
    let onOpenConversation: (Conversation) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var selected: ConversationPlace?

    var body: some View {
        let places = ConversationPlace.group(conversations)
        NavigationStack {
            Group {
                if places.isEmpty {
                    OmiEmptyState(conversations.isEmpty ? L("noConversationsYet") : L("unknownLocation"), systemImage: "map")
                        .frame(maxHeight: .infinity)
                } else {
                    Map(initialPosition: Self.position(places)) {
                        ForEach(places) { place in
                            Annotation(title(place), coordinate: place.location.coordinate) { pin(place) }
                        }
                    }
                    .mapStyle(.standard(pointsOfInterest: .excludingAll))
                    .ignoresSafeArea(edges: .bottom)
                }
            }
            .background(DS.Palette.background)
            .navigationTitle(L("conversationMap"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }.accessibilityLabel(L("close"))
                }
            }
            .sheet(item: $selected) { place in placeSheet(place) }
        }
    }

    private func pin(_ place: ConversationPlace) -> some View {
        Button {
            DSHaptics.selection()
            if let only = place.conversations.first, place.conversations.count == 1 { onOpenConversation(only) } else { selected = place }
        } label: {
            Group {
                if place.conversations.count == 1 {
                    Image(systemName: "mappin").font(.system(size: 15, weight: .bold))
                } else {
                    Text("\(place.conversations.count)").font(DS.Typography.callout.weight(.bold)).monospacedDigit()
                }
            }
            .foregroundStyle(DS.Palette.onAccent)
            .frame(width: 34, height: 34)
            .background(DS.Palette.agent, in: Circle())
            .overlay(Circle().stroke(DS.Palette.card, lineWidth: 2))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title(place))
        .accessibilityIdentifier("conversationMap.place")
    }

    /// Every place in view; one place (or places close together) at neighborhood scale, not the
    /// street-level zoom `.automatic` picks for a single pin.
    static func position(_ places: [ConversationPlace]) -> MapCameraPosition {
        let latitudes = places.map(\.location.latitude)
        let longitudes = places.map(\.location.longitude)
        guard let south = latitudes.min(), let north = latitudes.max(),
              let west = longitudes.min(), let east = longitudes.max() else { return .automatic }
        let center = CLLocationCoordinate2D(latitude: (south + north) / 2, longitude: (west + east) / 2)
        let span = MKCoordinateSpan(latitudeDelta: max(0.02, (north - south) * 1.5), longitudeDelta: max(0.02, (east - west) * 1.5))
        return .region(MKCoordinateRegion(center: center, span: span))
    }

    /// A single conversation's title, else "<n> conversations".
    private func title(_ place: ConversationPlace) -> String {
        guard place.conversations.count == 1, let only = place.conversations.first else {
            return L("nativeConversationsCount", String(place.conversations.count))
        }
        return only.title.isEmpty ? L("untitledConversation") : only.title
    }

    private func placeSheet(_ place: ConversationPlace) -> some View {
        NavigationStack {
            List(place.conversations.sorted { $0.date > $1.date }) { conversation in
                Button {
                    selected = nil
                    onOpenConversation(conversation)
                } label: {
                    ConversationRow(conversation, style: .plain)
                }
                .buttonStyle(.plain)
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }
            .listStyle(.plain)
            .omiList()
            .navigationTitle(place.location.shortAddress ?? title(place))
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
    }
}
