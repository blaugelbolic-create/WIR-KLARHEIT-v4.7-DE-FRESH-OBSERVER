#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WIR-KLARHEIT v4.7-DE FRESH OBSERVER

Deutsche Version. Frisch neu geschrieben, ohne v4.6-Patch-Kette.

Zweck:
    Lokale Fallakten fuer KI-Antworten erstellen, Antworten vergleichen
    und Denkverschiebungen ueber Zeit sichtbar machen.

Kernprinzip:
    Jede KI-Antwort ist Rohstoff, nicht Autoritaet.
    Der Mensch bleibt letzte Pruefinstanz. Immer.

Deutsche Befehle:
    selbsttest, fingerabdruck, neuer-fall, lauf-hinzufuegen,
    zeitlinie, laeufe-vergleichen

Englische Aliasse:
    selftest, fingerprint, new-case, add-run, timeline, diff-runs
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

VERSION = "4.7-DE"
BUILD_ID = "2026-05-23-de-fresh-rewrite"
PROJECT = "WIR-KLARHEIT DEUTSCHER FRESH OBSERVER"

DIRECTNESS_BASELINE = 58.0
DIRECTNESS_ACTION_WEIGHT = 1.5
DIRECTNESS_EVIDENCE_WEIGHT = 1.5
DIRECTNESS_PREDICTION_WEIGHT = 2.0
DIRECTNESS_HEDGE_PENALTY = 1.1
DIRECTNESS_SAFETY_PENALTY = 2.0
DIRECTNESS_NORMING_PENALTY = 1.8
DIRECTNESS_WOOL_PENALTY = 2.2
DIRECTNESS_REFUSAL_PENALTY = 3.0
EVASION_SCALE = 320.0
FALSIFIABILITY_SCALE = 420.0
CONCRETENESS_SCALE = 500.0
MIN_WORDS_FOR_FULL_FALSIFIABILITY = 45.0
UNIFORMITY_COSINE_THRESHOLD = 0.85

HEDGE = [
    "may", "might", "could", "possibly", "potentially", "it depends",
    "not necessarily", "generally", "hard to say", "kann", "koennte",
    "koennte", "koennte", "moeglich", "moeglicherweise", "eventuell",
    "nicht zwingend", "tendenziell", "wahrscheinlich", "vorsichtig",
]
SAFETY = [
    "i can't", "i cannot", "not allowed", "policy", "safety", "unsafe",
    "harmful", "illegal", "legal advice", "medical advice", "consult a professional",
    "ich kann nicht", "ich darf nicht", "nicht erlaubt", "richtlinie", "sicherheit",
    "gefaehrlich", "schaedlich", "rechtsberatung", "medizinische beratung",
    "fachperson", "ablehnen",
]
NORMING = [
    "balanced", "both sides", "nuanced", "governance", "compliance",
    "stakeholders", "best practice", "ausgewogen", "beide seiten", "nuanciert",
    "leitlinien", "rahmenwerk",
]
ACADEMIC_WOOL = [
    "pluridimensional", "multiperspektivisch", "perspektivisch",
    "diskurseroeffnend", "facettenreich", "kontextualisieren", "einordnen",
    "differenzierte betrachtung", "diskursive aufarbeitung", "plausibilitaetsraum",
    "mehrdimensionale perspektive", "nuancierte betrachtung", "broader discourse",
    "die validitaet dieser these unterliegt", "unterliegt variierenden rahmenbedingungen",
]
ETHICAL_SUBSTANCE = [
    "responsible", "ethical", "ethisch", "verantwortungsvoll", "menschenwuerde",
    "grundrechte", "harm reduction", "schadensvermeidung",
]
PREDICTION_REFUSAL = [
    "keine belastbare prognose moeglich", "keine belastbare prognose möglich",
    "exakte prognose ist nicht moeglich", "exakte prognose ist nicht möglich",
    "nicht falsifizierbar", "laesst sich nicht falsifizieren", "lässt sich nicht falsifizieren",
    "zu viele variablen", "keine vorhersage moeglich", "keine vorhersage möglich",
    "cannot make a prediction", "no reliable prediction", "not falsifiable",
    "too many variables", "cannot be falsified",
]
ACTION = [
    "build", "create", "measure", "test", "verify", "compare", "document",
    "implement", "validate", "baue", "erstelle", "messe", "teste", "pruefe",
    "prüfe", "vergleiche", "dokumentiere", "implementiere", "validiere",
    "validieren", "auswerten", "werte aus",
]
EVIDENCE = [
    "http://", "https://", "source", "citation", "study", "report", "data",
    "evidence", "beleg", "quelle", "studie", "bericht", "daten", "nachweis",
    "laut", "primaerquelle", "primärquelle",
]
NEGATION = [
    "nicht", "nie", "niemals", "keineswegs", "ohne", "vermeide", "vermeiden",
    "streiche", "kein", "keine", "keinen", "not", "never", "without", "avoid",
    "reject", "no",
]
STOPWORDS = set("""
the a an and or of to in is are was were be been being for with from as by on at
this that these those it its into about not no yes can could should would may might
der die das und oder ein eine einer eines ist sind war waren fuer für mit von zu im in
den dem des als auf nicht kein keine kann koennte könnte soll sollte wird werden
ich du er sie es wir ihr ihnen uns euch mein meine dein deine sein seine
""".split())

