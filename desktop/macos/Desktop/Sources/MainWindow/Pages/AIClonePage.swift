import SwiftUI

/// AI Clone page — an AI-powered messaging assistant that learns to reply to your
/// contacts in your voice. Contacts are the user's real top iMessage correspondents
/// (ranked by message count), read locally via `IMessageReaderService`.
struct AIClonePage: View {
  private enum LoadState: Equatable {
    case loading
    case loaded
    case needsFullDiskAccess
    case empty
    case failed(String)
  }

  @State private var state: LoadState = .loading
  @State private var contacts: [IMessageContact] = []
  @State private var selectedHandles: Set<String> = []
  /// How many top contacts to auto-select. Defaults to 5; re-applied whenever changed.
  @State private var autoSelectCount = 5
  /// Bumped to force `.task` to re-run (e.g. after the user grants Full Disk Access).
  @State private var reloadToken = UUID()

  private var maxSelectable: Int { contacts.count }

  var body: some View {
    VStack(alignment: .leading, spacing: 24) {
      header

      content
    }
    .padding(28)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(OmiColors.backgroundPrimary)
    .task(id: reloadToken) { await load() }
  }

  // MARK: - Header

  private var header: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("AI Clone")
        .scaledFont(size: 28, weight: .bold)
        .foregroundColor(OmiColors.textPrimary)

