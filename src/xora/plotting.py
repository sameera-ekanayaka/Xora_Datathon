"""One consistent chart style for every notebook and the video.

Colours follow a fixed categorical order so a series keeps its colour across
charts (Peliyagoda is always slot 1, Kandy slot 2, and so on).
"""

import matplotlib.pyplot as plt

# Categorical slots, used in this order and never cycled
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


def apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_SOFT,
        "axes.titlecolor": INK,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "lines.linewidth": 2,
        "legend.frameon": False,
        "figure.dpi": 110,
        "axes.prop_cycle": plt.cycler(color=SERIES),
    })
