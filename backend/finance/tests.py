"""Tests for finance analytics (synthetic data, no dataset needed)."""

from datetime import UTC, date, datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import analytics as a
from .analytics import Tx
from .models import Customer, CustomerProfile, Transaction

SALARY = 3000.0
RENT = 1000.0
SUBSCRIPTION = 12.99


def synthetic_txns(months=24, end=date(2026, 9, 30)):
    """Two years of a tidy customer with known monthly figures.

    Per month: salary 3000 on the 15th, rent 1000 on the 3rd, utilities
    3 x 30, groceries 4 x 50, restaurants 4 x 25, a 12.99 subscription on
    the 20th, two taxi rides of 20 and a 250 investment deposit.
    Monthly spend = 1000 + 90 + 200 + 100 + 12.99 + 40 = 1442.99.
    """
    start_year, start_month = a.shift_month(end.year, end.month, -(months - 1))
    rows = []
    for i in range(months):
        y, m = a.shift_month(start_year, start_month, i)

        def add(day, category, amount, merchant=None, mcc=None):
            rows.append(
                Tx(
                    date(y, m, day),
                    datetime(y, m, day, 12, tzinfo=UTC),
                    category,
                    amount,
                    0.0,
                    "",
                    merchant,
                    mcc,
                )
            )

        add(15, "Salary", SALARY)
        add(3, "Housing", -RENT)
        for day in (5, 12, 25):
            add(day, "Utilities", -30.0)
        for day in (2, 9, 16, 23):
            add(day, "Groceries", -50.0, f"MRC-GRO-{day:04d}", "5411")
        for day in (6, 13, 20, 27):
            add(day, "Restaurants", -25.0, f"MRC-RES-{day + m:04d}", "5812")
        add(20, "Entertainment", -SUBSCRIPTION, "MRC-ENT-SUBS", "7999")
        add(8, "Transportation", -20.0, "MRC-TRN-0001", "4121")
        add(22, "Transportation", -20.0, "MRC-TRN-0002", "4121")
        add(18, "Invest Deposit", -250.0)
    rows = a.prepare(rows)
    # Running balance starting from 500.
    balance = 500.0
    out = []
    for t in rows:
        balance += t.amount
        out.append(
            Tx(
                t.date,
                t.timestamp,
                t.category,
                t.amount,
                balance,
                "",
                t.merchant_id,
                t.mcc,
            )
        )
    return out


MONTHLY_SPEND = RENT + 90 + 200 + 100 + SUBSCRIPTION + 40


class BasketTests(SimpleTestCase):
    def setUp(self):
        self.txns = synthetic_txns()

    def test_movements_and_income_are_not_spend(self):
        for cat in ("Invest Deposit", "Salary Sweep", "Salary"):
            t = Tx(date(2026, 1, 1), None, cat, -10.0, 0.0)
            self.assertIsNone(a.classify_basket(t))

    def test_category_baskets(self):
        cases = {
            "Housing": "mandatory_regular",
            "Groceries": "mandatory_regular",
            "Health": "mandatory_irregular",
            "Travel": "mandatory_irregular",
            "Restaurants": "leakage",
            "Transportation": "leakage",
        }
        for cat, basket in cases.items():
            t = Tx(date(2026, 1, 1), None, cat, -10.0, 0.0)
            self.assertEqual(a.classify_basket(t), basket, cat)

    def test_subscription_detected_and_moved_to_bills(self):
        subs = a.detect_subscriptions(self.txns)
        self.assertEqual([s["merchant_id"] for s in subs], ["MRC-ENT-SUBS"])
        self.assertEqual(subs[0]["monthly_amount"], SUBSCRIPTION)
        t = Tx(
            date(2026, 1, 20),
            None,
            "Entertainment",
            -SUBSCRIPTION,
            0,
            "",
            "MRC-ENT-SUBS",
        )
        self.assertEqual(a.classify_basket(t, {"MRC-ENT-SUBS"}), "mandatory_regular")

    def test_basket_breakdown(self):
        baskets = {b["key"]: b for b in a.basket_breakdown(self.txns)}
        self.assertAlmostEqual(
            baskets["mandatory_regular"]["monthly_avg"],
            RENT + 90 + 200 + SUBSCRIPTION,
        )
        self.assertAlmostEqual(baskets["leakage"]["monthly_avg"], 140.0)
        self.assertAlmostEqual(sum(b["share"] for b in baskets.values()), 1, 3)


