import SwiftUI

struct TryAskingPopupView: View {
  let suggestions: [String]
  let onAsk: (String) -> Void
  let onDismiss: () -> Void

  private let calloutAmber = Color(hex: 0xE3BF63)

  var body: some View {
    GeometryReader { proxy in
      let popupWidth = min(max(proxy.size.width - 72, 560), 660)
      let popupHeight = min(max(proxy.size.height - 80, 360), 520)

      ZStack {
        Color.black.opacity(0.52)
          .ignoresSafeArea()
          .onTapGesture(perform: onDismiss)

        VStack {
          popupContent
        }
        .frame(width: popupWidth, height: popupHeight)
        .padding(26)
        .background(
          RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(OmiColors.backgroundSecondary.opacity(0.98))
        )
        .overlay(
          RoundedRectangle(cornerRadius: 28, style: .continuous)
            .stroke(calloutAmber.opacity(0.18), lineWidth: 1)
        )
        .overlay(alignment: .topLeading) {
          RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(
              LinearGradient(
                colors: [calloutAmber.opacity(0.12), .clear],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
              )
            )
            .allowsHitTesting(false)
        }
        .overlay(alignment: .topTrailing) {
          Button(action: onDismiss) {
            Image(systemName: "xmark")
              .font(.system(size: 12, weight: .bold))
              .foregroundColor(OmiColors.textTertiary)
              .frame(width: 28, height: 28)
              .background(
                Circle()
                  .fill(OmiColors.backgroundTertiary)
              )
          }
          .buttonStyle(.plain)
          .padding(18)
        }
        .shadow(color: .black.opacity(0.4), radius: 30, x: 0, y: 16)
      }
    }
  }

  private var popupContent: some View {
    VStack(alignment: .leading, spacing: 16) {
      HStack(spacing: 8) {
        Image(systemName: "sparkles")
          .font(.system(size: 11, weight: .semibold))
        Text("Suggested first ask")
          .font(.system(size: 12, weight: .semibold))
      }
      .foregroundColor(calloutAmber)
      .padding(.horizontal, 10)
      .padding(.vertical, 6)
      .background(
        Capsule()
          .fill(calloutAmber.opacity(0.14))
      )

      Text("What would you like to ask omi first?")
        .font(.system(size: 32, weight: .semibold, design: .serif))
        .foregroundColor(OmiColors.textPrimary)

      Text("Pick one and we’ll run it through the floating bar with your real context.")
        .font(.system(size: 15))
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)

      VStack(spacing: 14) {
        ForEach(suggestions, id: \.self) { suggestion in
          Button {
            onAsk(suggestion)
          } label: {
            HStack(spacing: 10) {
              Image(systemName: "sparkles")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(calloutAmber)

              Text(suggestion)
                .font(.system(size: 15, weight: .medium))
                .multilineTextAlignment(.leading)

              Spacer(minLength: 0)

              Image(systemName: "arrow.up.right")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(OmiColors.textQuaternary)
            }
            .contentShape(Rectangle())
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 16)
            .padding(.vertical, 16)
            .background(
              RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(OmiColors.backgroundTertiary.opacity(0.82))
            )
            .overlay(
              RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(OmiColors.backgroundQuaternary.opacity(0.9), lineWidth: 1)
            )
          }
          .buttonStyle(.plain)
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .padding(12)
  }
}

struct PromptSuggestionBanner: View {
  let suggestions: [String]
  let onOpen: () -> Void
  let onAsk: (String) -> Void
  let onDismiss: () -> Void

  private let calloutAmber = Color(hex: 0xC9972D)
  private let calloutCream = Color(hex: 0xF4E3AA)

  private func compactLabel(for suggestion: String) -> String {
    if suggestion.hasPrefix("What should I focus on today to ship ") {
      return "What should I focus on today?"
    }
    if suggestion.hasPrefix("Based on my recent work, what am I probably blocked on in ") {
      return "What am I probably blocked on?"
    }
    if suggestion == "Which follow-ups from my recent emails matter most today?" {
      return "Which email follow-ups matter most?"
    }
    if suggestion == "Where can I create more focus time in my calendar this week?" {
      return "Where can I create more focus time?"
    }
    if suggestion.hasPrefix("Help me break \"") {
      return "What are the next 3 steps?"
    }
    if suggestion == "What should I prioritize this week based on what you know about me?" {
      return "What should I prioritize this week?"
    }
    if suggestion == "What on my screen matters most right now?" {
      return "What matters most on my screen?"
    }
    if suggestion == "What is the highest-leverage thing I can do in the next 30 minutes?" {
      return "What should I do in the next 30 minutes?"
    }
    return suggestion
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Button(action: onOpen) {
        VStack(alignment: .leading, spacing: 14) {
          HStack(spacing: 8) {
            Image(systemName: "sparkles")
              .font(.system(size: 11, weight: .semibold))
            Text("Suggested first ask")
              .font(.system(size: 12, weight: .semibold))
          }
          .foregroundColor(Color.black.opacity(0.68))

          Text("Next step -> Ask omi")
            .font(.system(size: 20, weight: .semibold, design: .serif))
            .foregroundColor(Color.black.opacity(0.86))

          Text("Use your real screen and your existing context to get value quickly. Tap to open a few suggested questions.")
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(Color.black.opacity(0.72))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .buttonStyle(.plain)

      HStack(spacing: 8) {
        ForEach(Array(suggestions.prefix(3)), id: \.self) { suggestion in
          Button {
            onAsk(suggestion)
          } label: {
            Text(compactLabel(for: suggestion))
              .font(.system(size: 12, weight: .semibold))
              .foregroundColor(Color.black.opacity(0.74))
              .lineLimit(1)
              .padding(.horizontal, 12)
              .padding(.vertical, 9)
              .background(
                Capsule()
                  .fill(Color.white.opacity(0.5))
              )
          }
          .buttonStyle(.plain)
        }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(22)
    .background(
      RoundedRectangle(cornerRadius: 20, style: .continuous)
        .fill(
          LinearGradient(
            colors: [calloutCream, Color(hex: 0xEFD07A)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
          )
        )
    )
    .overlay(
      RoundedRectangle(cornerRadius: 20, style: .continuous)
        .stroke(calloutAmber.opacity(0.24), lineWidth: 1)
    )
    .overlay(alignment: .topTrailing) {
      ZStack(alignment: .topTrailing) {
        Circle()
          .fill(Color.white.opacity(0.3))
          .frame(width: 120, height: 120)
          .blur(radius: 34)
          .offset(x: 34, y: -42)
          .allowsHitTesting(false)

        Button(action: onDismiss) {
          Image(systemName: "xmark")
            .font(.system(size: 11, weight: .bold))
            .foregroundColor(Color.black.opacity(0.58))
            .frame(width: 24, height: 24)
            .background(
              Circle()
                .fill(Color.white.opacity(0.45))
            )
        }
        .buttonStyle(.plain)
        .padding(14)
      }
    }
  }
}
