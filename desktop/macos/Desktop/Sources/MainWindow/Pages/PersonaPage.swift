import OmiTheme
import SwiftUI

/// Page for managing user's AI persona/clone
struct PersonaPage: View {
  @Environment(\.dismiss) private var environmentDismiss
  var onDismiss: (() -> Void)? = nil  // Optional external dismiss handler for overlay-based presentation

  @State private var persona: Persona?
  @State private var isLoading = false
  @State private var errorMessage: String?

  // Creation form state
  @State private var showingCreateForm = false
  @State private var newPersonaName = ""
  @State private var newPersonaUsername = ""
  @State private var isCheckingUsername = false
  @State private var usernameAvailable: Bool?
  @State private var isCreating = false
  /// Create-sheet-scoped error. Kept separate from the page-wide `errorMessage`
  /// so a failed creation shows feedback inside the sheet instead of flipping
  /// the whole page (which has no persona yet) to the full-page error view.
  @State private var createErrorMessage: String?

  // Edit state
  @State private var isEditing = false
  @State private var editName = ""
  @State private var editDescription = ""

  // Delete confirmation
  @State private var showingDeleteConfirmation = false

  // Regenerate prompt
  @State private var isRegenerating = false

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: 0) {
      // Sheet header with close button
      HStack {
        Spacer()
        DismissButton(action: dismissSheet)
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.top, OmiSpacing.lg)

      ScrollView {
        VStack(spacing: 0) {
          // Header
          header
            .padding(.horizontal, OmiSpacing.section)
            .padding(.top, OmiSpacing.lg)
            .padding(.bottom, OmiSpacing.xxl)

          // Content
          if isLoading && persona == nil {
            loadingView
          } else if let error = errorMessage {
            errorView(error)
          } else if let persona = persona {
            personaDetailView(persona)
              .padding(.horizontal, OmiSpacing.section)
          } else {
            noPersonaView
              .padding(.horizontal, OmiSpacing.section)
          }

          Spacer()
        }
      }
    }
    .background(OmiColors.backgroundSecondary.opacity(0.3))
    .dismissableSheet(isPresented: $showingCreateForm) {
      createPersonaSheet
        .frame(width: 400, height: 400)
    }
    .alert("Delete Persona", isPresented: $showingDeleteConfirmation) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        Task { await deletePersona() }
      }
    } message: {
      Text("Are you sure you want to delete your AI persona? This cannot be undone.")
    }
    .task {
      await loadPersona()
    }
  }

  // MARK: - Header

  private var header: some View {
    HStack {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("AI Persona")
          .scaledFont(size: OmiType.title, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)

        Text("Create an AI clone of yourself that others can chat with")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      if persona != nil {
        Button {
          Task { await loadPersona() }
        } label: {
          Image(systemName: "arrow.clockwise")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
      }
    }
  }

  // MARK: - Loading View

  private var loadingView: some View {
    VStack(spacing: OmiSpacing.lg) {
      ProgressView()
        .scaleEffect(1.2)

      Text("Loading persona...")
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textTertiary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.top, 100)
  }

  // MARK: - Error View

  private func errorView(_ message: String) -> some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "exclamationmark.triangle")
        .scaledFont(size: OmiType.hero)
        .foregroundColor(OmiColors.error)

      Text(message)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)
        .multilineTextAlignment(.center)

      Button {
        Task { await loadPersona() }
      } label: {
        Text("Try Again")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.backgroundPrimary)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .background(OmiColors.accent)
          .cornerRadius(OmiChrome.elementRadius)
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: .infinity)
    .padding(.top, 100)
  }

  // MARK: - No Persona View

  private var noPersonaView: some View {
    VStack(spacing: OmiSpacing.xxl) {
      // Icon
      ZStack {
        Circle()
          .fill(OmiColors.accent.opacity(0.15))
          .frame(width: 100, height: 100)

        Image(systemName: "person.crop.circle.badge.plus")
          .scaledFont(size: 44)
          .foregroundColor(OmiColors.accent)
      }

      VStack(spacing: OmiSpacing.sm) {
        Text("No Persona Yet")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Text(
          "Create an AI clone of yourself using your public memories. Others can then chat with your persona to learn about you."
        )
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)
        .multilineTextAlignment(.center)
        .frame(maxWidth: 400)
      }

      Button {
        showingCreateForm = true
      } label: {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "plus")
          Text("Create Persona")
        }
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xxl)
        .padding(.vertical, OmiSpacing.md)
        .background(OmiColors.accent)
        .cornerRadius(OmiChrome.smallControlRadius)
      }
      .buttonStyle(.plain)

      // Info about public memories
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "info.circle")
          .scaledFont(size: OmiType.body)

        Text("Make memories public in the Memories page to enhance your persona")
          .scaledFont(size: OmiType.body)
      }
      .foregroundColor(OmiColors.textTertiary)
      .padding(.top, OmiSpacing.sm)
    }
    .frame(maxWidth: .infinity)
    .padding(.top, 80)
  }

  // MARK: - Persona Detail View

  private func personaDetailView(_ persona: Persona) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
      // Profile card
      HStack(spacing: OmiSpacing.xl) {
        // Avatar
        ZStack {
          Circle()
            .fill(OmiColors.accent.opacity(0.15))
            .frame(width: 80, height: 80)

          if !persona.image.isEmpty, let url = URL(string: persona.image) {
            AsyncImage(url: url) { image in
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            } placeholder: {
              Image(systemName: "person.fill")
                .scaledFont(size: 32)
                .foregroundColor(OmiColors.accent)
            }
            .frame(width: 80, height: 80)
            .clipShape(Circle())
          } else {
            Image(systemName: "person.fill")
              .scaledFont(size: 32)
              .foregroundColor(OmiColors.accent)
          }
        }

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(persona.name)
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          if let username = persona.username {
            Text("@\(username)")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          // Status badge
          HStack(spacing: OmiSpacing.xs) {
            Circle()
              .fill(statusColor(for: persona.status))
              .frame(width: 8, height: 8)

            Text(persona.statusText)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
          }
          .padding(.top, OmiSpacing.xxs)
        }

        Spacer()

        // Actions
        HStack(spacing: OmiSpacing.md) {
          Button {
            editName = persona.name
            editDescription = persona.description
            isEditing = true
          } label: {
            Image(systemName: "pencil")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
              .frame(width: 36, height: 36)
              .background(OmiColors.backgroundTertiary)
              .cornerRadius(OmiChrome.elementRadius)
          }
          .buttonStyle(.plain)

          Button {
            showingDeleteConfirmation = true
          } label: {
            Image(systemName: "trash")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.error)
              .frame(width: 36, height: 36)
              .background(OmiColors.error.opacity(0.15))
              .cornerRadius(OmiChrome.elementRadius)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(OmiSpacing.xl)
      .background(OmiColors.backgroundTertiary.opacity(0.5))
      .cornerRadius(OmiChrome.smallControlRadius)

      // Description section
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        Text("Description")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)

        if isEditing {
          TextEditor(text: $editDescription)
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textPrimary)
            .frame(height: 80)
            .padding(OmiSpacing.sm)
            .background(OmiColors.backgroundPrimary)
            .cornerRadius(OmiChrome.elementRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
            )
        } else {
          Text(persona.description.isEmpty ? "No description yet" : persona.description)
            .scaledFont(size: OmiType.body)
            .foregroundColor(persona.description.isEmpty ? OmiColors.textTertiary : OmiColors.textPrimary)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
      }
      .padding(OmiSpacing.lg)
      .background(OmiColors.backgroundTertiary.opacity(0.5))
      .cornerRadius(OmiChrome.smallControlRadius)

      // Stats section
      HStack(spacing: OmiSpacing.lg) {
        statCard(
          title: "Public Memories",
          value: "\(persona.publicMemoriesCount ?? 0)",
          icon: "brain.head.profile"
        )

        statCard(
          title: "Persona Prompt",
          value: persona.hasPrompt ? "Generated" : "Not Generated",
          icon: "text.bubble",
          isWarning: !persona.hasPrompt
        )
      }

      // Actions section
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        Text("Actions")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)

        if isEditing {
          HStack(spacing: OmiSpacing.md) {
            Button {
              isEditing = false
            } label: {
              Text("Cancel")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, OmiSpacing.md)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(OmiChrome.elementRadius)
            }
            .buttonStyle(.plain)

            Button {
              Task { await saveEdits() }
            } label: {
              Text("Save Changes")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.backgroundPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, OmiSpacing.md)
                .background(OmiColors.accent)
                .cornerRadius(OmiChrome.elementRadius)
            }
            .buttonStyle(.plain)
          }
        } else {
          Button {
            Task { await regeneratePrompt() }
          } label: {
            HStack {
              if isRegenerating {
                ProgressView()
                  .scaleEffect(0.8)
              } else {
                Image(systemName: "arrow.triangle.2.circlepath")
              }

              Text(isRegenerating ? "Regenerating..." : "Regenerate from Memories")
            }
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.accent)
            .frame(maxWidth: .infinity)
            .padding(.vertical, OmiSpacing.md)
            .background(OmiColors.accent.opacity(0.15))
            .cornerRadius(OmiChrome.elementRadius)
          }
          .buttonStyle(.plain)
          .disabled(isRegenerating)
        }
      }
      .padding(OmiSpacing.lg)
      .background(OmiColors.backgroundTertiary.opacity(0.5))
      .cornerRadius(OmiChrome.smallControlRadius)

      // Persona prompt preview (collapsible)
      if persona.hasPrompt, let prompt = persona.personaPrompt {
        personaPromptSection(prompt)
      }
    }
  }

  private func statCard(title: String, value: String, icon: String, isWarning: Bool = false) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.body)
          .foregroundColor(isWarning ? OmiColors.warning : OmiColors.accent)

        Text(title)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }

      Text(value)
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(isWarning ? OmiColors.warning : OmiColors.textPrimary)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(OmiSpacing.lg)
    .background(OmiColors.backgroundTertiary.opacity(0.5))
    .cornerRadius(OmiChrome.smallControlRadius)
  }

  @State private var isPromptExpanded = false

  private func personaPromptSection(_ prompt: String) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Button {
        OmiMotion.withGated {
          isPromptExpanded.toggle()
        }
      } label: {
        HStack {
          Text("Persona Prompt")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)

          Spacer()

          Image(systemName: isPromptExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
      }
      .buttonStyle(.plain)

      if isPromptExpanded {
        Text(prompt)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(OmiSpacing.md)
          .background(OmiColors.backgroundPrimary)
          .cornerRadius(OmiChrome.elementRadius)
      }
    }
    .padding(OmiSpacing.lg)
    .background(OmiColors.backgroundTertiary.opacity(0.5))
    .cornerRadius(OmiChrome.smallControlRadius)
  }

  private func statusColor(for status: String) -> Color {
    switch status {
    case "approved": return .green
    case "under-review": return .orange
    case "rejected": return .red
    default: return .gray
    }
  }

  // MARK: - Create Persona Sheet

  private var createPersonaSheet: some View {
    CreatePersonaSheetContent(
      newPersonaName: $newPersonaName,
      newPersonaUsername: $newPersonaUsername,
      isCheckingUsername: $isCheckingUsername,
      usernameAvailable: $usernameAvailable,
      isCreating: $isCreating,
      errorMessage: $createErrorMessage,
      onCheckUsername: checkUsername,
      onCreate: createPersona,
      canCreate: canCreate,
      onDismiss: {
        showingCreateForm = false
        createErrorMessage = nil
      }
    )
  }

  private var canCreate: Bool {
    !newPersonaName.isEmpty
      && (newPersonaUsername.isEmpty || (newPersonaUsername.count >= 3 && usernameAvailable == true))
  }

  // MARK: - API Calls

  private func loadPersona() async {
    isLoading = true
    errorMessage = nil

    do {
      persona = try await APIClient.shared.getPersona()
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .persona)
    }

    isLoading = false
  }

  private func createPersona() async {
    isCreating = true
    createErrorMessage = nil

    do {
      let username = newPersonaUsername.isEmpty ? nil : newPersonaUsername
      persona = try await APIClient.shared.createPersona(name: newPersonaName, username: username)
      showingCreateForm = false
      createErrorMessage = nil
      newPersonaName = ""
      newPersonaUsername = ""
    } catch {
      // Show the error inside the create sheet — never write the page-wide
      // errorMessage here, or the still-persona-less page flips to the
      // full-page error view behind the sheet.
      createErrorMessage = UserFacingErrorPresentation.message(for: error, while: .persona)
    }

    isCreating = false
  }

  private func deletePersona() async {
    do {
      try await APIClient.shared.deletePersona()
      persona = nil
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .persona)
    }
  }

  private func saveEdits() async {
    guard let currentPersona = persona else { return }

    do {
      let updated = try await APIClient.shared.updatePersona(
        name: editName != currentPersona.name ? editName : nil,
        description: editDescription != currentPersona.description ? editDescription : nil
      )
      persona = updated
      isEditing = false
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .persona)
    }
  }

  private func regeneratePrompt() async {
    isRegenerating = true

    do {
      let result = try await APIClient.shared.regeneratePersonaPrompt()
      // Reload persona to get updated data
      await loadPersona()
      log("Persona prompt regenerated using \(result.memoriesUsed) memories")
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .persona)
    }

    isRegenerating = false
  }

  private func checkUsername() async {
    guard newPersonaUsername.count >= 3 else {
      usernameAvailable = nil
      return
    }

    isCheckingUsername = true

    do {
      let result = try await APIClient.shared.checkPersonaUsername(newPersonaUsername)
      usernameAvailable = result.available
    } catch {
      usernameAvailable = nil
    }

    isCheckingUsername = false
  }
}