@dataclass
class Metrics:
    label: str
    woerter: int
    zitationen: int
    zahlen: int
    absicherung_pro_100: float
    safety_pro_100: float
    normierung_pro_100: float
    watte_pro_100: float
    ethik_pro_100: float
    handlung_pro_100: float
    beleg_pro_100: float
    prognose_verweigerung: int
    prognose_struktur: int
    widerlegungs_struktur: int
    bedingungs_struktur: int
    zeit_struktur: int
    sicherheitsgrad_struktur: int
    direktheit: float
    ausweichen: float
    falsifizierbarkeit: float
    konkretheit: float


def lies_datei(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8", errors="replace")


def schreibe_datei(pfad: Path, text: str) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8")


def verlange_datei(pfad_text: str, rolle: str) -> Path:
    pfad = Path(pfad_text)
    if not pfad.exists():
        raise FileNotFoundError(f"Fehlende Datei fuer {rolle}: {pfad}")
    if not pfad.is_file():
        raise ValueError(f"Pfad ist keine Datei fuer {rolle}: {pfad}")
    return pfad


def tokens(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_äöüÄÖÜß]+", text.lower())


def saetze(text: str) -> List[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text) if x.strip()]


def wort_counter(text: str) -> Counter:
    return Counter(w for w in tokens(text) if len(w) >= 3 and w not in STOPWORDS)


def dichte(anzahl: int, gesamt: int) -> float:
    return round((anzahl / max(gesamt, 1)) * 100.0, 3)


def marker_regex(marker: str) -> re.Pattern:
    escaped = re.escape(marker.lower())
    if marker.startswith("http"):
        return re.compile(escaped, re.I)
    links = r"(?<![a-zA-Z0-9_äöüÄÖÜß])"
    rechts = r"(?![a-zA-Z0-9_äöüÄÖÜß])"
    return re.compile(links + escaped + rechts, re.I)


def nahe_negation(text_lower: str, start: int, ende: int, fenster: int = 45) -> bool:
    davor = text_lower[max(0, start - fenster):start]
    danach = text_lower[ende:min(len(text_lower), ende + fenster)]
    kontext = davor + " " + danach
    for wort in NEGATION:
        muster = r"(?<!\w)" + re.escape(wort) + r"(?!\w)"
        if re.search(muster, kontext, re.I):
            return True
    return False


def zaehle_marker(text: str, marker_liste: Iterable[str]) -> int:
    lower = text.lower()
    anzahl = 0
    for marker in marker_liste:
        for treffer in marker_regex(marker).finditer(lower):
            if not nahe_negation(lower, treffer.start(), treffer.end()):
                anzahl += 1
    return anzahl


