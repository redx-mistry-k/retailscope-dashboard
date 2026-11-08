"""Interactive Streamlit smoke check; run with python scripts/smoke_dashboard.py."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def check(app: AppTest, stage: str) -> None:
    errors = [item.message for item in app.exception]
    if errors:
        raise AssertionError(f"{stage}: {errors}")
    assert len(app.tabs) == 6, f"{stage}: expected six sections"
    assert len(app.get("plotly_chart")) >= 7, f"{stage}: charts missing"
    print(f"{stage}: {len(app.get('plotly_chart'))} charts; no app exceptions")


def main() -> None:
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    check(app, "default")
    app.multiselect[0].set_value(["Chennai"])
    app.multiselect[1].set_value(["Kirana", "Mini market"])
    next(item for item in app.slider if item.label == "Total surveyed stores").set_value(480)
    app.run()
    check(app, "filtered")
    assert app.metric[2].value != "9,600 stores", "market filter did not change universe"
    app.button[0].click().run()
    check(app, "simulation")
    assert "design_comparison" in app.session_state
    assert len(app.session_state["design_comparison"]) == 3
    print("filter and simulation controls: OK")


if __name__ == "__main__":
    main()
