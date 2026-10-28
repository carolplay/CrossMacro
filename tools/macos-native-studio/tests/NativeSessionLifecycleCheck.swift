import Foundation

@main struct NativeSessionLifecycleCheck {
    static func main() {
        var state = NativeSessionLifecycle()
        precondition(state.receive(.screensDidSleep) == nil)
        precondition(state.available && !state.displaysAwake,
                     "Display sleep must not impersonate session deactivation")
        precondition(state.receive(.sessionResigned) == "session_inactive")
        precondition(!state.available)
        precondition(state.receive(.screensDidWake) == nil)
        precondition(!state.available && state.displaysAwake,
                     "Display wake must not reactivate an inactive session")
        precondition(state.receive(.systemWillSleep) == "system_sleep")
        _ = state.receive(.sessionBecameActive)
        precondition(!state.available, "An active session is insufficient while system sleeps")
        _ = state.receive(.systemDidWake)
        precondition(state.available)
        _ = state.receive(.sessionResigned)
        _ = state.receive(.systemDidWake)
        precondition(!state.available, "System wake must not override console-session state")
        print("PASS: display power, system sleep and console-session transitions stay separate. No UI/input or authentication changes.")
    }
}
