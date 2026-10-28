import Foundation

// Display power is not an authentication or console-session signal.
// Actual screen-lock and TCC checks remain at every input admission point.
struct NativeSessionLifecycle {
    enum Event {
        case sessionResigned, sessionBecameActive
        case systemWillSleep, systemDidWake
        case screensDidSleep, screensDidWake
    }
    private(set) var sessionActive = true
    private(set) var systemAwake = true
    private(set) var displaysAwake = true
    var available: Bool { sessionActive && systemAwake }

    mutating func receive(_ event: Event) -> String? {
        switch event {
        case .sessionResigned: sessionActive = false; return "session_inactive"
        case .sessionBecameActive: sessionActive = true
        case .systemWillSleep: systemAwake = false; return "system_sleep"
        case .systemDidWake: systemAwake = true
        case .screensDidSleep: displaysAwake = false
        case .screensDidWake: displaysAwake = true
        }
        return nil
    }
}
