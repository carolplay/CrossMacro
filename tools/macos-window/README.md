# macOS window-task prototype

This fork reuses CrossMacro's **existing Shell Command editor actions, macro
files, playback engine and scheduler**. A small external executor captures a
specific app window, reads it with local Apple Vision OCR and sends window-bound
input through an already installed CUA MCP runtime. No model is called at run
time. This is an experimental integration, not a replacement for the default
desktop backend or an implementation of background input for every Mac app.

## Requirements

- macOS and a working local CUA MCP installation with its normal OS permissions.
  The runtime is supplied by the user. Its proprietary binaries are **not**
  included, and its internal entry point is not a stable public SDK contract.
- Python 3.9+ (use an explicit executable path for GUI-launched macros).
- Xcode command-line tools to compile the local OCR helper.
- .NET 10 to build CrossMacro following `CONTRIBUTING.md`.

Build the OCR helper locally:

```sh
mkdir -p tools/macos-window/build
clang -fobjc-arc -fno-modules -framework Foundation -framework Vision \
  -framework ImageIO tools/macos-window/vision-ocr.m \
  -o tools/macos-window/build/vision-ocr
```

Copy `config.example.json` **outside this repository** and set the MCP manifest,
OCR binary, exact running application path/bundle ID, language, expected account
identity strings and private log directory. `authorized_tools` is the explicit
local app/capability allowlist used for normal MCP elicitation requests. Requests
for other applications or capabilities are declined; no persistent grant or
chat identity is synthesized. Keep account IDs, paths, screenshots and logs local.

`guard_command`, when set, is an argv array returning JSON with an `active`
executor field. A non-null active executor stops the task before backend startup.
A local advisory lock prevents this executor from running two steps at once.
This is not a distributed lock with other automation systems: do not schedule
another executor against the same game during this experiment.

## Create an editable CrossMacro macro

### Exploration idle rewards

`wos-idle-rewards.json` is a real, ten-step daily-reward workflow for the
788×1079 Chinese client. It verifies the configured identity, opens Exploration,
claims idle income, dismisses the reward overlay, checks that Claim is disabled,
and returns to the city. When already cooling down it skips the claim actions.
Use the same export/worker commands below with this workflow path. Load the
exported macro in the editor; each step is an ordinary Shell action.

