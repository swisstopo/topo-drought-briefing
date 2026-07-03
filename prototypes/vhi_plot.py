"""
VHI — last 3 weeks + 7-day Fourier forecast, 4 regions.
Produces vhi_forecast_plot.png in the same directory.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import requests

# ── config ──────────────────────────────────────────────────────────────────
STAC_ITEMS    = ("https://data.geo.admin.ch/api/stac/v1/collections/"
                 "ch.swisstopo.swisseo_vhi_v100/items")
CSV_ASSET_KEY = "vegetation-warnregions.csv"
MAX_WORKERS   = 12
PAGE_LIMIT    = 100
MIN_AVAIL     = 20.0
HORIZON       = 7
SENTINEL_YEAR = 2017
N_HARMONICS   = 2
STD_WINDOW    = 21   # ± DOY window for historical σ band

REGIONS = [
    {"id": 31, "name": "Östlicher Jura"},
    {"id": 33, "name": "Unteres Emmental"},
    {"id": 35, "name": "Westliches Berner Oberland"},
    {"id": 42, "name": "Östliches Mittelland"},
]

OUT = Path(__file__).parent / "vhi_forecast_plot.png"

# ── STAC / download (same as v3) ─────────────────────────────────────────────
def fetch_all_stac_items():
    items, url = [], f"{STAC_ITEMS}?limit={PAGE_LIMIT}"
    while url:
        r = requests.get(url, timeout=30); r.raise_for_status()
        d = r.json()
        for feat in d.get("features", []):
            assets  = feat.get("assets", {})
            csv_url = next((v["href"] for k, v in assets.items()
                            if k.endswith(CSV_ASSET_KEY)), None)
            if csv_url:
                items.append({"date": feat["id"], "csv_url": csv_url})
        url = next((lk["href"] for lk in d.get("links", [])
                    if lk["rel"] == "next"), None)
    return items


def _dl(item, cache_dir):
    fname = cache_dir / f"{item['date']}.csv"
    if fname.exists(): return
    try:
        r = requests.get(item["csv_url"], timeout=20); r.raise_for_status()
        fname.write_bytes(r.content)
    except Exception: pass


def download_all(items, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    missing = [i for i in items if not (cache_dir / f"{i['date']}.csv").exists()]
    if not missing: return
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(as_completed({ex.submit(_dl, i, cache_dir): i for i in missing}))


def build_series(items, cache_dir, region_id):
    rows = []
    for item in items:
        fpath = cache_dir / f"{item['date']}.csv"
        if not fpath.exists(): continue
        try:
            df   = pd.read_csv(fpath)
            row  = df[df["REGION_NR"] == region_id]
            if row.empty: continue
            vhi  = float(row["vhi_mean"].iloc[0])
            avl  = float(row["availability_percentage"].iloc[0])
            date = pd.to_datetime(item["date"].split("t")[0])
            rows.append({"date": date, "vhi": vhi, "avail": avl})
        except Exception: continue
    ts = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    ts = ts[(ts["avail"] >= MIN_AVAIL) & (ts["vhi"] < 100)].copy()
    ts["doy"]  = ts["date"].dt.dayofyear
    ts["year"] = ts["date"].dt.year
    return ts


# ── Fourier climatology ──────────────────────────────────────────────────────
def _X(doy_arr, n=N_HARMONICS):
    cols = [np.ones(len(doy_arr))]
    for k in range(1, n + 1):
        cols += [np.cos(2*np.pi*k*doy_arr/365.0),
                 np.sin(2*np.pi*k*doy_arr/365.0)]
    return np.column_stack(cols)


def fit_climatology(ts):
    doy = ts["doy"].values.astype(float)
    vhi = ts["vhi"].values.astype(float)
    coeffs, *_ = np.linalg.lstsq(_X(doy), vhi, rcond=None)
    doy_grid = np.arange(1, 367, dtype=float)
    clim = np.full(367, np.nan)
    clim[1:] = _X(doy_grid) @ coeffs
    return clim, coeffs


def historical_std(ts, clim, window=STD_WINDOW):
    """Per-DOY standard deviation of anomalies, smoothed over ± window days."""
    ts = ts.copy()
    ts["anom"] = ts["vhi"] - ts["doy"].map(
        lambda d: float(clim[min(int(d), 366)]) if not np.isnan(clim[min(int(d), 366)]) else np.nan)
    std_arr = np.full(367, np.nan)
    for d in range(1, 367):
        lo = max(1, d - window); hi = min(366, d + window)
        sub = ts[(ts["doy"] >= lo) & (ts["doy"] <= hi)]["anom"].dropna()
        std_arr[d] = sub.std() if len(sub) >= 5 else np.nan
    # fill remaining nans with global std
    global_std = ts["anom"].std()
    std_arr = np.where(np.isnan(std_arr), global_std, std_arr)
    return std_arr


def compute_rho(ts, clim):
    sentinel = ts[ts["year"] >= SENTINEL_YEAR].copy()
    sentinel["anom"] = sentinel["doy"].map(
        lambda d: float(clim[min(int(d), 366)]))
    sentinel["anom"] = sentinel["vhi"] - sentinel["doy"].map(
        lambda d: float(clim[min(int(d), 366)]))
    da = sentinel.set_index("date")["anom"]
    pa, pb = [], []
    for dt, a in da.items():
        for delta in range(HORIZON - 1, HORIZON + 2):
            t2 = dt + pd.Timedelta(days=delta)
            if t2 in da.index:
                pa.append(a); pb.append(float(da[t2])); break
    if len(pa) < 10: return 0.35
    return max(0.0, float(np.corrcoef(pa, pb)[0, 1]))


# ── build 7-day forecast from last observation ───────────────────────────────
def make_forecast(ts, clim, rho):
    """
    Return DataFrame of forecast points for t+1 … t+7 using AR(1) decay.

    The anomaly decays per-day so the path STARTS at the last observed
    value (h=0 → decay 1.0) and bends smoothly toward climatology,
    reaching Clim + rho·Anomaly at h=7 (same endpoint as the lag-7 model).
    """
    last = ts.iloc[-1]
    last_anom = float(last["vhi"]) - float(clim[min(int(last["doy"]), 366)])
    rho_daily = rho ** (1.0 / HORIZON)   # 7-day rho → 1-day rho, e.g. 0.30→0.84
    rows = []
    for h in range(1, HORIZON + 1):
        fdate = last["date"] + pd.Timedelta(days=h)
        fdoy  = int(fdate.dayofyear)
        c     = float(clim[min(fdoy, 366)])
        decay = rho_daily ** h           # 0.84, 0.71, 0.60, … 0.30 at h=7
        rows.append({"date": fdate, "vhi_hat": c + decay * last_anom,
                     "clim": c})
    return pd.DataFrame(rows)


# ── plot ─────────────────────────────────────────────────────────────────────
def plot_all(items, cache_dir):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle("VHI — Last 3 Weeks + 7-Day Tendency Forecast\n"
                 "Shaded band: climatological mean ± 1 σ  |  Dashed: seasonal mean",
                 fontsize=13, fontweight="bold")

    colours = {
        "obs":      "#1a6faf",   # steel blue
        "forecast": "#d4520e",   # burnt orange
        "clim":     "#555555",   # dark grey dashed
        "band":     "#bbbbbb",   # light grey fill
        "mean_line":"#999999",
    }

    for ax, reg in zip(axes.flat, REGIONS):
        ts = build_series(items, cache_dir, reg["id"])
        clim, _ = fit_climatology(ts)
        std_arr  = historical_std(ts, clim)
        rho      = compute_rho(ts, clim)

        # last observation date and 3-week window
        last_date  = ts["date"].max()
        start_date = last_date - pd.Timedelta(weeks=3)
        recent     = ts[ts["date"] >= start_date].copy()

        # forecast
        fc = make_forecast(ts, clim, rho)

        # build climatology + σ for the full display range
        display_start = start_date
        display_end   = fc["date"].max()
        _date_range_pd = pd.date_range(display_start, display_end, freq="D")
        date_range     = _date_range_pd.to_pydatetime()
        doys           = _date_range_pd.dayofyear
        clim_line     = np.array([float(clim[min(int(d), 366)]) for d in doys])
        std_line      = np.array([float(std_arr[min(int(d), 366)]) for d in doys])

        # convert to numpy so old matplotlib doesn't choke on pandas Series
        rec_dates = recent["date"].dt.to_pydatetime()
        rec_vhi   = recent["vhi"].to_numpy(dtype=float)
        fc_dates  = fc["date"].dt.to_pydatetime()
        fc_vhi    = fc["vhi_hat"].to_numpy(dtype=float)

        # ── draw ──
        # 1. ±1σ band
        ax.fill_between(date_range,
                        clim_line - std_line,
                        clim_line + std_line,
                        color=colours["band"], alpha=0.45, label="Clim ± 1σ", zorder=1)

        # 2. climatological mean
        ax.plot(date_range, clim_line,
                color=colours["clim"], linewidth=1.2, linestyle="--",
                label="Seasonal mean", zorder=2)

        # 3. observed VHI (last 3 weeks)
        ax.plot(rec_dates, rec_vhi,
                color=colours["obs"], linewidth=2.0, marker="o",
                markersize=5, label="Observed VHI", zorder=4)

        # 4. bridge: dotted line connecting last obs → first forecast point
        bridge_dates = [last_date.to_pydatetime(), fc_dates[0]]
        bridge_vals  = [rec_vhi[-1], fc_vhi[0]]
        ax.plot(bridge_dates, bridge_vals,
                color=colours["forecast"], linewidth=1.4, linestyle=":", zorder=3)

        # 5. forecast line
        ax.plot(fc_dates, fc_vhi,
                color=colours["forecast"], linewidth=2.0, marker="D",
                markersize=5, label=f"7-day forecast (ρ={rho:.2f})", zorder=4)

        # 6. vertical "now" line
        last_dt = last_date.to_pydatetime()
        ax.axvline(last_dt, color="#888888", linewidth=0.8,
                   linestyle="--", alpha=0.7)
        ax.text(last_dt, 1, " now", fontsize=7.5, color="#666666", va="bottom")

        # ── stats annotation ──
        obs_mean = float(recent["vhi"].mean())
        obs_std  = float(recent["vhi"].std())
        fc_mean  = float(fc["vhi_hat"].mean())
        ax.text(0.03, 0.97,
                f"Obs 3w: mean={obs_mean:.1f}  σ={obs_std:.1f}\n"
                f"Forecast 7d: mean={fc_mean:.1f}",
                transform=ax.transAxes,
                fontsize=8.5, va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc", alpha=0.85))

        # ── axes cosmetics ──
        ax.set_title(f"Region {reg['id']} — {reg['name']}", fontsize=11, fontweight="bold")
        ax.set_ylabel("VHI", fontsize=9)
        ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        ax.legend(fontsize=7.5, loc="lower right", framealpha=0.85)

        # shade forecast zone
        ax.axvspan(last_dt, fc_dates[-1],
                   color=colours["forecast"], alpha=0.04, zorder=0)

        # optional: thin horizontal VHI class lines
        for val in [20, 35, 50, 65]:
            ax.axhline(val, color="#dddddd", linewidth=0.6, zorder=0)

    fig.savefig(OUT, dpi=150, bbox_inches="tight")
    print(f"Saved → {OUT}")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    cache = Path(__file__).parent / "vhi_cache"
    print("Fetching STAC catalogue …")
    items = fetch_all_stac_items()
    print(f"  {len(items)} items")
    print("Checking cache …")
    download_all(items, cache)
    print("Plotting …")
    plot_all(items, cache)

if __name__ == "__main__":
    main()
