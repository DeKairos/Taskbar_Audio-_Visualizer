# Pre-push validation — 2026-10-15

The source changes are ready for a review/CI push. No release was published.

## Results

| Check | Result |
| --- | --- |
| Complete test suite, normal Windows permissions | 134 passed |
| Updater helper: installed, folder, single executable; update and rollback | All six cases passed |
| Dependency consistency (`pip check`) | Passed |
| Live default-output loopback | 91 finite spectrum frames in three seconds |
| Five mode painters | All rendered successfully |
| Skyline and response-speed save/reload | Passed using temporary settings |
| Current taskbar geometry | Verified at 125% display scaling |
| Frozen folder and single-file startup probes | Version, resources, modes, and runtime imports passed |
| Actual portable ZIP and executable updates | Both passed in disposable application folders |
| Actual portable ZIP and executable rollback | Both restored the baseline after a deliberate version mismatch |
| Inno Setup installer compilation | Passed |
| Whitespace/error checks (`git diff --check`) | Passed |

The initial updater failures were specific to the restricted execution sandbox.
The same six integration tests passed with normal user permissions, without
changing timeouts or weakening assertions. A deterministic capture test also
verifies reconnection after a simulated default-device change.

The build scripts now check dependency-installation, icon-generation, and
installer-compiler exit codes. Cleanup targets are validated before recursive
removal. `-SkipDependencyInstall` permits local builds using the checked environment.
The frozen startup probe also detects missing audio, rendering, tray, media, and
settings imports and reports failures in JSON.

## Local artifacts

Validation builds use version **1.4.0**, matching the existing tag, solely for
local testing. Choose a new release version before publishing; do not replace
the existing release or tag.

- `dist/AudioVisualizer/` — folder bundle
- `dist/AudioVisualizer-Portable-1.4.0.zip` — portable archive
- `dist/AudioVisualizer-Portable-1.4.0.exe` — standalone executable
- `dist/AudioVisualizer-Setup-1.4.0.exe` — installer
- `build/prepush-runtime-report.json` — runtime results
- `build/prepush-package-report.json` — actual-package update/rollback results
- `build/prepush-artifacts.json` — artifact sizes and SHA-256 hashes
- `build/prepush-*-build.log` — build/compiler output

Build outputs, temporary profiles, and test applications remain ignored by Git.
Portable-package checks used temporary profiles and exact-path process cleanup;
the existing installation and user settings were not changed.

## Remaining checks before a public release

- Real installer upgrade in a clean Windows VM, with startup enabled and disabled.
  Installed-helper logic and registry rollback passed with fake installers; the
  newly compiled installer was not installed over the user's existing app.
- Physical audio-device unplug/replug and mixed-DPI multi-monitor tests. The
  current display and headphones were exercised; additional layouts and switching
  have simulated regression coverage.
- Let remote CI finish before merging. Local tests used Python 3.10; CI also
  checks Python 3.11 and 3.12.

Suggested commit:

```text
feat: Harden taskbar visuals and app updates
```
