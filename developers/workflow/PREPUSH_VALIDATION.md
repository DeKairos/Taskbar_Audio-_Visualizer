# Release validation — 1.4.3

Validated on 2026-10-17 with Python 3.10 on Windows. The user confirmed the smooth
playback test build before promotion into the production runtime.

| Check | Result |
| --- | --- |
| Full local test suite | 212 passed |
| Dependency consistency (`pip check`) | No broken requirements |
| Native Windows button routing at 125% scaling | Previous, play/pause, next each dispatched once to a fake player |
| Native background hit testing | Clicks outside controls passed through |
| DPI mapping regression coverage | 100%, 125%, 150%, 200%, including negative monitor coordinates |
| Production native renderer | Animation, silence hide, resume, song card, and manual visibility passed |
| Production frame ownership | One paint per submitted frame; fixed spectrum bin count |
| Real session control | Play/pause accepted by Spotify and Comet without taskbar focus; original states restored |
| Shell replacement | Mocked taskbar replacement and missing-shell recovery passed |
| Update helpers | Full installed, portable folder, portable EXE update/rollback suite passed |

The paired local scheduling comparison alternated duplicate and single repaint
paths in one process. Both averaged about 62 FPS; CPU time per frame fell from
18.33 ms to 13.07 ms, about 29%. This is a local workload result, not a frame-rate
guarantee for other hardware or effect settings.

The production class retains the confirmed native drawing/input path. Diagnostic
timers, config overrides, update suppression, logging, and lock bypasses are not
part of the release startup. Normal config persistence, update checks and
single-instance behavior are restored. Native transport buttons use the painted
layout without changing the saved widget-control preference.

Folder and standalone packaging run the frozen startup self-test. GitHub CI
checks Python 3.11 and 3.12 before the release tag is pushed. The tag workflow
tests again and publishes the three exact versioned assets.

Remaining environment coverage: a clean-VM installer upgrade/uninstall, physical
mixed-DPI multi-monitor hardware, and device unplug/replug were not exercised in
this release session. Shell replacement and DPI conversions have automated
coverage; the current display has live coverage at 125% scaling.
