# macOS window-task prototype

This fork reuses CrossMacro's Shell Command actions, editor, playback and
scheduler. The external executor reads one app window with local Apple Vision
OCR and sends window-bound input through a user-installed CUA MCP runtime.
Runtime execution calls no model. This experimental integration does not supply
a general macOS background-input driver.

## Requirements

- macOS, Xcode command-line tools, Python3.9+; Pillow for pixel/crop conditions; NumPy for optional local image-template targets.
- An existing CUA MCP installation with normal permissions. Proprietary runtime
  binaries are not included and its internal entry point is not a stable SDK.
- .NET10 when building CrossMacro (see CONTRIBUTING.md).

Build OCR locally:

```sh
mkdir -p tools/macos-window/build
clang -fobjc-arc -fno-modules -framework Foundation -framework Vision \
  -framework ImageIO tools/macos-window/vision-ocr.m \
  -o tools/macos-window/build/vision-ocr
```

Copy `config.example.json` outside Git, then set the runtime manifest, OCR binary,
exact application path, expected identity strings and private log directory.
`authorized_tools` is a local allowlist for normal MCP elicitations; unknown
applications/capabilities are declined. No thread identity or grant is synthesized.
`guard_command` returns an `active` executor field; a non-null value blocks startup.
Coordinate the app separately: advisory locks alone do not reserve it from others.

## Workflow sources and editor

Production WOS workflows moved to
[codex-game-skills](https://github.com/carolplay/codex-game-skills/tree/main/skills/play-whiteout-survival-macros):
`actions/` owns business actions, `catalog.json` pins their versions/hashes, and
`macros/` owns independently versioned shift compositions and role profiles.
That skill's `scripts/run_visit.py` calls this generic executor once per batch.
Do not maintain another production WOS copy in this repository.

`example-profile.json` is a frozen illustration for format/export regression tests.
It uses calibrated Chinese game labels as example data; it is not a production
visit or authorization to operate an account. Recovery test fixtures are minimal
frozen contracts, independent of the sibling skills repository.

```sh
/absolute/python3 tools/macos-window/window_macro.py export \
  --config /private/config.json \
  --workflow tools/macos-window/example-profile.json \
  --output /private/example-profile.macro
/absolute/python3 tools/macos-window/window_macro.py serve \
  --config /private/config.json \
  --workflow tools/macos-window/example-profile.json
```

Load exported `.macro` through Editor → Load. Each step is a Shell Command action.
Coordinates and OCR rules live in workflow JSON; dedicated visual property panels
are not implemented. Exports embed absolute paths and must be regenerated after
moving sources. Old step exports remain snapshots: they do not inherit task-batch
recovery or new composition versions. For normal scheduled visits use one Shell
action invoking the skill's manifest runner, rather than the editor clicking steps.

The opt-in `CROSSMACRO_WINDOW_TASKS_ONLY=1` mode supports shell-only playback
without initializing a native desktop input driver. Native mouse events still
require a supported platform backend.

## Execution contracts

Conditions support text arrays and `all`, `any`, `none`, `timer_seconds`,
`green_regions`, `white_regions`, and regional text/crop OCR where declared.
`page_text_regions` optionally adds up to four bounded image crops to page-text
assertions. This reads calibrated headers/footers when dense art confuses full-image
OCR; it reuses the same screenshot, caches crop results, and never sends input.
`skip_if`/`skip_if_any` recognize explicitly allowed alternative branches.
`observe_attempts` repeats observations only; it never repeats a click. Workflows
may set `execution_timeout_seconds` (integer1–600) for the whole action after
backend initialization; otherwise the configuration budget is capped at120seconds.
A larger budget never resets after each click.

Bounded arrow `key` steps support only Up/Down/Left/Right, at most1000ms, with
page preconditions/postconditions and explicit `press_key` allowance. No arbitrary
text entry is implemented by this prototype.

`task_batch.py` runs a fixed ordered list. Each action may declare a city/other
anchor, bounded known-page exits, and `max_exit_steps`. A business failure remains
a deviation even when recovery succeeds; only a verified restored anchor permits
continuation. Unknown/ambiguous pages receive no blind exit input. Identity,
lock, permission, ownership and window-size errors stop the entire batch.

`workflow_versions.py` records executor release, ordered action versions and
canonical JSON hashes, including unexecuted tasks. The skill runner adds its
independent package/composition versions and hashes. Recovery reports inherit
parent action identity and identify the exact exit step/hash. Versions do not
certify that all business branches have passed.

`daily_operations.py` reserves before input and confirms after observation using
a local UTC-day ledger keyed by hashed role identity. Pending reservations block
repeat attempts after uncertain outcomes. Keep ledgers outside Git.

Integer inventory reads retry only the same calibrated image crop when full-frame
OCR is missing or ambiguous; an unreadable or ambiguous crop still stops input.
Steps may declare `budget_checks` with `bounds`, `min`, and `max_config`. The
selected integer must be within the configured local cap before input; a missing,
invalid or exceeded cap fails closed. This is a generic configuration guard;
game-specific amounts and strategy belong to the external workflow package.
Derived crop OCR results use `-ocr.json` names so the offline auditor counts them.

## Audio experiments

`audio-tap.m` uses macOS14.2+ Core Audio process taps. Build in a stable local
app bundle with `NSAudioCaptureUsageDescription`:

```sh
clang -fobjc-arc -fno-modules -mmacosx-version-min=14.2 \
  -framework AppKit -framework CoreAudio -framework AudioToolbox \
  tools/macos-window/audio-tap.m -o /private/AudioTap.app/Contents/MacOS/audio-tap
```

It captures the selected app's audio through normal macOS permission
flows. Build as a local app using the system frameworks; no compiled app or
permission grant is distributed. `audio_trial.py` records sample windows around
an existing workflow and `audio_feedback.py` compares signatures offline. Audio
is supplementary feedback; it does not prove identity, inventory or reward receipt.
Only the selected game process should be captured. Shadow mode removes no OCR
calls. Calibrated `audio_event` feedback may defer one post-action observation;
uncertain sound falls back to visual verification without repeating input.
`check_run.py` resolves deferred events only from the next visual precondition
or emits a review item; audio alone never verifies a reward.

```sh
python3 tools/macos-window/audio_trial.py --help
python3 tools/macos-window/check_run.py /private/runs/*/result.json
python3 -m unittest discover -s tools/macos-window -p 'test_*.py' -v
```

## Limits

Window layout, language and pixel regions require calibration. Store screenshots,
identity/budget config, recordings and execution reports outside public Git.
Standalone locked operation is not certified: a CUA call may fail because it
cannot be associated with a trusted ChatGPT thread. This is a fatal input failure;
do not retry through another tool, invent metadata or weaken lock protection.
Short successful samples do not prove unattended locked execution.

## Local observation extensions

Executor0.2.0 supports bounded image templates supplied by private `image_templates`
configuration, calibrated red/green/white pixel regions, multiple queue timer
regions, and positive inventory deltas with observation-only retries. Template
matching runs locally with NumPy/Pillow and never calls a model. Workflow
`finish_if` declares an early completion condition; the batch still verifies or
restores its declared exit anchor. `skip_if_step_skipped` links a feedback check
to an earlier optional action. Direction-arrow `key_count` is bounded to20.

OCR targets remain unique by default. A workflow can explicitly use a bounded
regular-expression target with `select: top-left`; ambiguous targets without
that selection still fail before input. New business actions belong in the
separate game skill, not this repository.
