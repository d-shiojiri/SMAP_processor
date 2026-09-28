#!/usr/bin/env python3
"""Apply grid-wise empirical CDF matching to 0.5-degree SMAP daily data.

Reference files are supplied by a JSON file containing either ``paths`` or a
``path_template`` with ``start_year`` and ``end_year``.  The reference variable
is sampled on the nearest reference date and nearest grid cell.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, num2date


def epoch_days(values: np.ndarray, units: str, calendar: str = "standard") -> np.ndarray:
    dates = num2date(values, units=units, calendar=calendar, only_use_cftime_datetimes=False, only_use_python_datetimes=False)
    epoch = dt.date(1970, 1, 1)
    return np.asarray([(
        dt.date(int(d.year), int(d.month), int(d.day)) - epoch
    ).days for d in dates], dtype=np.int32)


def load_paths(spec: Path) -> list[Path]:
    data = json.loads(spec.read_text())
    if "paths" in data: return [Path(p) for p in data["paths"]]
    return [Path(data["path_template"].format(year=y)) for y in range(int(data["start_year"]), int(data["end_year"]) + 1)]


def nearest(source: np.ndarray, target: np.ndarray, cyclic: bool = False) -> np.ndarray:
    if cyclic:
        delta = np.abs((source[:, None] - target[None, :] + 180.) % 360. - 180.)
    else: delta = np.abs(source[:, None] - target[None, :])
    return np.argmin(delta, axis=0)


def rank_match(raw: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Map every finite raw value through its cell's paired empirical CDF."""
    out = np.full(raw.shape, np.nan, np.float32)
    for col in range(raw.shape[1]):
        x, y = raw[:, col], ref[:, col]; pair = np.isfinite(x) & np.isfinite(y)
        if not pair.any(): continue
        xs, ys = np.sort(x[pair]), np.sort(y[pair]); n = len(xs)
        if n == 1: out[np.isfinite(x), col] = ys[0]; continue
        q = (np.arange(n) + .5) / n; use = np.isfinite(x)
        out[use, col] = np.interp(np.interp(x[use], xs, q, left=0., right=1.), q, ys, left=ys[0], right=ys[-1])
    return out


class References:
    def __init__(self, paths: list[Path], var: str, depth: int, input_lat: np.ndarray, input_lon: np.ndarray):
        self.sources: list[tuple[Path, str, int, np.ndarray, np.ndarray, dict[int, int]]] = []
        for path in paths:
            if not path.exists(): raise FileNotFoundError(path)
            with Dataset(path) as ds:
                time = ds.variables["time"]; days = epoch_days(time[:], time.units, getattr(time, "calendar", "standard"))
                lat = np.asarray(ds.variables["lat"][:]); lon = np.asarray(ds.variables["lon"][:])
                if lat.ndim != 1 or lon.ndim != 1: raise ValueError(f"Reference coordinates must be 1-D: {path}")
                lookup = {int(day): i for i, day in enumerate(days)}
            self.sources.append((path, var, depth, nearest(lat, input_lat), nearest(lon, input_lon, True), lookup))

    def block(self, days: np.ndarray, row: slice) -> np.ndarray:
        output = np.full((len(days), row.stop - row.start, 720), np.nan, np.float32)
        for path, var, depth, yi, xi, lookup in self.sources:
            wanted = [(j, lookup[int(day)]) for j, day in enumerate(days) if int(day) in lookup]
            if not wanted: continue
            with Dataset(path) as ds:
                data = ds.variables[var]
                for j, ti in wanted:
                    value = data[ti]
                    if value.ndim == 3: value = value[depth]
                    output[j] = np.asarray(value)[np.ix_(yi[row], xi)].astype(np.float32)
        return output


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_path", nargs="?", type=Path, default=Path("processed/l3_daily_0p5/SMAP_SPL3SMP_E_daily_0p5deg.nc"))
    p.add_argument("--reference-dict", type=Path, default=Path("reference_paths_template.json"))
    p.add_argument("--reference-var", default="SoilMoistV"); p.add_argument("--reference-depth", type=int, default=0)
    p.add_argument("--output-path", type=Path, default=Path("processed/l3_daily_0p5/SMAP_SPL3SMP_E_daily_0p5deg_cdf.nc"))
    p.add_argument("--block-rows", type=int, default=20); p.add_argument("--overwrite", action="store_true")
    a = p.parse_args()
    if a.output_path.exists() and not a.overwrite: raise FileExistsError(f"{a.output_path} exists; use --overwrite")
    with Dataset(a.input_path) as src:
        days = np.asarray(src.variables["time"][:], dtype=np.int32); lat = np.asarray(src.variables["lat"][:]); lon = np.asarray(src.variables["lon"][:])
        refs = References(load_paths(a.reference_dict), a.reference_var, a.reference_depth, lat, lon)
        a.output_path.parent.mkdir(parents=True, exist_ok=True)
        out = Dataset(a.output_path, "w", format="NETCDF4")
        out.createDimension("time", len(days)); out.createDimension("lat", len(lat)); out.createDimension("lon", len(lon))
        out.createVariable("time", "i4", ("time",))[:] = days; out.variables["time"].units = src.variables["time"].units
        out.createVariable("lat", "f4", ("lat",))[:] = lat; out.createVariable("lon", "f4", ("lon",))[:] = lon
        for period in ("am", "pm"):
            corrected = out.createVariable(f"soil_moisture_{period}", "f4", ("time", "lat", "lon"), zlib=True, complevel=4, fill_value=np.float32(np.nan)); corrected.units = "m3 m-3"; corrected.long_name = f"CDF-matched SMAP soil moisture ({period.upper()})"
            for extra in ("observation_time_min", "observation_count"):
                vin = src.variables[f"{extra}_{period}"]; vout = out.createVariable(f"{extra}_{period}", vin.dtype, vin.dimensions, zlib=True, complevel=4, fill_value=getattr(vin, "_FillValue", None)); vout[:] = vin[:]
            for start in range(0, len(lat), a.block_rows):
                rows = slice(start, min(start + a.block_rows, len(lat)))
                ref = refs.block(days, rows)
                raw = np.asarray(src.variables[f"soil_moisture_{period}"][:, rows, :], dtype=np.float32)
                corrected[:, rows, :] = rank_match(raw.reshape(len(days), -1), ref.reshape(len(days), -1)).reshape(raw.shape)
                print(f"{period.upper()} rows {rows.start}:{rows.stop}")
        out.title = "Grid-wise CDF-matched SMAP SPL3SMP_E v006 soil moisture"; out.reference_variable = a.reference_var; out.close()
    print(f"Wrote {a.output_path}")


if __name__ == "__main__": main()
