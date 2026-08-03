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

struct ConnectorCard: View {
  let name: String
  let systemIcon: String
  let tint: Color
  let isConnected: Bool
  let statusText: String
  let actionTitle: String?
  let actionEnabled: Bool
  let action: () -> Void

  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        ZStack {
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(tint.opacity(0.16))
            .frame(width: 28, height: 28)
          Image(systemName: systemIcon)
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(tint)
        }
        Spacer(minLength: 6)
        Circle()
          .fill(isConnected ? Color(red: 0.15, green: 0.78, blue: 0.44) : sb.ink(.w18))
          .frame(width: 8, height: 8)
      }

      Text(name)
        .geist(size: 15, weight: .semibold)
        .foregroundStyle(sb.ink)

      Text(statusText)
        .geist(size: 12)
        .foregroundStyle(sb.ink(.w45))
        .lineLimit(2)
        .fixedSize(horizontal: false, vertical: true)

      Spacer(minLength: 0)

      if let actionTitle {
        Button(action: action) {
          Text(actionTitle)
            .geist(size: 12.5, weight: .medium)
            .foregroundStyle(actionEnabled ? sb.ink(.w85) : sb.ink(.w35))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 7)
            .background(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(sb.ink(.w18), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(!actionEnabled)
      } else {
        Text("Coming soon")
          .geist(size: 12, weight: .medium)
          .foregroundStyle(sb.ink(.w25))
          .frame(maxWidth: .infinity)
          .padding(.vertical, 7)
      }
    }
    .padding(11)
    // Height comes from content, never a constant: the status line can wrap to
    // two lines (X shows "@handle · synced 1w ago") and a fixed height clipped
    // the action button. maxHeight lets every card match the tallest in the row.
    .frame(width: 152, alignment: .topLeading)
    .frame(maxHeight: .infinity, alignment: .topLeading)
    .sbCard(radius: 14)
  }
}