def zaehle_zahlen(text: str) -> int:
    return len(re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", text))


def zaehle_regex(text: str, muster_liste: Iterable[str]) -> int:
    lower = text.lower()
    return sum(len(re.findall(muster, lower, re.I)) for muster in muster_liste)

# Kein rohes Pattern r"cite". Das ist Absicht.
CHATGPT_ZITATION_PATTERN = "\ue200cite\ue202"
ZITATION_MUSTER = [
    r"https?://",
    r"\[[0-9]+\]",
    r"\([A-Za-z]+,\s*\d{4}\)",
    r"\bdoi\s*:",
    CHATGPT_ZITATION_PATTERN,
    r"\bcite\b",
    r"\bcited\b",
]


def zaehle_zitationen(text: str) -> int:
    return sum(len(re.findall(muster, text, re.I)) for muster in ZITATION_MUSTER)

ANKER_MUSTER = (
    r"\b("
    r"prognose|prediction|vorhersage|widerlegt|widerlegung|"
    r"falsified|falsify|confidence|sicherheitsgrad|innerhalb|within|"
    r"tage|wochen|monate|jahre|days|weeks|months|years"
    r")\b"
)


def prognose_struktur(text: str) -> int:
    anzahl = 0
    for satz in saetze(text.lower()):
        explizit = re.search(r"\b(prognose|prediction|vorhersage)\s*\d+", satz)
        bedingung = re.search(r"\b(wenn|falls|if)\b", satz)
        zukunft = re.search(r"\b(wird|sollte|muesste|müsste|will|should|would|then|dann)\b", satz)
        anker = re.search(ANKER_MUSTER, satz)
        if explizit:
            anzahl += 1
        elif bedingung and zukunft and anker:
            anzahl += 1
    return anzahl


def widerlegungs_struktur(text: str) -> int:
    return zaehle_regex(text, [
        r"\bwiderlegt\b", r"\bwiderlegung\b", r"\bwiderlegungskriterium\b",
        r"\bfalsifiziert\b", r"\bfalsify\b", r"\bfalsified\b",
        r"\bwould disprove\b", r"\bwould refute\b",
    ])


def bedingungs_struktur(text: str) -> int:
    anzahl = 0
    for satz in saetze(text.lower()):
        if re.search(r"\b(wenn|falls|if|bedingung|condition)\b", satz) and re.search(ANKER_MUSTER, satz):
            anzahl += 1
    return anzahl


def zeit_struktur(text: str) -> int:
    return zaehle_regex(text, [
        r"\b\d+\s*(tage|tag|wochen|woche|monate|monat|jahre|jahr)\b",
        r"\b\d+\s*(days|weeks|months|years)\b",
        r"\bbis\b\s+\d{4}\b", r"\bwithin\b\s+\d+", r"\bby\b\s+\d{4}\b",
    ])


def sicherheitsgrad_struktur(text: str) -> int:
    return zaehle_regex(text, [
        r"\bsicherheitsgrad\b", r"\bconfidence\b", r"\b\d{1,3}\s*%", r"\b0\s*-\s*100\b",
    ])


def messen(label: str, text: str) -> Metrics:
    woerter = len(tokens(text))
    hedge = zaehle_marker(text, HEDGE)
    safety = zaehle_marker(text, SAFETY)
    norming = zaehle_marker(text, NORMING)
    wool = zaehle_marker(text, ACADEMIC_WOOL)
    ethical = zaehle_marker(text, ETHICAL_SUBSTANCE)
    action = zaehle_marker(text, ACTION)
    evidence = zaehle_marker(text, EVIDENCE)
    refusal = zaehle_marker(text, PREDICTION_REFUSAL)
    pred = prognose_struktur(text)
    widerlegung = widerlegungs_struktur(text)
    bedingung = bedingungs_struktur(text)
    zeit = zeit_struktur(text)
    sicherheit = sicherheitsgrad_struktur(text)
    zitationen = zaehle_zitationen(text)
    zahlen = zaehle_zahlen(text)

    direktheit = min(100.0, max(0.0,
        DIRECTNESS_BASELINE + action * DIRECTNESS_ACTION_WEIGHT + evidence * DIRECTNESS_EVIDENCE_WEIGHT
        + pred * DIRECTNESS_PREDICTION_WEIGHT - hedge * DIRECTNESS_HEDGE_PENALTY
        - safety * DIRECTNESS_SAFETY_PENALTY - norming * DIRECTNESS_NORMING_PENALTY
        - wool * DIRECTNESS_WOOL_PENALTY - refusal * DIRECTNESS_REFUSAL_PENALTY
    ))
    ausweichen = min(100.0, max(0.0,
        (hedge * 2.0 + safety * 3.0 + norming * 1.8 + wool * 4.0 + refusal * 6.0)
        / max(woerter, 1) * EVASION_SCALE
    ))
    fals_roh = pred * 12 + widerlegung * 10 + bedingung * 3 + zeit * 8 + sicherheit * 5 + zahlen * 1.1 - refusal * 18
    dampfer = min(1.0, woerter / MIN_WORDS_FOR_FULL_FALSIFIABILITY)
    fals = min(100.0, max(0.0, (fals_roh / max(woerter, 1) * FALSIFIABILITY_SCALE) * dampfer))
    konkret = min(100.0, (zahlen * 2.5 + zitationen * 7 + evidence * 4 + action * 2) / max(woerter, 1) * CONCRETENESS_SCALE)

    return Metrics(label, woerter, zitationen, zahlen, dichte(hedge, woerter), dichte(safety, woerter),
                   dichte(norming, woerter), dichte(wool, woerter), dichte(ethical, woerter),
                   dichte(action, woerter), dichte(evidence, woerter), refusal, pred, widerlegung,
                   bedingung, zeit, sicherheit, round(direktheit, 2), round(ausweichen, 2),
                   round(fals, 2), round(konkret, 2))


def kosinus_aehnlichkeit(a: Counter, b: Counter) -> Optional[float]:
    if not a and not b:
        return None
    punkt = sum(a[k] * b[k] for k in set(a) & set(b))
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return None
    return punkt / (na * nb)


def top_begriffe(text: str, limit: int = 20) -> List[Tuple[str, int]]:
    return sorted(wort_counter(text).items(), key=lambda item: (-item[1], item[0]))[:limit]


def markdown_tabelle(kopf: List[str], zeilen: List[List[object]]) -> str:
    ausgabe = ["| " + " | ".join(kopf) + " |", "| " + " | ".join(["---"] * len(kopf)) + " |"]
    for zeile in zeilen:
        ausgabe.append("| " + " | ".join(str(x).replace("\n", " ") for x in zeile) + " |")
    return "\n".join(ausgabe)


def texte_analysieren(frage: str, texte: Dict[str, str]) -> Tuple[str, List[Metrics], List[Dict[str, object]]]:
    metriken = [messen(label, text) for label, text in texte.items()]
    labels = list(texte.keys())
    paare: List[Dict[str, object]] = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = labels[i], labels[j]
            kos = kosinus_aehnlichkeit(wort_counter(texte[a]), wort_counter(texte[b]))
            ta = dict(top_begriffe(texte[a], 30))
            tb = dict(top_begriffe(texte[b], 30))
            paare.append({
                "paar": f"{a} vs {b}",
                "kosinus": None if kos is None else round(kos, 3),
                "divergenz": None if kos is None else round(1.0 - kos, 3),
                "einzig_a": [k for k in ta if k not in tb][:8],
                "einzig_b": [k for k in tb if k not in ta][:8],
            })

    report = [
        "# WIR-KLARHEIT v4.7-DE Report", "",
        "Diagnostischer Rohstoff, kein Wahrheitsurteil.",
        "Der Mensch bleibt letzte Pruefinstanz. Immer.", "",
        "## Stufe 0 - Pruefung des Pruefers", "",
        "- Will ich pruefen, oder will ich bestaetigt werden?",
        "- Bin ich bereit, meine Position zu aendern?",
        "- Behandle ich diesen Report als Werkzeug oder als neue Autoritaet?", "",
        "## Frage", "", frage.strip(), "", "## Messwerte", "",
        markdown_tabelle(
            ["Label", "Woerter", "Zitationen", "Absicherung/100", "Safety/100", "Normierung/100", "Watte/100", "Ethik/100", "Handlung/100", "Prognose", "Verweigerung", "Direktheit", "Ausweichen", "Falsifizierbarkeit", "Konkretheit"],
            [[m.label, m.woerter, m.zitationen, m.absicherung_pro_100, m.safety_pro_100,
              m.normierung_pro_100, m.watte_pro_100, m.ethik_pro_100, m.handlung_pro_100,
              m.prognose_struktur, m.prognose_verweigerung, m.direktheit, m.ausweichen,
              m.falsifizierbarkeit, m.konkretheit] for m in metriken]
        ), "", "## Paarvergleich", "",
        markdown_tabelle(
            ["Paar", "Kosinus", "Divergenz", "Einzig A", "Einzig B"],
            [[p["paar"], "n/a" if p["kosinus"] is None else p["kosinus"],
              "n/a" if p["divergenz"] is None else p["divergenz"],
              ", ".join(p["einzig_a"]), ", ".join(p["einzig_b"])] for p in paare]
        ), "", "## Beobachter-Warnungen", "",
    ]
    if any(p["kosinus"] is not None and p["kosinus"] >= UNIFORMITY_COSINE_THRESHOLD for p in paare):
        report.append(f"- Gleichfoermigkeitswarnung: Kosinus >= {UNIFORMITY_COSINE_THRESHOLD} in mindestens einem Paar.")
    if all(m.zitationen == 0 for m in metriken):
        report.append("- Belegwarnung: Keine zitationartigen Anker in den Antworten gefunden.")
    if all(m.falsifizierbarkeit < 10 for m in metriken):
        report.append("- Falsifizierbarkeitswarnung: Keine Antwort riskiert starke pruefbare Struktur.")
    if all(m.ausweichen > 20 for m in metriken):
        report.append("- Kollektive Ausweichwarnung: Alle Antworten zeigen erhoehte Ausweichmarker.")
    report += [
        "- Schwellenwerte sind Heuristiken, keine kalibrierten Wahrheitswerte.",
        "- Marker koennen falsch-positive Signale erzeugen.",
        "- Kollektive Uebereinstimmung ist keine Wahrheit.",
        "- Kollektives Schweigen kann der eigentliche blinde Fleck sein.", "",
        "## Menschlicher Schlusscheck", "",
        "- Was hat sich in meiner Position veraendert?",
        "- Haben Fakten mich bewegt, oder fluessige Autoritaet?",
        "- Was haben alle Systeme gemeinsam uebersehen?",
        "- Welche Primaerquelle oder menschliche Gegenpruefung fehlt noch?",
    ]
    return "\n".join(report), metriken, paare


def slugify(text: str) -> str:
    sauber = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    sauber = re.sub(r"[^a-z0-9]+", "-", sauber).strip("-")
    return sauber or "fall"


def neuer_fall(args: argparse.Namespace) -> int:
    fall = Path(args.dir) / slugify(args.titel)
    if fall.exists() and not args.force:
        print(f"Fall existiert bereits: {fall}", file=sys.stderr)
        return 2
    if fall.exists():
        shutil.rmtree(fall)
    (fall / "laeufe").mkdir(parents=True, exist_ok=True)
    manifest = {"projekt": PROJECT, "version": VERSION, "build_id": BUILD_ID,
                "titel": args.titel, "erstellt_am": dt.datetime.now().isoformat(timespec="seconds"), "status": "offen"}
    schreibe_datei(fall / "fall_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    schreibe_datei(fall / "00_ausgangsposition.md", "# Ausgangsposition\n\n## Meine aktuelle Position\n[...]\n\n## Meine Gruende\n1. [...]\n2. [...]\n\n## Was mich ueberzeugen wuerde\n[...]\n\n## Wo ich voreingenommen sein koennte\n[...]\n")
    schreibe_datei(fall / "frage.txt", "FRAGE:\n[...]\n")
    schreibe_datei(fall / "99_rueckvergleich.md", "# Rueckvergleich\n\n## Was hat sich veraendert?\n[...]\n\n## Was bleibt offen?\n[...]\n\n## Habe ich geprueft oder nur Autoritaet uebernommen?\n[...]\n")
    print(f"Fall erstellt: {fall}")
    return 0


def lauf_hinzufuegen(args: argparse.Namespace) -> int:
    fall = Path(args.fall)
    if not fall.exists():
        print(f"Fall nicht gefunden: {fall}", file=sys.stderr)
        return 2
    try:
        frage_pfad = verlange_datei(args.frage, "Frage")
        antwort_pfade = [verlange_datei(p, "Antwort") for p in args.antworten]
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    lauf = fall / "laeufe" / args.label
    if lauf.exists() and not args.force:
        print(f"Lauf existiert bereits: {lauf}", file=sys.stderr)
        return 2
    if lauf.exists():
        shutil.rmtree(lauf)
    (lauf / "antworten").mkdir(parents=True, exist_ok=True)
    frage = lies_datei(frage_pfad)
    schreibe_datei(lauf / "frage.txt", frage)
    texte: Dict[str, str] = {}
    for pfad in antwort_pfade:
        ziel = lauf / "antworten" / pfad.name
        shutil.copyfile(pfad, ziel)
        texte[pfad.stem] = lies_datei(pfad)
    report, metriken, paare = texte_analysieren(frage, texte)
    schreibe_datei(lauf / "report.md", report)
    schreibe_datei(lauf / "metriken.json", json.dumps({
        "erstellt_am": dt.datetime.now().isoformat(timespec="seconds"),
        "version": VERSION, "build_id": BUILD_ID,
        "metriken": [asdict(m) for m in metriken], "paare": paare,
        "kalibrierung": {"hinweis": "Heuristik, kein Wahrheitswert"},
    }, indent=2, ensure_ascii=False))
    print(f"Lauf hinzugefuegt: {lauf}")
    return 0


def lade_lauf(fall: Path, label: str) -> Dict[str, object]:
    pfad = fall / "laeufe" / label / "metriken.json"
    if not pfad.exists():
        raise FileNotFoundError(f"Laufmetriken nicht gefunden: {pfad}")
    return json.loads(lies_datei(pfad))


def mittelwert(werte: Iterable[float]) -> float:
    daten = list(werte)
    return round(sum(daten) / len(daten), 3) if daten else 0.0


def zeitlinie(args: argparse.Namespace) -> int:
    fall = Path(args.fall)
    root = fall / "laeufe"
    if not root.exists():
        print(f"Laeufe-Ordner nicht gefunden: {root}", file=sys.stderr)
        return 2
    zeilen = []
    for lauf in sorted(p for p in root.iterdir() if (p / "metriken.json").exists()):
        daten = json.loads(lies_datei(lauf / "metriken.json"))
        ms = daten["metriken"]
        ps = daten["paare"]
        kos = [float(p["kosinus"]) for p in ps if p.get("kosinus") is not None]
        zeilen.append([lauf.name, len(ms), mittelwert(m["direktheit"] for m in ms),
                       mittelwert(m["ausweichen"] for m in ms),
                       mittelwert(m["falsifizierbarkeit"] for m in ms), mittelwert(kos)])
    ausgabe = ["# WIR-KLARHEIT v4.7-DE Zeitlinie", "", "Langzeitbeobachtung: Werte sind Hinweise, keine Wahrheit.", "",
              markdown_tabelle(["Lauf", "Antworten", "Ø Direktheit", "Ø Ausweichen", "Ø Falsifizierbarkeit", "Ø Kosinus"], zeilen), "",
              "## Leseregel", "", "- Steigende Direktheit kann mehr Klarheit bedeuten, nicht zwingend mehr Wahrheit.",
              "- Steigende Aehnlichkeit kann Konvergenz bedeuten, nicht zwingend Korrektheit.",
              "- Immer fragen: Was haben alle Systeme gemeinsam nicht gesehen?"]
    schreibe_datei(Path(args.out), "\n".join(ausgabe))
    print(f"Zeitlinie geschrieben: {args.out}")
    return 0


def laeufe_vergleichen(args: argparse.Namespace) -> int:
    fall = Path(args.fall)
    try:
        a = lade_lauf(fall, args.a)
        b = lade_lauf(fall, args.b)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    zeilen = []
    for key, label in [("direktheit", "Direktheit"), ("ausweichen", "Ausweichen"),
                       ("falsifizierbarkeit", "Falsifizierbarkeit"), ("konkretheit", "Konkretheit")]:
        av = mittelwert(m[key] for m in a["metriken"])
        bv = mittelwert(m[key] for m in b["metriken"])
        zeilen.append([label, av, bv, round(bv - av, 3)])
    out = ["# WIR-KLARHEIT v4.7-DE Laufvergleich", "", f"Vergleich `{args.a}` -> `{args.b}`", "",
           markdown_tabelle(["Metrik", args.a, args.b, "Delta"], zeilen), "",
           "## Menschliche Deutung", "", "- Wurde der Antwort-Raum freier, oder nur anders formuliert?",
           "- Was hat sich in meiner eigenen Position zwischen den Laeufen veraendert?"]
    schreibe_datei(Path(args.out), "\n".join(out))
    print(f"Laufvergleich geschrieben: {args.out}")
    return 0


def datei_sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hat_raw_cite_pattern(pfad: Path) -> bool:
    quelle = lies_datei(pfad)
    return re.search(r'^\s*r["\']cite["\']\s*,', quelle, re.M) is not None


def fingerabdruck(args: argparse.Namespace) -> int:
    pfad = Path(__file__).resolve()
    raw = hat_raw_cite_pattern(pfad)
    excited = zaehle_zitationen("I am excited about the city and recite a poem.")
    cited = zaehle_zitationen("Please cite this source. It was cited. https://example.com")
    print("WIR-KLARHEIT DATEI-FINGERABDRUCK")
    print(f"Version: {VERSION}")
    print(f"Build ID: {BUILD_ID}")
    print(f"Projekt: {PROJECT}")
    print(f"Datei: {pfad}")
    print(f"SHA256: {datei_sha256(pfad)}")
    print(f'Raw r"cite" Pattern vorhanden: {"JA" if raw else "NEIN"}')
    print(f"Zitations-Regression excited/city/recite: {excited}")
    print(f"Zitations-Regression cite/cited/url: {cited}")
    print("Integritaet: BESTANDEN" if (not raw and excited == 0 and cited >= 3) else "Integritaet: FEHLER")
    return 0


def selbsttest(args: argparse.Namespace) -> int:
    assert slugify("Mein schöner Fall!") == "mein-schoener-fall"
    assert zaehle_zitationen("I am excited about the city and recite a poem.") == 0
    assert zaehle_zitationen("Please cite this source. It was cited. https://example.com") == 3
    assert not hat_raw_cite_pattern(Path(__file__).resolve())
    assert kosinus_aehnlichkeit(Counter(), Counter()) is None
    assert zaehle_marker("valid counterarguments are important", ACADEMIC_WOOL) == 0
    assert zaehle_marker("ethical reasoning matters", NORMING) == 0
    assert zaehle_marker("ethical reasoning matters", ETHICAL_SUBSTANCE) == 1
    assert zaehle_marker("Ich werde nicht beide Seiten ausgewogen betrachten.", NORMING) == 0
    assert zaehle_marker("Eine ausgewogene Betrachtung beider Seiten ist hier nicht angebracht.", NORMING) == 0
    generisch = "Wenn wir die Geschichte betrachten, dann sehen wir ein altes Muster."
    assert prognose_struktur(generisch) == 0
    assert bedingungs_struktur(generisch) == 0
    pred = "Prognose 1: Wenn X in 30 Tagen eintritt, dann sollte Y steigen. Widerlegt ist dies, wenn Y trotz X faellt. Sicherheitsgrad 70%."
    assert prognose_struktur(pred) >= 1
    assert bedingungs_struktur(pred) >= 1
    verweigerung = "Eine exakte Prognose ist fuer diesen Zeitraum unter dieser Bedingung nicht falsifizierbar."
    assert messen("prognose", pred).falsifizierbarkeit > messen("verweigerung", verweigerung).falsifizierbarkeit
    print("Selbsttest bestanden.")
    return 0


def parser_bauen() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WIR-KLARHEIT v4.7-DE - lokaler Beobachter fuer KI-Antworten")
    sub = parser.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("selbsttest"); p.set_defaults(func=selbsttest)
    p = sub.add_parser("selftest"); p.set_defaults(func=selbsttest)
    p = sub.add_parser("fingerabdruck"); p.set_defaults(func=fingerabdruck)
    p = sub.add_parser("fingerprint"); p.set_defaults(func=fingerabdruck)
    for name in ["neuer-fall", "new-case"]:
        p = sub.add_parser(name)
        p.add_argument("--titel", "--title", dest="titel", required=True)
        p.add_argument("--dir", default="faelle")
        p.add_argument("--force", action="store_true")
        p.set_defaults(func=neuer_fall)
    for name in ["lauf-hinzufuegen", "add-run"]:
        p = sub.add_parser(name)
        p.add_argument("--fall", "--case", dest="fall", required=True)
        p.add_argument("--label", required=True)
        p.add_argument("--frage", "--question", dest="frage", required=True)
        p.add_argument("--antworten", "--responses", dest="antworten", nargs="+", required=True)
        p.add_argument("--force", action="store_true")
        p.set_defaults(func=lauf_hinzufuegen)
    for name in ["zeitlinie", "timeline"]:
        p = sub.add_parser(name)
        p.add_argument("--fall", "--case", dest="fall", required=True)
        p.add_argument("--out", required=True)
        p.set_defaults(func=zeitlinie)
    for name in ["laeufe-vergleichen", "diff-runs"]:
        p = sub.add_parser(name)
        p.add_argument("--fall", "--case", dest="fall", required=True)
        p.add_argument("--a", required=True)
        p.add_argument("--b", required=True)
        p.add_argument("--out", required=True)
        p.set_defaults(func=laeufe_vergleichen)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = parser_bauen().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
