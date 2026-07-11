import AppKit
import Foundation
import SwiftUI
import OmiTheme

// Clone test API models live in CloneTestModels.swift (Foundation-only so the
// request/response contract can be validated without the SwiftUI layer).

// MARK: - Service

/// One editable (their message, your reply) pair for the benchmark.
struct BenchmarkSampleDraft: Identifiable {
    let id = UUID()
    var incoming: String = ""
    var reply: String = ""
}

@MainActor
final class CloneTestService: ObservableObject {
    // Ask your clone
    @Published var question: String = ""
    @Published var askAnswer: CloneAskResponse?
    @Published var askLoading = false
    @Published var askError: String?

    // Benchmark against real replies
    @Published var samples: [BenchmarkSampleDraft] = [BenchmarkSampleDraft(), BenchmarkSampleDraft()]
    @Published var benchmark: CloneBenchmarkResult?
    @Published var benchmarkLoading = false
    @Published var benchmarkError: String?

    func ask() async {
        let trimmed = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        askLoading = true
        askError = nil
        do {
            let response: CloneAskResponse = try await APIClient.shared.post(
                "v1/clone/ask",
                body: CloneAskRequestPayload(question: trimmed, usePersona: true))
            askAnswer = response
        } catch {
            askError = Self.friendly(error)
        }
        askLoading = false
    }

    func addSample() {
        samples.append(BenchmarkSampleDraft())
    }

    func removeSample(_ sample: BenchmarkSampleDraft) {
        samples.removeAll { $0.id == sample.id }
        if samples.isEmpty { samples.append(BenchmarkSampleDraft()) }
    }

    func runBenchmark() async {
        let payload: [CloneBenchmarkSamplePayload] = samples.compactMap { draft in
            let incoming = draft.incoming.trimmingCharacters(in: .whitespacesAndNewlines)
            let reply = draft.reply.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !incoming.isEmpty, !reply.isEmpty else { return nil }
            return CloneBenchmarkSamplePayload(
                incomingMessage: incoming, actualReply: reply, contactName: nil, network: nil)
        }
        guard !payload.isEmpty else {
            benchmarkError = "Add at least one message with the reply you actually sent."
            return
        }
        benchmarkLoading = true
        benchmarkError = nil
        do {
            let result: CloneBenchmarkResult = try await APIClient.shared.post(
                "v1/clone/benchmark",
                body: CloneBenchmarkRequestPayload(samples: payload, usePersona: true))
            benchmark = result
        } catch {
            benchmarkError = Self.friendly(error)
        }
        benchmarkLoading = false
    }

    private static func friendly(_ error: Error) -> String {
        let message = (error as NSError).localizedDescription
        return message.isEmpty ? "Something went wrong. Please try again." : message
    }
}

// MARK: - View

