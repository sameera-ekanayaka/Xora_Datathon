"""Shared loading, styling and small helpers for the Streamlit pages."""

import sys
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
MODELS = ROOT / "models"
sys.path.insert(0, str(ROOT / "src"))

from xora import decisions as dl  # noqa: E402

BLUE, ORANGE, GREEN, AMBER, PINK = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
INK, SOFT, GRID = "#141413", "#5b5a55", "#e4e3df"
LIGHT_FILL = {"red": "#f9dcd8", "amber": "#fcebc6", "green": "#dcf2e7"}
LIGHT_INK = {"red": "#b03030", "amber": "#8a5d00", "green": "#11805a"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stCaption, button, input, label, p, div {font-family: 'Inter', sans-serif;}
.block-container {padding-top: 3.6rem; max-width: 1400px;}
.tile {background: #fff; border: 1px solid #e3e0d8; border-radius: 14px; padding: 0.9rem 1.1rem;}
.tile .l {font-size: 0.85rem; color: #5b5a55;}
.tile .v {font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.2;}
.tile .n {font-size: 0.82rem; color: #8c8a83;}
h1 {font-weight: 800; letter-spacing: -0.02em;}
.kicker {font-size: 0.8rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #8c8a83; margin-bottom: 0.2rem;}
.card {background: #fff; border: 1px solid #e3e0d8; border-radius: 14px; padding: 1rem 1.2rem; min-height: 12.5rem; margin-bottom: 0.4rem;}
.card h4 {margin: 0 0 0.3rem 0; font-size: 1.05rem;}
.card p {margin: 0; color: #5b5a55; font-size: 0.95rem; line-height: 1.45;}
.pill {display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-weight: 700; font-size: 0.78rem;
       letter-spacing: 0.05em; text-transform: uppercase;}
.msg {background: #f0f6fd; border: 1px solid #d6e5f7; border-radius: 14px; padding: 0.8rem 1rem; margin-bottom: 0.6rem;}
div[data-testid="stMetricValue"] {font-weight: 800;}
</style>
"""


def page(title: str, kicker: str, intro: str = "") -> None:
    st.set_page_config(page_title=f"Xora | {title}", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="kicker">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if intro:
        st.caption(intro)


def tiles(items) -> None:
    """A row of stat tiles: (label, value, note, colour)."""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value, note, colour = (list(item) + [None, None])[:4]
        col.markdown(f'<div class="tile"><div class="l">{label}</div><div class="v" style="color:{colour or INK}">{value}</div>'
                     f'<div class="n">{note or "&nbsp;"}</div></div>', unsafe_allow_html=True)


def pill(light: str) -> str:
    return f'<span class="pill" style="background:{LIGHT_FILL[light]};color:{LIGHT_INK[light]}">{light}</span>'


def paint(df: pd.DataFrame, col: str = "light"):
    """Colour each row by its traffic light."""
    return df.style.apply(lambda r: [f"background-color: {LIGHT_FILL.get(r[col], '')}"] * len(r), axis=1)


def plotly_layout(fig, height=380):
    titled = bool(fig.layout.title.text)
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=90 if titled else 40, b=10), paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(family="Inter, sans-serif", color=INK), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      hoverlabel=dict(bgcolor="white"))
    if titled:
        fig.update_layout(title=dict(y=0.97, yanchor="top"))
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


@st.cache_data
def load(name: str) -> pd.DataFrame:
    path = DATA / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.read_csv(DATA / f"{name}.csv")


@st.cache_resource
def model(name: str):
    return joblib.load(MODELS / name)


@st.cache_data
def manifest() -> dict:
    import json
    return json.loads((MODELS / "manifest.json").read_text())


clock = dl.clock
