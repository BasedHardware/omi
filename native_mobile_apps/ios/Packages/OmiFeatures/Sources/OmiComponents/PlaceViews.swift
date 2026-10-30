import MapKit
import OmiCore
import OmiDesign
import SwiftUI

/// Where a conversation happened: a small map with its pin and the area and city (Flutter
/// `GetGeolocationWidgets`). A tap opens the place in Maps.
public struct ConversationPlaceCard: View {
    let location: ConversationLocation
    @Environment(\.openURL) private var openURL

    public init(_ location: ConversationLocation) {
        self.location = location
    }

    public var body: some View {
        Button { openURL(PlaceLinks.maps(location)) } label: {
            ZStack(alignment: .bottomLeading) {
                Map(initialPosition: .region(MKCoordinateRegion(
                    center: location.coordinate, latitudinalMeters: 800, longitudinalMeters: 800
                )), interactionModes: []) {
                    Marker("", coordinate: location.coordinate).tint(DS.Palette.agent)
                }
                .mapStyle(.standard(pointsOfInterest: .excludingAll))
                .allowsHitTesting(false)
                LinearGradient(colors: [.black.opacity(0.55), .clear], startPoint: .bottom, endPoint: .center)
                    .allowsHitTesting(false)
                Label(location.shortAddress ?? L("unknownLocation"), systemImage: "mappin.and.ellipse")
                    .font(DS.Typography.callout.weight(.medium))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .padding(DS.Spacing.md)
            }
            .frame(height: 140)
            .clipShape(RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(L("location"))
        .accessibilityValue(location.shortAddress ?? L("unknownLocation"))
        .accessibilityIdentifier("conversation.place")
    }
}

public enum PlaceLinks {
    /// Apple Maps at the point (Flutter `MapsUtil.launchMap` prefers Apple Maps on iOS).
    public static func maps(_ location: ConversationLocation) -> URL {
        var components = URLComponents(string: "https://maps.apple.com/")!
        components.queryItems = [URLQueryItem(name: "ll", value: "\(location.latitude),\(location.longitude)")]
        return components.url!
    }
}

public extension ConversationLocation {
    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}
