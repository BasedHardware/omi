import Foundation

/// An exclusive `flock` over a read-modify-write of a file that is replaced by `rename(2)`.
///
/// A dedicated lock file that is only ever locked — never renamed, never replaced — so every writer
/// locks the same inode for the lifetime of the install. Locking the *destination* instead would lock
/// an inode that the next rename unlinks, after which two writers hold exclusive locks on two
/// different inodes and the lock means nothing.
///
/// `flock` is released by the kernel when the process dies, so a crashed writer cannot wedge the
/// file. That property is load-bearing here: both files this guards are written by
/// `context-for-claude-mcp`, a process Claude spawns and kills at will.
///
/// Extracted from `QueryStamp`, which had the only copy, when `ToolCallLedger` needed the identical
/// discipline over the identical failure mode. Two hand-written flock dances in one package is one
/// more than can be kept correct.
struct ContextFileLock {
    private let descriptor: Int32

    init(at url: URL) throws {
        descriptor = open(url.path, O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
        guard descriptor >= 0 else {
            throw ContextFileLockError.couldNotLock(
                path: url.path, reason: String(cString: strerror(errno)))
        }
    }

    func acquire() throws {
        while flock(descriptor, LOCK_EX) != 0 {
            // A signal interrupting the wait is not a failure to lock.
            guard errno == EINTR else {
                throw ContextFileLockError.couldNotLock(
                    path: "fd \(descriptor)", reason: String(cString: strerror(errno)))
            }
        }
    }

    /// Closing the descriptor releases the lock; unlocking first keeps that explicit.
    func release() {
        flock(descriptor, LOCK_UN)
        close(descriptor)
    }

    /// Writes `data` to `url` so no reader can ever observe a partial file.
    ///
    /// The payload goes to a uniquely named temp file in the same directory and is then `rename(2)`d
    /// onto the destination. POSIX rename is atomic within a filesystem: a reader opening the path
    /// gets either the whole previous file or the whole new one, never a mixture and never a
    /// zero-length truncation. Readers therefore take no lock at all and can never block a writer.
    ///
    /// The temp name carries the pid *and* a UUID. A shared temp name would let two processes
    /// interleave their bytes into one temp file and then rename the wreckage into place.
    static func replace(_ url: URL, with data: Data) throws {
        let directory = url.deletingLastPathComponent()
        let temp = directory.appendingPathComponent(
            ".\(url.lastPathComponent).\(ProcessInfo.processInfo.processIdentifier).\(UUID().uuidString).tmp")
        try data.write(to: temp)
        ContextPaths.setPermissions(temp, mode: 0o600)
        guard rename(temp.path, url.path) == 0 else {
            let reason = String(cString: strerror(errno))
            try? FileManager.default.removeItem(at: temp)
            throw ContextFileLockError.couldNotReplace(path: url.path, reason: reason)
        }
    }
}

enum ContextFileLockError: Error, LocalizedError, Equatable {
    case couldNotLock(path: String, reason: String)
    case couldNotReplace(path: String, reason: String)

    var errorDescription: String? {
        switch self {
        case let .couldNotLock(path, reason):
            return "Could not lock \(path): \(reason)"
        case let .couldNotReplace(path, reason):
            return "Could not replace \(path): \(reason)"
        }
    }
}
