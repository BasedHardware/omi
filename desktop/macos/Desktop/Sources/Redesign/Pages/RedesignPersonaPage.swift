import SwiftUI

/// The redesigned "how I sound as you" persona page — mockup `persona.html`,
/// light-styled. Tone preferences persist via @AppStorage so they survive
/// relaunch (and can be read by the drafting layer).
struct RedesignPersonaPage: View {
  @AppStorage("persona.shortAndDirect") private var shortAndDirect = true
  @AppStorage("persona.warmNotFormal") private var warmNotFormal = true
  @AppStorage("persona.emojiNowAndThen") private var emojiNowAndThen = true
  @AppStorage("persona.matchEachPerson") private var matchEachPerson = true

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        Text("PERSONA").inkEyebrow()

        VStack(alignment: .leading, spacing: 8) {
          Text("How I sound as you").inkH1()
          Text(
            "I learned your voice from how you actually text. This is what I copy when I draft. Tune it any time."
          )
          .inkSmall()
          .frame(maxWidth: 520, alignment: .leading)
          .fixedSize(horizontal: false, vertical: true)
        }

        voiceCard
        defaultsSection

        HStack(spacing: 4) {
          Text("I never send without you.").inkCaption()
          Button {
            NotificationCenter.default.post(
              name: .navigateToSidebarItem, object: nil, userInfo: ["rawValue": 23])
          } label: {
            Text("See a draft →")
              .font(InkFont.sans(12, .medium))
              .foregroundColor(Ink.accentStrong)
          }
          .buttonStyle(.plain)
        }
        .padding(.top, 4)
      }
      .frame(maxWidth: 720, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  // MARK: - Voice contrast card

  private var voiceCard: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 0) {
        Text("You usually sound like").inkCaption()

        // Casual draft — the dashed `.draft-compose` style, built inline.
        Text(
          "\u{201C}sending it now — rebased on main, summary's in the description. ping me if anything's off 👍\u{201D}"
        )
        .font(InkFont.sans(14)).foregroundColor(Ink.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        .padding(EdgeInsets(top: 12, leading: 14, bottom: 12, trailing: 14))
        .background(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(Ink.accentTint)
            .overlay(
              RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(
                  Ink.accent, style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
            )
        )
        .padding(.top, 12)

        Text("Not like").inkCaption().padding(.top, 16)

        // Formal received-style bubble (`.bubble.in`).
        Text(
          "\u{201C}Hello, please find the pull request attached for your kind review at your earliest convenience.\u{201D}"
        )
        .font(InkFont.sans(13.5)).foregroundColor(Ink.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        .padding(EdgeInsets(top: 9, leading: 13, bottom: 9, trailing: 13))
        .background(
          RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(Ink.surface2)
            .overlay(
              RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Ink.hair, lineWidth: 1)
            )
        )
        .padding(.top, 8)
      }
    }
  }

  // MARK: - Tone defaults

  private var defaultsSection: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Your defaults").inkH3().padding(.bottom, 4)

      toneRow("Short and direct", "Get to it. No filler.", $shortAndDirect)
      toneRow("Warm, not formal", "Friendly, lowercase-ish.", $warmNotFormal)
      toneRow("An emoji now and then", "Only where you'd use one.", $emojiNowAndThen)
      toneRow(
        "Match each person", "Looser with friends, tighter with work.", $matchEachPerson,
        showDivider: false)
    }
  }

  private func toneRow(
    _ label: String, _ sub: String, _ isOn: Binding<Bool>, showDivider: Bool = true
  ) -> some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        VStack(alignment: .leading, spacing: 2) {
          Text(label).font(InkFont.sans(14)).foregroundColor(Ink.ink)
          Text(sub).inkCaption()
        }
        Spacer(minLength: 12)
        InkToggle(isOn: isOn)
      }
      .padding(.vertical, 13)
      if showDivider {
        Rectangle().fill(Ink.hair).frame(height: 1)
      }
    }
  }
}
