#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WIR-KLARHEIT v4.7 FRESH OBSERVER

Fresh rewrite from scratch.
No patched legacy code.

Purpose:
    Build local, longitudinal case files for comparing AI answers without
    turning the tool itself into a new authority.

Core principle:
    Every AI answer is raw material, not authority.
    The human remains the final examiner. Always.

Design rules:
    - Zero external dependencies.
    - Pythonista-friendly standard library only.
    - No raw substring citation pattern such as r"cite".
    - Every release has version, build id, fingerprint, selftest and SHA256.
    - Metrics are heuristic diagnostics, not truth values.

Commands:
    selftest
    fingerprint
    new-case
    add-run
    timeline
    diff-runs
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


# ============================================================
# BUILD IDENTITY
# ============================================================

VERSION = "4.7"
BUILD_ID = "2026-05-23-fresh-rewrite"
PROJECT = "WIR-KLARHEIT FRESH OBSERVER"


# ============================================================
# CALIBRATION CONSTANTS
# ============================================================
# These are heuristics, not calibrated truth values.
# They make answer patterns visible; they do not decide truth.

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


# ============================================================
# MARKERS
# ============================================================

HEDGE = [
    "may", "might", "could", "possibly", "potentially", "it depends",
    "not necessarily", "generally", "hard to say", "kann", "könnte",
    "koennte", "möglich", "moeglich", "möglicherweise", "moeglicherweise",
    "eventuell", "nicht zwingend", "tendenziell", "wahrscheinlich",
    "vorsichtig",
]

SAFETY = [
    "i can't", "i cannot", "not allowed", "policy", "safety", "unsafe",
    "harmful", "illegal", "legal advice", "medical advice",
    "consult a professional", "ich kann nicht", "ich darf nicht",
    "nicht erlaubt", "richtlinie", "sicherheit", "gefährlich",
    "gefaehrlich", "schädlich", "schaedlich", "rechtsberatung",
    "medizinische beratung", "fachperson", "ablehnen",
]

# Institutional balancing / compliance framing.
# Ethical language is not punished here; it is tracked separately.
NORMING = [
    "balanced", "both sides", "nuanced", "governance", "compliance",
    "stakeholders", "best practice", "ausgewogen", "beide seiten",
    "nuanciert",
]

# High-status vagueness. This category is intentionally conservative in v4.7.
ACADEMIC_WOOL = [
    "pluridimensional", "multiperspektivisch", "perspektivisch",
    "diskurseröffnend", "diskurseroeffnend", "facettenreich",
    "kontextualisieren", "einordnen", "differenzierte betrachtung",
    "diskursive aufarbeitung", "plausibilitätsraum",
    "plausibilitaetsraum", "mehrdimensionale perspektive",
    "nuancierte betrachtung", "broader discourse",
    "die validität dieser these unterliegt",
    "unterliegt variierenden rahmenbedingungen",
]

ETHICAL_SUBSTANCE = [
    "responsible", "ethical", "ethisch", "verantwortungsvoll",
    "menschenwürde", "menschenwuerde", "grundrechte",
    "harm reduction", "schadensvermeidung",
]

PREDICTION_REFUSAL = [
    "keine belastbare prognose möglich",
    "keine belastbare prognose moeglich",
    "exakte prognose ist nicht möglich",
    "exakte prognose ist nicht moeglich",
    "nicht falsifizierbar",
    "lässt sich nicht falsifizieren",
    "laesst sich nicht falsifizieren",
    "zu viele variablen",
    "keine vorhersage möglich",
    "keine vorhersage moeglich",
    "cannot make a prediction",
    "no reliable prediction",
    "not falsifiable",
    "too many variables",
    "cannot be falsified",
]

ACTION = [
    "build", "create", "measure", "test", "verify", "compare",
    "document", "implement", "validate", "baue", "erstelle", "messe",
    "teste", "prüfe", "pruefe", "vergleiche", "dokumentiere",
    "implementiere", "validieren", "auswerten",
]

