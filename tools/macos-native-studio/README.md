# Macro Studio: V3 native device prototype

Version 0.1.7 candidate. This is development, not a production daily scheduler or a completed visual macro editor.

0.1.7 adds an opt-in `允许开发2小时` UI action in the controller and test window. It uses a monotonic two-hour deadline; normal `client_end` releases the actual execution lock while keeping the remaining user-authorized development scope. Default and restart state is disabled. Stop, expiry, session/screen sleep, permission revocation, App exit and a live client's120-second idle timeout revoke it. The socket protocol cannot arm or extend input; system permission and target checks remain per operation. Pure Swift tests cover one-run reset, between-run reuse, duration bounds, expiry and revocation.

The typed `open_test` operation opens only the built-in window and refuses during an active run. `shutdown` requests normal App termination only when no native run is active. These remove UI-navigation churn from development; neither grants input or system permissions. CLI names are `open-test` and `shutdown`. TCC identity continuity and WOS input still require separate live acceptance.

0.1.5 live negative: the direct-CG test click reached the built-in receiver at `(762,-160)` instead of the requested button's `(300,333)` AppKit point. The receiver log distinguishes a real coordinate defect from missing permission; the original failed test is retained. No WOS input was sent with this failed candidate.

0.1.6 keeps the explicit `skylight-cg-screen` event profile but defaults its separate window-location stamp to window-local coordinates. Private config can select `mouse_cg_window_stamp` (`local`/`screen`/`none`), `mouse_cg_location` (`screen`/`window`) and `mouse_cg_phase` (0–3) for bounded, logged comparisons without rebuilding each experiment. Config selects one encoding; there is no automatic retry or fallback on failure. The test window has its own input-enable and stop controls, and the App has a normal Quit menu. Pure encoding and36 native interface tests pass; live acceptance remains pending.

0.1.5 adds the explicit `skylight-cg-screen` experiment: construct CG mouse events directly, stamp screen coordinates and the target window, use a shared click-group and target phase3 for both down/up. Move/down/up are the only events; no off-screen activation primer, authentication envelope, source-identity rewriting, window-focus injection or global HID fallback is added. The 0.1.4 AppKit encodings remain unchanged when another profile is selected. This addresses a concrete difference from the referenced mouse construction, but does not prove WOS accepts it. A pure Swift encoding check and the36 native Python tests pass; the candidate builds. Its fresh ad-hoc signature requires renewed system permission before live testing.

Latest0.1.4 live scope: built-in counter2→3 passed with unchanged hardware-pointer samples and inactive test target. WOS screenshots/OCR/shared lock worked, but normal close/profile clicks did not change the page across sampled encodings, including a fresh WOS process. Manual input and timer movement were user-confirmed; NSRunningApplication activation logging stayedfalse and is insufficient to conclude the user's foreground action failed. V2 briefly recovered identity navigation, then another local batch lost active CUA binding. Production migration is still pending; native development and remaining daily tasks have separate checkpoints.

The AppKit app owns ScreenCaptureKit capture, Vision OCR, experimental process-directed input, a local Unix socket, and the real device lock. The Python action engine uses a typed `NativeBackend`; it never starts CUA or evaluates JavaScript. Existing action JSON, identity checks, image conditions, recovery and reports remain reusable. CUA remains a separate V2 backend; there is no failover after a denial.

### Latest acceptance snapshot

- 0.1.2: real built-in counter increments passed with both subtype 3 and subtype 0, using delayed release. The target App was inactive. This rules out subtype 3 being necessary for that test; it does not by itself isolate every other change.
- 0.1.3: optional `SLEventPostToPid` and `CGEventSetWindowLocation` compatibility bindings were added. These are **undocumented system APIs**, not OpenAI's CUA service. The public-only claim of the initial prototype does not apply to this opt-in transport. No authentication envelope, event-source identity rewrite, focus-record injection, global HID tap or security-setting change is included. Missing symbols stop the requested transport; there is no fallback or duplicate delivery through two transports. See `THIRD_PARTY_NOTICES.md`.
- The compatibility route passed the built-in counter with `skylight-local`. `skylight-screen` actually reached the test window at the wrong coordinates and failed, which was captured by the local receiver monitor. Pointer positions matched before/after the successful sample; the target remained inactive. This is one controlled sample, not general pointer-isolation certification.
- WOS: several input encodings were attempted. A welcome-page transition was observed after a `skylight-screen` click, but later close/profile actions did not reliably change the UI. One official CUA reference click closed the promotional popup; that action is recorded separately and is **not native acceptance**. No complete native WOS action has passed yet.
- 0.1.4 refreshes the release timestamp at delivery time, supports a bounded `mouse_hold_ms` (25–250, default 100), and an explicit `mouse_touch_phase_numbers` experiment. The old event was created before the delay, so its embedded timestamp did not represent the observed hold. This candidate compiled and both capture/accessibility grants were refreshed. The new self-test then timed out before input: a main-thread `open` of the shared Documents lock awaited a separate Documents-folder consent (confirmed by a thread sample and TCC signature-mismatch log). The timing hypothesis remains unverified. The user must handle that system prompt; do not relocate the lock or remove mutual exclusion to avoid it.

The diagnostic profiles additionally include `global-subtype3`, `skylight-screen`, `skylight-local`, `skylight-unstamped` and `skylight-local-command`; these are selected explicitly from the private App config. They never change automatically after an error. Runtime experiments and source changes must retain their actual version, settings and result. The installed candidate remains ad-hoc signed; reauthorization cannot be inferred from the settings toggle or an older bundle's grant.

## Build and identity

