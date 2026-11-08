"""Regenerate portfolio exports for the documented default synthetic scenario."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retailscope.data import STORE_TYPES, draw_sample, generate_population  # noqa: E402
from retailscope.reporting import build_pdf_report, export_csv  # noqa: E402
from retailscope.stats import estimate_market, summarize_regions  # noqa: E402


def main() -> None:
    population = generate_population(9600, seed=2026)
    sample = draw_sample(population, 720, seed=77)
    estimate = estimate_market(population, sample)
    regional = summarize_regions(population, sample)
    out = ROOT / "sample_outputs"
    out.mkdir(exist_ok=True)
    (out / "RetailScope_Regional_Estimates.csv").write_bytes(export_csv(regional))
    sample_columns = ["store_id", "region", "store_type", "observed_sales_inr", "response_status"]
    (out / "RetailScope_Survey_Sample.csv").write_bytes(export_csv(sample[sample_columns]))
    (out / "RetailScope_Stakeholder_Report.pdf").write_bytes(build_pdf_report(
        "Tamil Nadu (synthetic scenario)", estimate, regional, sample,
        confidence=.95, seed=77, selected_types=list(STORE_TYPES),
    ))
    for path in sorted(out.glob("RetailScope_*")):
        print(f"{path.name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
