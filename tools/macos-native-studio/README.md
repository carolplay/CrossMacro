# Macro Studio: V3 native device prototype

Version 0.1.0. This is S0/S1 development, not a production daily scheduler or a completed visual macro editor.

The AppKit app owns ScreenCaptureKit capture, Vision OCR, experimental `CGEvent.postToPid` input, a local Unix socket, and the real device lock. The Python action engine uses a typed `NativeBackend`; it never starts CUA or evaluates JavaScript. Existing action JSON, identity checks, image conditions, recovery and reports remain reusable. CUA remains a separate V2 backend; there is no failover after a denial.

## Build and identity

Run `./tools/macos-native-studio/build.sh` from this repository. The stable local destination is `local-apps/Macro Studio.app`, bundle ID `io.crossmacro.macro-studio`. Build products and module caches are ignored by Git. Only public Apple frameworks are linked. No root daemon, network listener, unlock service or OS security change is installed.

Default signing is ad hoc. It establishes an app bundle but does **not** prove stable TCC authorization across rebuilds. Set `MACRO_STUDIO_SIGN_IDENTITY` to a suitable existing signing identity for later signed builds; Developer ID/notarization are not included. Keep the app at a stable path. A code signing identity and a successful permission request are different from lock-screen access.

Some mixed Command Line Tools installations contain two SwiftBridging module maps. `MACRO_STUDIO_CLT_OVERLAY=1` uses a project-local compiler VFS overlay to hide the duplicate legacy map for the build only. It does not modify `/Library/Developer`.

## First setup (human-controlled)

Run `python3 tools/macos-native-studio/client.py doctor --expected-lock
/absolute/path/to/visit.lock --output /private/diagnostics` first. This only
reads the running app's permission/session state and installed code-signing
identity. It reports screen recording, Accessibility, session, input enablement,
active execution and shared-lock mismatch separately; it does not request or
grant access. A passing diagnostic means ready for the built-in test, not that
WOS, background input or lock-screen operation has passed. Ad-hoc signing is
reported explicitly; do not assume a stable bundle ID preserves TCC after a
rebuild. Running and installed bundle versions are kept separate.

1. While the Mac is unlocked, open the built app. Use its **申请系统权限** button and grant Screen Recording and Accessibility to **Macro Studio** in macOS settings. This is a new native app, not inherited ChatGPT/Python permission.
2. Put `config.example.json` at `~/Library/Application Support/Macro Studio/config.json` and replace its lock path with the real existing V2 `visit.lock`. Restart the app before testing. No second daily scheduler is installed.
3. Open the built-in test window, then click **允许本次输入** in Studio. The first test is restricted to this window, not WOS.
4. Use `python3 tools/macos-native-studio/client.py status`, then `windows`. `self-test --execute --output /private/test/evidence` performs one OCR-targeted test-button click and verifies the observed counter increases by exactly one. Repeated tests need no app restart; sending an event without the corresponding counter change fails.
5. Stop releases the real flock and revokes input. Session/screen sleep notifications and a 120-second idle watchdog also stop it. This prototype requires enabling each input session; unattended scheduling is a later milestone.

A preflight result, accepted event or interface success is not proof that the UI changed. Background input, pointer isolation, WOS touch alternatives, image geometry, permissions after restart/update, capture with the monitor asleep, and locked-session behavior all require separate evidence. V3 0.1.0 does **not** support locked operation. The WindowServer lock diagnostic is best-effort, not an unlock mechanism or a substitute for explicit session/permission checks.

## Protocol

The app permits the current local user on a `0600` Unix socket inside a `0700` support directory. It exposes only `status`, `windows`, `begin`, `screenshot`, `click`, `key`, and `end`; no arbitrary shell, JavaScript, file writes or remote listening. Allowed windows are WOS (`com.gof.global`) and the app's built-in test target. A random app-generated session capability belongs only to this local native protocol and has no relationship to CUA/ChatGPT credentials.

`begin` requires explicit window ID, exact dimensions, manual input enablement and acquisition of the shared OS flock. The app owns that flock until end/stop/session loss/timeout. Per-input checks refresh the same window ID, process and dimensions; a changed target blocks input. The lease and event log are observability data, not authority to seize a lock.

`click` uses reference-to-global window coordinates and process-directed events, never a global HID fallback. `key` supports a bounded set of arrows/Escape/Return/space/Tab, with holds at most 1000ms. Sending an event returns `effect_verified:false`; the action's after-condition must verify the result. Native wheel/drag and audio are not implemented in this prototype.

## Existing macro adapter