Iteration policy: builds now default to `local-apps/candidates/Macro Studio.app`. The build script refuses an ad-hoc overwrite of an existing fixed-path runtime before touching any bundle files.37 native tests include a real temporary-filesystem check that this guard leaves an existing app unchanged. A persistent signer must be selected and its identity measured across two builds before claiming permission continuity. Do not replace an existing code-bound requirement with an identifier-only requirement or modify TCC records.

Most iteration belongs in typed JSON input parameters, Python controllers and game packages outside the stable permission-owning host. A future opt-in, time-limited development arm should survive ordinary client `end` while still releasing the real execution lock; explicit Stop, expiry and session loss must revoke it. This is an application UX proposal, not an implemented or automatically enabled permission. The current installed0.1.5 remains one-session-at-a-time;0.1.6 is only a built candidate until signer/update admission is resolved.

Run `./tools/macos-native-studio/build.sh` from this repository. The stable local destination is `local-apps/Macro Studio.app`, bundle ID `io.crossmacro.macro-studio`. Build products and module caches are ignored by Git. Only public Apple frameworks are linked. No root daemon, network listener, unlock service or OS security change is installed.

Default signing is ad hoc. It establishes an app bundle but does **not** prove stable TCC authorization across rebuilds. Set `MACRO_STUDIO_SIGN_IDENTITY` to a suitable existing signing identity for later signed builds; Developer ID/notarization are not included. Keep the app at a stable path. A code signing identity and a successful permission request are different from lock-screen access.

`MACRO_STUDIO_APP_PATH` can build a candidate in a separate directory without replacing an authorized installation. A candidate build is not a permission or live-input test. Preserve the previous bundle before installing a candidate at the stable path.

### First native acceptance, 2026-10-24

The user-granted 0.1.0 installation reported Screen Recording and Accessibility allowed. Native capture/OCR worked, but the built-in counter did not increase after one process-directed click. That failed probe is not WOS acceptance. The 0.1.1 candidate constructs AppKit mouse events with the explicit target window number and sets both public CG window-routing fields before `postToPid`; no global input fallback was added. This change compiles but still requires a live counter test.

Installing the ad-hoc-signed 0.1.1 candidate at the same path actually lost both TCC grants. Permission persistence across rebuilds therefore failed in this environment; a fixed bundle identifier alone is insufficient. The original granted bundle was preserved locally. Stable signing remains a release prerequisite, and 0.1.1 awaits renewed user authorization before any live test. Client 0.1.4 preserves before/after frames, OCR, click coordinates and the observed title even when the counter test fails, and reports the running App version rather than a hard-coded version.

After removing and re-adding stale TCC entries, 0.1.1 actually obtained both grants. Its native capture/OCR passed, but the counter remained unchanged. A separately recorded CUA reference click incremented the counter; that reference is not native acceptance.

The 0.1.2 diagnostic candidate adds a local event monitor restricted to the built-in target, recording received event type, window-local coordinates and activation state without altering the event or incrementing the counter. Mouse release is delivered from a bounded background callback after 25ms, allowing AppKit's nested mouse-tracking loop to receive it. Own NSWindow coordinates and external process coordinates are encoded separately; an NSEvent/CGEvent roundtrip showed that overwriting the CG location changes external window-coordinate payloads, while an owned NSWindow can convert correctly using its known frame. This distinction remains a hypothesis to validate against actual input, not a proven explanation for the entire 0.1.1 failure.

The private App config accepts `mouse_event_profile`: `window` (default), `window-subtype0`, or `legacy-global`. These are explicit development experiments; no failure automatically changes profile or switches to a global event tap. `window` sets the public mouse-subtype field to 3, an experimental delivery detail whose effect must be observed. Each click logs its chosen profile and decoded coordinates. All modes retain permissions, target/size checks and the actual shared lock. No private framework calls or private setters are used. The 0.1.2 candidate still requires TCC re-authorization and real counter/WOS acceptance.

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

Native runner0.1.2 records structured failure details. App refusals still halt input, but actual `permission_denied:*`, App activation/session, shared-lock conflicts, target-window changes and other native failures are reported separately. An App activation refusal or socket access error is not labelled missing macOS TCC. The App binary remains0.1.0; native/client/contracts/lease tests total31.

Runner0.1.3 checks evidence-storage headroom before creating a device session (default1GiB, private configurable minimum_free_bytes) and writes summary metadata through fsync/atomic replacement. Disk preflight failure starts no App session. Failed metadata writes preserve the previous checkpoint;35 native/client/contracts/lease/storage tests pass. Production V2 tests exposed a real disk-full interruption; those failures and later continuations remain separate evidence.

Native observations also check a64MiB evidence reserve before requesting the next frame (private minimum_observation_free_bytes). Exhaustion raises a fatal storage error and leaves the remaining tasks unexecuted; no alternate input path or recovery clicks are attempted.36 native-side tests pass; this is a best-effort reserve, not a disk quota or a guarantee against concurrent writers.

### File-access admission diagnostic

A Documents-based shared lock also needs ordinary macOS Documents-folder consent. That grant can become stale after an ad-hoc rebuild independently of screen capture and Accessibility. The0.1.4 live probe blocked in `open` before lock acquisition and before any click; the existing lock was independently confirmed free. Current admission opens synchronously on the main thread, so a pending OS consent also stalls the UI. A future responsive admission path must keep stop/status available and reject late requests after a client timeout. Do not interpret transport timeout as an input-effect test.

### Candidate admission responsiveness

0.1.8 moves opening the shared Documents lock off the App main thread. Admission has an eight-second deadline; a delayed descriptor is closed instead of starting a late session after the client has timed out. Stop invalidates pending admissions, a second begin is rejected, and permissions/session state are checked again before accepting the acquired lock. This does not grant Documents access or avoid its system consent prompt. The temporary-lock check covers contention, open failure, timeout, and late-result release without sending UI input. Candidate only; native WOS acceptance remains pending.