// MARK: - Create Persona Sheet Content (extracted for proper dismiss handling)

private struct CreatePersonaSheetContent: View {
  @Binding var newPersonaName: String
  @Binding var newPersonaUsername: String
  @Binding var isCheckingUsername: Bool
  @Binding var usernameAvailable: Bool?
  @Binding var isCreating: Bool
  @Binding var errorMessage: String?
  let onCheckUsername: () async -> Void
  let onCreate: () async -> Void
  let canCreate: Bool
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text("Create AI Persona")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        DismissButton(action: dismissSheet)
      }
      .padding(OmiSpacing.xl)

      Divider()
        .background(OmiColors.textQuaternary.opacity(0.3))

      // Form
      VStack(alignment: .leading, spacing: OmiSpacing.xl) {
        // Name field
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          Text("Name")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)

          TextField("Your display name", text: $newPersonaName)
            .textFieldStyle(.plain)
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textPrimary)
            .padding(OmiSpacing.md)
            .background(OmiColors.backgroundPrimary)
            .cornerRadius(OmiChrome.elementRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
            )
        }

        // Username field
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          Text("Username (optional)")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)

          HStack {
            Text("@")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)

            TextField("username", text: $newPersonaUsername)
              .textFieldStyle(.plain)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textPrimary)
              .onChange(of: newPersonaUsername) { _, newValue in
                newPersonaUsername = newValue.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "_" }
                usernameAvailable = nil
                if !newPersonaUsername.isEmpty {
                  Task { await onCheckUsername() }
                }
              }

            if isCheckingUsername {
              ProgressView()
                .scaleEffect(0.7)
            } else if let available = usernameAvailable {
              Image(systemName: available ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundColor(available ? .green : .red)
            }
          }
          .padding(OmiSpacing.md)
          .background(OmiColors.backgroundPrimary)
          .cornerRadius(OmiChrome.elementRadius)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
              .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
          )

          Text("3-30 characters, lowercase letters, numbers, and underscores only")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }

        // Info
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "info.circle")
            .scaledFont(size: OmiType.body)

          Text("Your persona will be built from your public memories. Make more memories public to improve it.")
            .scaledFont(size: OmiType.caption)
        }
        .foregroundColor(OmiColors.textTertiary)
        .padding(OmiSpacing.md)
        .background(OmiColors.info.opacity(0.1))
        .cornerRadius(OmiChrome.elementRadius)

        Spacer()

        // Create error (sheet-scoped)
        if let errorMessage {
          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "exclamationmark.triangle.fill")
              .foregroundColor(OmiColors.error)
            Text(errorMessage)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.error)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(OmiSpacing.md)
          .background(OmiColors.error.opacity(0.1))
          .cornerRadius(OmiChrome.elementRadius)
        }

        // Create button
        Button {
          Task { await onCreate() }
        } label: {
          HStack {
            if isCreating {
              ProgressView()
                .scaleEffect(0.8)
            }

            Text(isCreating ? "Creating..." : "Create Persona")
          }
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.backgroundPrimary)
          .frame(maxWidth: .infinity)
          .padding(.vertical, OmiSpacing.md)
          .background(canCreate ? OmiColors.accent : OmiColors.textTertiary)
          .cornerRadius(OmiChrome.smallControlRadius)
        }
        .buttonStyle(.plain)
        .disabled(!canCreate || isCreating)
      }
      .padding(OmiSpacing.xl)
    }
    .frame(width: 400, height: 450)
    .background(OmiColors.backgroundSecondary)
  }
}
