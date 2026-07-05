// iOS Display bridge (DAT 0.7.0 `MWDATDisplay`).
//
// Owns:
//   - One `DeviceSession` targeting a (display-capable) device.
//   - One `Display` capability attached to that session.
//   - The display-state EventSink and the display-events EventSink
//     (tap / click / playback callbacks routed back to Dart by id).
//
// Declarative view trees arrive from Dart as plain JSON (`[String: Any]`),
// which we rebuild into Meta's `MWDATDisplay` component DSL
// (`FlexBox` / `Text` / `Image` / `Button` / `Icon` / `VideoPlayer`) and hand
// to `Display.send(_:)`. Interaction callbacks carry the Dart-assigned
// `callbackId` so the Dart side can dispatch to the right closure.
//
// All Meta SDK calls run on the main actor, matching `Wearables.shared`.

import Flutter
import UIKit
#if canImport(MWDATCore)
import MWDATCore
#endif
#if canImport(MWDATDisplay)
import MWDATDisplay
#endif

@MainActor
final class MetaDisplayManager: NSObject {
  /// The DeviceSession we created via `Wearables.shared.createSession`.
  private var deviceSession: DeviceSession?

  /// The display capability attached to `deviceSession`.
  private var display: Display?

  private var stateToken: (any AnyListenerToken)?

  /// The `onPlaybackEventId` of the `VideoPlayer` currently on screen, used to
  /// route `Display.onPlaybackEvent` back to the right Dart closure.
  private var currentVideoCallbackId: String?

  // EventSinks set by the plugin when Dart subscribes.
  fileprivate var displayStateSink: FlutterEventSink?
  fileprivate var displayEventsSink: FlutterEventSink?

  func setDisplayStateSink(_ sink: FlutterEventSink?) { displayStateSink = sink }
  func setDisplayEventsSink(_ sink: FlutterEventSink?) { displayEventsSink = sink }

  // MARK: - Lifecycle

  /// Creates a DeviceSession (targeting `deviceUUID` when given, otherwise the
  /// first paired device), attaches the display capability, and starts it.
  func startDisplaySession(deviceUUID: String?) async throws {
    if display != nil { return }

    let allIds = Wearables.shared.devices
    let selector: any DeviceSelector
    if let uuid = deviceUUID, let match = allIds.first(where: { $0 == uuid }) {
      selector = SpecificDeviceSelector(device: match)
    } else if let pick = allIds.first {
      selector = SpecificDeviceSelector(device: pick)
    } else {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -20,
        userInfo: [NSLocalizedDescriptionKey:
          "No glasses are currently paired. Open Meta AI to pair " +
          "Ray-Ban Display glasses, then try again."],
      )
    }

    let session = try Wearables.shared.createSession(deviceSelector: selector)
    self.deviceSession = session

    if session.state != .started {
      try session.start()
      try await Self.waitForDeviceSessionStarted(
        session,
        timeoutNs: 45_000_000_000,
      )
    }

    let display = try session.addDisplay()
    self.display = display

    display.onPlaybackEvent = { [weak self] event in
      Task { @MainActor in self?.handlePlaybackEvent(event) }
    }
    stateToken = display.statePublisher.listen { [weak self] state in
      Task { @MainActor in self?.displayStateSink?(Self.encode(state)) }
    }

