import CoreGraphics
import Foundation

/// Converts a commit-lease result that was superseded by a queued owner
/// transition into a capture-exclusion error so callers discard encoded bytes
/// instead of publishing them into the next owner's session.
enum RewindCaptureOwnerTransitionLease {
  static func resultOrExcluded<T>(
    value: T,
    ownerTransitionQueued: Bool,
    relativePath: String?,
    snapshot: RewindCaptureExclusionSnapshot
  ) throws -> T {
    guard !ownerTransitionQueued else {
      throw RewindCaptureExcludedError(relativePath: relativePath, snapshot: snapshot)
    }
    return value
  }
}

extension RewindIndexer {
  /// Reconcile finalized chunks left by an excluded frame when a prior file
  /// delete failed. The owner-scoped journal is cleared only after both the DB
  /// tombstone and filesystem delete succeed.
  func retryPendingExcludedVideoChunkCleanups() async {
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else { return }
    for relativePath in RewindExcludedVideoChunkCleanupJournal.pending(
      ownerID: ownerSnapshot.ownerID)
    {
      await cleanupExcludedVideoChunk(
        relativePath: relativePath, ownerSnapshot: ownerSnapshot)
    }
  }

  func cleanupExcludedVideoChunk(
    relativePath: String,
    ownerSnapshot: RewindCaptureOwnerSnapshot
  ) async {
    let ownerID = ownerSnapshot.ownerID
    RewindExcludedVideoChunkCleanupJournal.enqueue(
      relativePath: relativePath, ownerID: ownerID)
    let authorization = LocalMutationAuthorization {
      ownerSnapshot.isCurrent()
    }
    do {
      try await authorization.withCommitLease {
        try await self.removeExcludedVideoChunk(relativePath: relativePath)
      }
      RewindExcludedVideoChunkCleanupJournal.complete(
        relativePath: relativePath, ownerID: ownerID)
    } catch {
      logError("RewindIndexer: Deferred excluded video chunk cleanup", error: error)
    }
  }

  private func removeExcludedVideoChunk(relativePath: String) async throws {
    _ = try await RewindDatabase.shared.abandonVideoChunk(relativePath: relativePath)
    try await RewindStorage.shared.deleteVideoChunks(relativePaths: [relativePath])
  }

  /// The encoder reports an immutable path when it abandons a writer
  /// generation. Storage owns the DB tombstone and file deletion; keeping that
  /// mutation out of the encoder avoids a circular actor dependency and lets
  /// the persistence boundary reject stale post-OCR inserts for the path.
  @discardableResult
  func discardAbandonedVideoChunkIfNeeded(_ error: Error) async -> Bool {
    if let excluded = error as? RewindCaptureExcludedError {
      guard let relativePath = excluded.relativePath, !relativePath.isEmpty else {
        return true
      }
      let ownerSnapshot = excluded.snapshot.ownerSnapshot
      let ownerID = ownerSnapshot.ownerID
      // Persist the originating owner before any await. If an owner transition
      // has already won, the old path is retried only after that owner is active
      // again; it is never interpreted against the incoming owner's storage.
      RewindExcludedVideoChunkCleanupJournal.enqueue(
        relativePath: relativePath, ownerID: ownerID)
      let authorization = LocalMutationAuthorization {
        ownerSnapshot.isCurrent()
      }
      do {
        try await authorization.withCommitLease {
          let activePath = await VideoChunkEncoder.shared.currentChunkPath
          if activePath == relativePath {
            switch await VideoChunkEncoder.shared.cancel() {
            case .markerRecorded:
              _ = try await RewindStorage.shared.recoverAbandonedVideoChunkIfNeeded(
                RewindAbandonedVideoChunkError(relativePath: relativePath))
            case .markerWriteFailed(let reservation):
              try await RewindStorage.shared.recoverAfterMarkerWriteFailure(
                reservation: reservation)
              // The storage fallback intentionally swallows a final unlink
              // failure when it has a sidecar. Verify the privacy deletion here;
              // our owner journal remains until this idempotent pass succeeds.
              try await self.removeExcludedVideoChunk(relativePath: relativePath)
            case .noActiveChunk:
              try await self.removeExcludedVideoChunk(relativePath: relativePath)
            }
          } else {
            // The writer already finalized; tombstone and remove the whole
            // shared chunk so excluded pixels cannot remain in the artifact.
            try await self.removeExcludedVideoChunk(relativePath: relativePath)
          }
        }
        RewindExcludedVideoChunkCleanupJournal.complete(
          relativePath: relativePath, ownerID: ownerID)
      } catch {
        logError("RewindIndexer: Deferred stale frame chunk cleanup", error: error)
      }
      return true
    }
    do {
      return try await RewindStorage.shared.recoverAbandonedVideoChunkIfNeeded(error)
    } catch {
      logError("RewindIndexer: Failed to discard abandoned video chunk", error: error)
      return true
    }
  }

