"""Service tickets with templated free-text engineer notes.

The notes are deliberately INCONSISTENT — abbreviations, shorthand, mixed
casing ("He level low" / "helium lvl dropping" / "cryo issue") — because that
inconsistency is precisely what motivates an NLP/RAG layer over service text.

Leakage trap #2 lives here: these notes are written AFTER the failure and
describe it. They may feed a retrieval assistant, but must never feed the
failure classifier's feature windows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .degradation import MachineHistory

SYMPTOMS = {
    "CRYO": ["He level low", "helium lvl dropping fast", "cryo issue reported by site",
             "compressor running hot", "boil-off rate above spec"],
    "GRAD": ["gradient temp unstable", "grad coil overheating", "image artifacts, grad noise",
             "coil cooling loop pressure low"],
    "RF": ["rf power fluctuating", "RF amp fault intermittent", "SNR degraded, rf suspected"],
    "TUBE": ["arcing events increasing", "tube current unstable", "tube nearing EOL",
             "spits observed during exposure", "xray tube arc warnings"],
    "DET": ["detector noise high", "det module dropout", "image noise complaint from site"],
    "GANTRY": ["gantry vibration high", "bearing noise during rotation", "rotation speed unstable"],
    "PWR": ["voltage ripple above limit", "generator output unstable", "power fluctuation at site"],
}

ACTIONS = {
    "CRYO": ["replaced cold head assembly", "swapped compressor adsorber", "recharged helium + new seal kit"],
    "GRAD": ["replaced gradient amplifier board", "flushed coil cooling loop"],
    "RF": ["swapped RF amplifier module", "replaced RF fuse set, recal ok"],
    "TUBE": ["tube replaced, recalibrated", "new HV cable set + oil cooling unit", "tube insert swap done"],
    "DET": ["replaced detector module", "DAS board swap, pixel map redone"],
    "GANTRY": ["main bearing replaced", "slip ring brushes swapped, cleaned"],
    "PWR": ["HV generator board replaced", "capacitor bank swapped"],
}

CLOSERS = ["system back to spec.", "QA passed, released to clinical use.", "site confirmed ok.",
           "monitoring for 48h.", "customer informed."]

PM_NOTES = ["routine PM done, all checks passed", "preventive maint completed, minor adjustments",
            "PM visit - filters, cal check, no issues", "scheduled service done. nothing abnormal"]

NFF_NOTES = ["site reported alerts, no fault found on inspection", "checked logs, values back in range. NFF",
             "intermittent drift, could not reproduce. monitoring", "no fault found, sensor recal done as precaution"]


def build_tickets(
    machine: dict,
    hist: MachineHistory,
    dates: pd.DatetimeIndex,
    modality_cfg: dict,
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows = []
    mid = machine["machine_id"]
    engineers = machine["engineer_pool"]

    def note_variant(text: str) -> str:
        # Roughen the text: random casing and occasional trailing shorthand.
        if rng.random() < 0.3:
            text = text.lower()
        if rng.random() < 0.2:
            text += " (esc L2)" if rng.random() < 0.5 else " ref prev tkt"
        return text

    # Corrective tickets: one per failure.
    for day_idx, comp, sudden, downtime in hist.failures:
        fam = machine["warn_family_by_component"][comp]
        part = rng.choice(modality_cfg["components"][comp]["parts"])
        symptom = note_variant(rng.choice(SYMPTOMS[fam]))
        action = note_variant(rng.choice(ACTIONS[fam]))
        note = f"{symptom}. {action}. {rng.choice(CLOSERS)}"
        if sudden:
            note = f"sudden failure, no prior alerts. {note}"
        rows.append(
            {
                "machine_id": mid,
                "open_date": dates[day_idx],
                "close_date": dates[min(day_idx + downtime, len(dates) - 1)],
                "ticket_type": "corrective",
                "component": comp,
                "part_replaced": part,
                "engineer_id": rng.choice(engineers),
                "downtime_days": downtime,
                "note_text": note,
            }
        )

    # Preventive-maintenance tickets.
    for day_idx, mtype, _comp in hist.maintenance:
        if mtype != "scheduled" or day_idx >= len(dates):
            continue
        rows.append(
            {
                "machine_id": mid,
                "open_date": dates[day_idx],
                "close_date": dates[day_idx],
                "ticket_type": "preventive",
                "component": None,
                "part_replaced": None,
                "engineer_id": rng.choice(engineers),
                "downtime_days": 0,
                "note_text": note_variant(rng.choice(PM_NOTES)),
            }
        )

    # No-fault-found tickets from ~half of the false-precursor episodes.
    for start, end, comp in hist.false_episodes:
        if rng.random() < 0.5 and end < len(dates):
            rows.append(
                {
                    "machine_id": mid,
                    "open_date": dates[end],
                    "close_date": dates[end],
                    "ticket_type": "no_fault_found",
                    "component": comp,
                    "part_replaced": None,
                    "engineer_id": rng.choice(engineers),
                    "downtime_days": 0,
                    "note_text": note_variant(rng.choice(NFF_NOTES)),
                }
            )

    return pd.DataFrame(rows)
