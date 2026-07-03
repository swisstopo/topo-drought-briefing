"""
VHI 7-day tendency forecast - Fourier climatology + AR(1) anomaly decay
=======================================================================
Dependencies: numpy, pandas, requests  (matplotlib only for --plot)

Model
-----
    VHI_hat(t+h) = Climatology(DOY_t+h) + rho_daily^h * Anomaly(t)

    Climatology(DOY) : Fourier harmonic regression (2 harmonics) fitted to
                       35 years of daily VHI pooled by day-of-year.
    Anomaly(t)       : VHI_observed(t) - Climatology(DOY_t)
    rho_daily        : 1-day anomaly autocorrelation, derived from the
                       validated 7-day autocorrelation as rho_7 ** (1/7).

The per-day decay makes the forecast path START at the last observed value
(h=0 -> decay 1.0) and bend smoothly toward the seasonal mean, reaching
Climatology + rho_7 * Anomaly at h=7. The h=7 endpoint is identical to a
plain lag-7 anomaly-persistence model, so the cross-validated skill is
preserved while the visual path is continuous and mean-reverting.

Usage
-----
    python vhi_tendency.py --cache-dir ./vhi_cache            # run CV
    python vhi_tendency.py --cache-dir ./vhi_cache --plot     # + PNG
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

STAC_ITEMS    = ("https://data.geo.admin.ch/api/stac/v1/collections/"
                 "ch.swisstopo.swisseo_vhi_v100/items")
CSV_ASSET_KEY = "vegetation-warnregions.csv"
MAX_WORKERS   = 12
PAGE_LIMIT    = 100
MIN_AVAIL     = 20.0   # drop obs with < 20% pixel availability
HORIZON       = 7      # forecast horizon in days
SENTINEL_YEAR = 2017   # rho computed from near-daily Sentinel-2 era only
N_HARMONICS   = 2      # annual + semi-annual
STD_WINDOW    = 21     # +/- DOY window for historical sigma band (plot only)

REGIONS = [
    {"id": 31, "name": "Oestlicher Jura"},
    {"id": 33, "name": "Unteres Emmental"},
    {"id": 35, "name": "Westliches Berner Oberland"},
    {"id": 42, "name": "Oestliches Mittelland"},
]


# --- STAC catalogue + CSV download -----------------------------------------
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
    except Exception:
        pass


def download_all(items, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    missing = [i for i in items if not (cache_dir / f"{i['date']}.csv").exists()]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(as_completed({ex.submit(_dl, i, cache_dir): i for i in missing}))


def build_series(items, cache_dir, region_id):
    rows = []
    for item in items:
        fpath = cache_dir / f"{item['date']}.csv"
        if not fpath.exists(): continue
        try:
            df  = pd.read_csv(fpath)
            row = df[df["REGION_NR"] == region_id]
            if row.empty: continue
            vhi   = float(row["vhi_mean"].iloc[0])
            avail = float(row["availability_percentage"].iloc[0])
            date  = pd.to_datetime(item["date"].split("t")[0])
            rows.append({"date": date, "vhi": vhi, "avail": avail})
        except Exception:
            continue
    ts = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    ts = ts[(ts["avail"] >= MIN_AVAIL) & (ts["vhi"] < 100)].copy()
    ts["doy"]  = ts["date"].dt.dayofyear
    ts["year"] = ts["date"].dt.year
    return ts


# --- Fourier climatology ----------------------------------------------------
def _fourier_matrix(doy_arr, n=N_HARMONICS):
    cols = [np.ones(len(doy_arr))]
    for k in range(1, n + 1):
        cols += [np.cos(2 * np.pi * k * doy_arr / 365.0),
                 np.sin(2 * np.pi * k * doy_arr / 365.0)]
    return np.column_stack(cols)


def fit_climatology(ts):
    doy = ts["doy"].values.astype(float)
    vhi = ts["vhi"].values.astype(float)
    coeffs, *_ = np.linalg.lstsq(_fourier_matrix(doy), vhi, rcond=None)
    grid = np.arange(1, 367, dtype=float)
    clim = np.full(367, np.nan)
    clim[1:] = _fourier_matrix(grid) @ coeffs
    fitted = _fourier_matrix(doy) @ coeffs
    ss_res = np.sum((vhi - fitted) ** 2)
    ss_tot = np.sum((vhi - vhi.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return clim, r2


def _anomaly(vhi, doy, clim):
    c = clim[min(int(doy), 366)]
    return float(vhi - c) if not np.isnan(c) else 0.0


def compute_rho(ts, clim, horizon=HORIZON):
    """7-day anomaly autocorrelation, Sentinel-2 era only."""
    sub = ts[ts["year"] >= SENTINEL_YEAR].copy()
    if len(sub) < 20:
        return 0.35
    sub["anom"] = [_anomaly(r.vhi, r.doy, clim) for r in sub.itertuples()]
    da = sub.set_index("date")["anom"]
    a, b = [], []
    for dt, anom in da.items():
        for delta in range(horizon - 1, horizon + 2):
            t2 = dt + pd.Timedelta(days=delta)
            if t2 in da.index:
                a.append(anom); b.append(float(da[t2])); break
    if len(a) < 10:
        return 0.35
    return max(0.0, float(np.corrcoef(a, b)[0, 1]))


# --- AR(1) forecast path ----------------------------------------------------
def make_forecast(ts, clim, rho, horizon=HORIZON):
    """
    7-day forecast with per-day AR(1) anomaly decay.

    decay(h) = rho ** (h / horizon)  ->  1.0 at h=0, rho at h=horizon
    Path starts at the last observed value and bends toward climatology.
    """
    last = ts.iloc[-1]
    last_anom = _anomaly(last["vhi"], last["doy"], clim)
    rho_daily = rho ** (1.0 / horizon)
    rows = []
    for h in range(1, horizon + 1):
        fdate = last["date"] + pd.Timedelta(days=h)
        fdoy  = int(fdate.dayofyear)
        c     = float(clim[min(fdoy, 366)])
        decay = rho_daily ** h
        rows.append({"date": fdate, "vhi_hat": c + decay * last_anom, "clim": c})
    return pd.DataFrame(rows)


# --- Leave-one-year-out cross-validation (validates h=7 endpoint) -----------
def _forecast_endpoint_df(ts, clim, rho, horizon=HORIZON):
    d2v = dict(zip(ts["date"], ts["vhi"]))
    rows = []
    for r in ts.itertuples():
        anom   = _anomaly(r.vhi, r.doy, clim)
        target = r.date + pd.Timedelta(days=horizon)
        obs = None
        for delta in range(0, 4):
            for sign in ([1, -1] if delta > 0 else [1]):
                cand = target + pd.Timedelta(days=sign * delta)
                if cand in d2v:
                    obs = d2v[cand]; break
            if obs is not None: break
        if obs is None: continue
        ct = clim[min(int(target.dayofyear), 366)]
        if np.isnan(ct): continue
        rows.append({"year": r.date.year, "vhi_target": obs,
                     "f_clim": ct, "f_persist": r.vhi,
                     "f_anom": ct + rho * anom})
    return pd.DataFrame(rows)


def _rmse(a, b): return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))
def _skill(f, base, o):
    r = _rmse(base, o)
    return float(1.0 - _rmse(f, o) / r) if r > 0 else float("nan")


def loyo_cv(ts, horizon=HORIZON):
    results = []
    for y in sorted(ts["year"].unique()):
        train = ts[ts["year"] != y]
        if len(train) < 100: continue
        clim_y, _ = fit_climatology(train)
        rho_y     = compute_rho(train, clim_y, horizon)
        fdf       = _forecast_endpoint_df(ts, clim_y, rho_y, horizon)
        fy        = fdf[fdf["year"] == y]
        if len(fy) < 5 or y < SENTINEL_YEAR: continue
        obs = fy["vhi_target"].values
        results.append({"year": y, "n": len(fy), "rho": rho_y,
                        "rmse_persist": _rmse(fy["f_persist"], obs),
                        "rmse_clim":    _rmse(fy["f_clim"], obs),
                        "rmse_anom":    _rmse(fy["f_anom"], obs),
                        "ss_persist":   _skill(fy["f_anom"], fy["f_persist"], obs),
                        "ss_clim":      _skill(fy["f_anom"], fy["f_clim"], obs)})
    return pd.DataFrame(results)


# --- main -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="./vhi_cache")
    ap.add_argument("--plot", action="store_true", help="also write PNG")
    args = ap.parse_args()
    cache = Path(args.cache_dir)

    items = fetch_all_stac_items()
    download_all(items, cache)

    print(f"{'ID':>4}  {'Name':<28}  {'R2':>5}  {'rho':>5}  "
          f"{'SS_persist':>10}  {'SS_clim':>8}")
    for reg in REGIONS:
        ts = build_series(items, cache, reg["id"])
        clim, r2 = fit_climatology(ts)
        rho = compute_rho(ts, clim)
        cv  = loyo_cv(ts)
        ssp = cv["ss_persist"].mean() if not cv.empty else float("nan")
        ssc = cv["ss_clim"].mean()    if not cv.empty else float("nan")
        print(f"{reg['id']:>4}  {reg['name']:<28}  {r2:>5.3f}  {rho:>5.3f}  "
              f"{ssp:>+10.3f}  {ssc:>+8.3f}")

    if args.plot:
        from vhi_plot import plot_all   # plotting kept in a separate module
        plot_all(items, cache)


if __name__ == "__main__":
    main()
