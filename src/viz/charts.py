# src/viz/charts.py
"""
Plotly time-series chart: CDI (bar) + SPI-3m (line) for last 52 weeks.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_timeseries(historic_df: pd.DataFrame, region_id: int) -> go.Figure:
    region = historic_df[historic_df["drought_region_id"] == region_id].copy()
    region = region.sort_values("measured_at").tail(52)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=region["measured_at"],
            y=region["cdi"],
            name="CDI",
            marker_color=[
                {0: "#2ecc71", 1: "#f1c40f", 2: "#e67e22",
                 3: "#e74c3c", 4: "#8e44ad", 5: "#2c3e50"}.get(int(v), "#cccccc")
                for v in region["cdi"].fillna(0)
            ],
            opacity=0.8,
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=region["measured_at"],
            y=region["spi_3m"],
            name="SPI-3m",
            line=dict(color="#3498db", width=2),
            mode="lines",
        ),
        secondary_y=True,
    )

    fig.add_hline(y=-0.84, line_dash="dot", line_color="orange",
                  annotation_text="SPI-3m Schwelle (-0.84)", secondary_y=True)
    fig.add_hline(y=2, line_dash="dot", line_color="red",
                  annotation_text="CDI Schwelle (2)", secondary_y=False)

    fig.update_layout(
        title="Trockenheitsentwicklung - letzte 52 Wochen",
        xaxis_title="Datum",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=350,
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font_color="#c9d1d9",
    )
    fig.update_yaxes(title_text="CDI (0-5)", secondary_y=False, range=[0, 5.5])
    fig.update_yaxes(title_text="SPI-3m", secondary_y=True)

    return fig
