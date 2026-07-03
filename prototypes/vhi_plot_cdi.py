"""
7-day nowcast: VHI-only AR(1)  vs  CDI-conditioned reversion.
Overlays both forecasts so the correction is visible.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from pathlib import Path

import vhi_plot as VP   # reuse data + climatology functions

# Live CDI forecast for next week (week +1, valid 29.06-05.07 2026)
CDI_FORECAST = {31: 5, 33: 4, 35: 3, 42: 2}

# Calibration from historic archive: recovery fraction of a stressed anomaly
# in one week, by next-week CDI class -> implied 7-day reversion rho.
RHO_BY_CDI = {5: 0.94, 4: 0.85, 3: 0.66, 2: 0.60, 1: 0.37}

CDI_LABEL = {5: "extrem trocken", 4: "trocken", 3: "maessig",
             2: "leicht", 1: "normal"}

OUT = Path(__file__).parent / "vhi_nowcast_cdi_compare.png"


def forecast(ts, clim, rho, horizon=7):
    last = ts.iloc[-1]
    anom = float(last["vhi"]) - float(clim[min(int(last["doy"]), 366)])
    rho_daily = rho ** (1.0 / horizon)
    rows = []
    for h in range(1, horizon + 1):
        fdate = last["date"] + pd.Timedelta(days=h)
        c = float(clim[min(int(fdate.dayofyear), 366)])
        rows.append({"date": fdate, "vhi_hat": c + (rho_daily ** h) * anom})
    return pd.DataFrame(rows), anom


def main():
    items = VP.fetch_all_stac_items()
    cache = Path(__file__).parent / "vhi_cache"
    VP.download_all(items, cache)

    regions = [(31, "Oestlicher Jura"), (33, "Unteres Emmental"),
               (35, "Westliches Berner Oberland"), (42, "Oestliches Mittelland")]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle("7-Day VHI Nowcast: VHI-only AR(1)  vs  CDI-conditioned reversion\n"
                 "Grey band: climatological mean +/- 1 sigma",
                 fontsize=13, fontweight="bold")

    for ax, (rid, name) in zip(axes.flat, regions):
        ts = VP.build_series(items, cache, rid)
        clim, _ = VP.fit_climatology(ts)
        std_arr = VP.historical_std(ts, clim)
        rho_vhi = VP.compute_rho(ts, clim)               # old, autocorrelation
        cdi = CDI_FORECAST[rid]
        rho_cdi = RHO_BY_CDI[cdi]                          # new, CDI-conditioned

        fc_old, anom = forecast(ts, clim, rho_vhi)
        fc_new, _    = forecast(ts, clim, rho_cdi)

        last_date = ts["date"].max()
        start = last_date - pd.Timedelta(weeks=3)
        recent = ts[ts["date"] >= start]

        drange = pd.date_range(start, fc_new["date"].max(), freq="D")
        doys = drange.dayofyear
        clim_line = np.array([float(clim[min(int(d), 366)]) for d in doys])
        std_line  = np.array([float(std_arr[min(int(d), 366)]) for d in doys])
        drange_p = drange.to_pydatetime()

        rec_d = np.array(recent["date"].dt.to_pydatetime())
        rec_v = recent["vhi"].to_numpy(float)
        last_dt = last_date.to_pydatetime()
        old_d = np.array(fc_old["date"].dt.to_pydatetime())
        old_v = fc_old["vhi_hat"].to_numpy(float)
        new_d = np.array(fc_new["date"].dt.to_pydatetime())
        new_v = fc_new["vhi_hat"].to_numpy(float)

        ax.fill_between(drange_p, clim_line - std_line, clim_line + std_line,
                        color="#bbbbbb", alpha=0.4, label="Clim +/- 1sigma", zorder=1)
        ax.plot(drange_p, clim_line, "--", color="#555555", lw=1.1,
                label="Seasonal mean", zorder=2)
        ax.plot(rec_d, rec_v, "-o", color="#1a6faf", lw=2, ms=5,
                label="Observed VHI", zorder=5)
        # old VHI-only forecast (faint)
        ax.plot([last_dt, old_d[0]], [rec_v[-1], old_v[0]], ":", color="#d4520e",
                lw=1.2, alpha=0.5, zorder=3)
        ax.plot(old_d, old_v, ":D", color="#d4520e", lw=1.6, ms=4, alpha=0.55,
                label=f"VHI-only (rho={rho_vhi:.2f})", zorder=3)
        # new CDI-conditioned forecast (solid)
        ax.plot([last_dt, new_d[0]], [rec_v[-1], new_v[0]], "-", color="#b10026",
                lw=1.6, zorder=4)
        ax.plot(new_d, new_v, "-D", color="#b10026", lw=2.2, ms=6,
                label=f"CDI-conditioned (CDI={cdi}, rho={rho_cdi:.2f})", zorder=6)

        ax.axvline(last_dt, color="#888", lw=0.8, ls="--", alpha=0.7)
        ax.text(0.03, 0.97,
                f"CDI-Prognose n. Woche: {cdi} ({CDI_LABEL[cdi]})\n"
                f"VHI-only 7d:      {old_v[-1]:.0f}  (+{old_v[-1]-rec_v[-1]:.0f})\n"
                f"CDI-conditioned:  {new_v[-1]:.0f}  (+{new_v[-1]-rec_v[-1]:.0f})",
                transform=ax.transAxes, fontsize=8, va="top",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc", alpha=0.9))

        ax.set_title(f"Region {rid} - {name}", fontsize=11, fontweight="bold")
        ax.set_ylabel("VHI"); ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.tick_params(labelsize=8)
        ax.grid(axis="y", ls=":", alpha=0.5)
        ax.legend(fontsize=7.5, loc="lower left", framealpha=0.9)
        ax.axvspan(last_dt, new_d[-1], color="#d4520e", alpha=0.04, zorder=0)

    fig.savefig(OUT, dpi=150, bbox_inches="tight")
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
