# Beispiele

| Datei | Inhalt |
|---|---|
| `models/wandhalter.stl` | Geschlossenes L-Profil 60 × 25 × 50 mm (Demo-Modell) |
| `a1mini-pla-wandhalter.plan.json` | A1 mini, PLA, stabil + saubere Oberfläche, ohne Support |
| `a1mini-petg-support.plan.json` | A1 mini, PETG, stehend (Rotation), Tree-Support, Brim, Roh-Override |

**Anpassen vor der Nutzung** (in `$comment` markiert): `printer.profile`, `process.profile` und
`filaments[].profile` müssen exakt lokalen Profilnamen entsprechen:

```bash
bambu-butler profiles list --type machine --query "A1 mini"
bambu-butler profiles list --type process  --printer "Bambu Lab A1 mini 0.4 nozzle"
bambu-butler profiles list --type filament --printer "Bambu Lab A1 mini 0.4 nozzle" --query PLA
```

Die Namen in den Beispielen stammen aus den Systemprofilen von Bambu Studio v02.08; andere
Versionen können abweichende Namen haben (z. B. `Bambu PETG Basic @BBL A1M 0.4 nozzle`).

```bash
cd examples
bambu-butler validate a1mini-pla-wandhalter.plan.json
bambu-butler slice a1mini-pla-wandhalter.plan.json --dry-run
bambu-butler slice a1mini-pla-wandhalter.plan.json
```
