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
            .padding(.horizontal, 20)
            .padding(.top, 16)

            ScrollView {
                VStack(spacing: 0) {
                    // Header
                    header
                        .padding(.horizontal, 32)
                        .padding(.top, 16)
                        .padding(.bottom, 24)

                    // Content
                    if isLoading && persona == nil {
                        loadingView
                    } else if let error = errorMessage {
                        errorView(error)
                    } else if let persona = persona {
                        personaDetailView(persona)
                            .padding(.horizontal, 32)
                    } else {
                        noPersonaView
                            .padding(.horizontal, 32)
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
            VStack(alignment: .leading, spacing: 4) {
                Text("AI Persona")
                    .scaledFont(size: 28, weight: .bold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("Create an AI clone of yourself that others can chat with")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            if persona != nil {
                Button {
                    Task { await loadPersona() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
                .disabled(isLoading)
            }
        }
    }

    // MARK: - Loading View

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.2)

            Text("Loading persona...")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.top, 100)
    }

    // MARK: - Error View

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .scaledFont(size: 40)
                .foregroundColor(OmiColors.error)

            Text(message)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textSecondary)
                .multilineTextAlignment(.center)

            Button {
                Task { await loadPersona() }
            } label: {
                Text("Try Again")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(OmiColors.purplePrimary)
                    .cornerRadius(8)
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 100)
    }

    // MARK: - No Persona View

    private var noPersonaView: some View {
        VStack(spacing: 24) {
            // Icon
            ZStack {
                Circle()
                    .fill(OmiColors.purplePrimary.opacity(0.15))
                    .frame(width: 100, height: 100)

                Image(systemName: "person.crop.circle.badge.plus")
                    .scaledFont(size: 44)
                    .foregroundColor(OmiColors.purplePrimary)
            }

            VStack(spacing: 8) {
                Text("No Persona Yet")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("Create an AI clone of yourself using your public memories. Others can then chat with your persona to learn about you.")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 400)
            }

            Button {
                showingCreateForm = true
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "plus")
                    Text("Create Persona")
                }
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(.white)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(OmiColors.purplePrimary)
                .cornerRadius(10)
            }
            .buttonStyle(.plain)

            // Info about public memories
            HStack(spacing: 8) {
                Image(systemName: "info.circle")
                    .scaledFont(size: 13)

                Text("Make memories public in the Memories page to enhance your persona")
                    .scaledFont(size: 13)
            }
            .foregroundColor(OmiColors.textTertiary)
            .padding(.top, 8)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 80)
    }

    // MARK: - Persona Detail View

    private func personaDetailView(_ persona: Persona) -> some View {
        VStack(alignment: .leading, spacing: 24) {
            // Profile card
            HStack(spacing: 20) {
                // Avatar
                ZStack {
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.15))
                        .frame(width: 80, height: 80)

                    if !persona.image.isEmpty, let url = URL(string: persona.image) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        } placeholder: {
                            Image(systemName: "person.fill")
                                .scaledFont(size: 32)
                                .foregroundColor(OmiColors.purplePrimary)
                        }
                        .frame(width: 80, height: 80)
                        .clipShape(Circle())
                    } else {
                        Image(systemName: "person.fill")
                            .scaledFont(size: 32)
                            .foregroundColor(OmiColors.purplePrimary)
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(persona.name)
                        .scaledFont(size: 20, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)

                    if let username = persona.username {
                        Text("@\(username)")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    // Status badge
                    HStack(spacing: 6) {
                        Circle()
                            .fill(statusColor(for: persona.status))
                            .frame(width: 8, height: 8)

                        Text(persona.statusText)
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                    }
                    .padding(.top, 4)
                }

                Spacer()

                // Actions
                HStack(spacing: 12) {
                    Button {
                        editName = persona.name
                        editDescription = persona.description
                        isEditing = true
                    } label: {
                        Image(systemName: "pencil")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .frame(width: 36, height: 36)
                            .background(OmiColors.backgroundTertiary)
                            .cornerRadius(8)
                    }
                    .buttonStyle(.plain)

                    Button {
                        showingDeleteConfirmation = true
                    } label: {
                        Image(systemName: "trash")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.error)
                            .frame(width: 36, height: 36)
                            .background(OmiColors.error.opacity(0.15))
                            .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(20)
            .background(OmiColors.backgroundTertiary.opacity(0.5))
            .cornerRadius(12)

            // Description section
            VStack(alignment: .leading, spacing: 12) {
                Text("Description")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                if isEditing {
                    TextEditor(text: $editDescription)
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textPrimary)
                        .frame(height: 80)
                        .padding(8)
                        .background(OmiColors.backgroundPrimary)
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
                        )
                } else {
                    Text(persona.description.isEmpty ? "No description yet" : persona.description)
                        .scaledFont(size: 14)
                        .foregroundColor(persona.description.isEmpty ? OmiColors.textTertiary : OmiColors.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(16)
            .background(OmiColors.backgroundTertiary.opacity(0.5))
            .cornerRadius(12)

            // Stats section
            HStack(spacing: 16) {
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
            VStack(alignment: .leading, spacing: 12) {
                Text("Actions")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                if isEditing {
                    HStack(spacing: 12) {
                        Button {
                            isEditing = false
                        } label: {
                            Text("Cancel")
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                                .background(OmiColors.backgroundTertiary)
                                .cornerRadius(8)
                        }
                        .buttonStyle(.plain)

                        Button {
                            Task { await saveEdits() }
                        } label: {
                            Text("Save Changes")
                                .scaledFont(size: 14, weight: .semibold)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                                .background(OmiColors.purplePrimary)
                                .cornerRadius(8)
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
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(OmiColors.purplePrimary.opacity(0.15))
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .disabled(isRegenerating)
                }
            }
            .padding(16)
            .background(OmiColors.backgroundTertiary.opacity(0.5))
            .cornerRadius(12)

            // Persona prompt preview (collapsible)
            if persona.hasPrompt, let prompt = persona.personaPrompt {
                personaPromptSection(prompt)
            }
        }
    }

    private func statCard(title: String, value: String, icon: String, isWarning: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .scaledFont(size: 14)
                    .foregroundColor(isWarning ? OmiColors.warning : OmiColors.purplePrimary)

                Text(title)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Text(value)
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(isWarning ? OmiColors.warning : OmiColors.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
        .cornerRadius(12)
    }

    @State private var isPromptExpanded = false

    private func personaPromptSection(_ prompt: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                withAnimation {
                    isPromptExpanded.toggle()
                }
            } label: {
                HStack {
                    Text("Persona Prompt")
                        .scaledFont(size: 14, weight: .semibold)
                        .foregroundColor(OmiColors.textSecondary)

                    Spacer()

                    Image(systemName: isPromptExpanded ? "chevron.up" : "chevron.down")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }
            .buttonStyle(.plain)

            if isPromptExpanded {
                Text(prompt)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(OmiColors.backgroundPrimary)
                    .cornerRadius(8)
            }
        }
        .padding(16)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
        .cornerRadius(12)
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
            onCheckUsername: checkUsername,
            onCreate: createPersona,
            canCreate: canCreate,
            onDismiss: { showingCreateForm = false }
        )
    }

    private var canCreate: Bool {
        !newPersonaName.isEmpty &&
        (newPersonaUsername.isEmpty || (newPersonaUsername.count >= 3 && usernameAvailable == true))
    }

    // MARK: - API Calls

    private func loadPersona() async {
        isLoading = true
        errorMessage = nil

        do {
            persona = try await APIClient.shared.getPersona()
        } catch {
            errorMessage = "Failed to load persona: \(error.localizedDescription)"
        }

        isLoading = false
    }

    private func createPersona() async {
        isCreating = true

        do {
            let username = newPersonaUsername.isEmpty ? nil : newPersonaUsername
            persona = try await APIClient.shared.createPersona(name: newPersonaName, username: username)
            showingCreateForm = false
            newPersonaName = ""
            newPersonaUsername = ""
        } catch {
            // Show error in sheet
            errorMessage = error.localizedDescription
        }

        isCreating = false
    }

    private func deletePersona() async {
        do {
            try await APIClient.shared.deletePersona()
            persona = nil
        } catch {
            errorMessage = "Failed to delete persona: \(error.localizedDescription)"
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
            errorMessage = "Failed to save: \(error.localizedDescription)"
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
            errorMessage = "Failed to regenerate: \(error.localizedDescription)"
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
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                DismissButton(action: dismissSheet)
            }
            .padding(20)

            Divider()
                .background(OmiColors.textQuaternary.opacity(0.3))

            // Form
            VStack(alignment: .leading, spacing: 20) {
                // Name field
                VStack(alignment: .leading, spacing: 8) {
                    Text("Name")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)

                    TextField("Your display name", text: $newPersonaName)
                        .textFieldStyle(.plain)
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(12)
                        .background(OmiColors.backgroundPrimary)
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
                        )
                }

                // Username field
                VStack(alignment: .leading, spacing: 8) {
                    Text("Username (optional)")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)

                    HStack {
                        Text("@")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)

                        TextField("username", text: $newPersonaUsername)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 14)
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
                    .padding(12)
                    .background(OmiColors.backgroundPrimary)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
                    )

                    Text("3-30 characters, lowercase letters, numbers, and underscores only")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }

                // Info
                HStack(spacing: 8) {
                    Image(systemName: "info.circle")
                        .scaledFont(size: 13)

                    Text("Your persona will be built from your public memories. Make more memories public to improve it.")
                        .scaledFont(size: 12)
                }
                .foregroundColor(OmiColors.textTertiary)
                .padding(12)
                .background(OmiColors.info.opacity(0.1))
                .cornerRadius(8)

                Spacer()

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
                    .scaledFont(size: 15, weight: .semibold)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(canCreate ? OmiColors.purplePrimary : OmiColors.textTertiary)
                    .cornerRadius(10)
                }
                .buttonStyle(.plain)
                .disabled(!canCreate || isCreating)
            }
            .padding(20)
        }
        .frame(width: 400, height: 450)
        .background(OmiColors.backgroundSecondary)
    }
}
