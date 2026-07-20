import OmiTheme
import SwiftUI

// MARK: - View data (design layer). The host maps real stores → these.

/// One "needs you" approval or today follow-up row.
struct SBFollowUpRow: Identifiable {
  let id: String
  let label: String
  let sub: String
  let cta: String
  var run: () -> Void
  var skip: () -> Void
}

/// A conversation / calendar item in the TODAY list.
struct SBTodayItem: Identifiable {
  let id: String
  let title: String
  let meta: String
  let time: String
  var upcoming: Bool = false
  var onOpen: (() -> Void)? = nil
}

struct SBTodayData {
  var name: String?
  var isFreshUser: Bool
  var isListening: Bool
  var screenOn: Bool
  var followUps: [SBFollowUpRow]
  var liveConversationTitle: String?
  var conversations: [SBTodayItem]
  var upcoming: [SBTodayItem]
  var focusToday: String?
  var suggestedQuestions: [String]
}

// MARK: - Today

struct SBTodayPage: View {
  @Environment(\.sbTheme) private var sb

  let data: SBTodayData
  var onToggleListening: () -> Void
  var onToggleScreen: () -> Void
  var onAsk: (String) -> Void
  var onViewAllFollowUps: () -> Void
  var onStartRecording: () -> Void

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        captureToggles
        if data.isFreshUser {
          freshHero
        } else {
          seasoned
        }
      }
      .padding(.horizontal, 30)
      .padding(.bottom, 20)
    }
  }

  // MARK: capture toggle chips

  private var captureToggles: some View {
    HStack(spacing: 8) {
      toggleChip(
        on: data.isListening,
        onLabel: "Listening", offLabel: "Mic off",
        action: onToggleListening)
      toggleChip(
        on: data.screenOn,
        onLabel: "Screen", offLabel: "Screen off",
        action: onToggleScreen)
      Spacer()
    }
    .padding(.bottom, 14)
  }

  private func toggleChip(on: Bool, onLabel: String, offLabel: String, action: @escaping () -> Void)
    -> some View
  {
    Button(action: action) {
      HStack(spacing: 7) {
        Text(on ? onLabel : offLabel)
          .geist(size: 12.5)
          .foregroundStyle(on ? sb.ink(.w85) : sb.ink(.w45))
        // mini toggle
        ZStack(alignment: on ? .trailing : .leading) {
          RoundedRectangle(cornerRadius: 7).fill(on ? sb.ink : sb.ink(.w15))
            .frame(width: 24, height: 13)
          Circle().fill(on ? sb.inkInverted : sb.ink(.w6)).frame(width: 10, height: 10)
            .padding(.horizontal, 1.5)
        }
      }
      .padding(.leading, 11).padding(.trailing, 6).padding(.vertical, 5)
      .overlay(Capsule().stroke(sb.ink(.w12), lineWidth: 1))
    }
    .buttonStyle(.plain)
  }

  // MARK: fresh user hero

  private var freshHero: some View {
    VStack(spacing: 0) {
      Spacer(minLength: 30)
      SBLogo(size: 30, spinning: data.isListening)
      Text(data.name.map { "Hey \($0). I'm ready." } ?? "Hey. I'm ready.")
        .geist(size: 25, weight: .semibold, tracking: 25 * -0.02)
        .foregroundStyle(sb.ink)
        .padding(.top, 16)
      Text(
        data.isListening
          ? "I'm listening — continuously. Follow-ups appear as conversations end."
          : "I'm paused. Turn me on and I listen continuously — or I'll wake for your next meeting."
      )
      .geist(size: 14)
      .foregroundStyle(sb.ink(.w45))
      .multilineTextAlignment(.center)
      .padding(.top, 4)

      if !data.isListening {
        Button(action: onStartRecording) {
          Text("● Start recording")
            .geist(size: 14, weight: .semibold)
            .foregroundStyle(sb.inkInverted)
            .padding(.horizontal, 22).padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 11).fill(sb.ink))
        }
        .buttonStyle(.plain)
        .padding(.top, 16)
      }

      VStack(spacing: 7) {
        ForEach(data.suggestedQuestions, id: \.self) { q in
          Button { onAsk(q) } label: {
            Text(q)
              .geist(size: 14)
              .foregroundStyle(sb.ink(.w85))
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.horizontal, 13).padding(.vertical, 9)
              .overlay(RoundedRectangle(cornerRadius: 11).stroke(sb.ink(.w14), lineWidth: 1))
          }
          .buttonStyle(.plain)
        }
      }
      .frame(maxWidth: 340)
      .padding(.top, 18)

      Text("After each meeting, follow-ups land here — the email drafted, the task filed. You tap, I send.")
        .geist(size: 12.5)
        .foregroundStyle(sb.ink(.w3))
        .multilineTextAlignment(.center)
        .padding(.top, 18)
      Spacer(minLength: 20)
    }
    .frame(maxWidth: .infinity)
  }

  // MARK: seasoned user

  private var seasoned: some View {
    VStack(alignment: .leading, spacing: 0) {
      if !data.followUps.isEmpty {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
          SBSectionLabel(text: "Today's follow-ups · \(data.followUps.count)")
          Text("view all ›")
            .geistMono(size: 12)
            .foregroundStyle(sb.ink(.w25))
            .onTapGesture(perform: onViewAllFollowUps)
        }
        ForEach(data.followUps) { fu in
          followUpRow(fu)
        }
      } else {
        Text("No follow-ups waiting. Go have meetings — I'll handle the aftermath.")
          .geist(size: 14)
          .foregroundStyle(sb.ink(.w35))
          .padding(.vertical, 14)
          .frame(maxWidth: .infinity, alignment: .leading)
          .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
      }

      SBSectionLabel(text: "Today")
        .padding(.top, 18).padding(.bottom, 2)

      if data.isListening, let live = data.liveConversationTitle {
        HStack(spacing: 12) {
          HStack(spacing: 8) {
            Text(live).geist(size: 15).foregroundStyle(sb.ink(.w9))
            SBMiniWaveform()
          }
          Spacer()
          Text("live").geistMono(size: 12.5).foregroundStyle(sb.ink(.w4))
          Text("now").geistMono(size: 12.5).foregroundStyle(sb.ink(.w25))
        }
        .padding(.vertical, 11)
        .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
      }

      ForEach(data.conversations) { item in
        todayRow(item, titleToken: .w85)
      }
      ForEach(data.upcoming) { item in
        todayRow(item, titleToken: .w5)
      }

      if let focus = data.focusToday {
        HStack(spacing: 12) {
          Text("Focus").geist(size: 15).foregroundStyle(sb.ink(.w85))
          Spacer()
          Text(focus).geistMono(size: 12.5).foregroundStyle(sb.ink(.w4))
          Text("›").geistMono(size: 12.5).foregroundStyle(sb.ink(.w25))
        }
        .padding(.vertical, 11)
        .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
      }
    }
  }

  private func followUpRow(_ fu: SBFollowUpRow) -> some View {
    HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 2) {
        Text(fu.label).geist(size: 15.5, weight: .medium).foregroundStyle(sb.ink)
        Text(fu.sub).geist(size: 13).foregroundStyle(sb.ink(.w42))
      }
      Spacer(minLength: 8)
      SBInkButton(title: fu.cta, size: 13.5, horizontalPadding: 13, verticalPadding: 5, action: fu.run)
      Button(action: fu.skip) {
        Text("Later").geist(size: 13.5).foregroundStyle(sb.ink(.w45))
      }
      .buttonStyle(.plain)
    }
    .padding(.vertical, 13)
    .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
  }

  private func todayRow(_ item: SBTodayItem, titleToken: SBInk) -> some View {
    HStack(spacing: 12) {
      Text(item.title).geist(size: 15).foregroundStyle(sb.ink(titleToken))
      Spacer(minLength: 8)
      Text(item.meta).geistMono(size: 12.5).foregroundStyle(sb.ink(.w4))
      Text(item.time).geistMono(size: 12.5).foregroundStyle(sb.ink(.w25))
    }
    .padding(.vertical, 11)
    .contentShape(Rectangle())
    .onTapGesture { item.onOpen?() }
    .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
  }
}

/// A tiny 3-bar live-audio glyph for the "live" conversation row.
struct SBMiniWaveform: View {
  @Environment(\.sbTheme) private var sb
  @State private var phase = false
  var body: some View {
    HStack(spacing: 2) {
      ForEach(0..<3, id: \.self) { i in
        RoundedRectangle(cornerRadius: 1)
          .fill(sb.ink)
          .frame(width: 2, height: phase ? 9 : 4)
          .animation(
            .easeInOut(duration: 1).repeatForever().delay(Double(i) * 0.2), value: phase)
      }
    }
    .frame(height: 10)
    .onAppear { phase = true }
  }
}
