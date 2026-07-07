import AppKit
import SwiftUI

/// Shared UI building blocks for the messaging inboxes (iMessage, WhatsApp,
/// Telegram) so all three look and behave identically. Each page maps its own
/// model into these primitive-parameterized views instead of duplicating rows,
/// headers, bubbles, avatars, and the compose bar.
enum MessagingInbox {
  /// Incoming (not-from-me) bubble fill — a neutral dark gray shared by all three.
  static let incomingBubbleFill = Color(red: 0.17, green: 0.17, blue: 0.19)

  /// Greyish background for the left conversation list (the sidebar), a shade
  /// lighter than the near-black content pane so the two columns read distinctly —
  /// bringing back the look Telegram's native `List` gave.
  static let sidebarBackground = OmiColors.backgroundSecondary
  /// Selected-row fill in the list — lighter than the sidebar so selection stands out.
  static let sidebarSelection = OmiColors.backgroundTertiary

  /// Stable, readable per-sender color so "who said what" is clear at a glance in
  /// group chats. Deterministic from the name so a sender keeps the same color.
  static func senderColor(for name: String) -> Color {
    let palette: [Color] = [
      Color(red: 0.40, green: 0.71, blue: 1.00), Color(red: 0.53, green: 0.85, blue: 0.55),
      Color(red: 1.00, green: 0.71, blue: 0.40), Color(red: 0.98, green: 0.55, blue: 0.60),
      Color(red: 0.72, green: 0.64, blue: 0.98), Color(red: 0.42, green: 0.86, blue: 0.82),
      Color(red: 0.96, green: 0.80, blue: 0.36),
    ]
    // `hashValue` is randomized per process; fold the bytes ourselves so a sender
    // keeps one color for the whole session (and matches across the row + bubble).
    var h: UInt64 = 5381
    for b in name.utf8 { h = (h &* 33) &+ UInt64(b) }
    return palette[Int(h % UInt64(palette.count))]
  }

  // Cached formatters: `DateFormatter` init is expensive (locale/calendar setup) and
  // shortTime() runs on the conversation-row render path (re-invoked on every
  // selection change), so allocating one per call was needless churn.
  private static let timeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "h:mm a"
    return f
  }()
  private static let dayFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d"
    return f
  }()

  /// Compact chat-list timestamp: time today, "Yesterday", else "MMM d".
  static func shortTime(_ date: Date) -> String {
    let cal = Calendar.current
    if cal.isDateInToday(date) {
      return timeFormatter.string(from: date)
    } else if cal.isDateInYesterday(date) {
      return "Yesterday"
    } else {
      return dayFormatter.string(from: date)
    }
  }
}

// MARK: - Avatar

/// Circular avatar with a person-silhouette fallback. Decoded images are cached
/// so re-rendering the chat list (which happens on every selection change) never
/// re-decodes `Data` on the render path — a major source of open-chat lag.
struct InboxAvatar: View {
  let name: String
  let size: CGFloat
  var imageData: Data? = nil

  var body: some View {
    Group {
      if let data = imageData, let img = AvatarImageCache.image(data) {
        Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
      } else {
        Circle()
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            Image(systemName: "person.fill")
              .font(.system(size: size * 0.5))
              .foregroundColor(OmiColors.textTertiary)
          )
      }
    }
    .frame(width: size, height: size)
    .clipShape(Circle())
  }
}

/// Memoizes decoded avatar images keyed by their backing `Data` so the list can
/// re-render freely without paying `NSImage(data:)` per row every time.
enum AvatarImageCache {
  private static let cache: NSCache<NSData, NSImage> = {
    let c = NSCache<NSData, NSImage>()
    c.countLimit = 500
    return c
  }()

  static func image(_ data: Data) -> NSImage? {
    let key = data as NSData
    if let hit = cache.object(forKey: key) { return hit }
    guard let img = NSImage(data: data) else { return nil }
    cache.setObject(img, forKey: key)
    return img
  }
}

// MARK: - Conversation list row

/// A single conversation in the left list. Layout is symmetric: name + time on the
/// top line, preview + draft badge on the bottom line — so the "Draft" tag sits on
/// the right, directly under the timestamp.
struct InboxConversationRow: View {
  let name: String
  let preview: String
  let time: Date
  let avatarData: Data?
  let isSelected: Bool
  let draftReady: Bool
  /// When true, auto-reply escalated this chat: the message needs the user's input.
  /// Takes visual priority over `draftReady` — shows a "Needs you" pill instead.
  var needsInput: Bool = false
  let accent: Color

