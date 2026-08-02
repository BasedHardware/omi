import OmiTheme
import SwiftUI

// Row furniture for the People list, split out of PeoplePage so the page owns
// layout and these own their own presentation.

struct RelationshipPill: View {
  let text: String
  @Environment(\.sbTheme) private var sb

  /// The pipeline sometimes writes a whole sentence here. Keep the first clause
  /// so the row stays scannable instead of turning into a paragraph.
  private var label: String {
    let clause = text.split(whereSeparator: { ";.".contains($0) }).first.map(String.init) ?? text
    return clause.trimmingCharacters(in: .whitespaces)
  }

  var body: some View {
    Text(label)
      .geistMono(size: 10.5, tracking: 0.2)
      .foregroundStyle(sb.ink(.w6))
      .padding(.horizontal, 8)
      .padding(.vertical, 2)
      .background(Capsule().fill(sb.ink(.w08)))
      .lineLimit(1)
      .truncationMode(.tail)
      .frame(maxWidth: 260, alignment: .leading)
  }
}

struct ChannelDots: View {
  let channels: [PersonChannel]
  @Environment(\.sbTheme) private var sb

  var body: some View {
    HStack(spacing: 3) {
      ForEach(channels.prefix(6)) { channel in
        Circle()
          .fill(PeopleChannelPalette.color(for: channel.key))
          .frame(width: 7, height: 7)
      }
      if channels.count > 6 {
        Text("+\(channels.count - 6)")
          .geistMono(size: 9, tracking: 0)
          .foregroundStyle(sb.ink(.w35))
      }
    }
  }
}
