import AppKit
import Darwin

// Optional, explicitly selected compatibility transport. These are undocumented
// system APIs: availability does not certify delivery, stability or lock access.
// Design reference: trycua/cua platform-macos/input/{mouse,skylight}.rs (MIT).
// No authentication envelopes, source identity writes, focus records or HID tap.
enum NativeMouseTransport {
    typealias Post = @convention(c) (pid_t, CGEvent) -> Void
    typealias WindowLocation = @convention(c) (CGEvent, Double, Double) -> Void
    static let handle = dlopen("/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight", RTLD_NOW | RTLD_LOCAL)
    static let post: Post? = {
        guard let h=handle, let p=dlsym(h,"SLEventPostToPid") else { return nil }
        return unsafeBitCast(p,to:Post.self)
    }()
    static let setWindowLocation: WindowLocation? = {
        guard let h=handle, let p=dlsym(h,"CGEventSetWindowLocation") else { return nil }
        return unsafeBitCast(p,to:WindowLocation.self)
    }()
}