  var body: some View {
    HStack(spacing: 10) {
      InboxAvatar(name: name, size: 40, imageData: avatarData)
      VStack(alignment: .leading, spacing: 3) {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
          Text(name)
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)
          Spacer(minLength: 6)
          Text(MessagingInbox.shortTime(time))
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }
        HStack(alignment: .top, spacing: 6) {
          Text(preview)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textSecondary)
            .lineLimit(2)
            .frame(maxWidth: .infinity, alignment: .leading)
          // Show the pill ONLY once a reply has actually been drafted for this
          // chat — never on every awaiting thread. (Awaiting-reply gating lives in the
          // store, not this row.) An escalated chat shows "Needs you" and takes
          // priority over the plain "Draft ready".
          if needsInput {
            InboxNeedsInputBadge()
          } else if draftReady {
            InboxDraftBadge(accent: accent)
          }
        }
      }
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 10)
    .background(isSelected ? MessagingInbox.sidebarSelection : Color.clear)
    .contentShape(Rectangle())
  }
}

/// "Draft ready" pill used in the list row (right, under the time). Only rendered
/// when a reply has actually been drafted for the chat.
struct InboxDraftBadge: View {
  let accent: Color

  var body: some View {
    Text("Draft ready")
      .scaledFont(size: 9, weight: .semibold)
      .foregroundColor(.white)
      .padding(.horizontal, 5)
      .padding(.vertical, 1)
      .background(accent)
      .clipShape(Capsule())
      .fixedSize()
  }
}

/// Banner shown above the composer when auto-reply escalated this chat: explains why it
/// didn't auto-send, so the user reviews the pre-filled suggested draft with context.
struct InboxNeedsInputBanner: View {
  let reason: String

  var body: some View {
    HStack(spacing: 8) {
      Image(systemName: "exclamationmark.bubble.fill")
        .foregroundColor(.orange)
        .font(.system(size: 12))
      Text(
        reason.isEmpty
          ? "Auto-reply paused — this one needs you. Review the suggested reply below."
          : "Needs you: \(reason). Review the suggested reply below."
      )
      .scaledFont(size: 11, weight: .medium)
      .foregroundColor(OmiColors.textSecondary)
      .lineLimit(2)
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 8)
    .background(Color.orange.opacity(0.12))
  }
}

/// Banner shown above the composer when an availability-aware reply accepted a proposed
/// time and Omi added a tentative "hold" to the user's calendar. Confirm keeps it;
/// Discard deletes it. Shown even after a 1:1 auto-send so the user stays in control.
struct InboxHoldBanner: View {
  let hold: DraftHold
  let accent: Color
  let onConfirm: () -> Void
  let onDiscard: () -> Void

