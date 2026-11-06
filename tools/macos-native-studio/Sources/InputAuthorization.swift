import Foundation

// App-local user intent, separate from macOS grants and the execution lock.
// Only UI actions arm input; the protocol cannot grant or extend this scope.
struct InputAuthorization {
    private(set) var once = false
    private(set) var deadline: TimeInterval?
    mutating func allowOnce() { once = true; deadline = nil }
    mutating func allowDevelopment(now: TimeInterval, seconds: TimeInterval = 7200) -> Bool {
        guard now.isFinite, seconds.isFinite, seconds > 0, seconds <= 7200 else { return false }
        once = false; deadline = now + seconds; return true
    }
    func allowed(now: TimeInterval) -> Bool { once || (deadline.map { now < $0 } ?? false) }
    func expired(now: TimeInterval) -> Bool { deadline.map { now >= $0 } ?? false }
    func remaining(now: TimeInterval) -> TimeInterval { deadline.map { max(0, $0-now) } ?? 0 }
    mutating func finishRun(reason: String) {
        once = false
        if reason != "client_end" { deadline = nil }
    }
}
