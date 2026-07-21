import AppKit
import OmiTheme
import SwiftUI

/// The Second Brain conversational onboarding — a chat with Omi that streams
/// word-by-word and performs real side-effects. Replaces the legacy wizard.
struct SBOnboardingView: View {
  @Environment(\.sbTheme) private var sb
  @StateObject private var model: SBOnboardingModel

  /// Same dune background as sign-in, for a continuous entry experience.
  private static let backgroundImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "signin_bg", withExtension: "png") else { return nil }
    return NSImage(contentsOf: url)
  }()

  init(appState: AppState, chatProvider: ChatProvider, onComplete: (() -> Void)?) {
    _model = StateObject(
      wrappedValue: SBOnboardingModel(appState: appState, chatProvider: chatProvider, onComplete: onComplete))
  }

  var body: some View {
    ZStack {
      if let bg = Self.backgroundImage {
        Image(nsImage: bg)
          .resizable()
          .scaledToFill()
          .overlay(
            LinearGradient(
              colors: [.black.opacity(0.4), .black.opacity(0.5), .black.opacity(0.72)],
              startPoint: .top, endPoint: .bottom)
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .clipped()
          .ignoresSafeArea()
      } else {
        SBWallpaper()
      }
      panel
        .frame(width: 540, height: min(640, 900))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .overlay(alignment: .topTrailing) {
      Button(action: { model.skip() }) {
        Text("Skip")
          .geist(size: 13).foregroundStyle(sb.ink(.w45))
          .padding(.horizontal, 14).padding(.vertical, 7)
          .background(
            Capsule().fill(Color.white.opacity(0.06))
              .background(.ultraThinMaterial, in: Capsule())
          )
          .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
      }
      .buttonStyle(.plain)
      .help("Skip onboarding and go to your second brain")
      .padding(.top, 20).padding(.trailing, 24)
    }
    .onAppear { model.begin() }
  }

  private var panel: some View {
    VStack(spacing: 0) {
      ScrollViewReader { proxy in
        ScrollView {
          VStack(alignment: .leading, spacing: 14) {
            ForEach(model.thread) { msg in
              messageRow(msg)
            }
            if let streaming = model.streamingText {
              omiRow(streaming)
            }
            if model.typing {
              HStack(spacing: 10) {
                SBLogo(size: 16, spinning: true)
                Text("omi is typing…").geist(size: 12.5).foregroundStyle(sb.ink(.w4))
              }
            }
            if model.showWidget {
              widget.padding(.leading, 26).padding(.top, 2)
                .id("widget")
            }
            Color.clear.frame(height: 4).id("bottom")
          }
          .padding(.horizontal, 28).padding(.top, 26).padding(.bottom, 10)
        }
        .onChange(of: model.thread.count) { _, _ in scrollDown(proxy) }
        .onChange(of: model.showWidget) { _, _ in scrollDown(proxy) }
        .onChange(of: model.streamingText) { _, _ in scrollDown(proxy) }
      }
      // No progress dots — the user shouldn't count steps or feel a finish line.
      Color.clear.frame(height: 14)
    }
    .background(
      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .fill(Color.white.opacity(0.05))
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    )
    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(Color.white.opacity(0.12), lineWidth: 1))
    .shadow(color: .black.opacity(0.5), radius: 60, y: 30)
  }

  private func scrollDown(_ proxy: ScrollViewProxy) {
    withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo("bottom", anchor: .bottom) }
  }

  @ViewBuilder private func messageRow(_ msg: SBOnboardingModel.Msg) -> some View {
    if msg.isOmi { omiRow(msg.text) } else { meRow(msg.text) }
  }

  private func omiRow(_ text: String) -> some View {
    HStack(alignment: .top, spacing: 10) {
      SBLogo(size: 16, opacity: 0.9)
      Text(text).geist(size: 15.5).foregroundStyle(sb.ink(.w88)).lineSpacing(3)
        .frame(maxWidth: 380, alignment: .leading)
      Spacer(minLength: 0)
    }
  }

  private func meRow(_ text: String) -> some View {
    HStack {
      Spacer(minLength: 40)
      Text(text).geist(size: 15).foregroundStyle(sb.ink)
        .padding(.horizontal, 13).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 13, style: .continuous).fill(sb.ink(.w1)))
        .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(sb.ink(.w14), lineWidth: 1))
    }
  }

  // MARK: - Widgets per step

  @ViewBuilder private var widget: some View {
    switch model.step {
    case .promise: promiseWidget
    case .name: nameWidget
    case .role: roleWidget
    case .meet: meetWidget
    case .perm: permWidget
    case .files: filesWidget
    case .ptt: pttWidget
    case .launch: launchWidget
    case .calendar: calendarWidget
    case .capture: captureWidget
    }
  }

  private var promiseWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        trustRow("OPEN", "Every line of me is on GitHub.")
        Divider().overlay(sb.ink(.w08))
        trustRow("LOCAL", "I can think entirely on this Mac.")
        Divider().overlay(sb.ink(.w08))
        trustRow("YOURS", "Pause me from the notch. Delete anything, forever.")
      }
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Set up Omi →") { model.answerPromise() }
    }
  }

  private func trustRow(_ tag: String, _ text: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text(tag).geistMono(size: 11.5, weight: .medium).foregroundStyle(sb.ink(.w4)).frame(width: 52, alignment: .leading)
      Text(text).geist(size: 14).foregroundStyle(sb.ink(.w85))
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 14).padding(.vertical, 12)
  }

  private var nameWidget: some View {
    HStack(spacing: 8) {
      TextField("your name", text: $model.nameDraft)
        .textFieldStyle(.plain).geist(size: 15, weight: .medium).foregroundStyle(sb.ink)
        .padding(.horizontal, 13).padding(.vertical, 9)
        .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w06)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w12), lineWidth: 1))
        .onSubmit { model.answerName() }
      SBInkButton(title: "→", horizontalPadding: 15, verticalPadding: 9) { model.answerName() }
    }
    .frame(maxWidth: 360, alignment: .leading)
  }

  private var roleWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      FlowChips(items: ["Student", "Sales", "Consultant", "Founder", "Engineer", "Creator"]) { r in
        model.pickRole(r)
      }
      HStack(spacing: 8) {
        TextField("or just say it in your own words…", text: $model.roleDraft)
          .textFieldStyle(.plain).geist(size: 14).foregroundStyle(sb.ink)
          .padding(.horizontal, 13).padding(.vertical, 9)
          .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w06)))
          .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w12), lineWidth: 1))
          .onSubmit { model.answerRoleText() }
        SBInkButton(title: "→", horizontalPadding: 15, verticalPadding: 9) { model.answerRoleText() }
      }
      .frame(maxWidth: 360)
    }
  }

  private var meetWidget: some View {
    VStack(alignment: .leading, spacing: 7) {
      meetChip("inperson", "In person", "rooms · offices · lectures")
      meetChip("video", "Video calls", "Zoom · Meet · Teams")
      meetChip("both", "Both", "most days, a mix")
    }
    .frame(maxWidth: 360, alignment: .leading)
  }

  private func meetChip(_ key: String, _ label: String, _ sub: String) -> some View {
    Button { model.pickMeet(key, label: label) } label: {
      HStack(spacing: 6) {
        Text(label).geist(size: 14).foregroundStyle(sb.ink(.w85))
        Text(sub).geist(size: 12).foregroundStyle(sb.ink(.w4))
        Spacer()
      }
      .padding(.horizontal, 14).padding(.vertical, 11)
      .frame(maxWidth: .infinity, alignment: .leading)
      .overlay(RoundedRectangle(cornerRadius: 11).stroke(sb.ink(.w14), lineWidth: 1))
    }
    .buttonStyle(.plain)
  }

  private var permWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        ForEach(model.permKeys, id: \.self) { key in
          permRow(key)
        }
      }
      .padding(.horizontal, 14)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: model.anyPermGranted ? "Done ✓" : "Skip for now") { model.answerPerms() }
    }
  }

  private func permRow(_ key: String) -> some View {
    let meta = SBOnboardingView.permMeta(key)
    return HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 1) {
        Text(meta.name).geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
        Text(meta.why).geist(size: 12).foregroundStyle(sb.ink(.w4))
      }
      Spacer(minLength: 8)
      permTrailing(model.state(for: key)) { model.requestPerm(key) }
    }
    .padding(.vertical, 9)
  }

  private var filesWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 12) {
        VStack(alignment: .leading, spacing: 1) {
          Text("Full Disk Access").geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
          Text("answers can cite your files · read-only, stays on this Mac").geist(size: 12).foregroundStyle(sb.ink(.w4))
        }
        Spacer(minLength: 8)
        permTrailing(model.fdaState) { model.requestFullDiskAccess() }
      }
      .padding(.horizontal, 14).padding(.vertical, 9)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: model.fdaState == .on ? "Continue" : "Skip for now") { model.answerFiles() }
    }
  }

  private var pttWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 8) {
        Image(systemName: "mic.fill").font(.system(size: 12)).foregroundStyle(sb.ink(.w7))
        Text("Hold").geist(size: 14).foregroundStyle(sb.ink(.w85))
        keycap("fn")
        Text("and just talk — I answer out loud.").geist(size: 14).foregroundStyle(sb.ink(.w85))
      }
      HStack(spacing: 12) {
        VStack(alignment: .leading, spacing: 1) {
          Text("Accessibility").geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
          Text("catches the hold-fn shortcut anywhere on your Mac").geist(size: 12).foregroundStyle(sb.ink(.w4))
        }
        Spacer(minLength: 8)
        permTrailing(model.accState) { model.requestAccessibility() }
      }
      .padding(.horizontal, 14).padding(.vertical, 9)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: model.accState == .on ? "Continue" : "Skip for now") { model.answerPtt() }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  private func keycap(_ text: String) -> some View {
    Text(text)
      .geistMono(size: 12, weight: .medium)
      .foregroundStyle(sb.ink(.w9))
      .padding(.horizontal, 8).padding(.vertical, 3)
      .background(RoundedRectangle(cornerRadius: 6).fill(sb.ink(.w08)))
      .overlay(RoundedRectangle(cornerRadius: 6).stroke(sb.ink(.w14), lineWidth: 1))
  }

  private var launchWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 12) {
        VStack(alignment: .leading, spacing: 1) {
          Text("Launch at login").geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
          Text("I reopen automatically after a restart or quit").geist(size: 12).foregroundStyle(sb.ink(.w4))
        }
        Spacer(minLength: 8)
        SBToggleSwitch(isOn: Binding(get: { model.launchAtLogin }, set: { model.toggleLaunch($0) }))
      }
      .padding(.horizontal, 14).padding(.vertical, 9)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Continue") { model.answerLaunch() }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  @ViewBuilder
  private func permTrailing(_ state: SBOnboardingModel.PermState, action: @escaping () -> Void) -> some View {
    switch state {
    case .on: Text("✓ on").geistMono(size: 12).foregroundStyle(sb.ink(.w6))
    case .waiting: Text("macOS…").geistMono(size: 12).foregroundStyle(sb.ink(.w4))
    case .ask:
      Button(action: action) {
        Text("Allow").geist(size: 13, weight: .semibold).foregroundStyle(sb.inkInverted)
          .padding(.horizontal, 12).padding(.vertical, 4)
          .background(RoundedRectangle(cornerRadius: 7).fill(sb.ink))
      }
      .buttonStyle(.plain)
    }
  }

  private var calendarWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      Button { model.connectCalendar() } label: {
        HStack(spacing: 9) {
          GoogleLogo().frame(width: 14, height: 14)
          Text(calLabel).geist(size: 14, weight: .semibold).foregroundStyle(sb.inkInverted)
        }
        .padding(.horizontal, 18).padding(.vertical, 9)
        .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink))
      }
      .buttonStyle(.plain)
      if model.calState == "needsSignIn" {
        Text("Sign into Google in your browser, then try again.").geist(size: 12.5).foregroundStyle(sb.ink(.w4))
      }
      Button { model.skipCalendar() } label: {
        Text("Skip — you'll lose automatic meeting detection").geist(size: 13).foregroundStyle(sb.ink(.w35))
      }
      .buttonStyle(.plain)
    }
  }

  private var calLabel: String {
    switch model.calState {
    case "connecting": return "Connecting…"
    case "on": return "✓ Google Calendar connected"
    default: return "Connect Google Calendar"
    }
  }

  private var captureWidget: some View {
    VStack(spacing: 8) {
      Button { model.captureContinuous() } label: {
        Text("● Start listening — continuously").geist(size: 14, weight: .semibold).foregroundStyle(sb.inkInverted)
          .frame(maxWidth: .infinity).padding(.vertical, 11)
          .background(RoundedRectangle(cornerRadius: 11).fill(sb.ink))
      }
      .buttonStyle(.plain)
      Button { model.captureMeetingsOnly() } label: {
        HStack(spacing: 4) {
          Text("Only during meetings").geist(size: 14).foregroundStyle(sb.ink(.w85))
          Text("· from my calendar").geist(size: 12).foregroundStyle(sb.ink(.w4))
        }
        .frame(maxWidth: .infinity).padding(.vertical, 11)
        .overlay(RoundedRectangle(cornerRadius: 11).stroke(sb.ink(.w18), lineWidth: 1))
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: 340, alignment: .leading)
  }

  static func permMeta(_ key: String) -> (name: String, why: String) {
    switch key {
    case "microphone": return ("Microphone", "hears your side of conversations")
    case "system_audio": return ("System audio", "hears the other side — Zoom, Meet, calls")
    default: return (key, "")
    }
  }
}

/// Simple wrapping chip row.
private struct FlowChips: View {
  @Environment(\.sbTheme) private var sb
  let items: [String]
  let onPick: (String) -> Void
  var body: some View {
    let cols = [GridItem(.adaptive(minimum: 90), spacing: 7)]
    LazyVGrid(columns: cols, alignment: .leading, spacing: 7) {
      ForEach(items, id: \.self) { item in
        Button { onPick(item) } label: {
          Text(item).geist(size: 14).foregroundStyle(sb.ink(.w85))
            .padding(.horizontal, 16).padding(.vertical, 8)
            .overlay(Capsule().stroke(sb.ink(.w14), lineWidth: 1))
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }
}
