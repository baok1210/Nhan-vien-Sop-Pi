"""Unit tests for CashFlowPlanner — cost calculation, empty state, warnings."""
import json, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.publisher.cashflow_planner import CashFlowPlanner


def _make_fulfillment(tmpdir: str, orders: list[dict]):
    path = Path(tmpdir) / "orders_to_fulfill.json"
    path.write_text(json.dumps(orders, ensure_ascii=False), encoding="utf-8")


def test_empty_fulfillment_returns_no_error():
    """No fulfillment file → no crash, returns empty report."""
    cfg = {"cashflow": {}}
    planner = CashFlowPlanner(cfg, "test_store")
    report = planner.analyze_cash_cycle()
    assert report["summary"]["pending_orders"] == 0
    assert report["forecast"]["peak_capital_needed_vnd"] == 0


def test_cost_calculation_uses_live_rate():
    """Cost must use live exchange rate, not hardcoded 3500*2.5."""
    fulfill = [{
        "order_sn": "ORD001",
        "quantity": 1,
        "source_product_id": "ae_123",
        "order_total": 150000,
    }]
    # Write fulfillment data into data/ path (CashFlowPlanner reads from data/)
    Path("data").mkdir(exist_ok=True)
    (Path("data") / "orders_to_fulfill.json").write_text(
        json.dumps(fulfill), encoding="utf-8"
    )
    # Write pool with cost_cny = 10
    pool = [{"id": "ae_123", "price_cny": 10}]
    (Path("data") / "product_pool.json").write_text(
        json.dumps(pool), encoding="utf-8"
    )
    cfg = {
        "cashflow": {"lead_time_days": 3, "shopee_settlement_days": 1, "buffer_days": 0},
    }
    planner = CashFlowPlanner(cfg, "test_store")
    report = planner.analyze_cash_cycle()
    # Cost = 10 CNY × live rate (no multiplier), should NOT be 10*3500*2.5
    cost = report["summary"]["total_pending_cost_vnd"]
    assert cost > 0, f"Expected positive cost, got {cost}"
    assert cost < 10 * 3500 * 2.5, f"Cost {cost} still includes multiplier (was {10*3500*2.5})"
    # Cleanup
    (Path("data") / "orders_to_fulfill.json").unlink(missing_ok=True)
    (Path("data") / "product_pool.json").unlink(missing_ok=True)


def test_warning_generated_for_high_capital():
    """Peak capital > 50M triggers warning."""
    Path("data").mkdir(exist_ok=True)
    fulfill = []
    pool = []
    # Simulate 10 orders of expensive products
    for i in range(10):
        oid = f"ae_{i}"
        fulfill.append({
            "order_sn": f"ORD{i:03d}",
            "quantity": 10,
            "source_product_id": oid,
            "order_total": 5000000,
        })
        pool.append({"id": oid, "price_cny": 500})
    (Path("data") / "orders_to_fulfill.json").write_text(
        json.dumps(fulfill), encoding="utf-8"
    )
    (Path("data") / "product_pool.json").write_text(
        json.dumps(pool), encoding="utf-8"
    )
    cfg = {"cashflow": {"lead_time_days": 3, "shopee_settlement_days": 1, "buffer_days": 0}}
    planner = CashFlowPlanner(cfg, "test_store")
    report = planner.analyze_cash_cycle()
    # Cost per unit ≈ 500 × live rate (e.g. 3875) = 1,937,500 × 10 qty × 10 orders = 193,750,000
    # which exceeds 50,000,000 threshold
    assert report["warning"] is not None, f"Expected warning, got: peak={report['forecast']['peak_capital_needed_vnd']}"
    assert "⚠️" in report["warning"]
    for f in [Path("data") / "orders_to_fulfill.json", Path("data") / "product_pool.json"]:
        f.unlink(missing_ok=True)


if __name__ == "__main__":
    test_empty_fulfillment_returns_no_error()
    test_cost_calculation_uses_live_rate()
    test_warning_generated_for_high_capital()
    print("ALL PASS")
