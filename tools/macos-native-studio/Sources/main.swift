import AppKit
import ApplicationServices
import ScreenCaptureKit
import Vision
import ImageIO
import Darwin

let appVersion = "0.1.1"
let ownBundle = "io.crossmacro.macro-studio"
func screenLocked() -> Bool {
    // WindowServer diagnostic; not a supported unlock mechanism or lock-screen capability.
    return (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool ?? false
}
let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Macro Studio")
struct Failure: Error, CustomStringConvertible { let description: String; init(_ text: String) { description = text } }
func encode(_ value: Any) -> Data { (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])) ?? Data("{}".utf8) }
func point(_ raw: Any?) throws -> CGPoint {
    guard let a = raw as? [Double], a.count == 2, a.allSatisfy({ $0.isFinite }) else { throw Failure("invalid_point") }
    return CGPoint(x: a[0], y: a[1])
}
func onConsole() -> Bool {
    guard let s = CGSessionCopyCurrentDictionary() as? [String: Any] else { return false }
    return s[kCGSessionOnConsoleKey as String] as? Bool == true
}

@MainActor
final class Studio: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var label: NSTextField!
    var logView: NSTextView!
    var testWindow: NSWindow?
    var inputEnabled = false
    var sessionAvailable = true
    var selected: SCWindow?
    var sessionToken: String?
    var lockFD: Int32 = -1
    var lastActivity = Date()
    var runID: String?
    var seq = 0
    var timer: Timer?
    var socketFD: Int32 = -1
    var compatibilityLock: URL {
        let file = support.appendingPathComponent("config.json")
        if let data = try? Data(contentsOf: file), let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let path = config["compatibility_lock_file"] as? String, path.hasPrefix("/") { return URL(fileURLWithPath: path) }
        return support.appendingPathComponent("device.lock")
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        chmod(support.path, 0o700)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 500), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.title = "Macro Studio — V3 native runtime"
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12; stack.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        let title = NSTextField(labelWithString: "本地执行器 · 原生权限 · 无 CUA / 模型调用"); title.font = .boldSystemFont(ofSize: 20); stack.addArrangedSubview(title)
        label = NSTextField(wrappingLabelWithString: ""); stack.addArrangedSubview(label)
        let buttons = NSStackView(); buttons.orientation = .horizontal; buttons.spacing = 10
        for (name, action) in [("刷新状态", #selector(refresh)), ("申请系统权限", #selector(requestPermissions)), ("打开测试窗口", #selector(openTest)), ("允许本次输入", #selector(enable)), ("停止 / 释放", #selector(stop))] {
            let button = NSButton(title: name, target: self, action: action); buttons.addArrangedSubview(button)
        }
        stack.addArrangedSubview(buttons)
        stack.addArrangedSubview(NSTextField(wrappingLabelWithString: "首版仅支持已解锁用户会话。需手动允许输入；停止、会话离开、屏幕休眠或空闲超时均撤销。后台定向输入是否被目标接受，须逐个验证。"))
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; logView = NSTextView(); logView.isEditable = false; logView.font = .monospacedSystemFont(ofSize: 11, weight: .regular); scroll.documentView = logView; stack.addArrangedSubview(scroll)
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 230).isActive = true
        window.contentView = stack; window.center(); window.makeKeyAndOrderFront(nil)
        for name in [NSWorkspace.sessionDidResignActiveNotification, NSWorkspace.screensDidSleepNotification, NSWorkspace.willSleepNotification] {
            NSWorkspace.shared.notificationCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in MainActor.assumeIsolated { self?.sessionAvailable = false; self?.end("session_inactive") } }
        }
        NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.sessionDidBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in MainActor.assumeIsolated { self?.sessionAvailable = true; self?.refresh() } }
        NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.screensDidWakeNotification, object: nil, queue: .main) { [weak self] _ in MainActor.assumeIsolated { self?.sessionAvailable = true; self?.refresh() } }
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let s = self else { return }
                if s.sessionToken != nil && Date().timeIntervalSince(s.lastActivity) > 120 { s.end("client_timeout") }
            }
        }
        refresh(); startServer(); log("app_started", ["version": appVersion, "socket": support.appendingPathComponent("control.sock").path])
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { end("app_exit"); if socketFD >= 0 { Darwin.close(socketFD); unlink(support.appendingPathComponent("control.sock").path) } }
    @objc func refresh() {
        label.stringValue = "屏幕录制：\(CGPreflightScreenCaptureAccess() ? "已允许" : "未允许")   辅助功能：\(AXIsProcessTrusted() ? "已允许" : "未允许")\n输入：\(inputEnabled ? "本次允许" : "停止")   运行：\(runID ?? "无")\n权限主体：\(ownBundle) · \(Bundle.main.bundlePath)"
    }
    @objc func requestPermissions() {
        _ = CGRequestScreenCaptureAccess()
        _ = AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
        refresh()
    }
    @objc func enable() {
        guard sessionAvailable, onConsole(), !screenLocked(), AXIsProcessTrusted(), CGPreflightScreenCaptureAccess() else { log("enable_blocked", ["reason": "session_or_permissions"]); refresh(); return }
        inputEnabled = true; log("input_enabled_by_user", [:]); refresh()
    }
    @objc func stop() { end("user_stop") }
    @objc func openTest() {
        if let existing = testWindow { existing.makeKeyAndOrderFront(nil); return }
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 420), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        w.isReleasedWhenClosed = false; w.title = "Macro Studio Test Target"; let v = NSStackView(); v.orientation = .vertical; v.spacing = 20; v.edgeInsets = NSEdgeInsets(top: 40, left: 40, bottom: 40, right: 40)
        v.addArrangedSubview(NSTextField(labelWithString: "READY 测试窗口"))
        v.addArrangedSubview(NSButton(title: "点击计数 +1", target: self, action: #selector(testClick)))
        let field = NSTextField(string: ""); field.placeholderString = "键盘测试（不输入个人信息）"; v.addArrangedSubview(field)
        w.contentView = v; w.center(); w.makeKeyAndOrderFront(nil); testWindow = w
    }
    var clicks = 0
    @objc func testClick() { clicks += 1; testWindow?.title = "Macro Studio Test Target — \(clicks)"; log("test_click", ["count": clicks]) }
    func log(_ kind: String, _ fields: [String: Any]) {
        seq += 1; var event = fields; event["seq"] = seq; event["time"] = Date().timeIntervalSince1970; event["event"] = kind; event["run_id"] = runID ?? NSNull(); let data = encode(event) + Data([10])
        let file = support.appendingPathComponent("events.jsonl")
        if !FileManager.default.fileExists(atPath: file.path) { FileManager.default.createFile(atPath: file.path, contents: nil, attributes: [.posixPermissions: 0o600]) }
        if let h = try? FileHandle(forWritingTo: file) { h.seekToEndOfFile(); h.write(data); try? h.close() }
        logView?.textStorage?.append(NSAttributedString(string: String(data: data, encoding: .utf8) ?? "")); logView?.scrollToEndOfDocument(nil)
    }
    func end(_ reason: String) {
        log("session_ended", ["reason": reason]); sessionToken = nil; selected = nil; inputEnabled = false; runID = nil
        if lockFD >= 0 { flock(lockFD, LOCK_UN); Darwin.close(lockFD); lockFD = -1 }
        refresh()
    }
    func status() -> [String: Any] {
        return ["version": appVersion, "backend": "native-macos", "bundle_id": ownBundle, "app_path": Bundle.main.bundlePath,
                "screen_recording": CGPreflightScreenCaptureAccess(), "accessibility": AXIsProcessTrusted(), "on_console": onConsole(),
                "session_available": sessionAvailable, "screen_locked_diagnostic": screenLocked(), "lock_support": false, "input_enabled": inputEnabled, "run_id": runID ?? NSNull(),
                "global_pointer_impact": "unverified", "window_directed_input": "experimental_postToPid", "cua_dependency": false,
                "socket": support.appendingPathComponent("control.sock").path, "lock_file": compatibilityLock.path]
    }
    func shareable() async throws -> SCShareableContent {
        guard CGPreflightScreenCaptureAccess() else { throw Failure("permission_denied:screen_recording") }
        return try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
    }
    func checkSession(_ request: [String: Any], input: Bool = false) throws -> SCWindow {
        guard let t = request["session"] as? String, t == sessionToken, let w = selected else { throw Failure("invalid_session") }
        guard sessionAvailable, onConsole(), !screenLocked() else { end("session_inactive"); throw Failure("session_inactive") }
        guard CGPreflightScreenCaptureAccess() else { end("screen_permission_revoked"); throw Failure("permission_denied:screen_recording") }
        if input && (!inputEnabled || !AXIsProcessTrusted()) { end("input_disabled_or_revoked"); throw Failure("permission_denied:input") }
        lastActivity = Date(); return w
    }
    func checkedPoint(_ raw: Any?, window: SCWindow) throws -> CGPoint {
        let p = try point(raw)
        guard p.x >= 0, p.y >= 0, p.x < window.frame.width, p.y < window.frame.height else { throw Failure("point_outside_window") }
        return CGPoint(x: window.frame.minX + p.x, y: window.frame.minY + p.y)
    }
    func keyCode(_ key: String) throws -> CGKeyCode {
        let map: [String: CGKeyCode] = ["Up":126,"Down":125,"Left":123,"Right":124,"Escape":53,"Return":36,"space":49,"Tab":48]
        guard let code = map[key] else { throw Failure("unsupported_key") }; return code
    }
    func freshWindow(_ window: SCWindow) async throws -> SCWindow {
        let content = try await shareable()
        guard let fresh = content.windows.first(where: {$0.windowID == window.windowID}), fresh.owningApplication?.processID == window.owningApplication?.processID,
              fresh.frame.size == window.frame.size else { end("window_changed"); throw Failure("window_size_changed_or_target_gone") }
        return fresh
    }
    func handle(_ q: [String: Any]) async throws -> [String: Any] {
        guard let op = q["op"] as? String else { throw Failure("missing_operation") }
        if op == "status" { return status() }
        if op == "windows" {
            let c = try await shareable()
            return ["windows": c.windows.filter { $0.owningApplication?.bundleIdentifier == "com.gof.global" || ($0.owningApplication?.bundleIdentifier == ownBundle && ($0.title ?? "").hasPrefix("Macro Studio Test Target")) }.map { ["id": $0.windowID, "pid": $0.owningApplication!.processID, "bundle_id": $0.owningApplication!.bundleIdentifier, "title": $0.title ?? "", "width": $0.frame.width, "height": $0.frame.height] as [String: Any] }]
        }
        if op == "begin" {
            guard inputEnabled, sessionAvailable, onConsole(), !screenLocked(), AXIsProcessTrusted() else { throw Failure("input_not_enabled_in_app") }
            guard sessionToken == nil else { throw Failure("active_executor") }
            guard let wid = q["window_id"] as? UInt32, let expected = q["expected_size"] as? [Double], expected.count == 2,
                  let rid = q["run_id"] as? String, !rid.isEmpty, rid.count <= 100 else { throw Failure("invalid_begin") }
            let c = try await shareable()
            guard let w = c.windows.first(where: {$0.windowID == wid}), let bundle = w.owningApplication?.bundleIdentifier,
                  bundle == "com.gof.global" || (bundle == ownBundle && (w.title ?? "").hasPrefix("Macro Studio Test Target")) else { throw Failure("target_not_allowed") }
            guard [w.frame.width,w.frame.height] == expected else { throw Failure("window_size_changed") }
            guard sessionToken == nil, inputEnabled, !screenLocked() else { throw Failure("active_executor_or_disabled") }
            let fd = Darwin.open(compatibilityLock.path, O_CREAT | O_RDWR, 0o600)
            guard fd >= 0 else { throw Failure("lock_file_unavailable") }
            guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { Darwin.close(fd); throw Failure("active_executor") }
            lockFD = fd; selected = w; sessionToken = UUID().uuidString; runID = rid; lastActivity = Date(); log("session_started", ["window_id": wid, "target_bundle": bundle]); refresh()
            return ["session":sessionToken!, "window_id":wid, "size":expected, "backend":"native-macos", "version":appVersion]
        }
        if op == "end" { _ = try checkSession(q); end("client_end"); return ["ended":true] }
        let w = try checkSession(q, input: op != "screenshot")
        let fresh = try await freshWindow(w)
        // Recheck after asynchronous enumeration: a Stop action may have revoked the session.
        _ = try checkSession(q, input: op != "screenshot")
        if op == "screenshot" {
            let filter = SCContentFilter(desktopIndependentWindow: fresh)
            let config = SCStreamConfiguration(); config.width = Int(fresh.frame.width); config.height = Int(fresh.frame.height); config.showsCursor = false; config.ignoreShadowsSingleWindow = true
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
            _ = try checkSession(q)
            let data = NSMutableData(); guard let dest = CGImageDestinationCreateWithData(data, "public.png" as CFString, 1, nil) else { throw Failure("png_encoder_unavailable") }; CGImageDestinationAddImage(dest,image,nil); guard CGImageDestinationFinalize(dest) else { throw Failure("png_encoding_failed") }
            let ocr = VNRecognizeTextRequest(); ocr.recognitionLevel = .accurate; ocr.usesLanguageCorrection = false; ocr.recognitionLanguages = ["zh-Hans","en-US"]
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([ocr])
            let lines: [[String: Any]] = (ocr.results ?? []).compactMap { o in guard let t = o.topCandidates(1).first else {return nil}; let b=o.boundingBox; return ["text":t.string,"confidence":t.confidence,"bounds":[b.minX,1-b.maxY,b.width,b.height]] }
            log("observed", ["window_id":w.windowID,"width":image.width,"height":image.height])
            return ["png_base64":(data as Data).base64EncodedString(),"ocr":["width":image.width,"height":image.height,"lines":lines],"window_id":w.windowID]
        }
        guard let pid = fresh.owningApplication?.processID else { throw Failure("target_gone") }
        if op == "click" {
            let p = try checkedPoint(q["point"], window: fresh)
            // Process-directed events bypass WindowServer hit testing. Preserve an
            // explicit AppKit window number as well as the global CG location.
            let local = CGPoint(x:p.x-fresh.frame.minX,y:fresh.frame.height-(p.y-fresh.frame.minY))
            let number = seq + 1
            func mouse(_ type: NSEvent.EventType, _ pressure: Float) -> CGEvent? {
                guard let event = NSEvent.mouseEvent(with:type,location:local,modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:Int(fresh.windowID),context:nil,eventNumber:number,clickCount:1,pressure:pressure)?.cgEvent else { return nil }
                event.location = p
                event.setIntegerValueField(.mouseEventWindowUnderMousePointer,value:Int64(fresh.windowID))
                event.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent,value:Int64(fresh.windowID))
                return event
            }
            guard let down=mouse(.leftMouseDown,1), let up=mouse(.leftMouseUp,0) else { throw Failure("event_creation_failed") }
            down.postToPid(pid); up.postToPid(pid)
        } else if op == "key" {
            guard let key=q["key"] as? String, let ms=q["duration_ms"] as? Int, (0...1000).contains(ms) else { throw Failure("invalid_key") }
            let code=try keyCode(key); guard let down=CGEvent(keyboardEventSource:nil,virtualKey:code,keyDown:true),let up=CGEvent(keyboardEventSource:nil,virtualKey:code,keyDown:false) else {throw Failure("event_creation_failed")}
            down.postToPid(pid)
            // Release key even if Stop/session change occurs during the bounded hold.
            try? await Task.sleep(nanoseconds:UInt64(ms)*1_000_000); up.postToPid(pid)
        } else { throw Failure("unsupported_operation") }
        log("input_sent",["op":op,"window_id":w.windowID,"delivery":"postToPid","application_effect":"unverified"])
        return ["sent":true,"effect_verified":false]
    }
    func startServer() {
        let path=support.appendingPathComponent("control.sock").path
        let fd=Darwin.socket(AF_UNIX,SOCK_STREAM,0); guard fd >= 0 else {log("server_failed",[:]);return}
        // A separate process lock prevents a second app from unlinking an active socket.
        let serverLock=Darwin.open(support.appendingPathComponent("server.lock").path,O_CREAT|O_RDWR,0o600)
        guard serverLock >= 0, flock(serverLock,LOCK_EX|LOCK_NB)==0 else {Darwin.close(fd);if serverLock>=0 {Darwin.close(serverLock)};log("server_already_running",[:]);return}
        unlink(path); var address=sockaddr_un();address.sun_family=sa_family_t(AF_UNIX)
        let bytes=Array(path.utf8)+[0];guard bytes.count <= MemoryLayout.size(ofValue:address.sun_path) else {log("socket_path_too_long",[:]);Darwin.close(fd);Darwin.close(serverLock);return}
        withUnsafeMutableBytes(of:&address.sun_path) { raw in for i in bytes.indices {raw[i]=bytes[i]} }
        let bound=withUnsafePointer(to:&address) {p in p.withMemoryRebound(to:sockaddr.self,capacity:1) {Darwin.bind(fd,$0,socklen_t(MemoryLayout<sockaddr_un>.size))} }
        guard bound==0, Darwin.listen(fd,4)==0 else {Darwin.close(fd);Darwin.close(serverLock);log("socket_bind_failed",[:]);return}
        chmod(path,0o600);socketFD=fd
        DispatchQueue.global(qos:.utility).async {
            while true {
                let client=Darwin.accept(fd,nil,nil);if client<0 {break}
                var uid:uid_t=0;var gid:gid_t=0
                guard getpeereid(client,&uid,&gid)==0,uid==getuid() else {Darwin.close(client);continue}
                var timeout=timeval(tv_sec:10,tv_usec:0);setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,socklen_t(MemoryLayout<timeval>.size));setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&timeout,socklen_t(MemoryLayout<timeval>.size))
                var data=Data();var buffer=[UInt8](repeating:0,count:4096)
                while data.count<=1_048_576 {let n=Darwin.read(client,&buffer,buffer.count);if n<=0 {break};data.append(contentsOf:buffer.prefix(n));if data.contains(10) {break}}
                guard data.count<=1_048_576,let end=data.firstIndex(of:10),let q=try? JSONSerialization.jsonObject(with:data.prefix(upTo:end)) as? [String:Any] else {Darwin.close(client);continue}
                DispatchQueue.main.async {
                    Task { @MainActor in
                        var result:[String:Any]
                        do {result=["ok":true,"result":try await self.handle(q)]} catch {result=["ok":false,"error":String(describing:error)];self.log("operation_blocked",["op":q["op"] ?? "unknown","reason":String(describing:error)])}
                        let reply=encode(result)+Data([10]);reply.withUnsafeBytes { raw in var offset=0;while offset<raw.count {let n=Darwin.send(client,raw.baseAddress!.advanced(by:offset),raw.count-offset,0);if n<=0 {break};offset+=n} };Darwin.close(client)
                    }
                }
            }
            Darwin.close(serverLock)
        }
    }
}
if CommandLine.arguments.contains("--self-check") {
    print(String(data:encode(["version":appVersion,"bundle_id":ownBundle,"cua_dependency":false,"operations":["status","windows","begin","screenshot","click","key","end"],"lock_support":false]),encoding:.utf8)!)
} else {
    signal(SIGPIPE,SIG_IGN)
    MainActor.assumeIsolated { let app=NSApplication.shared;let delegate=Studio();app.delegate=delegate;app.setActivationPolicy(.regular);app.run() }
}
