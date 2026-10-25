# Fehlerbehebung

Erster Schritt immer: `bambu-butler doctor` und bei Aufträgen `report.md` sowie `cli.log` im Auftragsordner lesen.

## Installation

| Symptom | Ursache | Lösung |
|---|---|---|
| `ERROR: file or directory not found: #` (pytest) | zsh übergibt `# Kommentar` als Argument | Zeile ohne Kommentar ausführen oder `setopt interactivecomments` |
| `command not found: bambu-butler` | Nicht global installiert | `uv tool install --from . bambu-butler`, ggf. `uv tool update-shell` |
| Alte Version nach `git pull` | Tool-Installation ist eine Kopie | `uv tool install --force --from . bambu-butler` |
| `Bambu Studio wurde nicht gefunden` | App nicht unter `/Applications` | `--studio`, `BAMBU_BUTLER_STUDIO` oder `bambu-butler.json` |
| `Keine Profilquelle gefunden` | Ressourcen-/Datenordner unbekannt | `--resources /Applications/BambuStudio.app/Contents/Resources` |
| `'--help' hat nach 60s nicht geantwortet` | Erster Start von Bambu Studio, Gatekeeper-Dialog | App einmal normal öffnen, Dialoge bestätigen |

## Plan und Profile

| Meldung | Lösung |
|---|---|
| `Profil nicht gefunden: '…'` | Namen exakt übernehmen: `bambu-butler profiles list -t filament -q PETG`. Namen unterscheiden sich je nach Bambu-Studio-Version. |
| `incompatible_profile` | `profiles list --printer "<Drucker>"` listet nur passende Profile |
| `profile_not_instantiable` | Basisprofil gewählt (z. B. `fdm_process_common`) – ein konkretes Profil nehmen |
| `Elternprofil '…' fehlt` | Benutzerprofil basiert auf gelöschtem/umbenanntem Systemprofil: in Bambu Studio neu speichern |
| `Zyklische Profilvererbung` | Defekte Benutzerprofile – in Bambu Studio neu anlegen |
| `unknown_key` | Schlüssel existiert im Basisprofil nicht: `profiles show "<Profil>"` prüfen |
| `override_conflict` | Wert nur in `settings` **oder** `overrides.process` setzen |
| `layer_height_out_of_range` | Grenzen stehen im Druckerprofil (`min_layer_height`, `max_layer_height`) |
| `model_too_large` | Skalieren, drehen (`transform`) oder `auto_orient: true` (dann nur Warnung) |
| `filament_slot_missing` | 3MF nutzt mehr Filament-Slots als der Plan Filamente definiert |
| `Der Plan enthält blockierende offene Fragen` | Frage klären und entfernen oder `blocking: false` |

## Slicen (Exit 4)

`error.details.exit.name` bzw. `report.json → exit` nennt den Bambu-Studio-Rückgabecode.

| Code | Bedeutung | Was hilft |
|---|---|---|
| `CLI_CONFIG_FILE_ERROR` (-5) | Profil-JSON abgelehnt | `profiles/*.json` im Auftragsordner prüfen, Issue mit Bambu-Studio-Version melden |
| `CLI_PROCESS_NOT_COMPATIBLE` (-17) | Prozess passt nicht zum Drucker | Kompatibles Prozessprofil wählen |
| `CLI_MODIFIED_PARAMS_TO_PRINTER` (-23) | Druckbereich verändert | Keine `printable_*`/`bed_exclude_area`-Overrides |
| `CLI_NO_SUITABLE_OBJECTS` (-50) / `CLI_OBJECTS_PARTLY_INSIDE` (-52) | Objekt nicht (ganz) auf der Platte | `arrange: true`, Modell verkleinern |
| `CLI_FILAMENT_NOT_MATCH_BED_TYPE` (-61) | Filament passt nicht zur Platte | Anderes Filamentprofil oder Plattentyp im Projekt |
| `CLI_SLICING_ERROR` (-100) | Slicen fehlgeschlagen | `cli.log` lesen, Mesh mit `inspect` prüfen |
| `CLI_GCODE_PATH_OUTSIDE` (-104) | Brim/Support/Skirt außerhalb | Brim schmaler, Support nur vom Bett, Modell kleiner |
| `slicer_timeout` | Zeitlimit erreicht | `--timeout 1200`, Modell vereinfachen |
| „meldete Erfolg, aber das 3MF enthält keinen G-Code“ | Export ohne Slice | `cli.log` prüfen; nicht als Erfolg werten |
| `SIGSEGV`, `SIGABRT` … (negativer Code unter macOS/Linux) | Bambu Studio ist **abgestürzt**, kein CLI-Fehlercode | Siehe „Bekannte Abstürze“ unten; `cli.log` endet an der Absturzstelle |
| `NTSTATUS_0xC…` (Windows) | Bambu Studio ist abgestürzt (Windows-Ausnahme) | Wie oben |
| `CLI_DATA_FILE_ERROR` (-6) bei gültig wirkender STL | Bambu kann die Datei nicht lesen | Siehe „Bekannte Abstürze“: Binär-STL mit Null-Normalen |

