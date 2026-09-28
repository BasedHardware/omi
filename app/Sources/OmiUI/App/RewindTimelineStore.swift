import Foundation
import OmiKit

// Port of the `DesktopRewind.tsx` reader effect, store-side: the Recall page
// drives `refreshRewindTimeline` on appear / query change / the 15 s cadence,
// and `loadOlderRewindTimeline` from its Load-more button. The reader handle
// lives in `AppRuntime` so pagination survives view re-renders; a query
// change (or the 15 s refresh) rebuilds it, exactly like the upstream
// `useEffect` on `[bridge, query, revision]`.

extension AppStore {
    /// First page for `query` (also the refresh path — upstream rebuilds the
    /// reader on every revision tick).
    public func refreshRewindTimeline(query: String) async {
        let needle = String(query.trimmingCharacters(in: .whitespaces).prefix(200))
        guard let bridge = services.rewindTimeline else {
            runtime.rewindReader = nil
            runtime.rewindReaderQuery = nil
            rewindGroups = []
            rewindTimelineHasMore = false
            rewindTimelineWarning = nil
            rewindTimelineBusy = false
            return
        }
        rewindTimelineBusy = true
        let reader = RewindTimeline(bridge: bridge, query: needle)
        runtime.rewindReader = reader
        runtime.rewindReaderQuery = needle
        do {
            let page = try reader.next()
            rewindGroups = groupRewindFrames(page.frames)
            rewindTimelineHasMore = page.next
            rewindTimelineWarning = page.warning
        } catch {
            applyRewindFailure(error)
        }
        rewindTimelineBusy = false
    }

    /// The Load-more button (`hasMore && !busy` upstream).
    public func loadOlderRewindTimeline() async {
        guard !rewindTimelineBusy, rewindTimelineHasMore, !runtime.rewindLoadMorePending,
            let reader = runtime.rewindReader
        else { return }
        runtime.rewindLoadMorePending = true
        defer { runtime.rewindLoadMorePending = false }
        do {
            let page = try reader.next()
            // Frames arrive newest-first per page; older pages append.
            rewindGroups += groupRewindFrames(page.frames)
            rewindTimelineHasMore = page.next
            rewindTimelineWarning = page.warning ?? rewindTimelineWarning
        } catch {
            applyRewindFailure(error)
        }
    }

    /// `errorCopy` from DesktopRewind.tsx. `unavailable` clears the list
    /// quietly (missing history is normal); auth failures retire the reader.
    private func applyRewindFailure(_ error: any Error) {
        switch error as? RewindTimelineFailure {
        case .unavailable:
            rewindGroups = []
            rewindTimelineHasMore = false
            rewindTimelineWarning = nil
        case .rewindAuth, .ownerChanged:
            runtime.rewindReader = nil
            rewindGroups = []
            rewindTimelineHasMore = false
            rewindTimelineWarning = rewindAuthErrorCopy
        case .storage, nil:
            rewindTimelineWarning = rewindHistoryWarning
        }
    }
}

/// Exact copy from DesktopRewind.tsx `errorCopy`.
public let rewindAuthErrorCopy = "Sign in again from Settings to open your screen history."
