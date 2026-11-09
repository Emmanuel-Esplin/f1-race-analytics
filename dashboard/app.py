"""F1 race analytics dashboard: one tab per question, read from the DuckDB marts.

Run with `make dashboard` after `make gold`.
"""

from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

WAREHOUSE = Path(os.environ.get("F1_DATA_DIR", "data")) / "gold" / "warehouse.duckdb"

# Reference data-viz palette. One-series charts use slot 1; categorical slots keep this order,
# which is what keeps adjacent colours apart for colour-blind readers.
SERIES_1 = "#2a78d6"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
TOP_DRIVERS = len(CATEGORICAL)

st.set_page_config(page_title="F1 race analytics", page_icon="🏁", layout="wide")


@st.cache_data
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run one read-only query. Cached, because the marts only change when `make gold` runs."""
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return con.execute(sql, list(params)).df()


def bar(data: pd.DataFrame, value: str, label: str, title: str, tooltip: list) -> alt.Chart:
    """Horizontal bars, largest first, one hue: identity comes from the axis label."""
    return (
        alt.Chart(data, title=title)
        .mark_bar(color=SERIES_1, cornerRadiusEnd=4)
        .encode(
            x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(grid=True, tickMinStep=1)),
            # Every name shown in full: no overlap pruning, room for long names.
            y=alt.Y(
                f"{label}:N",
                sort="-x",
                title=None,
                scale=alt.Scale(paddingInner=0.25),
                axis=alt.Axis(labelLimit=220, labelOverlap=False),
            ),
            tooltip=tooltip,
        )
        .properties(height=alt.Step(30))
    )


def table(data: pd.DataFrame) -> None:
    """The same numbers as the chart, for screen readers and exact values."""
    with st.expander("Show as table"):
        st.dataframe(data, hide_index=True, width="stretch")


if not WAREHOUSE.exists():
    st.error(f"No warehouse at {WAREHOUSE}. Run `make gold` first.")
    st.stop()

st.title("F1 race analytics")
st.caption(
    "Data: Jolpica F1 API and OpenF1, not affiliated with Formula 1. "
    "Definitions: docs/metrics.md in the repo."
)

seasons = query("select distinct season from mart_race_winners order by season desc")["season"]
left, right, _ = st.columns([1, 1, 3])
season = int(left.selectbox("Season", seasons))
session = right.radio(
    "Sessions",
    ["race", "sprint"],
    horizontal=True,
    format_func=lambda s: {"race": "Grands prix", "sprint": "Sprints"}[s],
)

crashes = query(
    "select * from mart_race_crashes where season = ? and session_type = ? order by round",
    (season, session),
)
winners = query(
    "select * from mart_race_winners where season = ? and session_type = ? order by round",
    (season, session),
)
penalties = query(
    "select * from mart_penalties where season = ? and session_type = ? order by round",
    (season, session),
)

tiles = st.columns(5)
tiles[0].metric("Rounds", len(winners))
tiles[1].metric("Different winners", winners["driver_code"].nunique())
tiles[2].metric("Crashes", int(crashes["crashes"].sum()))
tiles[3].metric("Minutes lost to crashes", f"{crashes['time_lost_to_crashes_min'].sum():.0f}")
tiles[4].metric("Penalties", len(penalties))

tab_win, tab_crash, tab_lead, tab_pen = st.tabs(
    ["Winners", "Crashes and time lost", "Who is leading", "Penalties"]
)

with tab_win:
    wins = (
        winners.groupby(["driver_code", "driver_name"], as_index=False)
        .agg(wins=("round", "count"))
        .sort_values("wins", ascending=False)
    )
    st.altair_chart(
        bar(
            wins,
            "wins",
            "driver_name",
            "Wins per driver",
            [alt.Tooltip("driver_name:N", title="Driver"), alt.Tooltip("wins:Q", title="Wins")],
        ),
        width="stretch",
    )
    shown = (
        winners[
            ["round", "race_name", "driver_name", "constructor_name", "grid", "margin_to_second_ms"]
        ]
        .assign(margin_s=lambda d: (d["margin_to_second_ms"] / 1000).round(3))
        .drop(columns="margin_to_second_ms")
    )
    st.subheader("Every winner")
    st.dataframe(
        shown.rename(
            columns={
                "race_name": "race",
                "driver_name": "winner",
                "constructor_name": "team",
                "grid": "started",
                "margin_s": "margin to 2nd (s)",
            }
        ),
        hide_index=True,
        width="stretch",
    )

with tab_crash:
    st.caption(
        "A crash is a collision noted by race control, or a car that stopped as a Safety Car, "
        "VSC or red flag came out. Time lost is the minutes those periods lasted."
    )
    rounds = crashes.assign(race=lambda d: d["round"].astype(str) + " · " + d["race_name"])
    tip = [
        alt.Tooltip("race:N", title="Round"),
        alt.Tooltip("crashes:Q", title="Crashes"),
        alt.Tooltip("collisions:Q", title="Collisions"),
        alt.Tooltip("stopped_cars:Q", title="Stopped cars"),
        alt.Tooltip("safety_cars:Q", title="Safety Cars"),
        alt.Tooltip("virtual_safety_cars:Q", title="VSCs"),
        alt.Tooltip("red_flags:Q", title="Red flags"),
        alt.Tooltip("time_lost_to_crashes_min:Q", title="Minutes lost", format=".1f"),
    ]

    def per_round(value: str, title: str) -> alt.Chart:
        return (
            alt.Chart(rounds, title=title)
            .mark_bar(color=SERIES_1, cornerRadiusEnd=4)
            .encode(
                # Round numbers fit without slanting; the race name is in the tooltip.
                x=alt.X("round:O", title="Round", axis=alt.Axis(labelAngle=0)),
                y=alt.Y(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                tooltip=tip,
            )
            .properties(height=260)
        )

    # Two charts, not one with two y-axes: counts and minutes have different scales.
    st.altair_chart(per_round("crashes", "Crashes per round"), width="stretch")
    st.altair_chart(
        per_round("time_lost_to_crashes_min", "Minutes neutralised by crashes, per round"),
        width="stretch",
    )
    table(rounds.drop(columns=["season", "session_type", "session_key", "race"]))

    periods = query(
        "select round, race_name, period_type, start_lap, end_lap, duration_min, cause "
        "from mart_neutralised_time where season = ? and session_type = ? "
        "order by round, started_at",
        (season, session),
    )
    st.subheader("Every Safety Car, VSC and red flag")
    st.dataframe(periods, hide_index=True, width="stretch")

with tab_lead:
    standings = query(
        "select round, competitor_name as driver, points, position from "
        "mart_championship_progression where season = ? and championship = 'drivers' "
        "order by round",
        (season,),
    )
    last_round = standings["round"].max()
    # Colour follows the driver: the top drivers by final standing get fixed slots, in order.
    top = (
        standings[standings["round"] == last_round]
        .sort_values("position")
        .head(TOP_DRIVERS)["driver"]
        .tolist()
    )
    lines = standings[standings["driver"].isin(top)]
    colour = alt.Color(
        "driver:N",
        scale=alt.Scale(domain=top, range=CATEGORICAL[: len(top)]),
        legend=alt.Legend(title=None, orient="top"),
    )
    base = alt.Chart(lines).encode(
        x=alt.X("round:Q", title="Round", axis=alt.Axis(tickMinStep=1)),
        y=alt.Y("points:Q", title="Points"),
        color=colour,
    )
    hover = alt.selection_point(fields=["round"], nearest=True, on="pointerover", empty=False)
    chart = alt.layer(
        base.mark_line(strokeWidth=2),
        base.mark_point(size=64, filled=True)
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
        alt.Chart(lines)
        .mark_rule(color="gray", opacity=0.4)
        .encode(x="round:Q")
        .transform_filter(hover),
    ).properties(title=f"Drivers' championship, top {len(top)}", height=360)
    st.altair_chart(chart, width="stretch")
    leader = standings[(standings["round"] == last_round) & (standings["position"] == 1)]
    st.markdown(
        f"**Leader after round {last_round}:** {leader['driver'].iloc[0]} "
        f"({leader['points'].iloc[0]:.0f} points)"
    )
    table(standings[standings["round"] == last_round].sort_values("position"))

    laps = query(
        "select driver_name, sum(laps_led) as laps_led, count(*) as races_led "
        "from mart_lap_leaders where season = ? group by driver_name order by laps_led desc",
        (season,),
    )
    st.altair_chart(
        bar(
            laps,
            "laps_led",
            "driver_name",
            "Laps led in grands prix",
            [
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("laps_led:Q", title="Laps led"),
                alt.Tooltip("races_led:Q", title="Races with a lap led"),
            ],
        ),
        width="stretch",
    )

with tab_pen:
    per_driver = (
        penalties.groupby("driver_name", as_index=False)
        .agg(penalties=("penalty_type", "count"), seconds=("penalty_seconds", "sum"))
        .sort_values("penalties", ascending=False)
    )
    st.altair_chart(
        bar(
            per_driver,
            "penalties",
            "driver_name",
            "Penalties per driver",
            [
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("penalties:Q", title="Penalties"),
                alt.Tooltip("seconds:Q", title="Seconds added"),
            ],
        ),
        width="stretch",
    )
    st.subheader("Every penalty")
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
