# WIR-KLARHEIT v4.7 FRESH OBSERVER

## Frischer Neuaufbau

Diese Datei wurde komplett neu geschrieben.  
Keine Patch-Kette. Keine alten Dateifragmente. Keine Übernahme aus v4.6.x.

## Zweck

WIR-KLARHEIT v4.7 erstellt lokale, longitudinale Fallakten, um KI-Antworten über Zeit zu vergleichen, ohne das Tool selbst zur neuen Autorität zu machen.

> Jede KI-Antwort ist Rohstoff, nicht Autorität.  
> Der Mensch bleibt letzte Prüfinstanz.

## Build

- Version: `4.7`
- Build ID: `2026-05-23-fresh-rewrite`
- SHA256: `123f94db50fae07b0b563f061519781135926b88d4446a04d68e902b4f8373b2`

## Harte Prüfbefehle

```bash
python wirklarheit_v4_7_fresh_observer.py selftest
python wirklarheit_v4_7_fresh_observer.py fingerprint
```

Erwartet:

```text
Selftest passed.
Raw r"cite" pattern present: NO
Citation regression excited/city/recite: 0
Integrity: PASS
```

## Commands

```bash
python wirklarheit_v4_7_fresh_observer.py new-case --title "Mein Fall" --dir cases
python wirklarheit_v4_7_fresh_observer.py add-run --case cases/mein-fall --label run-001 --question question.txt --responses a.md b.md c.md
python wirklarheit_v4_7_fresh_observer.py timeline --case cases/mein-fall --out timeline.md
python wirklarheit_v4_7_fresh_observer.py diff-runs --case cases/mein-fall --a run-001 --b run-002 --out diff.md
```

## Wichtige Grenze

Das Tool entscheidet keine Wahrheit.  
Es macht Muster sichtbar.  
Der Report ist Rohstoff.  
Die Prüfung bleibt beim Menschen.
