import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Account: name and email, plan & usage, invite friends, then sign out and delete account.
/// The user ID sits in Developer (only people building with Omi need it).
struct AccountScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(SessionStore.self) private var session
    @State private var confirmSignOut = false
    @State private var confirmDelete = false
    @State private var editingName = false
    @State private var newName = ""
    @State private var shownName: String?

    var body: some View {
        SettingsList {
            Section {
                Button {
                    newName = shownName ?? settings.displayName ?? ""
                    editingName = true
                } label: {
                    LabeledContent(L("name")) {
                        Text(shownName ?? settings.displayName ?? L("notSet")).foregroundStyle(DS.Palette.inkSecondary)
                    }
                    .foregroundStyle(DS.Palette.ink)
                }
                .accessibilityIdentifier("account.name")
                LabeledContent(L("email")) {
                    Text(settings.email ?? L("notSet")).foregroundStyle(DS.Palette.inkSecondary).lineLimit(1)
                }
            }
            Section {
                NavigationLink(value: SettingsTopic.planUsage) {
                    SettingsRowLabel(
                        title: SettingsTopic.planUsage.title, systemImage: SettingsTopic.planUsage.systemImage,
                        value: settings.subscription.map(PlanUsageScreen.planName)
                    )
                }
                .accessibilityIdentifier("account.planUsage")
                NavigationLink(value: SettingsTopic.referral) {
                    SettingsRowLabel(title: SettingsTopic.referral.title, systemImage: SettingsTopic.referral.systemImage)
                }
                .accessibilityIdentifier("account.referral")
            }
            Section {
                // The whole setup again: languages, the Omi, the voice (closes Settings).
                Button { session.replayOnboarding() } label: {
                    SettingsRowLabel(title: L("nativeRedoOnboarding"), systemImage: "arrow.counterclockwise")
                }
                .accessibilityIdentifier("account.redoOnboarding")
            }
            Section {
                Button(L("nativeSignOut")) { confirmSignOut = true }
                    .foregroundStyle(DS.Palette.ink)
                    .accessibilityIdentifier("account.signOut")
                Button(L("nativeDeleteAccount"), role: .destructive) { confirmDelete = true }
            }
        }
        .omiPage(L("account"))
        .task { await settings.loadSubscription() }
        .confirmationDialog(L("signOutQuestion"), isPresented: $confirmSignOut, titleVisibility: .visible) {
            Button(L("nativeSignOut"), role: .destructive) { session.signOut() }
        }
        .confirmationDialog(L("nativeDeleteAccountQuestion"), isPresented: $confirmDelete, titleVisibility: .visible) {
            Button(L("nativeDeleteAccount"), role: .destructive) { Task { _ = await session.deleteAccount(reason: nil) } }
        } message: {
            Text(L("nativeDeleteAccountWarning"))
        }
        .alert(L("editName"), isPresented: $editingName) {
            TextField(L("nativeYourName"), text: $newName)
                .textContentType(.name)
            Button(L("cancel"), role: .cancel) {}
            Button(L("save")) {
                let name = newName
                Task {
                    await session.changeName(name)
                    settings.nameChanged(to: name)
                    shownName = settings.displayName
                    DSHaptics.success()
                }
            }
            .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
        } message: {
            Text(L("nativeHowShouldOmiCallYou"))
        }
    }
}
