"""Stakeholder-ready PDF report and CSV exports."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

from .stats import Estimate

NAVY = colors.HexColor("#101F33")
TEAL = colors.HexColor("#087C88")
GREY = colors.HexColor("#58677A")
LIGHT = colors.HexColor("#E8F4F5")
WHITE = colors.white
LINE = colors.HexColor("#DFE6EB")


def format_inr_crore(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"INR {value / 10_000_000:,.2f} Cr"


def export_csv(frame: pd.DataFrame) -> bytes:
    """Export a table with provenance embedded in every row."""
    data = frame.copy()
    data.insert(0, "data_provenance", "Synthetic simulation; not real NIQ or Tamil Nadu market data")
    return data.to_csv(index=False).encode("utf-8-sig")


def build_pdf_report(market_name: str, overall: Estimate, regional: pd.DataFrame,
                     sample: pd.DataFrame, confidence: float,
                     seed: int, selected_types: list[str],
                     generated_at: datetime | None = None) -> bytes:
    """Generate a two-page PDF. Source data is explicitly marked synthetic."""
    generated_at = generated_at or datetime.now()
    quality_missing = int(sample.observed_sales_inr.isna().sum())
    output = BytesIO()
    page_width, page_height = A4
    doc = BaseDocTemplate(output, pagesize=A4,
                          leftMargin=19 * mm, rightMargin=19 * mm,
                          topMargin=23 * mm, bottomMargin=19 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def decoration(canvas, document):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, page_height - 13 * mm, page_width, 13 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(WHITE)
        canvas.drawString(19 * mm, page_height - 8.5 * mm, "RETAILSCOPE / INTELLIGENCE REPORT")
        canvas.setStrokeColor(LINE)
        canvas.line(19 * mm, 14 * mm, page_width - 19 * mm, 14 * mm)
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(19 * mm, 10 * mm, "SYNTHETIC DATA  |  PORTFOLIO DEMONSTRATION")
        canvas.drawRightString(page_width - 19 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.addPageTemplates(PageTemplate(id="standard", frames=frame, onPage=decoration))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="HeroCustom", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=20, leading=24, textColor=NAVY, spaceAfter=9))
    styles.add(ParagraphStyle(name="SectionCustom", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=11.5, leading=15, textColor=NAVY, spaceBefore=13, spaceAfter=7))
    styles.add(ParagraphStyle(name="BodyCustom", parent=styles["BodyText"], fontSize=9,
                              leading=14, textColor=NAVY, spaceAfter=8))
    styles.add(ParagraphStyle(name="NoteCustom", parent=styles["BodyText"], fontSize=8,
                              leading=11.5, textColor=GREY, spaceAfter=7))
    styles.add(ParagraphStyle(name="MetricLabelCustom", fontName="Helvetica", fontSize=8,
                              leading=10, textColor=GREY, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="MetricValueCustom", fontName="Helvetica-Bold", fontSize=13,
                              leading=17, textColor=NAVY, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="TableHdrCustom", fontName="Helvetica-Bold", fontSize=8,
                              leading=11, textColor=WHITE, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="TableValCustom", fontName="Helvetica", fontSize=7.7,
                              leading=11, textColor=NAVY))

    P = lambda text, style="BodyCustom": Paragraph(escape(str(text)), styles[style])
    story = []
    story.append(Spacer(1, 4 * mm))
    story.append(P("Retail market intelligence", "HeroCustom"))
    story.append(P(f"{market_name}  |  Monthly sales estimate  |  {generated_at:%d %b %Y}", "NoteCustom"))
    story.append(P("Executive summary", "SectionCustom"))
    story.append(P(
        "This report estimates monthly FMCG retail sales from a simulated, stratified store survey. "
        "Figures are instructional, not actual market measurements or NIQ outputs."
    ))

    metrics = [
        ("Estimated monthly sales", format_inr_crore(overall.estimate_inr)),
        ("Estimated sales interval", f"{format_inr_crore(overall.ci_low_inr)} to {format_inr_crore(overall.ci_high_inr)}"),
        ("Stores in assumed universe", f"{overall.universe_n:,}"),
        ("Surveyed / response rate", f"{overall.sampled_n:,} / {overall.response_rate_pct:.1f}%"),
    ]
    cards = []
    for label, value in metrics:
        cards.append([P(label, "MetricLabelCustom"), P(value, "MetricValueCustom")])
    card_table = Table([[cards[0], cards[2]], [cards[1], cards[3]]], colWidths=[85 * mm, 85 * mm], rowHeights=[25 * mm, 25 * mm])
    card_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), .5, WHITE),
        ("LINEBEFORE", (1, 0), (1, -1), .5, WHITE),
    ]))
    story.append(card_table)
    story.append(P("Regional estimates", "SectionCustom"))
    header = ["Market", "Stores", "Responses", "Sales (INR Cr)", f"{confidence:.0%} interval (Cr)"]
    rows = [[P(c, "TableHdrCustom") for c in header]]
    for _, r in regional.iterrows():
        est = r.market_sales_inr / 10_000_000
        interval = (f"{r.ci_low_inr / 10_000_000:,.1f} - "
                    f"{r.ci_high_inr / 10_000_000:,.1f}") if pd.notna(r.ci_low_inr) else "N/A"
        rows.append([P(r.region, "TableValCustom"), P(f"{int(r.universe_stores):,}", "TableValCustom"),
                     P(int(r.responding_stores), "TableValCustom"),
                     P(f"{est:,.1f}" if pd.notna(est) else "N/A", "TableValCustom"),
                     P(interval, "TableValCustom")])
    table = Table(rows, colWidths=[39 * mm, 24 * mm, 27 * mm, 32 * mm, 48 * mm], repeatRows=1,
                  hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F4F7F8")]),
        ("LINEBELOW", (0, -1), (-1, -1), .5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(table)
    story.append(Spacer(1, 2 * mm))
    story.append(P("Intervals indicate modelled sampling uncertainty under the stated survey assumptions; they do not capture coverage, measurement or nonresponse bias.", "NoteCustom"))
    story.append(PageBreak())
    story.append(Spacer(1, 4 * mm))
    story.append(P("Methodology & quality", "HeroCustom"))
    story.append(P("Survey design", "SectionCustom"))
    story.append(P(
        "Synthetic finite population with store-level monthly FMCG sales; independent simple random samples "
        "without replacement within region-by-store-type strata. The population counts are assumed known "
        "for this demonstration. Store counts are not themselves estimated from an incomplete retail frame."
    ))
    story.append(P("Estimation", "SectionCustom"))
    story.append(P(
        "For each stratum, estimated market sales = population store count multiplied by the mean sales "
        "among responding sampled stores. The sum of stratum estimates gives the selected market total. "
        "Within-stratum respondent counts are used to adjust for simulated missing sales, which requires "
        "a missing-at-random-within-stratum assumption."
    ))
    story.append(P("Uncertainty", "SectionCustom"))
    story.append(P(
        f"Two-sided {confidence:.0%} normal-approximation confidence intervals are calculated from the "
        "sum of stratum variances with finite-population correction. These intervals are approximate, "
        "particularly with small samples or non-random nonresponse."
    ))
    story.append(P("Data quality & study scope", "SectionCustom"))
    story.append(P(f"Selected sample: {len(sample):,} stores; missing sales submissions: {quality_missing:,}; "
                   f"responding stores: {overall.responded_n:,}; analysis seed: {seed}."))
    story.append(P(f"Included store formats: {', '.join(selected_types)}."))
    story.append(P("Interpretation and next steps", "SectionCustom"))
    for paragraph in [
        "Use regional estimates to prioritise fieldwork and identify imprecise markets.",
        "Review low-response strata, unexpected sales values and coverage gaps before communicating results.",
        "To use this in a real retail index, validate the store universe, fieldwork design, data governance and frame quality; add appropriate nonresponse and calibration procedures.",
    ]:
        story.append(P("- " + paragraph))
    story.append(Spacer(1, 6 * mm))
    story.append(P("Important: All stores, regional totals and sales values in this project are simulated. Not affiliated with or endorsed by NielsenIQ.", "NoteCustom"))
    doc.build(story)
    return output.getvalue()