  var body: some View {
    HStack(spacing: 8) {
      Image(systemName: "calendar.badge.clock")
        .foregroundColor(accent)
        .font(.system(size: 12))
      VStack(alignment: .leading, spacing: 1) {
        Text("Tentative hold added")
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("\(hold.title) · \(hold.whenLabel)")
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
      }
      Spacer(minLength: 0)
      Button(action: onDiscard) {
        Text("Discard").scaledFont(size: 11, weight: .medium).foregroundColor(OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
      Button(action: onConfirm) {
        Text("Confirm").scaledFont(size: 11, weight: .semibold).foregroundColor(accent)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 8)
    .background(accent.opacity(0.10))
  }
}

/// "Needs you" pill: auto-reply couldn't safely answer this message and escalated it
/// for the user to review. Uses an attention color (orange) distinct from the accent
/// "Draft ready" pill so an escalated chat stands out in the list.
struct InboxNeedsInputBadge: View {
  var body: some View {
    Text("Needs you")
      .scaledFont(size: 9, weight: .semibold)
      .foregroundColor(.white)
      .padding(.horizontal, 5)
      .padding(.vertical, 1)
      .background(Color.orange)
      .clipShape(Capsule())
      .fixedSize()
  }
}

// MARK: - Chat detail header

/// Detail-pane header: avatar + name on the left, a trailing accessory (the
/// auto-reply toggle) on the right. Horizontal layout shared by all three.
struct InboxChatHeader<Trailing: View>: View {
  let name: String
  let avatarData: Data?
  @ViewBuilder var trailing: () -> Trailing

  var body: some View {
    HStack(spacing: 10) {
      InboxAvatar(name: name, size: 30, imageData: avatarData)
      Text(name)
        .scaledFont(size: 14, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .lineLimit(1)
      Spacer()
      trailing()
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 10)
    .background(OmiColors.backgroundPrimary)
  }
}

// MARK: - Message bubble

/// One chat bubble: text, optional inline image + caption, optional group-sender
/// label and avatar gutter. Accent fills the from-me bubble.
struct InboxBubble: View {
  let text: String
  let isFromMe: Bool
  let accent: Color
  /// Group + incoming: reserve the 26pt avatar column so consecutive bubbles align.
  var reserveGutter: Bool = false
  /// Non-nil only at the start of a sender's run (group chats) — shown as the
  /// colored name label and the gutter avatar.
  var senderName: String? = nil
  var senderAvatarData: Data? = nil
  /// Absolute path to an inline image to render above the (optional) caption.
  var imagePath: String? = nil
  var caption: String? = nil

  @State private var loadedImage: NSImage?

  var body: some View {
    HStack(alignment: .bottom, spacing: 6) {
      if isFromMe { Spacer(minLength: 60) }
      if reserveGutter {
        if senderName != nil {
          InboxAvatar(name: senderName ?? "?", size: 26, imageData: senderAvatarData)
        } else {
          Color.clear.frame(width: 26, height: 26)
        }
      }
      VStack(alignment: isFromMe ? .trailing : .leading, spacing: 2) {
        if let sender = senderName {
          Text(sender)
            .scaledFont(size: 11, weight: .semibold)
            .foregroundColor(MessagingInbox.senderColor(for: sender))
            .padding(.leading, 4)
        }
        if let path = imagePath {
          imageView(path)
          if let caption { textBubble(caption) }
        } else {
          textBubble(text)
        }
      }
      if !isFromMe { Spacer(minLength: 60) }
    }
  }

  @ViewBuilder
  private func textBubble(_ text: String) -> some View {
    Text(text)
      .scaledFont(size: 13)
      .foregroundColor(isFromMe ? .white : OmiColors.textPrimary)
      .padding(.horizontal, 12)
      .padding(.vertical, 8)
      .background(isFromMe ? accent : MessagingInbox.incomingBubbleFill)
      .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
  }

  @ViewBuilder
  private func imageView(_ path: String) -> some View {
    Group {
      if let img = loadedImage {
        Image(nsImage: img)
          .resizable()
          .aspectRatio(contentMode: .fit)
          .frame(maxWidth: 220, maxHeight: 260)
          .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
      } else {
        RoundedRectangle(cornerRadius: 16, style: .continuous)
          .fill(MessagingInbox.incomingBubbleFill)
          .frame(width: 160, height: 160)
          .overlay(
            Image(systemName: "photo")
              .font(.system(size: 28))
              .foregroundColor(OmiColors.textTertiary)
          )
      }
    }
    .task(id: path) {
      loadedImage = await InboxAttachmentImageCache.shared.image(atPath: path)
    }
  }
}

// MARK: - Compose bar

/// Bottom compose bar shared by all three inboxes: a rounded input pill that shows
/// a placeholder, an "Omi is drafting…" state, and a circular send button.
struct InboxComposeBar: View {
  @Binding var text: String
  let placeholder: String
  let accent: Color
  let canSend: Bool
  let onSend: () -> Void
  var isDrafting: Bool = false
  var errorText: String? = nil
  var infoText: String? = nil

  var body: some View {
    VStack(spacing: 6) {
      if let errorText {
        Text(errorText).scaledFont(size: 11).foregroundColor(.orange)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      if let infoText {
        Text(infoText).scaledFont(size: 11).foregroundColor(accent)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      HStack(alignment: .center, spacing: 10) {
        ZStack(alignment: .leading) {
          if text.isEmpty && !isDrafting {
            Text(placeholder).scaledFont(size: 13).foregroundColor(OmiColors.textTertiary)
              .padding(.leading, 14)
          }
          if isDrafting {
            HStack(spacing: 6) {
              ProgressView().controlSize(.small)
              Text("Omi is drafting…").scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
            }.padding(.leading, 14)
          }
          TextEditor(text: $text)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textPrimary)
            .scrollContentBackground(.hidden)
            .frame(minHeight: 20, maxHeight: 68)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 10)
            .opacity(isDrafting ? 0 : 1)
        }
        .padding(.vertical, 6)
        .background(
          RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
        )
        .overlay(
          RoundedRectangle(cornerRadius: 18, style: .continuous)
            .stroke(OmiColors.textTertiary.opacity(0.15), lineWidth: 1)
        )

        Button { onSend() } label: {
          Image(systemName: "arrow.up.circle.fill")
            .font(.system(size: 30))
            .foregroundColor(canSend ? accent : OmiColors.textTertiary.opacity(0.5))
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
      }
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 8)
    .background(OmiColors.backgroundPrimary)
    .overlay(alignment: .top) { Divider().overlay(OmiColors.textTertiary.opacity(0.15)) }
  }
}

// MARK: - Attachment image cache

/// Loads and caches attachment images off the SwiftUI render path (actor +
/// NSCache) so scrolling never decodes images synchronously in a view body.
/// Shared by all three inboxes.
actor InboxAttachmentImageCache {
  static let shared = InboxAttachmentImageCache()

  private let cache: NSCache<NSString, NSImage> = {
    let cache = NSCache<NSString, NSImage>()
    cache.countLimit = 200
    cache.totalCostLimit = 100 * 1024 * 1024  // 100MB
    return cache
  }()

  func image(atPath path: String) -> NSImage? {
    let key = path as NSString
    if let cached = cache.object(forKey: key) { return cached }
    if Task.isCancelled { return nil }
    guard let image = NSImage(contentsOfFile: path) else { return nil }
    cache.setObject(image, forKey: key, cost: Self.decodedByteCost(of: image))
    return image
  }

  private static func decodedByteCost(of image: NSImage) -> Int {
    var pixels = 0
    for rep in image.representations {
      pixels = max(pixels, rep.pixelsWide * rep.pixelsHigh)
    }
    if pixels == 0 { pixels = Int(image.size.width * image.size.height) }
    return max(1, pixels * 4)
  }
}
