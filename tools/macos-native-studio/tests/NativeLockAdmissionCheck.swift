import Foundation
import Darwin

@main struct NativeLockAdmissionCheck {
    static func main() async {
        let path = NSTemporaryDirectory()+"macro-lock-admission-"+UUID().uuidString
        defer { unlink(path) }
        let first = await NativeLockAdmission.acquire(path:path)
        precondition(first >= 0)
        let busy = await NativeLockAdmission.acquire(path:path)
        precondition(busy == -3)
        close(first)
        let unavailable = await NativeLockAdmission.acquire(path:path, opener:{_ in -1})
        precondition(unavailable == -1)
        let timedOut = await NativeLockAdmission.acquire(path:path, timeout:0.005, opener:{ p in
            usleep(50_000)
            return Darwin.open(p,O_CREAT|O_RDWR,0o600)
        })
        precondition(timedOut == -2)
        try? await Task.sleep(nanoseconds:100_000_000)
        let after = await NativeLockAdmission.acquire(path:path)
        precondition(after >= 0, "Late descriptor must not retain the device lock")
        close(after)
        print("PASS: unique lock, busy denial, open failure, bounded timeout, late result closes descriptor and releases lock. No UI or game input.")
    }
}
