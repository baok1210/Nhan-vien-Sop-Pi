"""Cash-Flow & Capital Planner — tracks order-to-payment cash cycle and forecasts
working capital needs for the next 7-14 days.

Uses historical order data from Shopee, cost data from 1688/AliExpress, and
configurable lead times to predict capital requirements.
"""
import json, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
from src.utils.logger import setup_logger
from src.utils.exchange_rate import get_cny_vnd_rate, FALLBACK_RATE

logger = setup_logger("cashflow_planner")

DATA_DIR = Path("data")


class CashFlowPlanner:
    def __init__(self, config: dict, store_id: str):
        self.store_id = store_id
        self.store_dir = DATA_DIR / store_id
        cf = config.get("cashflow", {})
        self.lead_time_days = int(cf.get("lead_time_days", 7))
        self.shopee_settlement_days = int(cf.get("shopee_settlement_days", 3))
        self.buffer_days = int(cf.get("buffer_days", 2))
        self.daily_capital_reserve = float(cf.get("daily_capital_reserve", 0))
        self.price_multiplier = float(config.get("niche", {}).get("price_multiplier", 2.5))

    # ── Data loaders ──────────────────────────────────────────────

    def load_fulfillment_data(self) -> list[dict]:
        path = DATA_DIR / "orders_to_fulfill.json"
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load fulfillment data: {e}")
            return []

    def load_product_pool(self) -> dict[str, dict]:
        path = DATA_DIR / "product_pool.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                return {i.get("id", ""): i for i in items}
            return items
        except Exception:
            return {}

    def load_pricing_report(self) -> dict[str, dict]:
        path = self.store_dir / "pricing_report.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {p.get("product_id", ""): p for p in data}
            return {p.get("product_id", ""): p for p in data.get("products", [])}
        except Exception:
            return {}

    # ── Cash flow analysis ────────────────────────────────────────

    def analyze_cash_cycle(self) -> dict:
        fulfillment = self.load_fulfillment_data()
        pool = self.load_product_pool()
        pricing = self.load_pricing_report()

        if not fulfillment:
            return self._empty_report("No fulfillment data")

        total_pending_cost = 0.0
        total_receivable = 0.0
        total_profit = 0.0
        product_counts: dict[str, int] = defaultdict(int)
        daily_projections: dict[str, dict] = {}

        today = datetime.now().date()
        for order in fulfillment:
            qty = order.get("quantity", 1)
            order_sn = order.get("order_sn", "")
            source_id = order.get("source_product_id", "")
            price_vnd = order.get("order_total", 0)
            if isinstance(price_vnd, str):
                try:
                    price_vnd = float(price_vnd)
                except ValueError:
                    price_vnd = 0

            # Cost from pool
            pool_item = pool.get(source_id, {})
            cost_cny = float(pool_item.get("price_cny", 0))

            # Final price from pricing report
            pricing_item = pricing.get(source_id, {})
            final_price = float(pricing_item.get("final_price_vnd", price_vnd))

            # Margin info: cost = CNY→VND (no multiplier), receivable = selling price
            try:
                rate = asyncio.run(get_cny_vnd_rate())
            except RuntimeError:
                rate = FALLBACK_RATE
            cost_vnd = cost_cny * rate
            receivable = final_price * qty if final_price else price_vnd * qty
            cost = cost_vnd * qty

            total_pending_cost += cost
            total_receivable += receivable
            total_profit += receivable - cost
            product_counts[source_id] += qty

            # Project cash-out day (order placed + lead time)
            order_date = today
            cash_out_day = today + timedelta(days=self.lead_time_days)
            cash_in_day = cash_out_day + timedelta(days=self.shopee_settlement_days)

            for label, day, amount in [
                ("cash_out", cash_out_day.isoformat(), cost),
                ("cash_in", cash_in_day.isoformat(), receivable),
            ]:
                if label not in daily_projections:
                    daily_projections[label] = {}
                day_str = day
                daily_projections[label][day_str] = \
                    daily_projections[label].get(day_str, 0) + amount

        # Calculate net daily projection
        net_daily = defaultdict(float)
        for typ, days in daily_projections.items():
            for day_str, amount in days.items():
                if typ == "cash_in":
                    net_daily[day_str] += amount
                else:
                    net_daily[day_str] -= amount

        # 7-day and 14-day forecast
        forecast_7 = sum(
            net_daily[(today + timedelta(days=d)).isoformat()]
            for d in range(7)
        )
        forecast_14 = forecast_7 + sum(
            net_daily[(today + timedelta(days=d)).isoformat()]
            for d in range(7, 14)
        )

        # Peak capital needed (maximum negative cumulative)
        cumulative = 0.0
        peak_capital = 0.0
        peak_day = today.isoformat()
        sorted_days = sorted(net_daily.keys())
        for day_str in sorted_days:
            cumulative += net_daily[day_str]
            if cumulative < peak_capital:
                peak_capital = cumulative
                peak_day = day_str

        peak_capital_needed = abs(peak_capital)
        reserve_needed = peak_capital_needed + self.daily_capital_reserve * 14

        report = {
            "store_id": self.store_id,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "pending_orders": len(fulfillment),
                "total_pending_cost_vnd": round(total_pending_cost),
                "total_receivable_vnd": round(total_receivable),
                "estimated_profit_vnd": round(total_profit),
                "profit_margin_pct": round(
                    total_profit / total_receivable * 100, 1
                ) if total_receivable else 0,
            },
            "forecast": {
                "forecast_7day_net_vnd": round(forecast_7),
                "forecast_14day_net_vnd": round(forecast_14),
                "peak_capital_needed_vnd": round(peak_capital_needed),
                "peak_capital_day": peak_day,
                "recommended_reserve_vnd": round(reserve_needed),
            },
            "daily_projections": dict(sorted(net_daily.items())),
            "lead_time_days": self.lead_time_days,
            "settlement_days": self.shopee_settlement_days,
            "buffer_days": self.buffer_days,
            "warning": None,
        }

        # Generate warnings
        if peak_capital_needed > 50_000_000:
            report["warning"] = (
                f"⚠️ Cần {peak_capital_needed:,.0f} VND vốn lưu động "
                f"trong {self.lead_time_days} ngày tới. "
                f"Chuẩn bị ứng trước tiền nhập hàng!"
            )
        elif peak_capital_needed > 20_000_000:
            report["warning"] = (
                f"⚠️ Dự kiến cần {peak_capital_needed:,.0f} VND "
                f"cho đơn hàng nguồn trong tuần tới."
            )
        else:
            report["warning"] = None

        return report

    def _empty_report(self, reason: str) -> dict:
        return {
            "store_id": self.store_id,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "pending_orders": 0,
                "total_pending_cost_vnd": 0,
                "total_receivable_vnd": 0,
                "estimated_profit_vnd": 0,
                "profit_margin_pct": 0,
            },
            "forecast": {
                "forecast_7day_net_vnd": 0,
                "forecast_14day_net_vnd": 0,
                "peak_capital_needed_vnd": 0,
                "peak_capital_day": "",
                "recommended_reserve_vnd": 0,
            },
            "daily_projections": {},
            "warning": None,
            "error": reason,
        }

    def save_report(self, report: dict):
        path = self.store_dir / "cashflow_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Cash flow report saved to {path}")
        if report.get("warning"):
            logger.warning(report["warning"])

    def run(self) -> dict:
        report = self.analyze_cash_cycle()
        self.save_report(report)
        return report
