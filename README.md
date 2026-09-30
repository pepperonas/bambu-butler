# Bambu Butler

**Druckwünsche in natürlicher Sprache → geprüfter Druckplan → Bambu-Studio-Projekt.**

Bambu Butler (v0.0.1) ist ein lokales CLI-Werkzeug plus eine Claude-Code-Skill. Du beschreibst in
Claude Code, was du drucken willst. Claude übersetzt das in einen versionierten JSON-Druckplan,
Bambu Butler prüft ihn gegen deine echten Bambu-Studio-Profile, erzeugt projektspezifische
Profilkopien, ruft die Bambu-Studio-CLI zum Slicen auf und öffnet das Ergebnis in der App.

- **Kein MCP, kein eigener KI-API-Zugang.** Claude Code ist die KI; die Python-Anwendung enthält kein Sprachmodell.
- **Lokal.** Keine Cloud-Dienste nötig.
- **Nachvollziehbar.** Jeder Auftrag bekommt einen Ordner mit Plan, aufgelösten Profilen, Änderungsliste, exaktem CLI-Aufruf, Log und Bericht.
- **Sicher.** Kein Befehl startet jemals einen physischen Druck.

> Primäre Plattform: macOS auf Apple Silicon. Windows und Linux sind in der Pfaderkennung vorbereitet.

## Installation