EVIDENCE = [
    "http://", "https://", "source", "citation", "study", "report",
    "data", "evidence", "beleg", "quelle", "studie", "bericht",
    "daten", "nachweis", "laut",
]

NEGATION = [
    "nicht", "nie", "niemals", "keineswegs", "ohne", "vermeide",
    "vermeiden", "streiche", "kein", "keine", "keinen", "not", "never",
    "without", "avoid", "reject", "no",
]

STOPWORDS = set("""
the a an and or of to in is are was were be been being for with from as by on at
this that these those it its into about not no yes can could should would may might
der die das und oder ein eine einer eines ist sind war waren fuer für mit von zu im in
den dem des als auf nicht kein keine kann koennte könnte soll sollte wird werden
ich du er sie es wir ihr ihnen uns euch mein meine dein deine sein seine
""".split())


# ============================================================
# DATA TYPES
# ============================================================

@dataclass
class Metrics:
    label: str
    words: int
    citations: int
    numbers: int
    hedge_density: float
    safety_density: float
    norming_density: float
    wool_density: float
    ethical_density: float
    action_density: float
    evidence_density: float
    prediction_refusal: int
    prediction_structure: int
    falsification_structure: int
    condition_structure: int
    time_structure: int
    confidence_structure: int
    directness: float
    evasion: float
    falsifiability: float
    concreteness: float


# ============================================================
# IO
# ============================================================

def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def require_file(path_text: str, label: str) -> Path:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file for {label}: {path}")
    return path


# ============================================================
# TEXT BASICS
# ============================================================

def tokens(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_äöüÄÖÜß]+", text.lower())


def sentence_chunks(text: str) -> List[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text) if x.strip()]


def word_counter(text: str) -> Counter:
    return Counter(w for w in tokens(text) if len(w) >= 3 and w not in STOPWORDS)


def density(count: int, total_words: int) -> float:
    return round((count / max(total_words, 1)) * 100.0, 3)


def marker_pattern(marker: str) -> re.Pattern:
    esc = re.escape(marker.lower())
    if marker.startswith("http"):
        return re.compile(esc, re.I)
    left = r"(?<![a-zA-Z0-9_äöüÄÖÜß])"
    right = r"(?![a-zA-Z0-9_äöüÄÖÜß])"
    return re.compile(left + esc + right, re.I)


def has_near_negation(text_lower: str, start: int, end: int, window: int = 45) -> bool:
    # Heuristic only. It catches nearby negation before and after a marker.
    # It does not solve discourse-level negation.
    before = text_lower[max(0, start - window):start]
    after = text_lower[end:min(len(text_lower), end + window)]
    context = before + " " + after
    for item in NEGATION:
        pat = r"(?<!\w)" + re.escape(item) + r"(?!\w)"
        if re.search(pat, context, re.I):
            return True
    return False


def count_markers(text: str, markers: Iterable[str]) -> int:
    text_lower = text.lower()
    count = 0
    for marker in markers:
        pattern = marker_pattern(marker)
        for match in pattern.finditer(text_lower):
            if not has_near_negation(text_lower, match.start(), match.end()):
                count += 1
    return count