class CashflowTests(SimpleTestCase):
    def setUp(self):
        self.txns = synthetic_txns()

    def test_monthly_cashflow(self):
        flow = a.monthly_cashflow(self.txns)
        self.assertEqual(len(flow), 12)
        self.assertEqual(flow[0]["month"], "2025-10")
        self.assertEqual(flow[-1]["month"], "2026-09")
        for m in flow:
            self.assertEqual(m["income"], SALARY)
            self.assertAlmostEqual(m["spend"], MONTHLY_SPEND)

    def test_summary_and_last_month(self):
        head = a.summary(self.txns)
        self.assertAlmostEqual(
            head["savings_rate"], round((SALARY - MONTHLY_SPEND) / SALARY, 4)
        )
        self.assertAlmostEqual(head["balance"], self.txns[-1].balance, 2)
        last = a.last_month_summary(self.txns)
        self.assertEqual(last["month"], "2026-09")
        self.assertAlmostEqual(last["spend"], MONTHLY_SPEND)

    def test_resolve_period(self):
        start, end, label = a.resolve_period("last_month")
        self.assertEqual((start, end), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(label, "September 2026")
        start, _, _ = a.resolve_period("last_3_months")
        self.assertEqual(start, date(2026, 7, 1))
        start, end, _ = a.resolve_period("2026-02")
        self.assertEqual(end, date(2026, 2, 28))
        with self.assertRaises(ValueError):
            a.resolve_period("someday")


class SafeToSpendTests(SimpleTestCase):
    def test_payday_and_bills(self):
        txns = synthetic_txns()
        pay = a.payday_pattern(txns)
        self.assertEqual(pay["cadence"], "monthly")
        self.assertEqual(pay["next_payday"], "2026-10-15")
        sts = a.safe_to_spend(txns)
        self.assertEqual(sts["days_until_payday"], 15)
        labels = {b["label"]: b for b in sts["upcoming_bills"]}
        self.assertEqual(labels["Housing"]["due"], "2026-10-03")
        self.assertEqual(labels["Housing"]["amount"], RENT)
        bills = sum(b["amount"] for b in sts["upcoming_bills"])
        expected = max(0, txns[-1].balance - bills - sts["reserve"])
        self.assertAlmostEqual(sts["amount"], expected, 1)
        self.assertAlmostEqual(sts["per_day"], expected / 15, 1)

    def test_no_salary_falls_back(self):
        txns = [Tx(date(2026, 9, 1), None, "Groceries", -10.0, 90.0)]
        sts = a.safe_to_spend(txns)
        self.assertEqual(sts["next_payday"], "2026-10-30")
        self.assertGreaterEqual(sts["amount"], 0)


class PersonaTests(SimpleTestCase):
    BASE = {
        "savings_rate": 0.05,
        "overdraft_days": 0,
        "invest_rate": 0.0,
        "cushion_months": 1.0,
        "leakage_share": 0.2,
        "weekend_leakage_share": 0.5,
    }

    def key(self, **kw):
        return a.assign_persona({**self.BASE, **kw})[0]

    def test_rules(self):
        self.assertEqual(self.key(), "balanced")
        self.assertEqual(
            self.key(savings_rate=0.0, overdraft_days=30), "paycheck_to_paycheck"
        )
        self.assertEqual(self.key(savings_rate=-0.2), "paycheck_to_paycheck")
        self.assertEqual(self.key(invest_rate=0.1), "investor")
        self.assertEqual(self.key(cushion_months=6), "comfortable")
        self.assertEqual(self.key(savings_rate=0.2), "steady_saver")
        self.assertEqual(self.key(leakage_share=0.4), "weekend_spender")

    def test_persona_payload(self):
        p = a.persona(synthetic_txns())
        self.assertEqual(p["key"], "investor")  # invests 250 / 3000 = 8.3%
        self.assertIn(p["key"], a.PERSONAS)
        self.assertTrue(p["traits"])


class ToolTests(SimpleTestCase):
    def setUp(self):
        self.txns = synthetic_txns()

    def test_taxi_stats(self):
        taxi = a.taxi_stats(self.txns, "last_3_months")
        self.assertEqual(taxi["rides"], 6)
        self.assertEqual(taxi["total"], 120.0)
        self.assertEqual(taxi["avg_per_ride"], 20.0)
        self.assertEqual(taxi["monthly_avg_last_12"], 40.0)

    def test_what_if(self):
        res = a.what_if(self.txns, "Restaurants", 20, years=2)
        self.assertEqual(res["current_monthly"], 100.0)
        self.assertEqual(res["monthly_saving"], 20.0)
        self.assertEqual(res["projection"][0]["saved"], 240.0)
        self.assertGreater(res["projection"][1]["with_interest"], 480.0)
        basket = a.what_if(self.txns, "leakage", 50, years=1)
        self.assertEqual(basket["monthly_saving"], 70.0)

    def test_compare_and_biggest(self):
        cmp = a.compare_months(self.txns, "2026-08", "2026-09")
        self.assertEqual(cmp["diff"], 0.0)
        big = a.biggest_expenses(self.txns, "last_month", 2)["items"]
        self.assertEqual(big[0]["amount"], RENT)
        by_type = a.spend_by_merchant_type(self.txns, "last_month")
        self.assertEqual(by_type["types"][0]["mcc"], None)  # rent, no MCC
        cats = a.spend_by_category(self.txns, "last_month")
        self.assertAlmostEqual(cats["total"], MONTHLY_SPEND)

    def test_category_trend(self):
        trend = a.category_trend(self.txns, "Groceries", 6)
        self.assertEqual(len(trend["months"]), 6)
        self.assertEqual(trend["monthly_avg"], 200.0)
        self.assertEqual(trend["change_pct"], 0.0)

    def test_insights(self):
        items = a.insights(self.txns)
        self.assertTrue(3 <= len(items) <= 5)
        for item in items:
            self.assertIn(item["tone"], {"good", "warn", "info"})
            self.assertTrue(item["text"])


class HomeReadinessTests(SimpleTestCase):
    def test_affordability_rules(self):
        est = a.affordability(3000, 500, 1000)
        self.assertEqual(est["max_payment"], 1050.0)
        loan = est["max_loan"]
        self.assertAlmostEqual(a.annuity_payment(loan), 1050.0, 2)
        self.assertAlmostEqual(
            est["deposit_needed"], est["max_property_price"] * 0.1, 1
        )
        gap = est["deposit_needed"] - 1000
        self.assertEqual(est["months_to_deposit"], -(-gap // 500))
        self.assertIsNone(a.affordability(3000, -10, 0)["months_to_deposit"])

    def test_with_application(self):
        app = {
            "mortgage_customer_id": "C0001",
            "final_decision": "rejected",
            "rejection_reason": "insufficient_equity",
            "final_property_price_eur": 200000,
            "final_requested_loan_eur": 190000,
            "final_equity_amount_eur": 10000,
        }
        events = [
            {"timestamp": datetime(2026, 5, 1), "event_type": "application_created"},
            {
                "timestamp": datetime(2026, 5, 3),
                "event_type": "property_added",
                "property_id": "P1",
                "property_price_estimate": 200000,
            },
            {"timestamp": datetime(2026, 6, 1), "event_type": "loan_decision"},
        ]
        home = a.home_readiness(synthetic_txns(), app, events)
        self.assertTrue(home["has_application"])
        self.assertEqual(home["decision"], "rejected")
        self.assertEqual(home["application"]["days_to_decision"], 31)
        self.assertEqual(home["application"]["properties_considered"], 1)
        self.assertIn("deposit", home["verdict"])

    def test_without_application(self):
        home = a.home_readiness(synthetic_txns())
        self.assertFalse(home["has_application"])
        self.assertIsNone(home["application"])
        self.assertGreater(home["max_property_price"], 0)


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        customer = Customer.objects.create(
            customer_id="CUST99999", customer_postal_code="00100", customer_age=30
        )
        Transaction.objects.bulk_create(
            Transaction(
                customer=customer,
                bank_account_id="ACC1",
                tx_date=t.date,
                tx_timestamp=t.timestamp,
                category=t.category,
                tx_amount_eur=round(t.amount, 2),
                balance_after_eur=round(t.balance, 2),
                transaction_type="",
                merchant_id=t.merchant_id,
                mcc_code=t.mcc,
            )
            for t in synthetic_txns(months=13)
        )

    def test_health(self):
        body = self.client.get(reverse("health")).json()
        self.assertEqual(body["status"], "ok")
        self.assertIn(body["llm"]["provider"], {"gemini", "offline"})
        self.assertEqual(body["data"]["customers"], 1)

    def test_list_and_overview(self):
        body = self.client.get(reverse("customer-list"), {"search": "9999"}).json()
        self.assertEqual(body["count"], 1)
        url = reverse("customer-overview", args=["CUST99999"])
        overview = self.client.get(url).json()
        self.assertEqual(overview["as_of"], "2026-09-30")
        self.assertEqual(len(overview["monthly_cashflow"]), 12)
        self.assertEqual(
            overview["customer"]["persona"]["key"], overview["persona"]["key"]
        )
        missing = self.client.get(reverse("customer-overview", args=["NOPE"]))
        self.assertEqual(missing.status_code, 404)
        self.assertFalse(CustomerProfile.objects.exists())
