import CoreGraphics

@main struct NativeClickEncodingCheck {
    static func main() {
        let point = CGPoint(x: -320, y: 190)
        for type: CGEventType in [.mouseMoved, .leftMouseDown, .leftMouseUp] {
            guard let event = NativeClickEncoding.make(type:type,screenPoint:point,
                windowID:123,pid:456,group:789) else { fatalError("Missing event") }
            precondition(event.type == type && event.location == point)
            precondition(event.getIntegerValueField(.mouseEventNumber) == (type == .mouseMoved ? 2 : 3))
            precondition(event.getIntegerValueField(.mouseEventClickState) == (type == .mouseMoved ? 0 : 1))
            precondition(event.getIntegerValueField(.mouseEventSubtype) == 3)
            precondition(event.getDoubleValueField(.mouseEventPressure) == (type == .leftMouseDown ? 1 : 0))
            precondition(event.getIntegerValueField(.eventTargetUnixProcessID) == 456)
            precondition(event.getIntegerValueField(.mouseEventWindowUnderMousePointer) == 123)
            precondition(event.getIntegerValueField(CGEventField(rawValue:51)!) == 123)
            precondition(event.getIntegerValueField(CGEventField(rawValue:58)!) == 789)
            precondition(event.flags.isEmpty)
        }
        precondition(NativeClickEncoding.make(type:.keyDown,screenPoint:point,windowID:123,pid:456,group:1) == nil)
        precondition(NativeClickEncoding.make(type:.leftMouseDown,screenPoint:point,windowID:123,pid:456,group:1,phase:2)!.getIntegerValueField(.mouseEventNumber) == 2)
        precondition(NativeClickEncoding.make(type:.leftMouseDown,screenPoint:point,windowID:123,pid:456,group:1,phase:4) == nil)
        precondition(NativeClickEncoding.make(type:.leftMouseDown,screenPoint:point,windowID:0,pid:456,group:1) == nil)
        precondition(NativeClickEncoding.make(type:.leftMouseDown,screenPoint:CGPoint(x:Double.nan,y:0),windowID:123,pid:456,group:1) == nil)
        var arm = InputAuthorization()
        precondition(!arm.allowed(now:100))
        arm.allowOnce(); precondition(arm.allowed(now:100))
        arm.finishRun(reason:"client_end"); precondition(!arm.allowed(now:101))
        precondition(!arm.allowDevelopment(now:100,seconds:7201))
        precondition(!arm.allowDevelopment(now:100,seconds:-1))
        precondition(arm.allowDevelopment(now:100,seconds:7200))
        arm.finishRun(reason:"client_end")
        precondition(arm.allowed(now:101) && arm.remaining(now:101) == 7199)
        precondition(!arm.allowed(now:7300) && arm.expired(now:7300))
        for reason in ["user_stop","session_inactive","client_timeout","screen_permission_revoked","development_expired","app_exit"] {
            precondition(arm.allowDevelopment(now:100))
            arm.finishRun(reason:reason)
            precondition(!arm.allowed(now:101) && arm.deadline == nil)
        }
        print("PASS: three event encodings, screen coordinates including negative display, window routing, phase/group/pressure metadata, no modifiers, invalid inputs. No events dispatched.")
        print("PASS: default-off, one-run reset, bounded two-hour opt-in, normal-end reuse, exact expiry and explicit revocation paths.")
    }
}