    await display.start()
  }

  /// Rebuilds [json] into the `MWDATDisplay` DSL and sends it to the glasses.
  func sendDisplayView(_ json: [String: Any]) async throws {
    guard let display = display else {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -21,
        userInfo: [NSLocalizedDescriptionKey:
          "No display session - call startDisplaySession first"],
      )
    }

    if (json["type"] as? String) == "videoPlayer" {
      let url = json["uri"] as? String ?? ""
      currentVideoCallbackId = json["onPlaybackEventId"] as? String
      let video = MWDATDisplay.VideoPlayer(
        provider: .uri(url),
        codec: .mp4,
        onError: { [weak self] _ in
          Task { @MainActor in self?.emitPlayback(eventName: "error") }
        },
      )
      try await display.send(video)
    } else {
      currentVideoCallbackId = nil
      let view = buildFlexBox(json)
      try await display.send(view)
    }
  }

  /// Detaches the display capability and tears down its device session.
  func stopDisplaySession() async {
    stateToken = nil
    currentVideoCallbackId = nil
    if let display = display {
      await display.stop()
    }
    display = nil
    deviceSession?.stop()
    deviceSession = nil
  }

  // MARK: - Callback plumbing

  private func emitCallback(_ id: String, type: String) {
    displayEventsSink?(["callbackId": id, "type": type] as [String: Any])
  }

  private func handlePlaybackEvent(_ event: VideoPlaybackEvent) {
    emitPlayback(eventName: Self.playbackWireName(event))
  }

  private func emitPlayback(eventName: String) {
    guard let id = currentVideoCallbackId else { return }
    displayEventsSink?(
      ["callbackId": id, "type": "playback", "event": eventName] as [String: Any]
    )
  }

  // MARK: - Tree builders

  private func buildChildren(_ json: [String: Any]) -> [any ViewComponent] {
    let kids = json["children"] as? [[String: Any]] ?? []
    return kids.compactMap { buildComponent($0) }
  }

  private func buildComponent(_ json: [String: Any]) -> (any ViewComponent)? {
    switch json["type"] as? String {
    case "flexBox": return buildFlexBox(json)
    case "text": return buildText(json)
    case "image": return buildImage(json)
    case "button": return buildButton(json)
    case "icon": return buildIcon(json)
    // `videoPlayer` is a root-only DisplayableView, not a nestable component.
    default: return nil
    }
  }

  private func buildFlexBox(_ json: [String: Any]) -> MWDATDisplay.FlexBox {
    let padding: MWDATDisplay.EdgeInsets? = (json["padding"] as? Int)
      .map { MWDATDisplay.EdgeInsets(all: CGFloat($0)) }

    // `FlexBox`'s content is a `@ComponentBuilder` result builder, so we
    // yield the precomputed children through it rather than returning an
    // array directly (the builder has no array `buildExpression`).
    let children = buildChildren(json)
    var box = MWDATDisplay.FlexBox(
      direction: Self.direction(json["direction"] as? String),
      spacing: CGFloat((json["spacing"] as? Int) ?? 0),
      alignment: Self.alignment(json["alignment"] as? String),
      crossAlignment: Self.alignment(json["crossAlignment"] as? String),
      wrap: (json["wrap"] as? Bool) ?? false,
      padding: padding,
    ) {
      for child in children { child }
    }

    if let bg = json["background"] as? String {
      box = box.background(Self.background(bg))
    }
    if let grow = json["flexGrow"] as? Double {
      box = box.flexGrow(Float(grow))
    }
    if let tapId = json["onTapId"] as? String {
      box = box.onTap { [weak self] in
        Task { @MainActor in self?.emitCallback(tapId, type: "tap") }
      }
    }
    return box
  }

  private func buildText(_ json: [String: Any]) -> MWDATDisplay.Text {
    MWDATDisplay.Text(
      json["text"] as? String ?? "",
      style: Self.textStyle(json["style"] as? String),
      color: Self.textColor(json["color"] as? String),
    )
  }

  private func buildImage(_ json: [String: Any]) -> MWDATDisplay.Image {
    MWDATDisplay.Image(
      uri: json["uri"] as? String ?? "",
      sizePreset: Self.imageSize(json["sizePreset"] as? String),
      cornerRadius: Self.cornerRadius(json["cornerRadius"] as? String),
    )
  }

  private func buildButton(_ json: [String: Any]) -> MWDATDisplay.Button {
    let iconName = (json["iconName"] as? String)
      .flatMap { MWDATDisplay.IconName(rawValue: $0) }
    let onClick: (@Sendable () -> Void)? = (json["onClickId"] as? String)
      .map { id in
        { [weak self] in
          Task { @MainActor in self?.emitCallback(id, type: "click") }
        }
      }
    return MWDATDisplay.Button(
      label: json["label"] as? String ?? "",
      style: Self.buttonStyle(json["style"] as? String),
      iconName: iconName,
      onClick: onClick,
    )
  }

  private func buildIcon(_ json: [String: Any]) -> MWDATDisplay.Icon {
    let name = (json["iconName"] as? String)
      .flatMap { MWDATDisplay.IconName(rawValue: $0) } ?? .checkmark
    return MWDATDisplay.Icon(name: name, style: .filled)
  }

  // MARK: - Enum mapping

  private static func direction(_ value: String?) -> MWDATDisplay.Direction {
    switch value {
    case "row": return .row
    case "column": return .column
    default: return .column
    }
  }

  private static func alignment(_ value: String?) -> MWDATDisplay.Alignment {
    switch value {
    case "center": return .center
    case "end": return .end
    case "start": return .start
    default: return .start
    }
  }

  private static func textStyle(_ value: String?) -> MWDATDisplay.TextStyle {
    switch value {
    case "heading": return .heading
    case "meta": return .meta
    default: return .body
    }
  }

  private static func textColor(_ value: String?) -> MWDATDisplay.TextColor {
    value == "secondary" ? .secondary : .primary
  }

  private static func imageSize(_ value: String?) -> MWDATDisplay.ImageSize {
    value == "icon" ? .icon : .fill
  }

  private static func cornerRadius(
    _ value: String?,
  ) -> MWDATDisplay.CornerRadius {
    switch value {
    case "small": return .small
    // The display SDK only ships none/small/medium; large collapses to medium.
    case "medium", "large": return .medium
    default: return .none
    }
  }

  private static func buttonStyle(
    _ value: String?,
  ) -> MWDATDisplay.ButtonStyle {
    value == "secondary" ? .secondary : .primary
  }

  private static func background(
    _ value: String?,
  ) -> MWDATDisplay.Background {
    value == "card" ? .card : .none
  }

  private static func encode(_ state: DisplayState) -> Int {
    switch state {
    case .starting: return 0
    case .started: return 1
    case .stopping: return 2
    case .stopped: return 3
    @unknown default: return 3
    }
  }

  /// Maps an iOS `VideoPlaybackEvent` to the wire token the Dart
  /// `DisplayPlaybackEventType` keys on. Derived from `String(describing:)` so
  /// it tolerates SDK additions to the playback-event enum.
  private static func playbackWireName(_ event: VideoPlaybackEvent) -> String {
    let raw = String(describing: event.type)
    if raw.hasPrefix("started") || raw.hasPrefix("playing") { return "playing" }
    if raw.hasPrefix("paused") { return "paused" }
    if raw.hasPrefix("ended") { return "ended" }
    if raw.hasPrefix("stopped") { return "stopped" }
    if raw.hasPrefix("error") { return "error" }
    return "unknown"
  }

  // MARK: - DeviceSession wait

  /// Polls `session.state` until it reaches `.started`, throwing on timeout or
  /// an early `.stopped`. Mirrors `MetaSessionManager`'s helper.
  private static func waitForDeviceSessionStarted(
    _ session: DeviceSession,
    timeoutNs: UInt64,
  ) async throws {
    let pollIntervalNs: UInt64 = 250_000_000
    let maxIterations = max(1, Int(timeoutNs / pollIntervalNs))
    for _ in 0..<maxIterations {
      if session.state == .started { return }
      if session.state == .stopped {
        throw NSError(
          domain: "meta_wearables_dat_flutter",
          code: -22,
          userInfo: [NSLocalizedDescriptionKey:
            "DeviceSession stopped before reaching .started"],
        )
      }
      try? await Task.sleep(nanoseconds: pollIntervalNs)
    }
    session.stop()
    throw NSError(
      domain: "meta_wearables_dat_flutter",
      code: -23,
      userInfo: [NSLocalizedDescriptionKey:
        "Glasses did not connect in time. Take them out of the case " +
        "and put them on, then try again."],
    )
  }
}