Existing scenario reference:
[`claim_exploration_idle_income`](https://github.com/AminulIslamSifat/whiteout-survival-bot/blob/main/usecases/exploration.py)
uses an Android ADB backend. This workflow was calibrated separately against the
macOS client and uses the local executor above, without importing that bot or its
account, spending, emulator or background services.

The optional `green_regions` conditions require Pillow in the chosen Python.
OCR checks page text, while a calibrated button region distinguishes enabled
green Claim from disabled grey Claim. A grey label still says Claim: OCR alone
cannot distinguish these states. Claiming starts a ten-minute cooldown, during
which the income-details dialog cannot be reopened. Do not assume immediate
reopening can verify a zero elapsed timer. Color regions and coordinates require
recalibration when the game layout, window size or language changes.

Condition objects support `all`, `any`, `none`, `timer_seconds`, and
`green_regions`; ordinary text arrays remain supported. `skip_if` explicitly
skips a step from its current local observation and records that fact.
`observe_attempts` (1–5) retries only post-action observations during animations,
never the click. The runtime calls no models. CrossMacro's reported event count
may be zero because these are script actions rather than native mouse events.

In macOS window-task mode the CLI preflight does not create a desktop input
device. Macros that request native input still fail at the disabled platform
factory; this is the same external-only mode used by the editor and scheduler.

```sh
/absolute/path/to/python3 tools/macos-window/window_macro.py export \
  --config /private/path/config.json \
  --workflow tools/macos-window/wos-profile.json \
  --output /private/path/wos-profile.macro
```

Open the generated file with **Editor → Load**. It restores four ordinary,
editable Shell Command actions: verify city, open profile, verify identity, and
return to city. The command/step selection, ordering and execution timeout can
be edited and saved in CrossMacro. OCR text and click coordinates currently live
in the JSON workflow; they do **not** yet have dedicated visual property panels.
The export embeds absolute paths; regenerate it when moving the project.

Before running GUI schedules, start the local worker from your terminal/runtime:

```sh
/absolute/path/to/python3 tools/macos-window/window_macro.py serve \
  --config /private/path/config.json \
  --workflow tools/macos-window/wos-profile.json
```

Add a `worker_socket` path to the local config, inside a private, current-user
directory (0700). The socket itself is 0600. The worker accepts only step names
from its loaded workflow; it does not accept commands, scripts, target apps or
configuration over IPC. Generated Shell actions use `request` to talk to this
worker, which serializes execution and retains one MCP connection. Stop it with
Ctrl-C (or SIGTERM when launched as a managed process).

In the local trial, starting the CUA runtime directly from a GUI-launched child
timed out during its initial tool call, while terminal-launched execution worked.
The worker is the tested integration route; its initialization still depends on
the user's installed runtime and desktop environment. This is not evidence that
the same initialization will work from launchd or after the host app exits.

Launch the platform app with these environment variables (an app bundle can
declare them in its local `LSEnvironment`):

```sh
export CROSSMACRO_CONFIG_DIR=/absolute/private/path/crossmacro-profile
export CROSSMACRO_WINDOW_TASKS_ONLY=1
dotnet run --project src/CrossMacro.UI.MacOS/CrossMacro.UI.MacOS.csproj
```

`CROSSMACRO_CONFIG_DIR` isolates profiles, schedules and logs from the user's
normal installation. The window-task mode starts the editor and scheduler,
without native global hotkeys, text expansion, triggers or recording services.
Native input/capture simulator factories explicitly reject requests in this
mode. The default application behavior is unchanged when the flag is absent.
External actions retain their own OS permission requirements.

Before scheduling, validate and replay the macro with the platform executable:

```sh
crossmacro macro validate /private/path/wos-profile.macro --json
crossmacro play /private/path/wos-profile.macro --json
crossmacro schedule add --name "WOS prototype once" \
  --macro /private/path/wos-profile.macro --at "2030-01-15T18:00:00"
```

New tasks start disabled. Enable a **single** future test in Schedule after
checking the target app, then keep CrossMacro running in the logged-in desktop
session. A one-time task becomes disabled after its attempt. Do not migrate
existing daily schedules until the trial is reliable.

## Execution behavior

- Each step takes a fresh target-window image and checks actual image dimensions
  against `reference_size`; a size change stops execution before a click.
- OCR must satisfy all preconditions. Identity-sensitive steps also require the
  configured identity strings. Clicks require a separate visual completion check.
- There are no blind retries, foreground fallback, global cursor events, cloud
  OCR or game network/memory APIs. A failure exits nonzero and is surfaced by
  CrossMacro's normal Shell/schedule status.
- The bundled WOS flow only opens a profile and returns. It spends no resources.
  Its sample coordinates are calibrated to a 788×1079 window, including title bar.
- Step logs contain timestamps, pass/fail conditions, screenshots and OCR JSON.
  Cancellation closes the owned MCP process group; it does not force clicks to
  recover an unknown game state.
- Lock screen, sleep, minimized windows, app upgrades and long unattended runs
  are not established by this prototype. The host/runtime currently must remain
  available. Shell steps each create a new MCP process, trading some startup
  overhead for simple cancellation and isolation. The exported GUI macro instead
  uses the persistent worker connection. A failed worker must be restarted before
  further scheduled work; no foreground fallback is attempted.

## Optional process-audio experiment and deferred check

`audio-tap.m` uses Apple's macOS 14.2+ Core Audio process tap to capture only the
configured app's output. It does not capture a microphone or fall back to the
global audio mix, and it leaves speaker output and default audio devices intact.
The private tap/aggregate device is destroyed on exit. Build it in a stable local
app bundle with an `NSAudioCaptureUsageDescription` and normal system audio
permission; do not put the resulting recordings in this repository.

```sh
clang -fobjc-arc -fno-modules -mmacosx-version-min=14.2 \
  -framework AppKit -framework CoreAudio -framework AudioToolbox \
  tools/macos-window/audio-tap.m -o /private/path/WOSAudioTap.app/Contents/MacOS/audio-tap
```

`audio_feedback.py` manages the capture, converts CAF to 16-bit WAV with the
system `afconvert`, and provides local time-aligned normalized-waveform template
scoring using NumPy. Silence or low/ambiguous scores never confirm an action. A matching sound
is a candidate event, not semantic proof that the expected page/reward changed.
Synthetic tests verify alignment and fallback, not real WOS sound accuracy.

Add `audio_capture: {"binary": "/private/path/to/audio-tap", "mode": "shadow"}`
to the private config. `audio_trial.py` wraps an existing CrossMacro macro,
records click timestamps from step reports, and writes `trial.json` with audio,
OCR/screenshot counts and a deferred check. Keep the external worker running and
the same DOTNET/window-task environment as ordinary playback. Shadow mode removes
zero screenshots/OCR calls: calibrate with held-out clicks, real rewards, disabled
clicks and background audio before enabling any faster path.

```sh
python3 tools/macos-window/audio_trial.py --config /private/config.json \
  --workflow tools/macos-window/wos-idle-rewards.json --player /path/to/CrossMacro.UI \
  --macro /private/wos-idle-rewards.macro --folder /private/audio-trial
python3 tools/macos-window/check_run.py /private/runs/*/result.json \
  --workflow tools/macos-window/wos-idle-rewards.json --output /private/check.json
```

`check_run.py` is independent of the execution loop. It records failed/missing
steps, unverified postconditions and uncertain audio in a recheck queue with
local evidence paths. A later local rule or model can review just that queue.
The checker itself never repeats game actions, uploads evidence, calls a model,
or marks an audio-only event as a verified reward. This separates fast routine
execution from deviation review and repair planning.

For an explicitly calibrated transition, set the step's `audio_event` and add a
matching entry under private `audio_feedback`, for example a `profile-open`
template, threshold 0.8 and two-second capture window. An accepted sound can
defer one post-action screenshot/OCR; missing or uncertain audio falls back to
visual verification without repeating the click. The next normal step still
observes its page and checks identity. The independent checker resolves a
deferred transition only when the immediate next visual precondition covers the
expected page text; otherwise it emits a review item. No reward step is enabled
for audio-only feedback by default. First test a small navigation flow, then
measure both call counts and latency; fewer OCR calls do not guarantee lower
latency with a fixed capture window.

## Tests

```sh
python3 -m unittest discover -s tools/macos-window -p 'test_*.py' -v
dotnet test tests/CrossMacro.UI.Tests/CrossMacro.UI.Tests.csproj -c Release \
  --filter 'FullyQualifiedName~ApplicationPathsEnvironmentTests|FullyQualifiedName~DesktopStartupRuntimeServiceTests'
```

The Python tests check OCR assertions, fail-closed input, invalid coordinates,
workflow export and coordinator exclusion. Platform integration must additionally
verify both screenshot results and the user's physical pointer during real runs.

## Additional WOS recordings

- `wos-mail-rewards.json`: identity check, Report/System/Alliance mail categories,
  batch read-and-claim, conditional reward dismissal, return to city. It never
  deletes mail. A successful click without a reward overlay is **not** evidence
  that new rewards were received. The no-new-reward replay was verified locally.
- `wos-vip-inspect.json`: identity check and VIP free-bundle inspection. It does
  not claim or buy anything. A bounded timer OCR region distinguishes the free
  bundle's cooldown from the unrelated VIP subscription expiry timer.
- `wos-idle-rewards.json`: actual exploration idle-reward claim, explicit disabled
  button branch, reward evidence and return to city. The approximately ten-minute
  claim interval applies to this reward category, not all game actions.

`timer_seconds` may include `bounds: [left, top, right, bottom]` in reference-window
pixels. Only OCR lines whose centers fall in that rectangle are searched, using
fresh local OCR geometry. Multiple/missing timers still fail closed. Do not
claim a cooldown merely because a generic page title was recognized.

The three-workflow local batch was measured at 48.35 seconds with 53 local
screenshots/OCR calls and zero runtime model calls. That is a **subset** of one
visit, not a complete daily routine benchmark. Role identity, screenshots,
recordings, per-role visit plans and full-run reports stay outside Git.

For labels that may move within a known control area, a click can use
`text_target` instead of `point`, for example:

```json
{"text_target":{"text":"一键已读","exact":false,"bounds":[430,1010,680,1070],"min_confidence":0.5}}
```

The executor requires one matching local OCR line inside the bounded area.
Duplicate, missing, low-confidence or out-of-window matches stop before input.
The normal page precondition and completion check still apply. Confidence
thresholds need calibration for each label/font; they are not probabilities of
semantic success.

A calibrated `offset: [dx, dy]` on a `text_target` can route an OCR row label to
its adjacent button. The final point is still checked against the reference
window. Keep offsets specific to a verified layout; ambiguous rows stop instead
of guessing a button.

## Latest recorded free flows

`wos-stamina-meal.json`, `wos-academy-supply.json`, and `wos-alliance-free.json`
are trial recordings. Their cooldown/empty branches passed a combined 61-step
CrossMacro replay (129.94s, 99 screenshots, 100 local OCR calls, zero model
calls). New reward branches have manual and offline predicate evidence, but
still need a live macro claim. Alliance help is inspection only. Do not count
these warm-state replays as a second complete daily visit.

The worker needs Pillow for color checks and local enlarged timer crops; optional
audio matching needs NumPy. Timer-only crops may normalize missing separators
only when all six digits remain, then validate hours/minutes/seconds and range.
The original image is reused; no extra capture or repeated click is required.

## Composable task batches

`task_batch.py` exposes `run_batch(config, [(task_name, workflow), ...], backend)`.
Each WOS workflow declares `task_contract.anchor`, bounded `exits`, and
`max_exit_steps`. A business assertion failure remains a deviation even if its
known exit restores the city; subsequent tasks may then run. Unknown or
ambiguous pages never receive an exit click. Identity, lock, permission,
window-size and ownership failures stop the batch without recovery input.

This differs from native per-step CrossMacro failure policy: a caller must use
the task batch coordinator to obtain task-level recovery. Earlier frozen GUI
recordings do not gain this behavior merely because their source JSON changed.

Step preconditions and observation steps may retry local screenshots/OCR up to the declared
`observe_attempts` bound (1–30), without repeating any click. This covers temporary
reward animations. VIP now has a bounded free-claim branch as well as cooldown.
`wos-daily-earned.json` claims already-completed daily-task rewards; game-queued progress-reward overlays are drained within a fixed bound. Explicit
per-chest clicking and doing incomplete tasks are outside its scope.


New WOS candidates include free recruitment (key inventory snapshots), alliance
help, ordinary-resource donation (exact regional remaining-count/cost assertions
and an unchanged diamond inventory), and three independent training workflows.
The training candidates preserve selected tier and quantity (at most1200), never
click diamond completion or acceleration, and have not been validated for all
roles/states. All game workflows require a closed city overview at their city
anchor; a visible overview has its own declared close exit. Local game logs and
account configuration must remain outside the repository.


Next-round candidates (`wos-crystal-ordinary.json`,
`wos-crystal-half-price.json`, `wos-expert-camp-rewards.json`) are separate from
the stable visit. Lab navigation now reaches the laboratory using bounded overview scrolling,
but its button OCR assertion (1 versus I) still stops playback before consumption;
its lab exit has the same gap. Full playback remains unverified. Expert coverage
is limited to one calibrated camp entry: two actual reward-badge claims passed
on one trial role, with reward/recruitment banners and a drained badge; another
trial role passed the empty state. This does not cover all Expert rewards.
No bank automation is implemented: the bank tab entry remains unresolved.
Navigation `key` steps accept only four arrows for at most1000ms, require fresh
page preconditions and postconditions, and never retry input. The local client
configuration must explicitly authorize `press_key` to use them. White-badge
pixel conditions require both page text and calibrated bounds. Bounded arrow
input has now been exercised during lab navigation.

The half-price click reserves `first-half-price-refinement` in an absolute,
local `daily_state_file` before input. Keys use a hashed role identity and UTC
game day; pending and confirmed entries both prevent another attempt. A visual
postcondition confirms the reservation, while uncertain input stays pending for
review. Ledger tests pass; this consumption path has not yet been exercised in
a full live macro. Keep the ledger outside Git.
