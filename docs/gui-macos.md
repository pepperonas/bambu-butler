# macOS GUI adapter

The adapter (`src/bambu_butler/gui_macos.py`) is optional. Preparing and slicing never need it.

## What it does

| Action | How | Reliability |
|---|---|---|
| Open project | `open -a /Applications/BambuStudio.app <file>` | Reliable (Launch Services) |
| Activate app | `osascript -e 'tell application "BambuStudio" to activate'` | Reliable for any app |
| Check permissions | `System Events` → `UI elements enabled` | Reliable; shows whether Accessibility is granted |
| Read window titles | `System Events` → `name of every window` of process `BambuStudio` | Works with Accessibility granted |

## What it deliberately does not do

- Bambu Studio has no documented AppleScript dictionary; nothing assumes one exists.
- No screen coordinates, no synthetic clicks, no keystrokes into the app.
- No confirming of dialogs. If the expected file is not visible in a window title (e.g. an update
  or save dialog is open), the adapter reports it and stops.

Instead it prints manual steps, e.g. "In Bambu Studio 'Platte slicen' klicken und die Vorschau prüfen".

## Permissions

- **Automation**: System Settings → Privacy & Security → Automation → allow your terminal
  (or Claude Code) to control "System Events".
- **Accessibility**: System Settings → Privacy & Security → Accessibility → enable your terminal.

`bambu-butler gui check` reports missing permissions in German.

## Verified behaviour (macOS, Bambu Studio 02.08.02.61, 2026-10-25)

- `open` launches Bambu Studio and loads the project; permissions were detected correctly.
- A cold start took about 8 s until the project window existed. `open --check-gui` therefore polls for
  up to 30 s (wall-clock) instead of checking once after a fixed pause.
- **Stale window title:** when a running Bambu Studio opened a second project into the same window,
  the window visibly showed the new project, but Accessibility still reported the old title. The check
  then says "not confirmed" although the right project is open. `expected_found` is a hint only.
- Quitting Bambu Studio via AppleScript returned "User cancelled (-128)" while the screen was locked;
  the adapter never quits the app.