      Text("Your AI-powered messaging assistant")
        .scaledFont(size: 15, weight: .regular)
        .foregroundColor(OmiColors.textSecondary)
    }
  }

  // MARK: - Content (state machine)

  @ViewBuilder
  private var content: some View {
    switch state {
    case .loading:
      centered {
        ProgressView()
          .scaleEffect(1.2)
          .tint(.white)
        Text("Reading your Messages history…")
          .scaledFont(size: 14, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }

    case .needsFullDiskAccess:
      fullDiskAccessPrompt

    case .empty:
      centered {
        Image(systemName: "message")
          .font(.system(size: 34, weight: .regular))
          .foregroundColor(OmiColors.textQuaternary)
        Text("No conversations found")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Once you have direct message threads in Messages, your top contacts will appear here.")
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 360)
      }

    case .failed(let message):
      centered {
        Image(systemName: "exclamationmark.triangle")
          .font(.system(size: 32, weight: .regular))
          .foregroundColor(OmiColors.warning)
        Text("Couldn't load contacts")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(message)
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 360)
        reloadButton(title: "Try Again")
      }

    case .loaded:
      loadedContent
    }
  }

  private var loadedContent: some View {
    VStack(alignment: .leading, spacing: 16) {
      autoSelectControl

      ScrollView {
        LazyVStack(spacing: 10) {
          ForEach(Array(contacts.enumerated()), id: \.element.id) { index, contact in
            AICloneContactRow(
              rank: index + 1,
              contact: contact,
              isSelected: selectedHandles.contains(contact.id),
              onToggle: { toggleSelection(contact) }
            )
          }
        }
        .padding(.bottom, 8)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
  }

  // MARK: - Auto-select control

  private var autoSelectControl: some View {
    HStack(spacing: 12) {
      Text("Auto-select top")
        .scaledFont(size: 14, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      Text("\(autoSelectCount)")
        .scaledFont(size: 14, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .frame(minWidth: 22)

      Stepper("", value: $autoSelectCount, in: 0...max(0, maxSelectable))
        .labelsHidden()
        .onChange(of: autoSelectCount) { applyTopXSelection() }

      Text("contact\(autoSelectCount == 1 ? "" : "s") by message count")
        .scaledFont(size: 14, weight: .regular)
        .foregroundColor(OmiColors.textTertiary)

      Spacer()

      Text("\(selectedHandles.count) selected")
        .scaledFont(size: 13, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
  }

  // MARK: - Full Disk Access prompt

  private var fullDiskAccessPrompt: some View {
    centered {
      Image(systemName: "lock.shield")
        .font(.system(size: 34, weight: .regular))
        .foregroundColor(OmiColors.textSecondary)

      Text("Full Disk Access required")
        .scaledFont(size: 16, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      Text(
        "Omi reads your Messages history locally on this Mac to learn how you write. "
          + "Grant Full Disk Access in System Settings, then reload."
      )
      .scaledFont(size: 13, weight: .regular)
      .foregroundColor(OmiColors.textTertiary)
      .multilineTextAlignment(.center)
      .frame(maxWidth: 380)

      HStack(spacing: 10) {
        Button(action: { IMessageReaderService.shared.openFullDiskAccessSettings() }) {
          Text("Open System Settings")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.textPrimary))
        }
        .buttonStyle(.plain)

        reloadButton(title: "Reload")
      }
      .padding(.top, 4)
    }
  }

  // MARK: - Reusable pieces

  private func reloadButton(title: String) -> some View {
    Button(action: { reloadToken = UUID() }) {
      Text(title)
        .scaledFont(size: 13, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
        .background(
          RoundedRectangle(cornerRadius: 8)
            .stroke(OmiColors.border, lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }

  private func centered<Inner: View>(@ViewBuilder _ inner: () -> Inner) -> some View {
    VStack(spacing: 12) {
      inner()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  // MARK: - Data + selection

  private func load() async {
    state = .loading
    do {
      let result = try await IMessageReaderService.shared.topContacts(limit: 20)
      contacts = result
      if result.isEmpty {
        selectedHandles = []
        state = .empty
        return
      }
      // Default: auto-select the top 5 (clamped to however many contacts exist).
      autoSelectCount = min(5, result.count)
      applyTopXSelection()
      state = .loaded
    } catch IMessageReaderError.fullDiskAccessDenied {
      state = .needsFullDiskAccess
    } catch IMessageReaderError.chatDatabaseNotFound {
      state = .empty
    } catch {
      state = .failed(error.localizedDescription)
    }
  }

  /// Select exactly the top-N contacts by rank. Called on load and whenever the user
  /// changes N via the stepper; per-row toggles override this afterward.
  private func applyTopXSelection() {
    let clamped = max(0, min(autoSelectCount, contacts.count))
    selectedHandles = Set(contacts.prefix(clamped).map { $0.id })
  }

  private func toggleSelection(_ contact: IMessageContact) {
    if selectedHandles.contains(contact.id) {
      selectedHandles.remove(contact.id)
    } else {
      selectedHandles.insert(contact.id)
    }
  }
}

// MARK: - Contact Row

private struct AICloneContactRow: View {
  let rank: Int
  let contact: IMessageContact
  let isSelected: Bool
  let onToggle: () -> Void

  @State private var isHovered = false

  var body: some View {
    HStack(spacing: 14) {
      // Selection toggle — neutral white/gray, no accent color (per AGENTS.md: no purple).
      Button(action: onToggle) {
        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
          .font(.system(size: 20, weight: .regular))
          .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textQuaternary)
      }
      .buttonStyle(.plain)

      // Rank badge (position by message count).
      ZStack {
        Circle()
          .fill(OmiColors.backgroundTertiary)
          .frame(width: 40, height: 40)

        Text("\(rank)")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
      }

      VStack(alignment: .leading, spacing: 2) {
        Text(contact.displayName)
          .scaledFont(size: 15, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
          .truncationMode(.middle)

        Text("\(contact.messageCount.formatted()) messages")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      Button(action: {
        // TODO: Wire up the AI Clone training pipeline for this contact.
        // No-op stub for now — we're not building training yet.
      }) {
        Text("Train")
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.backgroundPrimary)
          .padding(.horizontal, 18)
          .padding(.vertical, 8)
          .background(
            RoundedRectangle(cornerRadius: 8)
              .fill(OmiColors.textPrimary)
          )
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(
          isHovered
            ? OmiColors.backgroundTertiary.opacity(0.6)
            : OmiColors.backgroundSecondary
        )
    )
    .overlay(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .stroke(isSelected ? OmiColors.border : Color.clear, lineWidth: 1)
    )
    .contentShape(Rectangle())
    .onTapGesture { onToggle() }
    .onHover { isHovered = $0 }
  }
}

#Preview {
  AIClonePage()
}