/// "Test your clone": ask it a personal question (grounded in your memories), and
/// benchmark it against replies you actually sent, so you can trust it before it
/// speaks for you.
struct CloneTestView: View {
    @StateObject private var service = CloneTestService()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                askCard
                benchmarkCard
            }
            .padding()
        }
    }

    private var askCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Ask your clone", systemImage: "person.fill.questionmark")
                .font(.headline)
            Text(
                "Ask anything personal. The clone answers from your memories and your persona, so you can see how well it knows you before it speaks for you."
            )
            .font(.caption)
            .foregroundStyle(OmiColors.textTertiary)

            HStack(spacing: 8) {
                TextField("What did I decide about the Japan trip?", text: $service.question)
                    .textFieldStyle(.plain)
                    .padding(8)
                    .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 8))
                    .onSubmit { Task { await service.ask() } }
                Button {
                    Task { await service.ask() }
                } label: {
                    if service.askLoading {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Ask")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.primary)
                .disabled(
                    service.askLoading
                        || service.question.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            if let error = service.askError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(OmiColors.textTertiary)
            }
            if let answer = service.askAnswer {
                VStack(alignment: .leading, spacing: 6) {
                    Text(answer.answer)
                        .font(.body)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    HStack(spacing: 8) {
                        badge(
                            answer.grounded ? "From your memories" : "No memory support",
                            ok: answer.grounded)
                        Text("\(answer.memoriesUsed) memories searched")
                            .font(.caption2)
                            .foregroundStyle(OmiColors.textQuaternary)
                        if answer.personaUsed {
                            Text("in your persona voice")
                                .font(.caption2)
                                .foregroundStyle(OmiColors.textQuaternary)
                        }
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding()
        .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(OmiColors.border))
    }

    private var benchmarkCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Benchmark against your real replies", systemImage: "checkmark.seal")
                .font(.headline)
            Text(
                "Paste a few messages people sent you and the reply you actually sent. The clone drafts each one blind, and we score how often it would have matched you."
            )
            .font(.caption)
            .foregroundStyle(OmiColors.textTertiary)

            ForEach($service.samples) { $sample in
                samplePairEditor($sample)
            }

            HStack {
                Button {
                    service.addSample()
                } label: {
                    Label("Add another", systemImage: "plus")
                }
                .buttonStyle(.bordered)
                Spacer()
                Button {
                    Task { await service.runBenchmark() }
                } label: {
                    if service.benchmarkLoading {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Run benchmark")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.primary)
                .disabled(service.benchmarkLoading)
            }

            if let error = service.benchmarkError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(OmiColors.textTertiary)
            }
            if let result = service.benchmark {
                benchmarkResultView(result)
            }
        }
        .padding()
        .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(OmiColors.border))
    }

    private func samplePairEditor(_ sample: Binding<BenchmarkSampleDraft>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("They wrote")
                    .font(.caption2)
                    .foregroundStyle(OmiColors.textQuaternary)
                Spacer()
                if service.samples.count > 1 {
                    Button {
                        service.removeSample(sample.wrappedValue)
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(OmiColors.textQuaternary)
                    }
                    .buttonStyle(.plain)
                }
            }
            TextEditor(text: sample.incoming)
                .font(.callout)
                .frame(minHeight: 40)
                .padding(4)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(OmiColors.border))
            Text("You replied")
                .font(.caption2)
                .foregroundStyle(OmiColors.textQuaternary)
            TextEditor(text: sample.reply)
                .font(.callout)
                .frame(minHeight: 40)
                .padding(4)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(OmiColors.border))
        }
        .padding(8)
        .background(OmiColors.backgroundTertiary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
    }

    private func benchmarkResultView(_ result: CloneBenchmarkResult) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("\(result.matched)/\(result.total)")
                    .font(.title).bold()
                Text("matched your reply")
                    .font(.callout)
                    .foregroundStyle(OmiColors.textTertiary)
                Spacer()
                Text("\(percent(result.matchRate))%")
                    .font(.title2).bold()
                    .foregroundStyle(result.matchRate >= 0.5 ? OmiColors.success : OmiColors.textSecondary)
            }
            Text("Average closeness \(percent(result.averageScore))%")
                .font(.caption)
                .foregroundStyle(OmiColors.textQuaternary)
            ForEach(Array(result.items.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Image(systemName: item.match ? "checkmark.circle.fill" : "xmark.circle")
                            .foregroundStyle(item.match ? OmiColors.success : OmiColors.textTertiary)
                        Text(item.incomingMessage)
                            .font(.caption)
                            .lineLimit(1)
                        Spacer()
                        Text("\(percent(item.score))%")
                            .font(.caption2)
                            .foregroundStyle(OmiColors.textQuaternary)
                    }
                    Text("Clone: \(item.generatedReply)")
                        .font(.caption2)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(2)
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(.top, 4)
    }

    private func badge(_ text: String, ok: Bool) -> some View {
        Text(text)
            .font(.caption2)
            .foregroundStyle(ok ? OmiColors.success : OmiColors.textTertiary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(ok ? OmiColors.success.opacity(0.15) : OmiColors.border, in: Capsule())
    }

    private func percent(_ value: Double) -> Int {
        Int((value * 100).rounded())
    }
}
