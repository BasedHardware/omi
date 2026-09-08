import OmiTheme
import SwiftUI

/// Lead of the generic floating-bar notification card: kind glyph plus the
/// category-aware copy stack. Extracted so `FloatingControlBarView` does not
/// grow past the product-file line-count freeze while the title/body layout
/// learns not to shout the Settings category louder than the actual content.
struct FloatingBarNotificationCardLead: View {
  let copy: ProactiveNotificationCopy.CardLines
  var messageLineLimit: Int = 3
  var footer: String? = nil

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      ZStack {
        RoundedRectangle(cornerRadius: 13, style: .continuous)
          .fill(
            LinearGradient(
              colors: [Color.white.opacity(0.18), Color.white.opacity(0.08)],
              startPoint: .top,
              endPoint: .bottom
            )
          )
          .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
              .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
          )
          .frame(width: 44, height: 44)

        Image(systemName: copy.systemImage)
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(.white)
      }

      VStack(alignment: .leading, spacing: 3) {
        if let caption = copy.caption {
          Text(caption)
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(.white.opacity(0.5))
            .lineLimit(1)
        }
        Text(copy.heading)
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(.white)
          .lineLimit(copy.detail == nil ? 3 : 1)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)
        if let detail = copy.detail, !detail.isEmpty {
          Text(detail)
            .scaledFont(size: OmiType.body)
            .foregroundColor(.white.opacity(0.78))
            .lineLimit(messageLineLimit)
            .lineSpacing(1.5)
            .fixedSize(horizontal: false, vertical: true)
        }
        if let footer, !footer.isEmpty {
          Text(footer)
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundColor(.white.opacity(0.45))
            .lineLimit(1)
        }
      }
    }
  }
}