### Bekannte Abstürze und Lesefehler (Bambu Studio 02.08.02.61, macOS)

Beide Fälle liegen in Bambu Studio selbst und lassen sich ohne Bambu Butler mit der nackten CLI
nachstellen (geprüft am 2026-10-25).

- **Mehrere Filamente auf dem A1 mini (ein Extruder) → `SIGSEGV`.** Jeder Slice mit zwei
  Filamentprofilen, bei dem Objekte wirklich auf Slot 1 und 2 verteilt sind, stürzt ab, direkt nach
  `update_filament_maps_to_config` im Log. Das gilt für ein Mehrfarb-3MF genauso wie für zwei STLs mit
  `--load-filament-ids "1,2"`. Zwei Filamentprofile, aber alle Objekte auf Slot 1, slicen normal.
  **Ursache:** `filament_colour` hat in `PrintConfig.cpp` (v02.08.02.61) die Voreinstellung
  `{"#00AE42"}`, also genau einen Eintrag, und die CLI verlängert die Liste nicht auf die Zahl der
  Filamente. **Abhilfe, mit der nackten CLI geprüft:** die Farben auf der Kommandozeile übergeben,
  `--filament-colour "#00AE42;#FF6A13"`. Dann rechnet die CLI die Spülmengen-Matrix wie die Oberfläche
  aus den Farben aus (`calc_flush_vol`, im Test 2 × 2 mit 318/234 mm³ statt der festen 4 × 4-Voreinstellung)
  und slict sauber (Beispiel: 12,4 g + 10,43 g). Nur die Farben in die Filamentprofile zu schreiben
  verhindert zwar den Absturz, lässt aber die 4 × 4-Matrix stehen; die Spülmengen stimmen dann nicht.
  Bambu Butler übergibt die Farben noch nicht; bis dahin Mehrfarb-Projekte in der Oberfläche slicen
  (`bambu-butler prepare`, dann `open`). Andere Drucker wurden nicht geprüft.
- **Slicen aus STL hängt bei „glfwInit Success.“** Nach dem Slicen erzeugt die CLI Vorschaubilder
  über OpenGL. Am 2026-10-25 hing dieser Schritt bei gesperrtem Bildschirm und gleichzeitig offener
  Bambu-Studio-Oberfläche ohne CPU-Last, auch bei einem Lauf, der vorher durchging. Welche der beiden
  Bedingungen es auslöst, ist nicht geklärt. 3MF-Eingaben, die schon Vorschaubilder enthalten,
  waren nicht betroffen. Das Zeitlimit (`--timeout`) beendet den Lauf sauber mit `slicer_timeout`.
- **Binär-STL mit Nullvektor als Normale und kleiner Grundfläche → `CLI_DATA_FILE_ERROR`.** Ein
  Würfel mit X und Y ≤ 15 mm wurde abgelehnt, derselbe Würfel mit berechneten Normalen oder als ASCII-STL
  nicht; 15 × 20 mm ging auch mit Null-Normalen. `inspect` meldet solche Dateien als in Ordnung. Abhilfe:
  STL aus dem CAD-Programm neu exportieren (dann mit Normalen).

Ausführlich: Tabelle `CLI_ERRORS` in `src/bambu_butler/slicer.py`.

## Öffnen und GUI (macOS)

| Symptom | Lösung |
|---|---|
| Projekt öffnet sich nicht | Manuell: `open -a BambuStudio <datei.3mf>` |
| `Keine Automations-Berechtigung` | Systemeinstellungen → Datenschutz & Sicherheit → Automation → Terminal → System Events |
| `Bedienungshilfen-Zugriff fehlt` | Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen → Terminal |
| Fenster zeigt anderes Projekt | Offene Dialoge in Bambu Studio manuell schließen; Bambu Butler bestätigt nichts automatisch |
