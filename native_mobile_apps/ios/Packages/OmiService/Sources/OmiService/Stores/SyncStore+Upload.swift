import Foundation
import OmiDevice
import OmiNetwork

/// Sending what the Omi recorded and the phone kept: one file at a time, then the backend's jobs
/// for them. Split out of `SyncStore.swift` for length only.
extension SyncStore {
    /// Uploads every finished recording, then checks on jobs still processing.
    public func uploadPending() async {
        guard !uploading else { return }
        uploading = true
        // Files are being sent: the app stays awake for them too, not only for the read.
        lease?.acquire()
        beginProgress()
        defer {
            uploading = false
            lease?.release()
            refresh()
        }
        var tried: Set<String> = []
        // Another account's recordings wait for that account (an untagged one is the current user's);
        // signed out, nothing goes anywhere.
        let account = userID()
        func isMine(_ recording: PendingRecording) -> Bool {
            account != nil && (recording.owner == nil || recording.owner == account)
        }
        while let next = files.state.recordings.first(where: {
            $0.jobID == nil && $0.manual != true && !$0.isKept && !tried.contains($0.filename) && isMine($0)
        }) {
            tried.insert(next.filename)
            guard let data = files.data(for: next) else {
                files.remove(next.filename)
                continue
            }
            do {
                let upload = try await api.uploadOfflineRecording(filename: next.filename, data: data)
                progress?.done += next.seconds
                if let jobID = upload.jobID, upload.status != "completed" {
                    files.setJob(jobID, for: next.filename)
                } else {
                    files.remove(next.filename)
                }
            } catch let APIError.http(status, _) where [400, 413, 422].contains(status) {
                // The server will never take this file (bad time, too old, undecodable).
                files.remove(next.filename)
            } catch {
                scheduleRetry()
                return
            }
            refresh()
        }
        await checkJobs()
    }

    private func checkJobs() async {
        var waiting = false
        for recording in files.state.recordings {
            guard let jobID = recording.jobID else { continue }
            do {
                guard let job = try await api.syncJob(id: jobID) else {
                    files.setJob(nil, for: recording.filename)
                    waiting = true
                    continue
                }
                if !job.isFinished {
                    waiting = true
                } else if job.status == "completed" || job.isPermanentFailure {
                    files.remove(recording.filename)
                } else if recording.failedJobs < 2 {
                    files.setJob(nil, for: recording.filename, failed: true)
                    waiting = true
                } else {
                    // Failed three times: tried again on the next launch or connect, not in a loop.
                    files.setJob(nil, for: recording.filename, failed: true)
                }
            } catch {
                waiting = true
            }
        }
        if waiting { scheduleRetry() }
    }

    private func scheduleRetry() {
        retryTask?.cancel()
        retryTask = Task { [weak self, retryDelay] in
            try? await Task.sleep(for: retryDelay)
            guard !Task.isCancelled else { return }
            await self?.uploadPending()
        }
    }

    func beginProgress() {
        guard progress == nil else { return }
        let total = files.state.recordings.filter { $0.jobID == nil && $0.manual != true && !$0.isKept }.reduce(0) { $0 + $1.seconds }
            + Double(files.state.devicePending) * files.state.secondsPerRecord * 2
        if total > 0 { progress = (0, total) }
    }
}
