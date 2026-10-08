#!/usr/bin/env python3
"""Average SMAP data to the AMSR slot-compatible 0.5-degree NetCDF format.

AM retrievals are represented by the AMSR-compatible ``A_01`` slot and PM
retrievals by ``D_01``. Soil moisture is stored as percent, as in AMSR files.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
from netCDF4 import Dataset


def target_grid() -> tuple[np.ndarray, np.ndarray]:
    return (89.75 - np.arange(360, dtype=np.float32) * .5, -179.75 + np.arange(720, dtype=np.float32) * .5)


def mapping(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    iy = np.floor((90.0 - lat) / .5).astype(np.int64)
    ix = np.floor((np.mod(lon + 180., 360.) - 180.) / .5).astype(np.int64)
    good = np.isfinite(lat) & np.isfinite(lon) & (iy >= 0) & (iy < 360) & (ix >= 0) & (ix < 720)
    out = np.full(lat.shape, -1, dtype=np.int64); out[good] = iy[good] * 720 + ix[good]
    return out.ravel()


def aggregate(values: np.ndarray, minutes: np.ndarray, cell: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = np.isfinite(values.ravel()) & (cell >= 0)
    count = np.bincount(cell[valid], minlength=360 * 720).astype(np.int32)
    sums = np.bincount(cell[valid], weights=values.ravel()[valid], minlength=360 * 720)
    tsums = np.bincount(cell[valid], weights=minutes.ravel()[valid], minlength=360 * 720)
    soil = np.full(360 * 720, np.nan, np.float32); time = soil.copy(); used = count > 0
    soil[used] = (sums[used] / count[used]).astype(np.float32); time[used] = (tsums[used] / count[used]).astype(np.float32)
    return soil.reshape(360, 720), time.reshape(360, 720), count.reshape(360, 720)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_dir", nargs="?", type=Path, default=Path("processed/l3_daily"))
    p.add_argument("output_path", nargs="?", type=Path, default=Path("processed/l3_daily_0p5/SMAP_SMC_daily_0p5deg_avg.nc"))
    p.add_argument("--overwrite", action="store_true")
    a = p.parse_args(); files = sorted(a.input_dir.glob("SMAP_SPL3SMP_E_daily_*.nc"))
    if not files: raise FileNotFoundError(f"No merged files in {a.input_dir}")
    if a.output_path.exists() and not a.overwrite: raise FileExistsError(f"{a.output_path} exists; use --overwrite")
    a.output_path.parent.mkdir(parents=True, exist_ok=True)
    lat, lon = target_grid(); out = Dataset(a.output_path, "w", format="NETCDF4")
    out.createDimension("time", None); out.createDimension("lat", 360); out.createDimension("lon", 720)
    t = out.createVariable("time", "i4", ("time",)); t.units = "days since 1970-01-01 00:00:00"; out.createVariable("lat", "f4", ("lat",))[:] = lat; out.createVariable("lon", "f4", ("lon",))[:] = lon
    variables = {}
    for slot in ("A_01", "D_01"):
        soil = out.createVariable(f"soil_moisture_{slot}", "f4", ("time", "lat", "lon"), zlib=True, complevel=4, fill_value=np.float32(np.nan))
        obs = out.createVariable(f"observation_time_min_{slot}", "f4", ("time", "lat", "lon"), zlib=True, complevel=4, fill_value=np.float32(np.nan))
        soil.units = "%"; soil.long_name = f"daily mean soil moisture ({slot}, 0.5 degree)"
        obs.units = "minutes since 00:00 UTC of corresponding time day"; obs.long_name = f"daily mean observation time ({slot}, 0.5 degree)"
        variables[f"soil_moisture_{slot}"] = soil
        variables[f"observation_time_min_{slot}"] = obs
    index = 0
    for file in files:
        with Dataset(file) as src:
            cell = mapping(src.variables["latitude"][:], src.variables["longitude"][:])
            for i, day in enumerate(src.variables["time"][:]):
                t[index] = day
                for period, slot in (("am", "A_01"), ("pm", "D_01")):
                    soil, obs, count = aggregate(src.variables[f"soil_moisture_{period}"][i], src.variables[f"observation_time_min_{period}"][i], cell)
                    # SMAP source uses m3/m3; AMSR query/CDF code expects percent.
                    variables[f"soil_moisture_{slot}"][index] = soil * 100.0
                    variables[f"observation_time_min_{slot}"][index] = obs
                index += 1
        print(f"Processed {file}")
    out.title = "SMAP SPL3SMP_E v006 daily 0.5-degree averages (AMSR slot-compatible)"; out.close(); print(f"Wrote {a.output_path}")


if __name__ == "__main__": main()
