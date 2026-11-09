"""F1 race analytics dashboard: a one-page overview of the five questions, read from DuckDB.

Layout: headline cards with per-round sparklines, auto-written insights, then a bento grid of
charts, and the full tables under "Explore the data". Run with `make dashboard` after
`make gold`. Colours come from .streamlit/config.toml (the reference data-viz palette), so
light and dark mode each get their own validated steps.
"""

from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

WAREHOUSE = Path(os.environ.get("F1_DATA_DIR", "data")) / "gold" / "warehouse.duckdb"
TOP_DRIVERS = 6  # Lines on one chart stay readable up to about six.
SESSION_LABELS = {"race": "Grands prix", "sprint": "Sprints"}

st.set_page_config(page_title="F1 race analytics", page_icon="🏁", layout="wide")


@st.cache_data
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run one read-only query. Cached, because the marts only change when `make gold` runs."""
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return con.execute(sql, list(params)).df()


# Recessive axes: no domain line or ticks, light dashed grid, so the marks carry the chart.
QUIET_X = {"domain": False, "ticks": False, "grid": False, "labelPadding": 6}
QUIET_Y = {"domain": False, "ticks": False, "gridDash": [2, 3], "labelPadding": 6}
# Vega lays labels out to the chart edge; the card's rounded border then clips them.
PAD = {"left": 16, "right": 12, "top": 4, "bottom": 4}


def card(title: str, subtitle: str | None = None):
    """A bordered bento card with a title. Use as a context manager."""
    box = st.container(border=True)
    box.markdown(f"**{title}**")
    if subtitle:
        box.caption(subtitle)
    return box


def hbar(data: pd.DataFrame, value: str, label: str, tooltip: list) -> alt.Chart:
    """Horizontal bars, largest first, one hue: the axis label carries identity."""
    return (
        alt.Chart(data)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(**QUIET_Y, tickMinStep=1)),
            y=alt.Y(
                f"{label}:N",
                sort="-x",
                title=None,
                scale=alt.Scale(paddingInner=0.3),
                axis=alt.Axis(**QUIET_X, labelLimit=180, labelOverlap=False),
            ),
            tooltip=tooltip,
        )
        .properties(height=alt.Step(26), padding=PAD)
    )


def per_round(data: pd.DataFrame, value: str, tooltip: list) -> alt.Chart:
    """Vertical bars by round number; the race name lives in the tooltip."""
    return (
        alt.Chart(data)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("round:O", title="Round", axis=alt.Axis(**QUIET_X, labelAngle=0)),
            y=alt.Y(f"{value}:Q", title=None, axis=alt.Axis(**QUIET_Y, tickMinStep=1)),
            tooltip=tooltip,
        )
        .properties(height=220, padding=PAD)
    )


def per_race_delta(current: pd.Series, previous: pd.Series) -> str | None:
    """Change in the per-race average against last season, e.g. '+0.4'."""
    if previous.empty or current.empty:
        return None
    return f"{current.mean() - previous.mean():+.1f}"


if not WAREHOUSE.exists():
    st.error(f"No warehouse at {WAREHOUSE}. Run `make gold` first.")
    st.stop()

# --- Header and filters ---------------------------------------------------------------------

seasons = query("select distinct season from mart_race_winners order by season")["season"].tolist()
head, controls = st.columns([3, 2], vertical_alignment="bottom")
with controls:
    picked = st.segmented_control("Season", seasons, default=seasons[-1], key="season")
    picked_session = st.segmented_control(
        "Sessions",
        list(SESSION_LABELS),
        default="race",
        format_func=SESSION_LABELS.get,
        key="session",
    )
# A segmented control can be clicked off; fall back to the defaults rather than show nothing.
season = int(picked or seasons[-1])
session = picked_session or "race"

crashes = query(
    "select * from mart_race_crashes where season = ? and session_type = ? order by round",
    (season, session),
)
previous = query(
    "select * from mart_race_crashes where season = ? and session_type = ? order by round",
    (season - 1, session),
)
winners = query(
    "select * from mart_race_winners where season = ? and session_type = ? order by round",
    (season, session),
)
penalties = query(
    "select * from mart_penalties where season = ? and session_type = ? order by round",
    (season, session),
)
prev_penalties = query(
    "select count(*) as n from mart_penalties where season = ? and session_type = ?",
    (season - 1, session),
)["n"].iloc[0]
standings = query(
    "select round, competitor_name as driver, points, position, wins from "
    "mart_championship_progression where season = ? and championship = 'drivers' order by round",
    (season,),
)
last_round = int(standings["round"].max())

with head:
    st.title("F1 race analytics")
    st.badge(f"{season} · after round {last_round}", icon=":material/flag:", color="blue")
    st.caption(
        "Winners, crashes, time lost, leaders and penalties. Data: Jolpica F1 API and OpenF1 "
        "(not affiliated with Formula 1). Definitions in docs/metrics.md."
    )

# --- Headline cards --------------------------------------------------------------------------

penalties_per_round = (
    penalties.groupby("round").size().reindex(crashes["round"], fill_value=0).tolist()
)
compare = f"per race vs {season - 1}"
kpis = st.columns(5)
prev_winners = query(
    "select count(distinct driver_code) as n from mart_race_winners "
    "where season = ? and session_type = ?",
    (season - 1, session),
)["n"].iloc[0]
kpis[0].metric(
    "Rounds",
    len(winners),
    border=True,
    height="stretch",
    help="Races (or sprints) with results so far this season.",
)
kpis[1].metric(
    "Different winners",
    winners["driver_code"].nunique(),
    border=True,
    height="stretch",
    delta=int(winners["driver_code"].nunique() - prev_winners) if prev_winners else None,
    delta_color="off",
    delta_description=f"vs all of {season - 1}",
)
kpis[2].metric(
    "Crashes",
    int(crashes["crashes"].sum()),
    border=True,
    height="stretch",
    delta=per_race_delta(crashes["crashes"], previous["crashes"]),
    delta_color="inverse",
    delta_description=compare,
    chart_data=crashes["crashes"].tolist(),
    chart_type="bar",
)
kpis[3].metric(
    "Minutes lost to crashes",
    f"{crashes['time_lost_to_crashes_min'].sum():.0f}",
    border=True,
    height="stretch",
    delta=per_race_delta(crashes["time_lost_to_crashes_min"], previous["time_lost_to_crashes_min"]),
    delta_color="inverse",
    delta_description=compare,
    chart_data=crashes["time_lost_to_crashes_min"].tolist(),
    chart_type="area",
)
kpis[4].metric(
    "Penalties",
    len(penalties),
    border=True,
    height="stretch",
    delta=(
        f"{len(penalties) / max(len(crashes), 1) - prev_penalties / len(previous):+.1f}"
        if len(previous)
        else None
    ),
    delta_color="inverse",
    delta_description=compare,
    chart_data=penalties_per_round,
    chart_type="bar",
)

# --- Insights: the takeaway in words, so nobody has to read it off a chart -----------------------

final = standings[standings["round"] == last_round].sort_values("position")
laps = query(
    "select driver_name, sum(laps_led) as laps_led, sum(race_laps) as race_laps, "
    "count(*) as races_led from mart_lap_leaders where season = ? group by driver_name "
    "order by laps_led desc",
    (season,),
)
season_laps = query(
    "select sum(laps) as laps from (select distinct round, race_laps as laps "
    "from mart_lap_leaders where season = ?)",
    (season,),
)["laps"].iloc[0]

insights = st.columns(4)
if len(final) >= 2:
    lead, second = final.iloc[0], final.iloc[1]
    insights[0].info(
        f"**{lead['driver']}** leads the championship by **{lead['points'] - second['points']:.0f}"
        f" points** over {second['driver']}.",
        icon=":material/emoji_events:",
    )
if not crashes.empty:
    wild = crashes.sort_values(["crashes", "time_lost_to_crashes_min"], ascending=False).iloc[0]
    insights[1].info(
        f"Most chaotic: **{wild['race_name']}** with **{wild['crashes']} crashes** and "
        f"{wild['time_lost_to_crashes_min']:.0f} minutes neutralised.",
        icon=":material/warning:",
    )
if not laps.empty and season_laps:
    top = laps.iloc[0]
    insights[2].info(
        f"**{top['driver_name']}** led **{top['laps_led'] / season_laps:.0%}** of all grand prix "
        f"laps, in {top['races_led']} races.",
        icon=":material/speed:",
    )
if not penalties.empty:
    worst = penalties["driver_name"].value_counts()
    insights[3].info(
        f"Most penalised: **{worst.index[0]}** with **{worst.iloc[0]}** penalties "
        f"({SESSION_LABELS[session].lower()}).",
        icon=":material/gavel:",
    )

# --- Bento grid --------------------------------------------------------------------------------

left, right = st.columns([3, 2])
with left, card("Drivers' championship", f"Points after each round, top {TOP_DRIVERS}"):
    top = final.head(TOP_DRIVERS)["driver"].tolist()
    lines = standings[standings["driver"].isin(top)]
    # Colour follows the driver: the domain is the final order, so slots never shuffle.
    colour = alt.Color(
        "driver:N",
        scale=alt.Scale(domain=top),
        legend=alt.Legend(
            title=None,
            orient="top",
            symbolType="circle",
            columnPadding=18,
            labelLimit=200,
            columns=3,
        ),
    )
    base = alt.Chart(lines).encode(
        x=alt.X(
            "round:Q",
            title="Round",
            scale=alt.Scale(domain=[1, last_round], nice=False),
            axis=alt.Axis(**QUIET_X, tickMinStep=1),
        ),
        y=alt.Y("points:Q", title=None, axis=alt.Axis(**QUIET_Y)),
        color=colour,
    )
    hover = alt.selection_point(fields=["round"], nearest=True, on="pointerover", empty=False)
    st.altair_chart(
        alt.layer(
            base.mark_line(strokeWidth=2, interpolate="monotone"),
            base.mark_point(size=70, filled=True)
            .encode(
                opacity=alt.condition(hover, alt.value(1), alt.value(0)),
                tooltip=[
                    alt.Tooltip("driver:N", title="Driver"),
                    alt.Tooltip("round:Q", title="Round"),
                    alt.Tooltip("points:Q", title="Points"),
                    alt.Tooltip("position:Q", title="Position"),
                ],
            )
            .add_params(hover),
            alt.Chart(lines).mark_rule(opacity=0.25).encode(x="round:Q").transform_filter(hover),
            # Left padding keeps three-digit y labels from being clipped by the card edge.
        ).properties(height=330, padding=PAD),
        width="stretch",
    )

with right, card("Standings", f"After round {last_round}"):
    st.dataframe(
        final[["position", "driver", "points"]].head(10),
        hide_index=True,
        width="stretch",
        column_config={
            "position": st.column_config.NumberColumn("Pos", width="small"),
            "driver": st.column_config.TextColumn("Driver", width="medium"),
            "points": st.column_config.ProgressColumn(
                "Points",
                format="%d",
                min_value=0,
                max_value=float(final["points"].max()),
                width="medium",
            ),
        },
    )

tip = [
    alt.Tooltip("race_name:N", title="Race"),
    alt.Tooltip("crashes:Q", title="Crashes"),
    alt.Tooltip("collisions:Q", title="Collisions"),
    alt.Tooltip("stopped_cars:Q", title="Stopped cars"),
    alt.Tooltip("safety_cars:Q", title="Safety Cars"),
    alt.Tooltip("virtual_safety_cars:Q", title="VSCs"),
    alt.Tooltip("red_flags:Q", title="Red flags"),
    alt.Tooltip("time_lost_to_crashes_min:Q", title="Minutes lost", format=".1f"),
]
# Two charts, not one with two y-axes: counts and minutes have different scales.
c1, c2 = st.columns(2)
with (
    c1,
    card(
        "Crashes per round",
        "Collisions noted by race control, plus cars that stopped "
        "and brought out a Safety Car, VSC or red flag",
    ),
):
    st.altair_chart(per_round(crashes, "crashes", tip), width="stretch")
with c2, card("Minutes lost to crashes", "Safety Car, VSC and red-flag time caused by a crash"):
    st.altair_chart(per_round(crashes, "time_lost_to_crashes_min", tip), width="stretch")

col_wins, col_laps, col_pens = st.columns(3)
with col_wins, card("Wins", SESSION_LABELS[session]):
    wins = winners.groupby("driver_name", as_index=False).agg(wins=("round", "count"))
    st.altair_chart(
        hbar(
            wins,
            "wins",
            "driver_name",
            [alt.Tooltip("driver_name:N", title="Driver"), alt.Tooltip("wins:Q", title="Wins")],
        ),
        width="stretch",
    )
with col_laps, card("Laps led", "Grands prix only"):
    st.altair_chart(
        hbar(
            laps.head(8),
            "laps_led",
            "driver_name",
            [
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("laps_led:Q", title="Laps led"),
                alt.Tooltip("races_led:Q", title="Races with a lap led"),
            ],
        ),
        width="stretch",
    )
with col_pens, card("Penalties", "Most penalised drivers"):
    per_driver = (
        penalties.groupby("driver_name", as_index=False)
        .agg(penalties=("penalty_type", "count"), seconds=("penalty_seconds", "sum"))
        .sort_values("penalties", ascending=False)
        .head(8)
    )
    st.altair_chart(
        hbar(
            per_driver,
            "penalties",
            "driver_name",
            [
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("penalties:Q", title="Penalties"),
                alt.Tooltip("seconds:Q", title="Seconds added"),
            ],
        ),
        width="stretch",
    )

# --- The tables behind every chart --------------------------------------------------------------

st.subheader("Explore the data")
t_win, t_crash, t_periods, t_pen = st.tabs(
    ["Winners", "Crashes by round", "Safety Cars and red flags", "Penalties"]
)
with t_win:
    st.dataframe(
        winners.assign(margin_s=winners["margin_to_second_ms"] / 1000)[
            ["round", "race_name", "driver_name", "constructor_name", "grid", "margin_s"]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "round": "Round",
            "race_name": "Race",
            "driver_name": "Winner",
            "constructor_name": "Team",
            "grid": "Started",
            "margin_s": st.column_config.NumberColumn("Margin to 2nd (s)", format="%.3f"),
        },
    )
with t_crash:
    st.dataframe(
        crashes.drop(columns=["season", "session_type", "session_key"]),
        hide_index=True,
        width="stretch",
    )
with t_periods:
    st.dataframe(
        query(
            "select round, race_name, period_type, start_lap, end_lap, duration_min, cause "
            "from mart_neutralised_time where season = ? and session_type = ? "
            "order by round, started_at",
            (season, session),
        ),
        hide_index=True,
        width="stretch",
    )
with t_pen:
    st.dataframe(
        penalties[
            [
                "round",
                "race_name",
                "driver_name",
                "penalty_type",
                "penalty_seconds",
                "reason",
                "lap_number",
            ]
        ],
        hide_index=True,
        width="stretch",
    )
