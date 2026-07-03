"""
Does CDI improve the 1-week VHI forecast?  (weekly historic archive)
====================================================================
Compares, per region, with leave-one-year-out cross-validation:

  M0 climatology        VHI_hat(t+1) = Clim(week+1)
  M1 persistence        VHI_hat(t+1) = VHI(t)
  M2 VHI anom-persist   VHI_hat(t+1) = Clim + rho * anom_vhi(t)          (current model)
  M3 + CDI              add CDI(t) as predictor
  M4 + full drivers     add CDI, hydro, SPI(1/3/6/12m) as predictors
  M4* perfect-CDI       M4 but using CDI(t+1) analysis (upper bound: a
                        perfect 1-week CDI forecast)

Target: VHI anomaly one week ahead. Data is weekly, so +1 row = +7 days.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "hist" / "weekly_historic_regions.csv"

SENTINEL_YEAR = 2017          # dense era for CV
N_HARMONICS   = 2
FOCUS         = [31, 33, 35, 42]
# predictor column names as they appear in the pairs frame (value at time t)
DRIVERS_M4    = ["cdi_t", "hydro_t", "spi_1m", "spi_3m", "spi_6m", "spi_12m"]


# --- load -------------------------------------------------------------------
def load():
    df = pd.read_csv(CSV, sep=";", skiprows=3)
    df["date"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    df = df.rename(columns={"drought_region_id": "region"})
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["doy"]  = df["date"].dt.dayofyear
    df["year"] = df["date"].dt.year
    # VHI >= 108 is treated as a no-data / cap sentinel (archive max is 109)
    df.loc[df["vhi"] >= 108, "vhi"] = np.nan
    return df


# --- Fourier climatology on VHI --------------------------------------------
def _X(doy, n=N_HARMONICS):
    doy = np.asarray(doy, float)
    cols = [np.ones(len(doy))]
    for k in range(1, n + 1):
        cols += [np.cos(2*np.pi*k*doy/365.0), np.sin(2*np.pi*k*doy/365.0)]
    return np.column_stack(cols)


def fit_clim(sub):
    m = sub["vhi"].notna()
    coeffs, *_ = np.linalg.lstsq(_X(sub.loc[m, "doy"]), sub.loc[m, "vhi"].values, rcond=None)
    return coeffs


def clim_at(doy, coeffs):
    return float((_X([doy]) @ coeffs)[0])


# --- build supervised pairs for one region ----------------------------------
def build_pairs(df_reg, coeffs):
    """Pair each week t with the observation ~7 days later (t+1 week)."""
    d = df_reg.sort_values("date").reset_index(drop=True).copy()
    d["clim"] = d["doy"].map(lambda x: clim_at(x, coeffs))
    d["anom_vhi"] = d["vhi"] - d["clim"]
    date_to_idx = {dt: i for i, dt in enumerate(d["date"])}

    rows = []
    for i, r in d.iterrows():
        target_dt = r["date"] + pd.Timedelta(days=7)
        # accept the nearest row within +/- 3 days of the +7d target
        j = None
        for delta in range(0, 4):
            for s in ([1, -1] if delta else [1]):
                cand = target_dt + pd.Timedelta(days=s*delta)
                if cand in date_to_idx:
                    j = date_to_idx[cand]; break
            if j is not None: break
        if j is None:
            continue
        tgt = d.iloc[j]
        if pd.isna(r["vhi"]) or pd.isna(tgt["vhi"]):
            continue
        rows.append({
            "year": r["year"],
            "vhi_t": r["vhi"], "anom_t": r["anom_vhi"], "clim_t": r["clim"],
            "vhi_tp1": tgt["vhi"], "clim_tp1": tgt["clim"],
            "anom_tp1": tgt["vhi"] - tgt["clim"],
            # predictors at t
            "cdi_t": r["cdi"], "hydro_t": r["hydro_index"],
            "spi_1m": r["spi_1m"], "spi_3m": r["spi_3m"],
            "spi_6m": r["spi_6m"], "spi_12m": r["spi_12m"],
            # perfect-forecast predictor: CDI at t+1
            "cdi_tp1": tgt["cdi"],
        })
    return pd.DataFrame(rows)


# --- linear model helpers ---------------------------------------------------
def _design(P, cols):
    X = [np.ones(len(P))]
    for c in cols:
        X.append(P[c].values.astype(float))
    return np.column_stack(X)


def _fit_predict(train, test, cols, target="anom_tp1"):
    """OLS on anomaly target; returns predicted VHI (clim_tp1 + anom_hat)."""
    Xtr = _design(train, cols); ytr = train[target].values.astype(float)
    beta, *_ = np.linalg.lstsq(Xtr, ytr, rcond=None)
    Xte = _design(test, cols)
    anom_hat = Xte @ beta
    return test["clim_tp1"].values + anom_hat


def rmse(a, b): return float(np.sqrt(np.mean((np.asarray(a)-np.asarray(b))**2)))
def skill(f, base, o):
    r = rmse(base, o); return float(1.0 - rmse(f, o)/r) if r > 0 else np.nan


# --- LOYO CV for one region -------------------------------------------------
def cv_region(P):
    P = P.dropna(subset=["anom_t", "cdi_t", "hydro_t", "spi_1m", "spi_3m",
                         "spi_6m", "spi_12m", "cdi_tp1"]).copy()
    P = P[P["year"] >= SENTINEL_YEAR]
    years = sorted(P["year"].unique())
    acc = {k: [] for k in ["M0", "M1", "M2", "M3", "M4", "M4star", "obs_n"]}
    for y in years:
        tr = P[P["year"] != y]; te = P[P["year"] == y]
        if len(tr) < 60 or len(te) < 5:
            continue
        obs = te["vhi_tp1"].values
        # M0 climatology
        m0 = te["clim_tp1"].values
        # M1 persistence
        m1 = te["vhi_t"].values
        # M2 VHI anomaly-persistence (single predictor: anom_t)
        m2 = _fit_predict(tr, te, ["anom_t"])
        # M3 + CDI(t)
        m3 = _fit_predict(tr, te, ["anom_t", "cdi_t"])
        # M4 + full drivers
        m4 = _fit_predict(tr, te, ["anom_t"] + DRIVERS_M4)
        # M4* perfect CDI forecast: swap contemporaneous cdi_t for cdi_tp1
        m4s = _fit_predict(tr, te, ["anom_t", "cdi_tp1"] + DRIVERS_M4[1:])  # drop cdi_t, keep hydro+spi
        acc["M0"].append(rmse(m0, obs)); acc["M1"].append(rmse(m1, obs))
        acc["M2"].append(rmse(m2, obs)); acc["M3"].append(rmse(m3, obs))
        acc["M4"].append(rmse(m4, obs)); acc["M4star"].append(rmse(m4s, obs))
        acc["obs_n"].append(len(te))
    if not acc["M2"]:
        return None
    return {k: (np.mean(v) if k != "obs_n" else int(np.sum(v))) for k, v in acc.items()}


# --- main -------------------------------------------------------------------
def main():
    df = load()
    print(f"VHI range in archive: {df['vhi'].min():.1f} .. {df['vhi'].max():.1f}")
    print(f"CDI range: {df['cdi'].min():.0f} .. {df['cdi'].max():.0f}\n")

    all_regions = sorted(df["region"].unique())
    summary = []
    for reg in all_regions:
        sub = df[df["region"] == reg]
        if sub["vhi"].notna().sum() < 150:
            continue
        coeffs = fit_clim(sub)
        P = build_pairs(sub, coeffs)
        res = cv_region(P)
        if res is None:
            continue
        # skill of M2/M3/M4 vs M2 baseline (does CDI beat VHI-only?)
        ss_m3_vs_m2 = 1 - res["M3"]/res["M2"]
        ss_m4_vs_m2 = 1 - res["M4"]/res["M2"]
        ss_m4s_vs_m2 = 1 - res["M4star"]/res["M2"]
        summary.append({"region": reg, **res,
                        "ss_M3_vs_M2": ss_m3_vs_m2,
                        "ss_M4_vs_M2": ss_m4_vs_m2,
                        "ss_M4s_vs_M2": ss_m4s_vs_m2})

    S = pd.DataFrame(summary)
    print("=" * 92)
    print("RMSE by model (lower better) + skill of CDI models vs M2 (VHI-only anomaly persistence)")
    print("=" * 92)
    print(f"{'reg':>4} {'n':>5} | {'M0clim':>7} {'M1pers':>7} {'M2vhi':>7} "
          f"{'M3+cdi':>7} {'M4+drv':>7} {'M4*perf':>8} | "
          f"{'M3>M2':>7} {'M4>M2':>7} {'M4*>M2':>7}")
    print("-" * 92)
    def row(r, star=""):
        return (f"{int(r['region']):>4} {int(r['obs_n']):>5} | "
                f"{r['M0']:>7.2f} {r['M1']:>7.2f} {r['M2']:>7.2f} "
                f"{r['M3']:>7.2f} {r['M4']:>7.2f} {r['M4star']:>8.2f} | "
                f"{r['ss_M3_vs_M2']:>+7.3f} {r['ss_M4_vs_M2']:>+7.3f} {r['ss_M4s_vs_M2']:>+7.3f} {star}")
    for _, r in S.iterrows():
        star = " <focus" if int(r["region"]) in FOCUS else ""
        print(row(r, star))
    print("-" * 92)
    m = S.mean(numeric_only=True)
    print(f"{'MEAN':>4} {'':>5} | {m['M0']:>7.2f} {m['M1']:>7.2f} {m['M2']:>7.2f} "
          f"{m['M3']:>7.2f} {m['M4']:>7.2f} {m['M4star']:>8.2f} | "
          f"{m['ss_M3_vs_M2']:>+7.3f} {m['ss_M4_vs_M2']:>+7.3f} {m['ss_M4s_vs_M2']:>+7.3f}")
    print()
    print(f"Regions evaluated: {len(S)}")
    print(f"Focus regions {FOCUS}:")
    print(S[S['region'].isin(FOCUS)][['region','M2','M3','M4','M4star',
          'ss_M3_vs_M2','ss_M4_vs_M2','ss_M4s_vs_M2']].to_string(index=False))


if __name__ == "__main__":
    main()
