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

# 2. Average to the AMSR slot-compatible 0.5-degree daily grid.
python3 upscale_smap_l3_0p5deg.py --overwrite

# 3. CDF match using the AMSR implementation through the SMAP wrapper.
python3 cdf_match_smap.py --overwrite
```

Stage 1 retains the `Retrieval_recommended` quality-flagged values only and keeps AM/PM as separate variables. Stage 2 writes AM as `soil_moisture_A_01` and PM as `soil_moisture_D_01`, with matching `observation_time_min_*` variables. Those exact slot names and `(time, lat, lon)` layout are required by `AMSR_processor`'s query and CDF modules. Soil moisture is converted from the SMAP source unit (m3/m3) to the AMSR-compatible percent convention.

`cdf_match_smap.py` calls the same CDF module used for AMSR and therefore writes the same A/D-slot layout. Its default output is `processed/l3_daily_0p5/SMAP_SMC_daily_0p5deg_cdf.nc`.

`reference_paths_template.json` is a template for the reference soil-moisture NetCDF files. Edit it for the actual reference location and period. Reference files must provide `time`, 1-D `lat`/`lon`, and `SoilMoistV` (or specify `--reference-var`); a depth dimension is supported via `--reference-depth`.

## Download

The downloader reads an Earthdata token from `~/.earthdata_token` (or `EARTHDATA_TOKEN`) and stores source files under `SPL3SMP_E_v006/YYYY/`.

```bash
python3 download_spl3smp_e_v6.py
```
