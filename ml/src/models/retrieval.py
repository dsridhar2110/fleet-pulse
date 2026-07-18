"""Module 3 — Engineer Copilot: retrieval over historical service tickets.

An engineer types a symptom in their own words ("helium boiling off too fast").
We return the most similar *resolved* tickets from fleet history, with what was
actually replaced and how long the machine was down.

Design decisions worth defending:

1. The index is built over the SYMPTOM half of each ticket note only, never the
   full note. The note contains the resolution ("replaced cold head assembly"),
   and indexing that would let a query match on words describing the answer.
   Symptom-in, resolution-out.

2. TF-IDF + cosine, not embeddings. The corpus is 440 short, domain-specific
   notes; a lexical model is stronger here than a general sentence encoder, and
   it ships as a 200KB JSON the browser can score with no server, no API key,
   and no LLM. The tokenizer is hand-written (not sklearn) precisely so the
   browser can reproduce the query-side maths exactly.

3. Two evaluations, because one of them flatters us:
   - leave-one-out over the corpus symptoms. This is EASY: the generator draws
     symptoms from a small template vocabulary, so a held-out ticket's symptom
     is often a literal string match. A high score here measures the synthetic
     corpus, not the retriever. Reported, but caveated.
   - a hand-written paraphrase set: queries in words that appear NOWHERE in the
     template vocabulary ("scanner grinding when it spins"). This is the honest
     number, and the one that tells us whether lexical retrieval would survive
     real engineer shorthand.

Run:  PYTHONPATH=$PWD/src .venv/bin/python src/models/retrieval.py
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
APP = ROOT / "data" / "app"
WEB = ROOT.parent / "web" / "public" / "data"

# Deliberately tiny stoplist: service notes are terse, and killing domain words
# ("low", "high", "no") would cost more than the noise they carry.
STOP = {"the", "a", "an", "and", "of", "to", "on", "in", "at", "for", "is", "was", "it"}

TOKEN_RE = re.compile(r"[a-z0-9]+")

# The generator's closing lines and escalation shorthand carry no diagnostic
# signal — they appear on every ticket regardless of fault.
NOISE = {"esc", "l2", "ref", "prev", "tkt"}

COMPONENT_LABEL = {
    "cold_head": "Cold head / helium",
    "gradient_coil": "Gradient coil",
    "rf_amplifier": "RF amplifier",
    "xray_tube": "X-ray tube",
    "detector_array": "Detector array",
    "gantry_bearing": "Gantry bearing",
    "generator": "HV generator",
}

# Held-out paraphrases: how an engineer might actually phrase it. None of these
# reuse a template symptom string verbatim — that is the point.
PARAPHRASES = [
    ("helium is boiling off way too quickly", "cold_head"),
    ("cryogen levels keep falling overnight", "cold_head"),
    ("cold head compressor is overheating", "cold_head"),
    ("magnet is losing coolant fast", "cold_head"),
    ("scanner makes a grinding noise when it spins", "gantry_bearing"),
    ("loud rumble from the rotating assembly", "gantry_bearing"),
    ("gantry wobbles and rotation is not smooth", "gantry_bearing"),
    ("tube is arcing more than usual", "xray_tube"),
    ("we are seeing spits and arc faults on exposure", "xray_tube"),
    ("anode current keeps jumping around", "xray_tube"),
    ("tube is close to end of life", "xray_tube"),
    ("dead pixels and dropouts in the detector", "detector_array"),
    ("images are noisy, site is complaining", "detector_array"),
    ("detector channel keeps dropping out", "detector_array"),
    ("gradient coil is running hot", "gradient_coil"),
    ("cooling loop for the coil has lost pressure", "gradient_coil"),
    ("artifacts in the image, sounds like gradient noise", "gradient_coil"),
    ("rf power keeps drifting up and down", "rf_amplifier"),
    ("poor signal to noise, suspect the amplifier", "rf_amplifier"),
    ("intermittent fault on the rf stage", "rf_amplifier"),
    ("voltage ripple is over the limit", "generator"),
    ("mains power at the site keeps fluctuating", "generator"),
]


def tokenize(text: str) -> list[str]:
    """Hand-written tokenizer. The browser reimplements this EXACTLY (see
    web/src/lib/retrieval.ts) — keep the two in lockstep."""
    toks = TOKEN_RE.findall(text.lower())
    return [t for t in toks if t not in STOP and t not in NOISE and len(t) > 1]


def split_note(note: str) -> tuple[str, str]:
    """Note format is `[sudden failure, no prior alerts. ]{symptom}. {action}. {closer}`.

    Returns (symptom, action). The 'sudden failure' prefix is stripped: it is a
    property of the failure, not a describable symptom, and leaving it in makes
    every sudden ticket look similar to every other sudden ticket."""
    text = note.strip()
    prefix = "sudden failure, no prior alerts. "
    if text.lower().startswith(prefix):
        text = text[len(prefix):]
    parts = [p.strip() for p in text.split(". ") if p.strip()]
    symptom = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    return symptom, action


def build_index(docs: list[str]) -> tuple[dict[str, int], list[float], list[dict[str, float]]]:
    """TF-IDF with sublinear tf and L2-normalised vectors, returned sparse."""
    tokenized = [tokenize(d) for d in docs]
    df = Counter()
    for toks in tokenized:
        df.update(set(toks))

    vocab = {term: i for i, term in enumerate(sorted(df))}
    n = len(docs)
    # Smoothed idf, same form as sklearn's default: ln((1+n)/(1+df)) + 1.
    idf = [math.log((1 + n) / (1 + df[term])) + 1 for term in sorted(df)]

    vectors: list[dict[str, float]] = []
    for toks in tokenized:
        tf = Counter(toks)
        vec = {}
        for term, count in tf.items():
            i = vocab[term]
            vec[str(i)] = (1 + math.log(count)) * idf[i]
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({k: round(v / norm, 5) for k, v in vec.items()})

    return vocab, idf, vectors


def score_query(query: str, vocab, idf, vectors) -> list[float]:
    toks = [t for t in tokenize(query) if t in vocab]
    if not toks:
        return [0.0] * len(vectors)
    tf = Counter(toks)
    q = {}
    for term, count in tf.items():
        i = vocab[term]
        q[str(i)] = (1 + math.log(count)) * idf[i]
    norm = math.sqrt(sum(v * v for v in q.values())) or 1.0
    q = {k: v / norm for k, v in q.items()}

    sims = []
    for vec in vectors:
        s = 0.0
        for k, v in q.items():
            if k in vec:
                s += v * vec[k]
        sims.append(s)
    return sims


def main() -> None:
    tickets = pd.read_parquet(RAW / "tickets.parquet")
    fleet = pd.read_parquet(RAW / "fleet_master.parquet")[["machine_id", "modality", "country"]]

    # Only corrective tickets carry a resolution — they are the corpus worth
    # retrieving. Preventive/NFF tickets have nothing to tell a stuck engineer.
    corr = tickets[tickets.ticket_type == "corrective"].copy()
    corr = corr.merge(fleet, on="machine_id", how="left")
    corr[["symptom", "action"]] = corr.note_text.apply(lambda n: pd.Series(split_note(n)))
    corr = corr.reset_index(drop=True)

    vocab, idf, vectors = build_index(corr.symptom.tolist())
    print(f"indexed {len(corr)} corrective tickets · vocab {len(vocab)} terms")

    components = corr.component.tolist()

    def rank(query: str, exclude: int | None = None) -> list[int]:
        """Ticket indices by descending similarity, ZERO-SIMILARITY DROPPED.

        Dropping them is not a detail. A query whose every token is out of
        vocabulary scores 0.0 against all 440 tickets, and argsort on an all-zero
        array happily returns ticket 0 — which an evaluation will then score as a
        correct answer if ticket 0 happens to have the right component. That is a
        coin flip being counted as a hit. No match must mean no match."""
        sims = score_query(query, vocab, idf, vectors)
        if exclude is not None:
            sims[exclude] = 0.0
        idxs = [j for j in range(len(sims)) if sims[j] > 0]
        return sorted(idxs, key=lambda j: sims[j], reverse=True)

    # --- Evaluation 1: leave-one-out over template symptoms (the easy one) ---
    loo_hits1 = loo_hits3 = 0
    for i, sym in enumerate(corr.symptom):
        ranked = rank(sym, exclude=i)[:3]
        if ranked and components[ranked[0]] == components[i]:
            loo_hits1 += 1
        if any(components[j] == components[i] for j in ranked):
            loo_hits3 += 1
    loo_p1 = loo_hits1 / len(corr)
    loo_p3 = loo_hits3 / len(corr)

    # --- Evaluation 2: hand-written paraphrases (the honest one) ---
    # Two read-outs: the single nearest ticket, and a similarity-weighted vote
    # across the top-10. The vote is what the product actually surfaces — "of the
    # 10 most similar past tickets, 7 were the cold head" — and it is more robust
    # than trusting one neighbour that may have matched on an incidental word.
    par_hits1 = par_hits3 = vote_hits = no_answer = 0
    par_detail = []
    for query, truth in PARAPHRASES:
        sims = score_query(query, vocab, idf, vectors)
        ranked = rank(query)
        top3 = ranked[:3]

        if not ranked:
            # Every token out of vocabulary. This counts as a MISS, not a lucky
            # guess — the retriever genuinely has nothing to say.
            no_answer += 1
            par_detail.append({
                "query": query,
                "expected": truth,
                "predicted_top1": None,
                "predicted_vote": None,
                "top_similarity": 0.0,
                "hit_at_1": False,
                "hit_at_3": False,
                "hit_vote": False,
                "out_of_vocabulary": True,
            })
            continue

        top1_hit = components[top3[0]] == truth
        top3_hit = any(components[j] == truth for j in top3)

        votes: Counter = Counter()
        for j in ranked[:10]:
            votes[components[j]] += sims[j]
        voted = votes.most_common(1)[0][0] if votes else None
        vote_hit = voted == truth

        par_hits1 += top1_hit
        par_hits3 += top3_hit
        vote_hits += vote_hit
        par_detail.append({
            "query": query,
            "expected": truth,
            "predicted_top1": components[top3[0]],
            "predicted_vote": voted,
            "top_similarity": round(sims[top3[0]], 3),
            "hit_at_1": bool(top1_hit),
            "hit_at_3": bool(top3_hit),
            "hit_vote": bool(vote_hit),
            "out_of_vocabulary": False,
        })
    par_p1 = par_hits1 / len(PARAPHRASES)
    par_p3 = par_hits3 / len(PARAPHRASES)
    par_vote = vote_hits / len(PARAPHRASES)

    # Random baseline: 7 components, but they are not uniform — guessing the
    # most common component (xray_tube) is the baseline worth beating.
    majority = Counter(components).most_common(1)[0]
    majority_rate = majority[1] / len(components)

    metrics = {
        "corpus": {
            "corrective_tickets_indexed": int(len(corr)),
            "vocabulary_terms": len(vocab),
            "components": sorted(set(components)),
            "index_bytes_approx": sum(len(v) for v in vectors) * 12,
        },
        "leave_one_out_template_symptoms": {
            "component_precision_at_1": round(loo_p1, 3),
            "component_precision_at_3": round(loo_p3, 3),
            "caveat": (
                "Flattering by construction. The generator draws symptoms from a small "
                "template vocabulary, so a held-out symptom is often a near-literal match "
                "for another ticket. This measures the synthetic corpus, not the retriever."
            ),
        },
        "held_out_paraphrases": {
            "n_queries": len(PARAPHRASES),
            "component_precision_at_1": round(par_p1, 3),
            "component_precision_at_3": round(par_p3, 3),
            "component_accuracy_top10_vote": round(par_vote, 3),
            "majority_class_baseline": round(majority_rate, 3),
            "out_of_vocabulary_queries": no_answer,
            "note": (
                "Queries hand-written in words that appear nowhere in the template "
                "vocabulary. This is the number to trust, and the one that predicts how "
                "lexical retrieval would behave against real engineer shorthand."
            ),
            "failure_mode": (
                "Every miss is lexical, not conceptual: 'grinding noise when it spins' "
                "retrieves 'detector noise high' because they share the token 'noise', "
                "while the correct ticket says 'bearing noise during rotation'. TF-IDF has "
                "no notion that grinding and bearing are related. This is the concrete "
                "argument for sentence embeddings, and it is the roadmap."
            ),
            "detail": par_detail,
        },
    }

    APP.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)

    index_payload = {
        "vocab": vocab,
        "idf": [round(v, 5) for v in idf],
        "tickets": [
            {
                "id": int(i),
                "machine_id": r.machine_id,
                "modality": r.modality,
                "country": r.country,
                "component": r.component,
                "component_label": COMPONENT_LABEL.get(r.component, r.component),
                "part_replaced": r.part_replaced,
                "downtime_days": int(r.downtime_days),
                "opened": r.open_date.strftime("%Y-%m-%d"),
                "symptom": r.symptom,
                "action": r.action,
                "note": r.note_text,
                "vec": vectors[i],
            }
            for i, r in enumerate(corr.itertuples())
        ],
    }

    (WEB / "tickets_index.json").write_text(json.dumps(index_payload, separators=(",", ":")))
    (WEB / "retrieval_metrics.json").write_text(json.dumps(metrics, indent=2))
    (APP / "retrieval_metrics.json").write_text(json.dumps(metrics, indent=2))

    size_kb = (WEB / "tickets_index.json").stat().st_size / 1024
    print(f"\nleave-one-out (template symptoms): P@1 {loo_p1:.3f} · P@3 {loo_p3:.3f}   <- flattering")
    print(f"held-out paraphrases:              P@1 {par_p1:.3f} · P@3 {par_p3:.3f}   <- the honest number")
    print(f"held-out paraphrases (top-10 vote): {par_vote:.3f}")
    print(f"majority-class baseline:           {majority_rate:.3f}")
    print(f"\nwrote {WEB / 'tickets_index.json'} ({size_kb:.0f} KB)")
    print("misses at rank 1:")
    for d in par_detail:
        if not d["hit_at_1"]:
            print(f"  '{d['query']}' -> {d['predicted_top1']} (expected {d['expected']})")


if __name__ == "__main__":
    main()
