import CoreGraphics

// Event construction only: no dispatch, activation, authentication or HID tap.
// An explicit experimental profile; existing encodings remain unchanged.
enum NativeClickEncoding {
    static func make(type: CGEventType, screenPoint: CGPoint, windowID: UInt32,
                     pid: Int32, group: Int64, phase: Int64 = 3) -> CGEvent? {
        guard [.mouseMoved, .leftMouseDown, .leftMouseUp].contains(type),
              screenPoint.x.isFinite, screenPoint.y.isFinite,
              windowID > 0, pid > 0, (0...3).contains(phase),
              let event = CGEvent(mouseEventSource: nil, mouseType: type,
                                  mouseCursorPosition: screenPoint, mouseButton: .left)
        else { return nil }
        event.flags = []
        event.setIntegerValueField(.mouseEventNumber, value: type == .mouseMoved ? 2 : phase)
        event.setIntegerValueField(.mouseEventClickState, value: type == .mouseMoved ? 0 : 1)
        event.setIntegerValueField(.mouseEventButtonNumber, value: 0)
        event.setIntegerValueField(.mouseEventSubtype, value: 3)
        event.setDoubleValueField(.mouseEventPressure, value: type == .leftMouseDown ? 1 : 0)
        event.setIntegerValueField(.eventTargetUnixProcessID, value: Int64(pid))
        event.setIntegerValueField(.mouseEventWindowUnderMousePointer, value: Int64(windowID))
        event.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent, value: Int64(windowID))
        if let field = CGEventField(rawValue: 51) { event.setIntegerValueField(field, value: Int64(windowID)) }
        if let field = CGEventField(rawValue: 58) { event.setIntegerValueField(field, value: group) }
        return event
    }
}
