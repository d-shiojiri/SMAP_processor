#!/usr/bin/env python3
"""Run the AMSR CDF matcher on the AMSR-compatible SMAP 0.5-degree file.

This is intentionally a thin SMAP-default wrapper around the canonical
``AMSR_processor/cdf_match_amsr_modules`` implementation. Consequently the
CDF output retains the exact AMSR A/D-slot NetCDF contract.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_AMSR_ROOT = Path("/data02/shiojiri/DATA/AMSR")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_path", nargs="?", type=Path, default=Path("processed/l3_daily_0p5/SMAP_SMC_daily_0p5deg_avg.nc"), help="AMSR-slot-compatible SMAP input NetCDF.")
    p.add_argument("--reference-dict", default="reference_paths_template.json")
    p.add_argument("--reference-var", default="SoilMoistV")
    p.add_argument("--reference-time", default=None); p.add_argument("--reference-lat", default=None); p.add_argument("--reference-lon", default=None)
    p.add_argument("--reference-depth", type=int, default=0)
    p.add_argument("--start", default=None); p.add_argument("--end", default=None)
    p.add_argument("--step-hours", type=float, default=24.0); p.add_argument("--window-hours", type=float, default=24.0)
    p.add_argument("--output-dir", type=Path, default=Path("processed/l3_daily_0p5"))
    p.add_argument("--output-mode", choices=("merged", "per-file"), default="merged")
    p.add_argument("--output-file", type=Path, default=Path("SMAP_SMC_daily_0p5deg_cdf.nc"))
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--reference-cache-size", type=int, default=32)
    p.add_argument("--amsr-root", type=Path, default=DEFAULT_AMSR_ROOT, help="Directory containing cdf_match_amsr_modules (default: %(default)s).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    module_root = args.amsr_root.resolve()
    if not (module_root / "cdf_match_amsr_modules" / "pipeline.py").is_file():
        raise FileNotFoundError(f"AMSR CDF module not found under: {module_root}")
    sys.path.insert(0, str(module_root))
    from cdf_match_amsr_modules.pipeline import CDFMatchConfig, run_cdf_matching

    run_cdf_matching(CDFMatchConfig(
        input_path=args.input_path, reference=None, reference_dict=args.reference_dict,
        reference_time=args.reference_time, reference_lat=args.reference_lat,
        reference_lon=args.reference_lon, reference_var=args.reference_var,
        start=args.start, end=args.end, step_hours=args.step_hours,
        window_hours=args.window_hours, output_dir=args.output_dir,
        output_mode=args.output_mode, output_file=args.output_file,
        overwrite=args.overwrite, reference_cache_size=args.reference_cache_size,
        reference_depth=args.reference_depth,
    ))


if __name__ == "__main__":
    main()
