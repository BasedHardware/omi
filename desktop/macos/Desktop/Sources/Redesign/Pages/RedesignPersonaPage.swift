import SwiftUI

/// The redesigned "how I sound as you" persona page — mockup `persona.html`,
/// light-styled. Renders the user's learned Tone & Style guide from the backend
/// (`GET /v1/users/tone-guide`): the sounds-like/not-like contrast + trait
/// defaults come from `persona_summary`, and the full long guide (`guide_text`)
/// is rendered below. Falls back to illustrative copy until a guide exists.
struct RedesignPersonaPage: View {
  @State private var guide: ToneGuideResponse?
  @State private var loaded = false

  // Trait fallbacks (used only until a real guide is loaded).
  @AppStorage("persona.shortAndDirect") private var shortAndDirect = true
  @AppStorage("persona.warmNotFormal") private var warmNotFormal = true
  @AppStorage("persona.emojiNowAndThen") private var emojiNowAndThen = true
  @AppStorage("persona.matchEachPerson") private var matchEachPerson = true

  private var persona: PersonaSummary? { guide?.personaSummary }

  private var soundsLike: String {
    persona?.soundsLike
      ?? "sending it now — rebased on main, summary's in the description. ping me if anything's off 👍"
  }
  private var notLike: String {
    persona?.notLike
      ?? "Hello, please find the pull request attached for your kind review at your earliest convenience."
  }

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

        // The full learned guide — the long, detailed voice writeup.
        if let text = guide?.guideText, !text.isEmpty {
          fullGuideSection(text)
        }

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
    .task {
      if loaded { return }
      loaded = true
      guide = try? await APIClient.shared.getToneGuide()
    }
  }

  // MARK: - Voice contrast card

  private var voiceCard: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 0) {
        Text("You usually sound like").inkCaption()

        // Casual draft — the dashed `.draft-compose` style, built inline.
        Text("\u{201C}\(soundsLike)\u{201D}")
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
        Text("\u{201C}\(notLike)\u{201D}")
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

      if let traits = persona?.traits, !traits.isEmpty {
        // Read-only reflections of the learned voice (derived from the fingerprint).
        ForEach(Array(traits.enumerated()), id: \.element.id) { index, trait in
          toneRow(
            trait.label, trait.subtitle, .constant(trait.on),
            showDivider: index < traits.count - 1)
        }
      } else {
        toneRow("Short and direct", "Get to it. No filler.", $shortAndDirect)
        toneRow("Warm, not formal", "Friendly, lowercase-ish.", $warmNotFormal)
        toneRow("An emoji now and then", "Only where you'd use one.", $emojiNowAndThen)
        toneRow(
          "Match each person", "Looser with friends, tighter with work.", $matchEachPerson,
          showDivider: false)
      }
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

  // MARK: - Full learned guide

  private func fullGuideSection(_ text: String) -> some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack {
        Text("The full write-up").inkH3()
        Spacer()
        if let n = guide?.sampleCount, n > 0 {
          Text("from \(n) messages").inkCaption()
        }
      }
      .padding(.bottom, 8)

      InkCard {
        GuideProse(text: text)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
  }
}

/// Lightweight Markdown renderer for the tone guide: `##`/`###` headings, `-`/`*`
/// bullets, and paragraphs with inline **bold**/*italic* — styled in the Ink system
/// so the long guide reads like the reference "Tone & Style" writeup.
private struct GuideProse: View {
  let text: String

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
        switch block.kind {
        case .h2:
          Text(block.content)
            .font(InkFont.serif(19, .semibold))
            .foregroundColor(Ink.ink)
            .padding(.top, 6)
        case .h3:
          Text(block.content)
            .font(InkFont.sans(14, .semibold))
            .foregroundColor(Ink.ink)
            .padding(.top, 4)
        case .bullet:
          HStack(alignment: .top, spacing: 8) {
            Text("•").font(InkFont.sans(14)).foregroundColor(Ink.muted)
            inline(block.content)
          }
        case .paragraph:
          inline(block.content)
        }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .textSelection(.enabled)
  }

  private func inline(_ s: String) -> some View {
    Text(attributed(s))
      .font(InkFont.sans(14))
      .foregroundColor(Ink.body)
      .frame(maxWidth: .infinity, alignment: .leading)
      .fixedSize(horizontal: false, vertical: true)
  }

  private func attributed(_ s: String) -> AttributedString {
    (try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
      ?? AttributedString(s)
  }

  private struct Block {
    enum Kind { case h2, h3, bullet, paragraph }
    let kind: Kind
    let content: String
  }

  private var blocks: [Block] {
    text.split(separator: "\n", omittingEmptySubsequences: true).compactMap { raw in
      let line = raw.trimmingCharacters(in: .whitespaces)
      if line.isEmpty { return nil }
      if line.hasPrefix("### ") { return Block(kind: .h3, content: String(line.dropFirst(4))) }
      if line.hasPrefix("## ") { return Block(kind: .h2, content: String(line.dropFirst(3))) }
      if line.hasPrefix("# ") { return Block(kind: .h2, content: String(line.dropFirst(2))) }
      if line.hasPrefix("- ") || line.hasPrefix("* ") {
        return Block(kind: .bullet, content: String(line.dropFirst(2)))
      }
      return Block(kind: .paragraph, content: line)
    }
  }
}
