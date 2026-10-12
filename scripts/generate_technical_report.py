"""Build the measured, three-page RouteWise PDF report."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.evaluation import evaluate_dataset
from backend.app.services.route_optimizer import load_dataset

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "technical-report.pdf"
INK = colors.HexColor("#17324D")
MUTED = colors.HexColor("#52687D")
TEAL = colors.HexColor("#087E8B")
PALE = colors.HexColor("#EAF4F5")
LINE = colors.HexColor("#D8E2EA")
PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT = 0.68 * inch
RIGHT = PAGE_WIDTH - LEFT
CONTENT_WIDTH = RIGHT - LEFT
BOTTOM = 0.64 * inch

TITLE = ParagraphStyle(
    "Title",
    fontName="Helvetica-Bold",
    fontSize=23,
    leading=27,
    textColor=INK,
    spaceAfter=6,
)
SUBTITLE = ParagraphStyle(
    "Subtitle",
    fontName="Helvetica",
    fontSize=10,
    leading=14,
    textColor=MUTED,
)
HEADING = ParagraphStyle(
    "Heading",
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=16,
    textColor=INK,
    spaceBefore=5,
    spaceAfter=5,
)
BODY = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=9,
    leading=12.3,
    textColor=INK,
    alignment=TA_LEFT,
    spaceAfter=7,
)
SMALL = ParagraphStyle(
    "Small",
    fontName="Helvetica",
    fontSize=8,
    leading=10.2,
    textColor=MUTED,
    spaceAfter=6,
)
FORMULA = ParagraphStyle(
    "Formula",
    fontName="Helvetica-Bold",
    fontSize=9,
    leading=13,
    textColor=INK,
    backColor=PALE,
    borderColor=LINE,
    borderWidth=0.5,
    borderPadding=8,
    spaceBefore=2,
    spaceAfter=8,
)
TABLE_TEXT = ParagraphStyle(
    "TableText",
    fontName="Helvetica",
    fontSize=7.4,
    leading=9,
    textColor=INK,
)
TABLE_HEAD = ParagraphStyle(
    "TableHead",
    fontName="Helvetica-Bold",
    fontSize=7.5,
    leading=9,
    textColor=colors.white,
)


class Report:
    def __init__(self, pdf: canvas.Canvas) -> None:
        self.pdf = pdf
        self.y = PAGE_HEIGHT - 0.7 * inch
        self.page_number = 1

    def paragraph(self, text: str, style: ParagraphStyle = BODY, gap: float = 0) -> None:
        item = Paragraph(text, style)
        _, height = item.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
        if self.y - height < BOTTOM + 22:
            raise RuntimeError(
                f"Technical report page {self.page_number} overflowed; "
                "reduce or reflow the page content before writing the PDF."
            )
        item.drawOn(self.pdf, LEFT, self.y - height)
        self.y -= height + gap

    def table(
        self,
        rows: list[list[Any]],
        widths: list[float],
    ) -> None:
        formatted = [
            [Paragraph(str(value), TABLE_HEAD if index == 0 else TABLE_TEXT)
             for value in row]
            for index, row in enumerate(rows)
        ]
        item = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        item.wrapOn(self.pdf, CONTENT_WIDTH, PAGE_HEIGHT)
        _, height = item.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
        if self.y - height < BOTTOM + 22:
            raise RuntimeError(
                f"Technical report table overflows page {self.page_number}."
            )
        item.drawOn(self.pdf, LEFT, self.y - height)
        self.y -= height + 8

    def heading(self, text: str) -> None:
        self.paragraph(text, HEADING)

    def new_page(self, title: str) -> None:
        self.footer()
        self.pdf.showPage()
        self.page_number += 1
        self.y = PAGE_HEIGHT - 0.72 * inch
        self.pdf.setFillColor(TEAL)
        self.pdf.setFont("Helvetica-Bold", 8)
        self.pdf.drawString(LEFT, PAGE_HEIGHT - 0.45 * inch, "ROUTEWISE  /  TECHNICAL REPORT")
        self.paragraph(title, HEADING, gap=5)

    def footer(self) -> None:
        self.pdf.setStrokeColor(LINE)
        self.pdf.line(LEFT, BOTTOM + 13, RIGHT, BOTTOM + 13)
        self.pdf.setFillColor(MUTED)
        self.pdf.setFont("Helvetica", 7.5)
        self.pdf.drawString(LEFT, BOTTOM, "Synthetic assignment prototype · Illustrative assumptions only")
        self.pdf.drawRightString(RIGHT, BOTTOM, f"{self.page_number} / 3")


def _strategy_table(evaluation: dict[str, Any]) -> list[list[str]]:
    rows = [[
        "Strategy",
        "Avg cost<br/>(USD)",
        "Avg time<br/>(days)",
        "Avg risk",
        "Avg balanced<br/>penalty",
    ]]
    names = (
        ("weighted_optimizer", "Weighted"),
        ("cheapest_feasible", "Cheapest"),
        ("fastest_feasible", "Fastest"),
        ("reliability_oriented", "Reliability"),
    )
    for key, label in names:
        summary = evaluation["results"][key]
        rows.append(
            [
                label,
                f"{summary['average_cost_usd']:,.2f}",
                f"{summary['average_transit_days']:.2f}",
                f"{summary['average_risk_penalty']:.6f}",
                f"{summary['average_total_penalty']:.6f}",
            ]
        )
    return rows


def generate_report() -> Path:
    shipments, routes = load_dataset(Path(__file__).resolve().parents[1] / "data")
    result = evaluate_dataset(shipments, routes)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=letter, pageCompression=1)
    pdf.setTitle("RouteWise — Explainable Shipment Route Optimizer")
    pdf.setAuthor("RouteWise")
    report = Report(pdf)

    pdf.setFillColor(TEAL)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(LEFT, PAGE_HEIGHT - 0.42 * inch, "ROUTEWISE  /  TECHNICAL REPORT")
    report.y = PAGE_HEIGHT - 0.92 * inch
    report.paragraph("Explainable Shipment<br/>Route Optimizer", TITLE)
    report.paragraph(
        "Method, architecture, and measured outcomes · Assignment prototype",
        SUBTITLE,
        gap=9,
    )
    report.heading("Problem and scope")
    report.paragraph(
        "RouteWise compares candidate transport routes where spend, delivery time, "
        "and risk trade off. It is a local decision-support demonstration, not a "
        "carrier forecast or production recommendation. No machine-learning model "
        "is trained."
    )
    report.paragraph(
        "The fixed-seed synthetic dataset contains <b>30 shipments</b> and "
        f"<b>{len(routes)} candidate routes</b> "
        f"(four per shipment). <b>{result['shipments_with_feasible_routes']}</b> "
        "shipments have at least one route meeting all limits; "
        f"<b>{result['shipments_without_feasible_routes']}</b> have none. "
        f"There are <b>{result['pareto_frontier']['eligible_route_count']}</b> "
        "computed-feasible route records."
    )
    report.heading("System design")
    report.paragraph(
        "A React and TypeScript dashboard calls typed FastAPI endpoints. Pydantic "
        "validates API inputs; the Python route optimizer is the single authority "
        "for computed feasibility, normalization, scoring, ranking, and "
        "explanations. A separate evaluation service reuses that engine for "
        "profile sensitivity and feasible-route baselines. The CSV files are "
        "loaded using paths relative to the project. Optional Groq commentary "
        "uses minimized computed facts and deterministic local fallback."
    )
    report.paragraph(
        "<b>Core safety rule:</b> stored CSV feasibility flags are audit targets, "
        "not the selection source. All five mandatory limits are recomputed, and "
        "a shipment with no eligible route returns no recommendation plus "
        "candidate-specific rejection reasons.",
        FORMULA,
    )

    report.new_page("Optimization methodology")
    report.paragraph(
        "For each candidate, cost (USD), transit days, delay probability, "
        "congestion risk, and geopolitical risk must all be no greater than the "
        "shipment's corresponding maximum. Invalid or missing values are rejected. "
        "Optional request overrides replace supported maxima for that call."
    )
    report.heading("Objective")
    report.paragraph(
        "Cost and time are min-max normalized among computed-feasible routes for "
        "the same shipment. Equal values map to neutral 0.5. Risk remains a "
        "unit-interval weighted sum. The lower objective ranks first.",
        BODY,
    )
    report.paragraph(
        "Risk = 0.50 × delay + 0.25 × congestion + 0.25 × geopolitical risk<br/>"
        "Penalty = w<sub>cost</sub> × normalized cost + "
        "w<sub>time</sub> × normalized time + "
        "w<sub>risk</sub> × risk",
        FORMULA,
    )
    report.paragraph(
        "The coefficients are illustrative assumptions, not estimates learned "
        "from observed outcomes. Weights are finite, nonnegative, and sum to one "
        "within 1e-9. Presets are cost-sensitive, balanced (0.40/0.30/0.30), "
        "time-sensitive, and reliability-sensitive. Route ID breaks equal "
        "displayed-score ties deterministically."
    )
    report.heading("Evaluation protocol")
    report.paragraph(
        "The weighted optimizer is compared with the cheapest, fastest, and "
        "lowest-risk computed-feasible candidates. Each selected route is "
        "evaluated with the balanced objective for comparison. Feasibility rate "
        "uses all 30 shipments as its denominator. Pareto analysis minimizes "
        "cost, duration, and illustrative risk independently for each shipment."
    )
    report.paragraph(
        "A baseline is a selection rule, not ground truth. A lower score or a "
        "lower individual metric on these generated records does not establish "
        "real-world optimality, predictive accuracy, or savings.",
        SMALL,
    )

    report.new_page("Measured results and limitations")
    report.paragraph(
        f"Balanced-profile evaluation: {result['shipment_count']} shipments, "
        f"{result['shipments_with_feasible_routes']} with an eligible route, "
        f"{result['shipments_without_feasible_routes']} with none. Feasibility "
        f"label mismatches: {result['feasibility_label_mismatch_warnings']}. "
        "Every reported strategy has zero constraint violations.",
        BODY,
    )
    report.table(
        _strategy_table(result),
        [1.16 * inch, 1.10 * inch, 0.92 * inch, 0.86 * inch, 1.1 * inch],
    )
    sensitivity = result["profile_sensitivity"]
    balanced = sensitivity["balanced"]
    changes = {
        name: sum(
            counts.get(route_id, 0) != balanced.get(route_id, 0)
            for route_id in set(counts) | set(balanced)
        ) // 2
        for name, counts in sensitivity.items()
        if name != "balanced"
    }
    report.paragraph(
        "Against balanced, profile changes were "
        f"{changes['cost_sensitive']} cost-sensitive, "
        f"{changes['time_sensitive']} time-sensitive, and "
        f"{changes['reliability_sensitive']} reliability-sensitive selections "
        f"out of {result['shipments_with_feasible_routes']} feasible shipments. "
        f"The per-shipment Pareto frontiers contain "
        f"{result['pareto_frontier']['non_dominated_route_count']} of "
        f"{result['pareto_frontier']['eligible_route_count']} feasible routes "
        f"(average size {result['pareto_frontier']['average_frontier_size_per_feasible_shipment']})."
    )
    report.heading("Hypothetical disruption analysis")
    report.paragraph(
        "The Disruption Lab applies bounded deterministic risk increments and "
        "cost/time percentage changes to copied route records, then reuses the "
        "optimizer to recompute feasibility and rankings. It reports per-route "
        "metric changes, rejections, feasible counts, recommendation switches, "
        "and fallback availability. The source dataset is not mutated; if no "
        "candidate passes the active limits, the result has no recommendation. "
        "This is illustrative scenario analysis, not a forecast or measured "
        "resilience claim.",
        SMALL,
    )
    report.heading("Interpretation and limits")
    report.paragraph(
        "In this snapshot, the weighted strategy's mean balanced penalty is "
        f"{result['results']['weighted_optimizer']['average_total_penalty']:.6f}; "
        "the cheapest baseline has lower mean spend but a higher mean balanced "
        "penalty and longer mean transit time. The fastest baseline averages "
        f"{result['results']['fastest_feasible']['average_transit_days']:.2f} days "
        "at higher mean cost. The reliability-oriented baseline has the lowest "
        "mean illustrative risk penalty. These are descriptive trade-offs, not "
        "business outcomes."
    )
    report.paragraph(
        "The dataset is small, synthetic, and fixed-seed; profiles and risk "
        "coefficients have not been calibrated. Capacity, schedules, emissions, "
        "uncertainty, and live disruptions are outside the model. Validate "
        "constraints and scoring with logistics stakeholders and governed "
        "operational data before any real use. Future evaluation should include "
        "observed disruptions, freshness controls, human review, and additional "
        "stakeholder-approved objectives.",
        SMALL,
    )

    if report.page_number != 3:
        raise RuntimeError(f"Expected a 3-page report, got {report.page_number} pages.")
    report.footer()
    pdf.save()
    return OUTPUT


if __name__ == "__main__":
    print(f"Wrote {generate_report()}")
