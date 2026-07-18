"""Generate the figures for reports/data-model-eda/ (run with ml/.venv python).

Usage:  cd fleet-pulse && ml/.venv/bin/python reports/data-model-eda/make_figures.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
IMG = Path(__file__).resolve().parent / "img"
IMG.mkdir(exist_ok=True)
RAW = REPO / "ml" / "data" / "raw"

plt.style.use(REPO / "design" / "fleetpulse.mplstyle")

TEAL = "#0E8A92"
TEAL_BRIGHT = "#17B9C0"
PETROL = "#08262B"
DEEP = "#0A4B52"
SLATE = "#5F8B92"
CRITICAL = "#D64545"
HEALTHY = "#1F9E78"
INK = "#0A2226"
INK_SOFT = "#47656B"
LINE = "#D7E4E4"

fleet = pd.read_parquet(RAW / "fleet_master.parquet")
tel = pd.read_parquet(RAW / "telemetry")
err = pd.read_parquet(RAW / "error_events.parquet")
fail = pd.read_parquet(RAW / "failures.parquet")
mnt = pd.read_parquet(RAW / "maintenance.parquet")
tkt = pd.read_parquet(RAW / "tickets.parquet")


# ---------------------------------------------------------------- fig 1: data model
def fig_data_model():
    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    ax.set_xlim(0, 118)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def box(x, y, w, h, title, lines, hub=False):
        face = PETROL if hub else "white"
        txt = "white" if hub else INK
        sub = TEAL_BRIGHT if hub else INK_SOFT
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=face, edgecolor=TEAL,
                                   linewidth=1.4, zorder=3, clip_on=False))
        ax.text(x + 2.4, y + h - 6, title, fontsize=11, fontweight="bold",
                color=txt, family="monospace", zorder=4, va="center")
        for i, ln in enumerate(lines):
            ax.text(x + 2.4, y + h - 10.2 - i * 4.4, ln, fontsize=7.8,
                    color=sub, family="monospace", zorder=4, va="center")

    # hub (dimension table)
    hub_x, hub_y, hub_w, hub_h = 3, 34, 32, 32
    box(hub_x, hub_y, hub_w, hub_h, "fleet_master",
        ["500 rows · 1 per machine", "PK  machine_id", "the asset register:",
         "modality, model, hospital,", "country, install_date"], hub=True)

    # spokes (event/fact tables): (title, rows-line, key-line, y-position)
    sp_x, sp_w, sp_h = 64, 38, 16.5
    spokes = [
        ("telemetry",    "1,041,129 · machine-day-sensor",  "PK (machine_id,date,sensor)",   81),
        ("error_events", "323,220 · one per emission",      "no PK · append-only log",       61.5),
        ("failures",     "440 · the GROUND TRUTH",          "PK (machine_id,date,component)", 42),
        ("maintenance",  "1,454 · one per visit",           "grain (machine_id,date,type)",  22.5),
        ("tickets",      "1,610 · one per ticket",          "no natural PK (see note)",       3),
    ]
    for title, rows_ln, key_ln, y in spokes:
        box(sp_x, y, sp_w, sp_h, title, [rows_ln, key_ln])
        ax.annotate("", xy=(hub_x + hub_w, hub_y + hub_h / 2),
                    xytext=(sp_x, y + sp_h / 2),
                    arrowprops=dict(arrowstyle="-|>", color=SLATE, lw=1.2,
                                    shrinkA=2, shrinkB=2,
                                    connectionstyle="arc3,rad=-0.06"), zorder=2)

    # edge label
    ax.text(49.5, 53.5, "N : 1 on machine_id", fontsize=8.6, color=SLATE,
            family="monospace", ha="center",
            bbox=dict(facecolor="white", edgecolor=LINE, pad=2.5), zorder=5)

    # soft link: corrective ticket ~ failure (clean vertical dashed line, right of boxes)
    link_x = sp_x + sp_w + 3
    ax.annotate("", xy=(link_x, 42 + sp_h / 2), xytext=(link_x, 3 + sp_h / 2),
                arrowprops=dict(arrowstyle="-|>", color=CRITICAL, lw=1.2,
                                linestyle="--", shrinkA=0, shrinkB=0), zorder=2)
    ax.plot([sp_x + sp_w, link_x], [42 + sp_h / 2, 42 + sp_h / 2], color=CRITICAL, lw=1.2, ls="--", zorder=2)
    ax.plot([sp_x + sp_w, link_x], [3 + sp_h / 2, 3 + sp_h / 2], color=CRITICAL, lw=1.2, ls="--", zorder=2)
    ax.text(link_x + 2, 30, "corrective ticket\n≈ failure\n(machine_id,\n open_date)",
            fontsize=7.8, color=CRITICAL, family="monospace", va="center", ha="left")

    ax.set_title("Fleet Pulse raw data model — star schema: one dimension, five event tables",
                 fontsize=12, color=INK, loc="left", pad=14)
    fig.savefig(IMG / "data_model.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------- fig 2: fleet composition
def fig_fleet_composition():
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))

    mod = fleet["modality"].value_counts()
    axes[0].bar(mod.index, mod.values, color=[TEAL, TEAL_BRIGHT, SLATE], width=0.62)
    for i, v in enumerate(mod.values):
        axes[0].text(i, v + 4, f"{v}", ha="center", fontsize=10, color=INK)
    axes[0].set_title("Fleet by modality (500 machines)", loc="left")
    axes[0].set_ylabel("machines")
    axes[0].set_ylim(0, 260)

    yr = fleet["install_date"].dt.year.value_counts().sort_index()
    axes[1].bar(yr.index.astype(str), yr.values, color=DEEP, width=0.7)
    axes[1].set_title("Install year — a mixed-age fleet (2015–2024)", loc="left")
    axes[1].set_ylabel("machines")
    axes[1].tick_params(axis="x", rotation=45)

    fig.tight_layout()
    fig.savefig(IMG / "fleet_composition.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------- fig 3: class balance + components
def fig_class_balance():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))

    f = fail.copy()
    f["week"] = f["failure_date"].dt.to_period("W")
    fweeks = f.drop_duplicates(["machine_id", "week"]).shape[0]
    total = 500 * 52
    clean = total - fweeks

    bars = axes[0].bar(["clean\nmachine-weeks", "failure\nmachine-weeks"],
                       [clean, fweeks], color=[SLATE, CRITICAL], width=0.55)
    axes[0].text(0, clean + 600, f"{clean:,}", ha="center", fontsize=10.5, color=INK)
    axes[0].text(1, fweeks + 600, f"{fweeks:,}  ({fweeks / total:.1%})",
                 ha="center", fontsize=10.5, color=CRITICAL, fontweight="bold")
    axes[0].set_title("Class balance — the number that shapes the ML problem", loc="left")
    axes[0].set_ylabel("machine-weeks (2025)")

    comp = fail["component"].value_counts().sort_values()
    axes[1].barh(comp.index, comp.values, color=TEAL, height=0.6)
    for i, v in enumerate(comp.values):
        axes[1].text(v + 2, i, f"{v}", va="center", fontsize=9.5, color=INK)
    axes[1].set_title("Failures by component (440 total)", loc="left")
    axes[1].set_xlabel("failures in 2025")
    axes[1].set_xlim(0, 225)

    fig.tight_layout()
    fig.savefig(IMG / "class_balance.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------- fig 4: telemetry signature
def fig_helium_drift():
    m = "FP-MRI-0001"
    s = tel[(tel["machine_id"] == m) & (tel["sensor"] == "helium_level")].sort_values("date")
    f_date = pd.Timestamp("2025-07-18")  # cold_head failure from failures.parquet

    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(s["date"], s["value"], color=TEAL, lw=1.3)
    ax.axvline(f_date, color=CRITICAL, ls="--", lw=1.3)
    ax.text(f_date, ax.get_ylim()[1], "  cold_head failure — 2025-07-18",
            color=CRITICAL, fontsize=9.5, va="top")
    ax.set_title(f"{m} — helium_level through 2025: slow boil-off drift, then repair reset", loc="left")
    ax.set_ylabel("helium level (%)")
    fig.tight_layout()
    fig.savefig(IMG / "helium_drift.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


fig_data_model()
fig_fleet_composition()
fig_class_balance()
fig_helium_drift()
print("wrote:", *sorted(p.name for p in IMG.glob("*.png")))
