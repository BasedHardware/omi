import SwiftUI

/// Standalone file indexing view: consent → scanning → complete.
/// Works in two contexts:
/// 1. Embedded in OnboardingView step 4 (new users)
/// 2. Shown as a sheet on app launch in DesktopHomeView (existing users)
struct FileIndexingView: View {
    enum Phase { case consent, scanning, complete }

    @State private var phase: Phase = .consent
    @State private var scanningFolder: String = ""
    @State private var totalFilesScanned: Int = 0

    /// Called when user completes (with file count) or skips (with 0)
    var onComplete: (Int) -> Void

    var body: some View {
        VStack(spacing: 16) {
            Spacer()

            contentView

            Spacer()

            buttonSection
        }
        .padding(24)
    }

    // MARK: - Content

    @ViewBuilder
    private var contentView: some View {
        switch phase {
        case .consent:
            VStack(spacing: 16) {
                Image(systemName: "folder.badge.gearshape")
                    .scaledFont(size: 48)
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Get to Know You")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Let Omi look at your files to understand what you work on, your projects, and interests.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    Image(systemName: "lock.shield")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                    Text("Only scans ~/Downloads, ~/Documents, ~/Desktop")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 4)
            }

        case .scanning:
            VStack(spacing: 16) {
                ProgressView()
                    .scaleEffect(1.5)
                    .padding(.bottom, 8)

                Text("Scanning your files...")
                    .font(.title2)
                    .fontWeight(.semibold)

                if !scanningFolder.isEmpty {
                    Text("~/\(scanningFolder)")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.purplePrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 4)
                        .background(OmiColors.purplePrimary.opacity(0.1))
                        .cornerRadius(6)
                }

                Text("\(totalFilesScanned.formatted()) files found")
                    .font(.title3)
                    .foregroundColor(.secondary)
                    .monospacedDigit()
            }

        case .complete:
            VStack(spacing: 16) {
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 48)
                    .foregroundColor(.green)

                Text("\(totalFilesScanned.formatted()) files indexed!")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Let's see what we found!")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }
        }
    }

    // MARK: - Buttons

    private var buttonSection: some View {
        VStack(spacing: 8) {
            Button(action: handleMainAction) {
                Text(mainButtonTitle)
                    .frame(maxWidth: 200)
                    .padding(.vertical, 8)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(phase == .scanning)

            if phase == .consent {
                Button(action: skip) {
                    Text("Skip")
                        .scaledFont(size: 13)
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var mainButtonTitle: String {
        switch phase {
        case .consent: return "Get Started"
        case .scanning: return "Scanning..."
        case .complete: return "Start Using Omi"
        }
    }

    // MARK: - Actions

    private func handleMainAction() {
        switch phase {
        case .consent:
            startScanning()
        case .scanning:
            break
        case .complete:
            onComplete(totalFilesScanned)
        }
    }

    private func startScanning() {
        phase = .scanning
        totalFilesScanned = 0

        Task {
            let home = FileManager.default.homeDirectoryForCurrentUser
            let folders = [
                ("Downloads", home.appendingPathComponent("Downloads")),
                ("Documents", home.appendingPathComponent("Documents")),
                ("Desktop", home.appendingPathComponent("Desktop")),
            ]

            for (name, url) in folders {
                await MainActor.run {
                    scanningFolder = name
                }
                let count = await FileIndexerService.shared.scanFolders([url])
                await MainActor.run {
                    totalFilesScanned += count
                }
            }

            await MainActor.run {
                UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
                scanningFolder = ""
                phase = .complete
            }
        }
    }

    private func skip() {
        log("FileIndexingView: User skipped file indexing")
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
        onComplete(0)
    }
}