Voraussetzungen: Python 3.11+, [uv](https://docs.astral.sh/uv/), [Bambu Studio](https://bambulab.com/de/download/studio).

```bash
git clone https://github.com/pepperonas/bambu-butler.git
cd bambu-butler
uv sync
uv run bambu-butler doctor
```

Global als Befehl `bambu-butler` installieren (optional):

```bash
uv tool install --from . bambu-butler
bambu-butler --version
```

### Pfade

Bambu Butler sucht Bambu Studio automatisch (macOS: `/Applications/BambuStudio.app`,
Daten in `~/Library/Application Support/BambuStudio`). Jeder Pfad lässt sich überschreiben –
Reihenfolge: CLI-Option > Umgebungsvariable > `bambu-butler.json` > Auto-Erkennung.

| Wert | CLI-Option | Umgebungsvariable |
|---|---|---|
| Executable | `--studio` | `BAMBU_BUTLER_STUDIO` |
| Ressourcen (Systemprofile) | `--resources` | `BAMBU_BUTLER_RESOURCES` |
| Datenordner (Benutzerprofile) | `--data-dir` | `BAMBU_BUTLER_DATA_DIR` |
| Auftragsordner | `--jobs-dir` | `BAMBU_BUTLER_JOBS_DIR` |
| Timeout (s) | `--timeout` (bei `slice`/`prepare`) | `BAMBU_BUTLER_TIMEOUT` |
| Konfigurationsdatei | `--config` | `BAMBU_BUTLER_CONFIG` |

`bambu-butler init` legt `bambu-butler.json`, `jobs/` und `plans/` im aktuellen Ordner an.

## Befehle

Globale Optionen stehen **vor** dem Unterbefehl, z. B. `bambu-butler --json doctor`.

| Befehl | Zweck |
|---|---|
| `init [ORDNER]` | Arbeitsordner mit Konfiguration anlegen |
| `doctor [--strict]` | Bambu Studio, Version, CLI-Optionen, Profile und fehlende Abhängigkeiten prüfen |
| `profiles list [-t TYP] [-p DRUCKER] [-q TEXT] [--all]` | Profile auflisten, optional nur kompatible |
| `profiles show NAME [--raw] [-k KEYS]` | Profil mit aufgelöster Vererbung anzeigen |
| `inspect MODELL [-p DRUCKER]` | STL/3MF analysieren: Maße, Einheit, Objekte, Metadaten, Geometrie, Druckraum |
| `template MODELL -p DRUCKER [-o DATEI]` | Planvorlage mit den Standardprofilen des Druckers |
| `validate PLAN` | Schema + Kompatibilität mit vorhandenen Profilen prüfen |
| `prepare PLAN [--dry-run]` | Auftragsordner + ungeslictes 3MF-Projekt erzeugen |
| `slice PLAN [--dry-run] [--timeout S]` | Vorbereiten und mit der Bambu-Studio-CLI slicen |
| `open PROJEKT.3mf [--check-gui]` | In Bambu Studio öffnen |
| `schema [-o DATEI]` | JSON-Schema des Druckplans ausgeben |
| `gui check` | macOS: Automations-/Bedienungshilfen-Berechtigungen prüfen |
| `printer status` | Stand der Druckersteuerung (nicht implementiert) |

`--json` liefert maschinenlesbare Ausgabe (`{"ok": true, ...}` bzw. `{"ok": false, "error": {...}}`).
Exit-Codes: 0 ok · 1 Fehler · 2 Plan ungültig/inkompatibel · 3 Bambu Studio fehlt · 4 Slicer fehlgeschlagen/Timeout · 5 nicht unterstützt.

## Der Druckplan

Eigenes, stabiles Format `bambu-butler/print-plan` Version 1 –
Schema: [`schemas/print-plan.v1.schema.json`](schemas/print-plan.v1.schema.json),
Details: [`docs/plan-schema.md`](docs/plan-schema.md).

```json
{
  "schema": "bambu-butler/print-plan",
  "schema_version": "1",
  "request": "Stabile Halterung, saubere Oberfläche, wenig Support",
  "model": {"path": "halter.stl"},
  "printer": {"profile": "Bambu Lab A1 mini 0.4 nozzle", "nozzle_diameter_mm": 0.4},
  "process": {"profile": "0.20mm Standard @BBL A1M"},
  "filaments": [{"profile": "Bambu PLA Basic @BBL A1M", "material": "PLA"}],
  "settings": {
    "quality": {"seam": "back"},
    "strength": {"wall_loops": 4, "top_layers": 5, "infill_density_percent": 25, "infill_pattern": "gyroid"},
    "support": {"enabled": true, "style": "tree_auto", "build_plate_only": true}
  },
  "assumptions": [{"text": "Last wirkt auf den senkrechten Schenkel."}],
  "rationale": [{"setting": "wall_loops", "value": 4, "reason": "Festigkeit kommt aus den Wänden."}],
  "open_questions": []
}
```

Bambu Butler unterscheidet ausdrücklich drei Stufen:

1. **Schema-gültig** – das JSON entspricht dem Schema.
2. **Kompatibel** – Profile existieren, passen zusammen (`compatible_printers`), Material und Düse stimmen, Overrides sind bekannte Schlüssel, Schichthöhe liegt in den Druckergrenzen, das Modell passt in den Druckraum.
3. **Geslict** – Bambu Studio hat tatsächlich ein 3MF mit G-Code erzeugt. Druckzeit und Filamentverbrauch werden nur dann (aus `Metadata/slice_info.config` bzw. `result.json`) angezeigt.

## Auftragsordner

```
jobs/20260930-131500-halter/
├── plan.json            # verwendeter Plan
├── profiles/            # vollständig aufgelöste Profile für die CLI
│   ├── machine.json
│   ├── process.json     # z. B. "0.20mm Standard @BBL A1M [bambu-butler halter]", from: User
│   └── filament_1.json
├── changes.json         # Änderungen gegenüber den Basisprofilen
├── input/halter.stl     # Kopie des Eingabemodells
├── command.json         # exakte Argumentliste, Timeout, Versionen
├── cli.log              # stdout/stderr von Bambu Studio
├── result.json          # von Bambu Studio geschrieben (falls ausgeführt)
├── halter.3mf           # geslictes Projekt (bzw. halter.prepared.3mf bei prepare)
├── report.md            # Bericht für Menschen
└── report.json          # Bericht für Maschinen
```

Originale Bambu-Profile werden nie verändert.

## Mit Claude Code nutzen

Die Skill liegt unter [`.claude/skills/bambu-butler/SKILL.md`](.claude/skills/bambu-butler/SKILL.md)
und wird automatisch geladen, wenn du Claude Code in diesem Repository startest (oder mit `/bambu-butler`).

```text
> Bereite ~/Downloads/halter.stl für meinen Bambu Lab A1 mini mit PLA vor.
  Die Halterung soll stabil sein, eine saubere sichtbare Oberfläche haben
  und möglichst wenig Support benötigen.
```

Claude prüft die Umgebung, untersucht Modell und Profile, schreibt `plans/halter.plan.json` mit
Begründungen und Annahmen, validiert, slict und öffnet das Ergebnis. Rückfragen kommen nur, wenn
Entscheidendes fehlt (z. B. Material oder Belastungsrichtung). Ein Druck wird nie automatisch gestartet.

## Funktionsumfang 0.0.1

Siehe [`docs/features.md`](docs/features.md) für die vollständige Übersicht.

| Funktion | Status |
|---|---|
| Installation erkennen (`doctor`), Pfade überschreibbar | ✅ |
| System- und Benutzerprofile lesen, Vererbung + `include` auflösen | ✅ |
| Fehlende Eltern, Zyklen, inkompatible Kombinationen erkennen | ✅ |
| STL (binär/ASCII) und 3MF analysieren | ✅ |
| Druckplan-Schema v1, Validierung, Mapping auf verifizierte Bambu-Schlüssel | ✅ |
| Auftragsordner, Änderungsliste, Bericht, Dry-Run, Timeouts, `--json` | ✅ |
| Slicen über die Bambu-Studio-CLI | ✅ implementiert, mit Test-Double getestet – echter Lauf siehe Einschränkungen |
| Öffnen in Bambu Studio | ✅ |
| macOS-GUI-Adapter | ⚠️ nur Aktivieren/Fenster/Berechtigungen prüfen |
| Druckersteuerung (senden, starten, pausieren, Temperaturen) | ❌ nicht implementiert, siehe [`docs/printer-control.md`](docs/printer-control.md) |

## Einschränkungen

- Die Entwicklung fand in einer Linux-Umgebung ohne Bambu Studio statt. CLI-Optionen, Profilformat,
  Rückgabecodes und Ergebnisdateien wurden gegen den **Quellcode** von Bambu Studio v02.08.04 geprüft und
  mit echten BBL-Systemprofilen getestet; ein echter Slice-Lauf steht noch aus. Führe als erstes
  `bambu-butler doctor` und einen Testauftrag aus.
- Bei 3MF-Eingaben lädt Bambu Butler die Filamente des Plans per `--load-filaments`; die Bambu-CLI
  ersetzt damit die Filamentprofile des Projekts. Objekte verweisen im 3MF auf Slot-Nummern – ob Farben,
  Slot-Zuordnungen und AMS-Informationen dabei vollständig erhalten bleiben, ist **nicht verifiziert**.
  Bambu Butler erfindet keine Farb-/AMS-Zuordnungen, warnt bei abweichender Filamentanzahl und bricht ab,
  wenn Objekte Slots nutzen, die der Plan nicht definiert. Prüfe Mehrfarbprojekte in Bambu Studio.
- `compatible_printers_condition`-Ausdrücke werden nicht ausgewertet (Warnung statt Entscheidung).
- Aus einem Mesh lassen sich Belastungsrichtung, optimale Ausrichtung oder Supportbedarf nicht sicher bestimmen.
- Plattentyp (`curr_bed_type`) ist im Plan noch nicht wählbar; es gilt der Standard des Projekts/Druckers.

## Entwicklung

```bash
uv sync
uv run pytest
uv run ruff check src tests
```

Siehe [`CLAUDE.md`](CLAUDE.md).

## Lizenz

MIT – siehe [LICENSE](LICENSE). Bambu Studio und Bambu Lab sind Marken der jeweiligen Inhaber;
dieses Projekt ist nicht mit Bambu Lab verbunden.

---

© 2026 Martin Pfeffer | [celox.io](https://celox.io)
