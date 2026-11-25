"""Render the README charts (light + dark SVG) from results/*.json.

    uv run --with matplotlib python tools/make_charts.py

Palette: the dataviz reference palette, validated for both modes (blue/orange pass CVD and
contrast checks). Static images, so every value that matters is printed on the chart.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES, OUT = ROOT / "results", ROOT / "assets" / "charts"
THEMES = {
    "light": {"bg": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#e4e3df",
              "blue": "#2a78d6", "orange": "#eb6834", "muted": "#b9b8b2"},
    "dark": {"bg": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "grid": "#383835",
             "blue": "#3987e5", "orange": "#d95926", "muted": "#5c5b56"},
}
plt.rcParams.update({"font.family": ["Inter", "Helvetica Neue", "Arial", "sans-serif"],
                     "font.size": 11, "svg.fonttype": "none"})


def load(p):
    return json.loads((RES / p).read_text())


def frame(ax, t):
    ax.set_facecolor(t["bg"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(colors=t["ink2"], length=0)
    ax.grid(axis="x", color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name, t_name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}-{t_name}.svg", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def experiments(tn, t):
    names = ["baseline", "consumer_kills", "duplicates_and_reordering", "poison_messages",
             "postgres_outage", "broker_restart", "slow_sink_backpressure"]
    label = {"baseline": "Baseline", "consumer_kills": "6 consumer SIGKILLs",
             "duplicates_and_reordering": "10% duplicates + reordering",
             "poison_messages": "1% poison messages", "postgres_outage": "Postgres frozen 45 s",
             "broker_restart": "Broker restart", "slow_sink_backpressure": "Slow sink (backpressure)"}
    rows = [load(f"experiments/{n}.json") for n in names][::-1]
    fig, ax = plt.subplots(figsize=(8.6, 3.9), facecolor=t["bg"])
    frame(ax, t)
    ys = range(len(rows))
    vals = [r["seconds_to_caught_up"] for r in rows]
    ax.barh(list(ys), vals, height=0.56, color=t["blue"], edgecolor=t["bg"], linewidth=2)
    for y, r in zip(ys, rows):
        rec = r["reconcile"]
        if rec["exact_match"]:
            note = "matches batch exactly"
        else:
            note = f"matches batch except the {r['producer']['poison']:,} replaced"
        ax.text(r["seconds_to_caught_up"] + 1.5, y, f"{r['seconds_to_caught_up']:.0f} s  ·  {note}",
                va="center", color=t["ink"], fontsize=10)
    ax.set_yticks(list(ys), [label[n] for n in names][::-1], color=t["ink"])
    ax.set_xlim(0, max(vals) * 2.05)
    ax.set_xlabel("Seconds until the consumer group caught up (150,701 messages, 4,000/s)",
                  color=t["ink2"])
    ax.set_title("Every fault, same answer as the batch path", loc="left", color=t["ink"],
                 fontsize=13, fontweight="bold", pad=12)
    save(fig, "experiments", tn)


def indexes(tn, t):
    pg = load("bench/pg_serving.json")
    win = load("bench/pg_window_query.json")
    q = [("repo_history", "One repo's history"), ("repo_by_name", "Lookup by owner/name"),
         ("daily_top_stars", "Daily top 20 by stars")]
    rows = [(lab, pg["pk_only"]["queries"][k]["p50_ms"], pg["with_indexes"]["queries"][k]["p50_ms"])
            for k, lab in q]
    rows.append(("7-day top 20 by merges", win["A_default"]["p50_ms"], win["C_partial_index"]["p50_ms"]))
    rows = rows[::-1]
    fig, ax = plt.subplots(figsize=(8.6, 3.4), facecolor=t["bg"])
    frame(ax, t)
    h = 0.34
    for i, (lab, a, b) in enumerate(rows):
        ax.barh(i + h / 2 + 0.02, a, height=h, color=t["orange"], edgecolor=t["bg"], linewidth=2)
        ax.barh(i - h / 2 - 0.02, b, height=h, color=t["blue"], edgecolor=t["bg"], linewidth=2)
        ax.text(a * 1.12, i + h / 2 + 0.02, f"{a:,.1f} ms", va="center", color=t["ink"], fontsize=9.5)
        ax.text(b * 1.12, i - h / 2 - 0.02, f"{b:,.2f} ms", va="center", color=t["ink"], fontsize=9.5)
    ax.set_xscale("log")
    ax.set_xlim(0.2, 4000)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], color=t["ink"])
    ax.set_xlabel("p50 latency (log scale), 300 calls per query (100 for the 7-day query)", color=t["ink2"])
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=t["orange"], label="Primary key only"),
                       Patch(color=t["blue"], label="Access-pattern index (partial covering index for 7-day)")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False,
              labelcolor=t["ink"], fontsize=9.5, borderaxespad=0.3)
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    ax.xaxis.set_major_locator(FixedLocator([1, 10, 100, 1000]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f} ms"))
    ax.set_title("Postgres serving queries, before and after indexing", loc="left", color=t["ink"],
                 fontsize=13, fontweight="bold", pad=30)
    save(fig, "indexes", tn)


def archive(tn, t):
    d = load("runs/archive-sizes.json")["bytes"]
    ks = list(d)
    # real time axis: months since Jan 2024, so uneven sampling shows as uneven spacing
    x = [(int(k[:4]) - 2024) * 12 + int(k[5:]) - 1 for k in ks]
    mb = [d[k] / 1e6 for k in ks]
    fig, ax = plt.subplots(figsize=(8.6, 3.2), facecolor=t["bg"])
    frame(ax, t)
    ax.grid(axis="y", color=t["grid"], linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.plot(x, mb, color=t["blue"], linewidth=2)
    ax.scatter(x, mb, s=40, color=t["blue"], edgecolors=t["bg"], linewidths=2, zorder=3)
    change = (2025 - 2024) * 12 + 9 + 6 / 31  # 7 Oct 2025
    ax.axvline(change, color=t["ink2"], linewidth=1, linestyle=(0, (3, 3)))
    ax.text(change + 0.4, max(mb) * 0.98, "GitHub trims Events API\npayloads (7 Oct 2025)",
            color=t["ink2"], fontsize=9.5, va="top")
    for k, dx in (("2025-05", 0), ("2026-11", -18)):
        i = ks.index(k)
        ax.annotate(f"{d[k] / 1e6:.1f} MB", (x[i], d[k] / 1e6), xytext=(dx, 10), textcoords="offset points",
                    ha="center", color=t["ink"], fontsize=9.5)
    ticks = [(y - 2024) * 12 + m - 1 for y in (2024, 2025, 2026) for m in (1, 7)]
    labels = [f"{['Jan', 'Jul'][j % 2]} {2024 + j // 2}" for j in range(6)]
    ax.set_xticks(ticks, labels, color=t["ink2"], fontsize=9.5)
    ax.set_xlim(4, 36)
    ax.set_ylabel("MB per hourly file", color=t["ink2"])
    ax.set_ylim(0, max(mb) * 1.15)
    ax.set_title("GH Archive hourly file size (15:00 UTC on the 15th, sampled months)", loc="left",
                 color=t["ink"], fontsize=13, fontweight="bold", pad=12)
    save(fig, "archive-size", tn)


def ml(tn, t):
    r = load("ml/volume-monitor.json")
    b = r["test"]["baselines_mae_log"]
    rows = [("Same hour yesterday", b["same_hour_yesterday"], False),
            ("Gradient boosting (level)", r["test"]["model_mae_log"], False),
            ("Trailing 24 h median", b["trailing_24h_median"], False),
            ("Boosting on change + conformal", r["delta_variants"]["delta_hgb_conformal"]["test_mae_log"], False),
            ("Persistence + conformal (champion)", r["delta_variants"]["persistence_conformal"]["test_mae_log"], True)]
    fig, ax = plt.subplots(figsize=(8.6, 3.0), facecolor=t["bg"])
    frame(ax, t)
    for i, (lab, v, champ) in enumerate(rows):
        ax.barh(i, v, height=0.56, color=t["blue"] if champ else t["muted"], edgecolor=t["bg"], linewidth=2)
        ax.text(v + 0.01, i, f"{v:.3f}", va="center", color=t["ink"], fontsize=10)
    ax.set_yticks(range(len(rows)), [x[0] for x in rows], color=t["ink"])
    ax.set_xlim(0, 0.6)
    ax.set_xlabel("Test MAE on log(events), 111 held-out hours (lower is better)", color=t["ink2"])
    ax.set_title("The simplest model won", loc="left", color=t["ink"], fontsize=13,
                 fontweight="bold", pad=12)
    save(fig, "ml", tn)


for tn, t in THEMES.items():
    for fn in (experiments, indexes, archive, ml):
        fn(tn, t)
print("ok", sorted(p.name for p in OUT.glob("*.svg")))
