#!/usr/bin/env python3
"""Merge SPL3SMP_E v006 daily HDF5 granules into yearly NetCDF files.

The source global EASE-Grid is retained. AM and PM retrievals are separate
variables; only retrievals marked ``Retrieval_recommended`` are retained.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import h5py
import numpy as np
from netCDF4 import Dataset

DATE_RE = re.compile(r"_(\d{8})_")
EPOCH_2000_NOON = dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc).timestamp()


def files_by_year(root: Path, start: int | None, end: int | None) -> dict[int, list[Path]]:
    out: dict[int, list[Path]] = {}
    for path in sorted(root.rglob("SMAP_L3_SM_P_E_*.h5")):
        match = DATE_RE.search(path.name)
        if not match:
            continue
        year = int(match.group(1)[:4])
        if (start and year < start) or (end and year > end):
            continue
        out.setdefault(year, []).append(path)
    return out


def read_pass(handle: h5py.File, group: str, soil: str, tname: str, qname: str) -> tuple[np.ndarray, np.ndarray]:
    g = handle[group]
    sm = g[soil][:].astype(np.float32)
    secs = g[tname][:].astype(np.float64)
    quality = g[qname][:].astype(np.uint16)
    # Bit 0 is Retrieval_recommended.  Source valid range is 0.02--0.5 m3/m3.
    valid = ((quality & 1) != 0) & np.isfinite(sm) & (sm >= 0.02) & (sm <= 0.5) & np.isfinite(secs) & (secs > 0)
    sm[~valid] = np.nan
    minutes = np.full(sm.shape, np.nan, dtype=np.float32)
    minutes[valid] = np.mod((EPOCH_2000_NOON + secs[valid]) / 60.0, 1440.0).astype(np.float32)
    return sm, minutes


def create_output(path: Path, lat: np.ndarray, lon: np.ndarray) -> Dataset:
    path.parent.mkdir(parents=True, exist_ok=True)
    ds = Dataset(path, "w", format="NETCDF4")
    ny, nx = lat.shape
    ds.createDimension("time", None); ds.createDimension("y", ny); ds.createDimension("x", nx)
    t = ds.createVariable("time", "i4", ("time",)); t.units = "days since 1970-01-01 00:00:00"; t.calendar = "standard"
    for name, values, units in (("latitude", lat, "degrees_north"), ("longitude", lon, "degrees_east")):
        v = ds.createVariable(name, "f4", ("y", "x"), zlib=True, complevel=4); v[:] = values; v.units = units
    for name, long_name, units in (
        ("soil_moisture_am", "recommended AM soil moisture", "m3 m-3"),
        ("soil_moisture_pm", "recommended PM soil moisture", "m3 m-3"),
        ("observation_time_min_am", "AM observation time", "minutes since 00:00 UTC"),
        ("observation_time_min_pm", "PM observation time", "minutes since 00:00 UTC"),
    ):
        v = ds.createVariable(name, "f4", ("time", "y", "x"), zlib=True, complevel=4, chunksizes=(1, min(256, ny), min(512, nx)), fill_value=np.float32(np.nan))
        v.units = units; v.long_name = long_name
    ds.title = "Merged SMAP SPL3SMP_E v006 daily soil moisture"
    ds.source = "NSIDC SPL3SMP_E v006"
    ds.quality_filter = "retrieval_qual_flag bit 0 (Retrieval_recommended)"
    return ds


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, default=Path("SPL3SMP_E_v006"))
    p.add_argument("--output-dir", type=Path, default=Path("processed/l3_daily"))
    p.add_argument("--start-year", type=int); p.add_argument("--end-year", type=int)
    p.add_argument("--overwrite", action="store_true")
    a = p.parse_args()
    grouped = files_by_year(a.input_dir, a.start_year, a.end_year)
    if not grouped: raise FileNotFoundError(f"No SPL3SMP_E HDF5 files under {a.input_dir}")
    for year, paths in grouped.items():
        out = a.output_dir / f"SMAP_SPL3SMP_E_daily_{year}.nc"
        if out.exists() and not a.overwrite: raise FileExistsError(f"{out} exists; use --overwrite")
        if out.exists(): out.unlink()
        with h5py.File(paths[0], "r") as src:
            lat = src["Soil_Moisture_Retrieval_Data_AM/latitude"][:]
            lon = src["Soil_Moisture_Retrieval_Data_AM/longitude"][:]
        ds = create_output(out, lat, lon)
        for i, path in enumerate(paths):
            date = dt.datetime.strptime(DATE_RE.search(path.name).group(1), "%Y%m%d").date()
            with h5py.File(path, "r") as src:
                am, tam = read_pass(src, "Soil_Moisture_Retrieval_Data_AM", "soil_moisture", "tb_time_seconds", "retrieval_qual_flag")
                pm, tpm = read_pass(src, "Soil_Moisture_Retrieval_Data_PM", "soil_moisture_dca_pm", "tb_time_seconds_pm", "retrieval_qual_flag_dca_pm")
            ds.variables["time"][i] = (date - dt.date(1970, 1, 1)).days
            ds.variables["soil_moisture_am"][i] = am; ds.variables["soil_moisture_pm"][i] = pm
            ds.variables["observation_time_min_am"][i] = tam; ds.variables["observation_time_min_pm"][i] = tpm
            if (i + 1) % 30 == 0 or i + 1 == len(paths): print(f"{year}: {i + 1}/{len(paths)}")
        ds.close(); print(f"Wrote {out}")


if __name__ == "__main__": main()