  func encodeFrameIfCurrent(
    image: CGImage,
    timestamp: Date,
    snapshot: RewindCaptureExclusionSnapshot
  ) async throws -> VideoChunkEncoder.EncodedFrame? {
    let authorization = LocalMutationAuthorization {
      RewindCaptureExclusionGeneration.isOwnerCurrent(snapshot)
    }
    let encoded: VideoChunkEncoder.EncodedFrame?
    do {
      // Report whether an owner transition queued behind the lease. Returning a
      // successful encode after that verdict would publish superseded pixels into
      // the next owner's session; convert it to an exclusion so cleanup runs.
      let (value, ownerTransitionQueued) = try await authorization.withCommitLeaseReportingOwnerTransition {
        guard RewindCaptureExclusionGeneration.begin(snapshot) else {
          throw RewindCaptureExcludedError(
            relativePath: nil, snapshot: snapshot)
        }
        defer { RewindCaptureExclusionGeneration.end(snapshot) }
        return try await VideoChunkEncoder.shared.addFrame(image: image, timestamp: timestamp)
      }
      encoded = try RewindCaptureOwnerTransitionLease.resultOrExcluded(
        value: value,
        ownerTransitionQueued: ownerTransitionQueued,
        relativePath: value?.videoChunkPath,
        snapshot: snapshot)
    } catch let excluded as RewindCaptureExcludedError {
      throw excluded
    } catch {
      guard RewindCaptureExclusionGeneration.isOwnerCurrent(snapshot) else {
        throw RewindCaptureExcludedError(
          relativePath: nil, snapshot: snapshot)
      }
      throw error
    }
    guard RewindCaptureExclusionGeneration.isCurrent(snapshot) else {
      if let encoded {
        throw RewindCaptureExcludedError(
          relativePath: encoded.videoChunkPath, snapshot: snapshot)
      }
      return nil
    }
    return encoded
  }

  func insertScreenshotIfCurrent(
    _ screenshot: Screenshot,
    snapshot: RewindCaptureExclusionSnapshot
  ) async throws -> Screenshot {
    let authorization = LocalMutationAuthorization {
      RewindCaptureExclusionGeneration.isOwnerCurrent(snapshot)
    }
    do {
      let (value, ownerTransitionQueued) = try await authorization.withCommitLeaseReportingOwnerTransition {
        guard RewindCaptureExclusionGeneration.begin(snapshot) else {
          throw RewindCaptureExcludedError(
            relativePath: screenshot.videoChunkPath, snapshot: snapshot)
        }
        defer { RewindCaptureExclusionGeneration.end(snapshot) }
        guard RewindCaptureExclusionGeneration.isCurrent(snapshot) else {
          throw RewindCaptureExcludedError(
            relativePath: screenshot.videoChunkPath, snapshot: snapshot)
        }
        return try await RewindDatabase.shared.insertScreenshot(screenshot)
      }
      return try RewindCaptureOwnerTransitionLease.resultOrExcluded(
        value: value,
        ownerTransitionQueued: ownerTransitionQueued,
        relativePath: value.videoChunkPath,
        snapshot: snapshot)
    } catch let excluded as RewindCaptureExcludedError {
      throw excluded
    } catch {
      guard RewindCaptureExclusionGeneration.isOwnerCurrent(snapshot) else {
        throw RewindCaptureExcludedError(
          relativePath: screenshot.videoChunkPath, snapshot: snapshot)
      }
      throw error
    }
  }
}
