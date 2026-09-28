# SMAP SPL3SMP_E v006 processor

This repository processes the downloaded SMAP Enhanced L3 daily 9 km soil-moisture product (`SPL3SMP_E`, version 6) in three stages compatible with the AMSR processor workflow. Source HDF5 and generated NetCDF files are deliberately excluded from Git.

## Requirements

Python 3.10+ with `numpy`, `h5py`, and `netCDF4`:

```bash
python3 -m pip install numpy h5py netCDF4
```

## Workflow

Run all commands from this directory.

```bash
# 1. Merge daily HDF5 files into yearly 9 km EASE-Grid NetCDF files.
python3 merge_smap_l3_daily.py --overwrite

# 2. Average both AM and PM fields to 0.5-degree daily grids.
python3 upscale_smap_l3_0p5deg.py --overwrite

# 3. Grid-wise empirical CDF matching against the reference specified below.
python3 cdf_match_smap.py --overwrite
```

Stage 1 retains the `Retrieval_recommended` quality-flagged values only and keeps AM/PM as separate variables. Stage 2 computes daily mean, observation count, and mean observation time independently for AM and PM. Stage 3 maps each 0.5-degree SMAP cell independently to the reference distribution using paired dates; it preserves observation-time and count variables.

`reference_paths_template.json` is a template for the reference soil-moisture NetCDF files. Edit it for the actual reference location and period. Reference files must provide `time`, 1-D `lat`/`lon`, and `SoilMoistV` (or specify `--reference-var`); a depth dimension is supported via `--reference-depth`.

## Download

The downloader reads an Earthdata token from `~/.earthdata_token` (or `EARTHDATA_TOKEN`) and stores source files under `SPL3SMP_E_v006/YYYY/`.

```bash
python3 download_spl3smp_e_v6.py
```
