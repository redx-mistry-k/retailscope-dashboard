from pathlib import Path

import pytest

from retailscope.data import STORE_TYPES, draw_sample, generate_population
from retailscope.reporting import build_pdf_report, export_csv, format_inr_crore
from retailscope.stats import estimate_market, summarize_regions


def test_reporting_units():
    assert format_inr_crore(10_000_000) == "INR 1.00 Cr"
    assert format_inr_crore(87_500_000) == "INR 8.75 Cr"


def test_csv_export_embeds_synthetic_provenance():
    import io
    import pandas as pd

    source = pd.DataFrame({"region": ["Chennai"], "market_sales_inr": [123.0]})
    exported = pd.read_csv(io.BytesIO(export_csv(source)))
    assert exported.loc[0, "data_provenance"].startswith("Synthetic simulation")
    assert exported.loc[0, "market_sales_inr"] == 123.0


def test_pdf_generation_is_valid_nonempty_bytes(tmp_path):
    pop = generate_population(1000, 7)
    sample = draw_sample(pop, 240, 2, nonresponse_rate=0)
    estimate = estimate_market(pop, sample)
    regions = summarize_regions(pop, sample)
    pdf = build_pdf_report("Tamil Nadu", estimate, regions, sample,
                           confidence=0.95, seed=2, selected_types=list(STORE_TYPES))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2500
    filename = tmp_path / "sample.pdf"
    filename.write_bytes(pdf)
    assert filename.stat().st_size == len(pdf)
