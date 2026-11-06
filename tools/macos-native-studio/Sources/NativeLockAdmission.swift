import Foundation
import Darwin

// Documents consent can block open(). Keep that wait off the UI thread and
// discard any descriptor returned after the client's bounded admission window.
final class NativeLockAdmission: @unchecked Sendable {
    private let mutex = NSLock()
    private var completed = false
    private let continuation: CheckedContinuation<Int32, Never>
    init(_ continuation: CheckedContinuation<Int32, Never>) { self.continuation = continuation }
    func finish(_ fd: Int32) {
        mutex.lock()
        if completed {
            mutex.unlock()
            if fd >= 0 { Darwin.close(fd) }
            return
        }
        completed = true
        mutex.unlock()
        continuation.resume(returning: fd)
    }
    static func acquire(path: String, timeout: TimeInterval = 8,
                        opener: @escaping @Sendable (String) -> Int32 = { Darwin.open($0, O_CREAT | O_RDWR, 0o600) }) async -> Int32 {
        await withCheckedContinuation { continuation in
            let gate = NativeLockAdmission(continuation)
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + timeout) { gate.finish(-2) }
            DispatchQueue.global(qos: .userInitiated).async {
                let fd = opener(path)
                guard fd >= 0 else { gate.finish(-1); return }
                guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { Darwin.close(fd); gate.finish(-3); return }
                gate.finish(fd)
            }
        }
    }
}