`native_visit.py` reads the existing manifest and validates every selected workflow before connecting. Without `--execute` it is fully offline. Explicit targeted tasks remain reported as targeted development. With execution, the app acquires the shared lock; the Python runner does not take a second conflicting flock. The engine retains its per-log lock and existing guard configuration.

```
python3 tools/macos-native-studio/native_visit.py \
  --package-root /absolute/path/to/codex-game-skills/skills/play-whiteout-survival-macros \
  --config /private/native-profile.json --log-root /private/runs \
  --manifest /absolute/path/to/skill/macros/shift-1.json \
  --profile mature-test --tasks mail
```

Add `--execute` only after native permissions and the test-window probe are verified. Copy the private role's current identity, image templates and resource policy to a separate native profile, adding `native_window_id`, `native_expected_size` and `native_lock_file`; do not remove guard checks. This does not migrate V2 configuration or scheduling automatically.

Python and Pillow are still external runtime dependencies in this first developer build. The device app is native and contains the offline OCR executable, but complete engine packaging, the visual editor, schedule ownership and production migration remain unfinished.

## Validation

- Existing engine tests: `python3 -m unittest discover -s tools/macos-window`.
- Native dispatch and denied-start tests: `python3 -m unittest discover -s tools/macos-native-studio/tests`.
- Built app `Contents/MacOS/MacroStudio --self-check`: checks binary/protocol identity without starting AppKit or accessing devices.
- Real acceptance: test target capture/click/keys, pointer before/after and background behavior, restart/rebuild permission identity, shared-lock collision and stop, then one WOS identity roundtrip and a targeted existing action. Offline tests do not satisfy these real-device checks.

Sources: [ScreenCaptureKit screenshot manager](https://developer.apple.com/documentation/screencapturekit/scscreenshotmanager), [process-directed CGEvent](https://developer.apple.com/documentation/coregraphics/cgevent/posttopid(_:)), [Accessibility trust](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions).

## Offline contracts and current client changes

Client diagnostics/probe revision 0.1.2 reports an absent or inaccessible native App as an explicit non-ready diagnostic and saves failed probe evidence in a new output directory without masking the original failure. The installed App remains 0.1.0 until an explicit rebuild; Python client changes do not grant native permissions.

`capability_contracts.py` resolves a game-owned versioned JSON registry of `pages` and `exits` before connecting to any device. A reference is exactly `{"$page":"name"}` or `{"$exit":"name"}`; field overrides, unknown references, cycles and excessive expansion fail offline. Compiled workflows retain both the authored content hash and registry identity/hash. Use `native_visit.py --contract-registry /path/to/game/ui-contracts.json` explicitly; existing inline workflows and V2 production are unchanged. The device backend contains no WOS page names. Registry availability does not certify the corresponding UI branch.

Shared engine 0.4.8 distinguishes its local workflow budget from device/transport failure. A local budget exhaustion remains a deviation; a fresh, at most 60-second declared-page recovery may restore the anchor before the following task. Each exit shares the same absolute recovery deadline, and an exhausted recovery is not restarted. Unknown pages stop the batch. Lock, identity, size, permission and transport timeout failures remain fatal with no recovery input. These limits are not native TCC permissions or a way around a platform refusal.

Diagnostic client 0.1.3 also probes the existing shared regular lock without creating, following symlinks, or modifying its contents. Another V2 executor blocks test readiness even if Studio's own run is empty. This is only a snapshot: native `begin` still takes the actual lock atomically. The native client/contracts test suite now contains 24 tests.

Shared engine 0.4.9 extends the existing full-frame-first OCR option to `text_target` click coordinates. `prefer_frame_ocr:true` requires `crop_ocr:true`: one confident in-bounds full-frame match can resolve the same target directly; absent, ambiguous or low-confidence matches retain the same saved-frame crop fallback. Scope, offset bounds, exact/regex matching and uniqueness checks remain enforced. This is opt-in; unchanged actions keep the original behavior. Engine tests: 136; native/client/contracts tests: 24. Native WOS acceptance remains separate.

Native runner 0.1.1 supports an explicit private `native_lease_file` and `native_role`. Only after App `begin` succeeds and an actual held lock is confirmed does it record native-run metadata; local activity refreshes that metadata, not App/OS permissions. Cleanup marks released only after the physical lock is free, preserves another owner's record, and reports uncertain cleanup instead of claiming success. The local run identifier is unrelated to ChatGPT/CUA trust or credentials. Both helper tests and runner-level tests use real temporary flocks; native/client/contracts tests now total 29. No installed App rebuild is required for this client change.