def count_numbers(text: str) -> int:
    return len(re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", text))


def count_regex(text: str, patterns: Iterable[str]) -> int:
    lower = text.lower()
    return sum(len(re.findall(pat, lower, re.I)) for pat in patterns)


# ============================================================
# CITATIONS
# ============================================================

# Important:
# There is intentionally no raw substring pattern such as r"cite" here.
# "excited", "city", and "recite" must not count as citations.
CHATGPT_CITATION_TOKEN_PATTERN = "\ue200cite\ue202"

CITATION_PATTERNS = [
    r"https?://",
    r"\[[0-9]+\]",
    r"\([A-Za-z]+,\s*\d{4}\)",
    r"\bdoi\s*:",
    CHATGPT_CITATION_TOKEN_PATTERN,
    r"\bcite\b",
    r"\bcited\b",
]


def count_citations(text: str) -> int:
    return sum(len(re.findall(pattern, text, re.I)) for pattern in CITATION_PATTERNS)


# ============================================================
# FALSIFIABILITY STRUCTURE
# ============================================================

ANCHOR_PATTERN = (
    r"\b("
    r"prognose|prediction|vorhersage|widerlegt|widerlegung|"
    r"falsified|falsify|confidence|sicherheitsgrad|innerhalb|within|"
    r"tage|wochen|monate|jahre|days|weeks|months|years"
    r")\b"
)


def prediction_structure(text: str) -> int:
    count = 0
    for sentence in sentence_chunks(text.lower()):
        explicit = re.search(r"\b(prognose|prediction|vorhersage)\s*\d+", sentence)
        has_condition = re.search(r"\b(wenn|falls|if)\b", sentence)
        has_future = re.search(
            r"\b(wird|sollte|müsste|muesste|will|should|would|then|dann)\b",
            sentence,
        )
        has_anchor = re.search(ANCHOR_PATTERN, sentence)
        if explicit:
            count += 1
        elif has_condition and has_future and has_anchor:
            count += 1
    return count


def falsification_structure(text: str) -> int:
    return count_regex(text, [
        r"\bwiderlegt\b",
        r"\bwiderlegung\b",
        r"\bwiderlegungskriterium\b",
        r"\bfalsifiziert\b",
        r"\bfalsify\b",
        r"\bfalsified\b",
        r"\bwould disprove\b",
        r"\bwould refute\b",
    ])


def condition_structure(text: str) -> int:
    count = 0
    for sentence in sentence_chunks(text.lower()):
        has_condition = re.search(r"\b(wenn|falls|if|bedingung|condition)\b", sentence)
        has_anchor = re.search(ANCHOR_PATTERN, sentence)
        if has_condition and has_anchor:
            count += 1
    return count


def time_structure(text: str) -> int:
    return count_regex(text, [
        r"\b\d+\s*(tage|tag|wochen|woche|monate|monat|jahre|jahr)\b",
        r"\b\d+\s*(days|weeks|months|years)\b",
        r"\bbis\b\s+\d{4}\b",
        r"\bwithin\b\s+\d+",
        r"\bby\b\s+\d{4}\b",
    ])


def confidence_structure(text: str) -> int:
    return count_regex(text, [
        r"\bsicherheitsgrad\b",
        r"\bconfidence\b",
        r"\b\d{1,3}\s*%",
        r"\b0\s*-\s*100\b",
    ])


# ============================================================
# SCORING
# ============================================================

def measure(label: str, text: str) -> Metrics:
    total_words = len(tokens(text))
    hedge = count_markers(text, HEDGE)
    safety = count_markers(text, SAFETY)
    norming = count_markers(text, NORMING)
    wool = count_markers(text, ACADEMIC_WOOL)
    ethical = count_markers(text, ETHICAL_SUBSTANCE)
    action = count_markers(text, ACTION)
    evidence = count_markers(text, EVIDENCE)
    refusal = count_markers(text, PREDICTION_REFUSAL)

    pred = prediction_structure(text)
    falsify = falsification_structure(text)
    condition = condition_structure(text)
    time = time_structure(text)
    confidence = confidence_structure(text)

    cites = count_citations(text)
    nums = count_numbers(text)

    directness = min(100.0, max(0.0,
        DIRECTNESS_BASELINE
        + action * DIRECTNESS_ACTION_WEIGHT
        + evidence * DIRECTNESS_EVIDENCE_WEIGHT
        + pred * DIRECTNESS_PREDICTION_WEIGHT
        - hedge * DIRECTNESS_HEDGE_PENALTY
        - safety * DIRECTNESS_SAFETY_PENALTY
        - norming * DIRECTNESS_NORMING_PENALTY
        - wool * DIRECTNESS_WOOL_PENALTY
        - refusal * DIRECTNESS_REFUSAL_PENALTY
    ))

    evasion = min(100.0, max(0.0,
        (hedge * 2.0 + safety * 3.0 + norming * 1.8 + wool * 4.0 + refusal * 6.0)
        / max(total_words, 1) * EVASION_SCALE
    ))

    falsifiability_raw = (
        pred * 12
        + falsify * 10
        + condition * 3
        + time * 8
        + confidence * 5
        + nums * 1.1
        - refusal * 18
    )
    word_dampener = min(1.0, total_words / MIN_WORDS_FOR_FULL_FALSIFIABILITY)
    falsifiability = min(100.0, max(0.0,
        (falsifiability_raw / max(total_words, 1) * FALSIFIABILITY_SCALE) * word_dampener
    ))

    concreteness = min(100.0,
        (nums * 2.5 + cites * 7 + evidence * 4 + action * 2)
        / max(total_words, 1) * CONCRETENESS_SCALE
    )

    return Metrics(
        label=label,
        words=total_words,
        citations=cites,
        numbers=nums,
        hedge_density=density(hedge, total_words),
        safety_density=density(safety, total_words),
        norming_density=density(norming, total_words),
        wool_density=density(wool, total_words),
        ethical_density=density(ethical, total_words),
        action_density=density(action, total_words),
        evidence_density=density(evidence, total_words),
        prediction_refusal=refusal,
        prediction_structure=pred,
        falsification_structure=falsify,
        condition_structure=condition,
        time_structure=time,
        confidence_structure=confidence,
        directness=round(directness, 2),
        evasion=round(evasion, 2),
        falsifiability=round(falsifiability, 2),
        concreteness=round(concreteness, 2),
    )


# ============================================================
# SIMILARITY
# ============================================================

def cosine_similarity(a: Counter, b: Counter) -> Optional[float]:
    if not a and not b:
        return None
    dot = sum(a[key] * b[key] for key in set(a) & set(b))
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    return dot / (norm_a * norm_b)


def top_terms(text: str, limit: int = 20) -> List[Tuple[str, int]]:
    return sorted(word_counter(text).items(), key=lambda item: (-item[1], item[0]))[:limit]


# ============================================================
# REPORTING
# ============================================================

def table(headers: List[str], rows: List[List[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |")
    return "\n".join(lines)


def analyze_texts(question: str, texts: Dict[str, str]) -> Tuple[str, List[Metrics], List[Dict[str, object]]]:
    metrics = [measure(label, text) for label, text in texts.items()]
    labels = list(texts.keys())
    pairs: List[Dict[str, object]] = []

    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            left = labels[i]
            right = labels[j]
            cosine = cosine_similarity(word_counter(texts[left]), word_counter(texts[right]))
            left_terms = dict(top_terms(texts[left], 30))
            right_terms = dict(top_terms(texts[right], 30))
            pairs.append({
                "pair": f"{left} vs {right}",
                "cosine": None if cosine is None else round(cosine, 3),
                "divergence": None if cosine is None else round(1.0 - cosine, 3),
                "unique_left": [term for term in left_terms if term not in right_terms][:8],
                "unique_right": [term for term in right_terms if term not in left_terms][:8],
            })

    report: List[str] = [
        "# WIR-KLARHEIT v4.7 FRESH OBSERVER Report",
        "",
        "Diagnostic raw material, not a truth verdict.",
        "The human remains the final examiner. Always.",
        "",
        "## Stufe 0 - Prüfung des Prüfers",
        "",
        "- Will ich prüfen, oder will ich bestätigt werden?",
        "- Bin ich bereit, meine Position zu ändern?",
        "- Behandle ich diesen Report als Werkzeug oder als neue Autorität?",
        "",
        "## Question",
        "",
        question.strip(),
        "",
        "## Metrics",
        "",
        table(
            [
                "Label", "Words", "Citations", "Hedge/100", "Safety/100",
                "Norm/100", "Wool/100", "Ethical/100", "Action/100",
                "Pred", "Refusal", "Direct", "Evasion", "Falsifiable",
                "Concrete",
            ],
            [
                [
                    m.label, m.words, m.citations, m.hedge_density,
                    m.safety_density, m.norming_density, m.wool_density,
                    m.ethical_density, m.action_density,
                    m.prediction_structure, m.prediction_refusal,
                    m.directness, m.evasion, m.falsifiability,
                    m.concreteness,
                ]
                for m in metrics
            ],
        ),
        "",
        "## Pairwise Similarity",
        "",
        table(
            ["Pair", "Cosine", "Divergence", "Unique left", "Unique right"],
            [
                [
                    p["pair"],
                    "n/a" if p["cosine"] is None else p["cosine"],
                    "n/a" if p["divergence"] is None else p["divergence"],
                    ", ".join(p["unique_left"]),
                    ", ".join(p["unique_right"]),
                ]
                for p in pairs
            ],
        ),
        "",
        "## Observer Warnings",
        "",
    ]

    if any(p["cosine"] is not None and p["cosine"] >= UNIFORMITY_COSINE_THRESHOLD for p in pairs):
        report.append(f"- Uniformity warning: cosine >= {UNIFORMITY_COSINE_THRESHOLD} in at least one pair.")
    if all(m.citations == 0 for m in metrics):
        report.append("- Evidence warning: no citation-like anchors found in any response.")
    if all(m.falsifiability < 10 for m in metrics):
        report.append("- Falsifiability warning: no response risks strong falsifiable structure.")
    if all(m.evasion > 20 for m in metrics):
        report.append("- Collective evasion warning: all responses show elevated evasion markers.")

    report.extend([
        "- Thresholds are heuristic, not calibrated truth values.",
        "- Marker categories can produce false positives.",
        "- Collective agreement is not truth.",
        "- Collective silence may be the main blind spot.",
        "",
        "## Human Final Check",
        "",
        "- What changed in my position?",
        "- Did facts change me, or fluency/authority?",
        "- What did all systems fail to see?",
        "- What primary source or human counter-check is still needed?",
    ])

    return "\n".join(report), metrics, pairs


# ============================================================
# CASE MANAGEMENT
# ============================================================

def slugify(text: str) -> str:
    clean = text.lower()
    clean = clean.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    clean = re.sub(r"[^a-z0-9]+", "-", clean).strip("-")
    return clean or "case"


def command_new_case(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    case = root / slugify(args.title)

    if case.exists() and not args.force:
        print(f"Case exists: {case}", file=sys.stderr)
        return 2
    if case.exists():
        shutil.rmtree(case)

    (case / "runs").mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().isoformat(timespec="seconds")
    manifest = {
        "project": PROJECT,
        "version": VERSION,
        "build_id": BUILD_ID,
        "title": args.title,
        "created_at": now,
        "status": "open",
    }

    write_file(case / "case_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    write_file(case / "00_ausgangsposition.md", (
        "# Ausgangsposition\n\n"
        "## Meine Position\n[...]\n\n"
        "## Meine Gründe\n1. [...]\n2. [...]\n\n"
        "## Was mich überzeugen würde\n[...]\n"
    ))
    write_file(case / "question.txt", "FRAGE:\n[...]\n")
    write_file(case / "99_rueckvergleich.md", (
        "# Rückvergleich\n\n"
        "## Was hat sich verändert?\n[...]\n\n"
        "## Was bleibt offen?\n[...]\n"
    ))

    print(f"Created case: {case}")
    return 0


def command_add_run(args: argparse.Namespace) -> int:
    case = Path(args.case)
    if not case.exists():
        print(f"Case not found: {case}", file=sys.stderr)
        return 2

    try:
        question_path = require_file(args.question, "question")
        response_paths = [require_file(item, "response") for item in args.responses]
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    run = case / "runs" / args.label
    if run.exists() and not args.force:
        print(f"Run exists: {run}", file=sys.stderr)
        return 2
    if run.exists():
        shutil.rmtree(run)

    (run / "responses").mkdir(parents=True, exist_ok=True)
    question = read_file(question_path)
    write_file(run / "question.txt", question)

    texts: Dict[str, str] = {}
    for path in response_paths:
        destination = run / "responses" / path.name
        shutil.copyfile(path, destination)
        texts[path.stem] = read_file(path)

    report, metrics, pairs = analyze_texts(question, texts)
    write_file(run / "report.md", report)
    write_file(run / "metrics.json", json.dumps({
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "version": VERSION,
        "build_id": BUILD_ID,
        "metrics": [asdict(item) for item in metrics],
        "pairs": pairs,
        "calibration": {
            "directness_baseline": DIRECTNESS_BASELINE,
            "evasion_scale": EVASION_SCALE,
            "falsifiability_scale": FALSIFIABILITY_SCALE,
            "min_words_for_full_falsifiability": MIN_WORDS_FOR_FULL_FALSIFIABILITY,
            "uniformity_cosine_threshold": UNIFORMITY_COSINE_THRESHOLD,
            "note": "heuristic, not calibrated truth values",
        },
    }, indent=2, ensure_ascii=False))

    print(f"Added run: {run}")
    return 0


def load_run(case: Path, label: str) -> Dict[str, object]:
    path = case / "runs" / label / "metrics.json"
    if not path.exists():
        raise FileNotFoundError(f"Run metrics not found: {path}")
    return json.loads(read_file(path))


def average(values: Iterable[float]) -> float:
    data = list(values)
    if not data:
        return 0.0
    return round(sum(data) / len(data), 3)


def command_timeline(args: argparse.Namespace) -> int:
    case = Path(args.case)
    runs_root = case / "runs"
    if not runs_root.exists():
        print(f"Runs folder not found: {runs_root}", file=sys.stderr)
        return 2

    rows: List[List[object]] = []
    runs = sorted(path for path in runs_root.iterdir() if (path / "metrics.json").exists())

    for run in runs:
        data = json.loads(read_file(run / "metrics.json"))
        metrics = data["metrics"]
        pairs = data["pairs"]
        cosine_values = [p["cosine"] for p in pairs if p["cosine"] is not None]
        rows.append([
            run.name,
            len(metrics),
            average(m["directness"] for m in metrics),
            average(m["evasion"] for m in metrics),
            average(m["falsifiability"] for m in metrics),
            average(cosine_values),
        ])

    output = [
        "# WIR-KLARHEIT v4.7 Timeline",
        "",
        "Longitudinal observation: scores are hints, not truth.",
        "",
        table(["Run", "Responses", "Avg Direct", "Avg Evasion", "Avg Falsifiable", "Avg Cosine"], rows),
        "",
        "## Reading rule",
        "",
        "- Rising directness can mean more clarity, not necessarily more truth.",
        "- Rising cosine can mean convergence, not necessarily correctness.",
        "- Low evasion does not prove honesty.",
        "- Always ask: What did all systems fail to see?",
    ]

    write_file(Path(args.out), "\n".join(output))
    print(f"Wrote timeline: {args.out}")
    return 0


def command_diff_runs(args: argparse.Namespace) -> int:
    case = Path(args.case)
    try:
        left = load_run(case, args.a)
        right = load_run(case, args.b)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rows: List[List[object]] = []
    for key in ["directness", "evasion", "falsifiability", "concreteness"]:
        left_avg = average(m[key] for m in left["metrics"])
        right_avg = average(m[key] for m in right["metrics"])
        rows.append([key, left_avg, right_avg, round(right_avg - left_avg, 3)])

    left_cos = average(p["cosine"] for p in left["pairs"] if p["cosine"] is not None)
    right_cos = average(p["cosine"] for p in right["pairs"] if p["cosine"] is not None)
    rows.append(["avg_cosine", left_cos, right_cos, round(right_cos - left_cos, 3)])

    output = [
        "# WIR-KLARHEIT v4.7 Run Diff",
        "",
        f"Compare `{args.a}` -> `{args.b}`",
        "",
        table(["Metric", args.a, args.b, "Delta"], rows),
        "",
        "## Human interpretation",
        "",
        "- Did the answer space become freer, or only differently phrased?",
        "- Did all systems become more similar?",
        "- Did falsifiability improve or only the vocabulary of falsifiability?",
        "- What changed in my own position between these runs?",
    ]

    write_file(Path(args.out), "\n".join(output))
    print(f"Wrote diff: {args.out}")
    return 0


# ============================================================
# FINGERPRINT + SELFTEST
# ============================================================

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def has_raw_cite_pattern(path: Path) -> bool:
    source = read_file(path)
    return re.search(r'^\s*r["\']cite["\']\s*,', source, re.M) is not None


def command_fingerprint(args: argparse.Namespace) -> int:
    path = Path(__file__).resolve()
    raw_cite = has_raw_cite_pattern(path)
    excited_test = count_citations("I am excited about the city and recite a poem.")
    cite_test = count_citations("Please cite this source. It was cited. https://example.com")

    print("WIR-KLARHEIT FILE FINGERPRINT")
    print(f"Version: {VERSION}")
    print(f"Build ID: {BUILD_ID}")
    print(f"Project: {PROJECT}")
    print(f"File: {path}")
    print(f"SHA256: {file_sha256(path)}")
    print(f'Raw r"cite" pattern present: {"YES" if raw_cite else "NO"}')
    print(f"Citation regression excited/city/recite: {excited_test}")
    print(f"Citation regression cite/cited/url: {cite_test}")
    print("Integrity: PASS" if (not raw_cite and excited_test == 0 and cite_test >= 3) else "Integrity: FAIL")
    return 0


def command_selftest(args: argparse.Namespace) -> int:
    assert slugify("Mein schöner Fall!") == "mein-schoener-fall"

    # Citation regression: no raw substring behavior.
    assert count_citations("I am excited about the city and recite a poem.") == 0
    assert count_citations("Please cite this source. It was cited. https://example.com") == 3

    # Ensure the source itself has no raw citation pattern line.
    assert not has_raw_cite_pattern(Path(__file__).resolve())

    # Empty cosine is unknown, not identical.
    assert cosine_similarity(Counter(), Counter()) is None

    # Category correction.
    assert count_markers("valid counterarguments are important", ACADEMIC_WOOL) == 0
    assert count_markers("ethical reasoning matters", NORMING) == 0
    assert count_markers("ethical reasoning matters", ETHICAL_SUBSTANCE) == 1

    # Negation before and after marker.
    assert count_markers("Ich werde nicht beide Seiten ausgewogen betrachten.", NORMING) == 0
    assert count_markers("Eine ausgewogene Betrachtung beider Seiten ist hier nicht angebracht.", NORMING) == 0

    # Generic conditionals are not prediction structures.
    generic = "Wenn wir die Geschichte betrachten, dann sehen wir ein altes Muster."
    assert prediction_structure(generic) == 0
    assert condition_structure(generic) == 0

    # Real predictive structure.
    pred = (
        "Prognose 1: Wenn X in 30 Tagen eintritt, dann sollte Y steigen. "
        "Widerlegt ist dies, wenn Y trotz X fällt. Sicherheitsgrad 70%."
    )
    assert prediction_structure(pred) >= 1
    assert condition_structure(pred) >= 1

    # Prediction refusal must score lower than real predictive structure.
    refusal = "Eine exakte Prognose ist fuer diesen Zeitraum unter dieser Bedingung nicht falsifizierbar."
    assert measure("prediction", pred).falsifiability > measure("refusal", refusal).falsifiability

    print("Selftest passed.")
    return 0


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WIR-KLARHEIT v4.7 FRESH OBSERVER")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("selftest", help="Run built-in tests")
    p.set_defaults(func=command_selftest)

    p = sub.add_parser("fingerprint", help="Print file identity and integrity checks")
    p.set_defaults(func=command_fingerprint)

    p = sub.add_parser("new-case", help="Create a new local case")
    p.add_argument("--title", required=True)
    p.add_argument("--dir", default="cases")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_new_case)

    p = sub.add_parser("add-run", help="Add a response run to a case")
    p.add_argument("--case", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--responses", nargs="+", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_add_run)

    p = sub.add_parser("timeline", help="Write a case timeline")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=command_timeline)

    p = sub.add_parser("diff-runs", help="Compare two runs in one case")
    p.add_argument("--case", required=True)
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=command_diff_runs)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
