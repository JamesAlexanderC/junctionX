"""Tests for the Money Coach: router, tools, SSE view and the Gemini loop.

No dataset or API key needed: customers are synthetic (see finance.tests)
and the Gemini client is a fake that replays scripted responses.
"""

import json
from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from google.genai import types

from finance import analytics as a
from finance.models import Customer, Transaction
from finance.tests import synthetic_txns

from . import tools, vocab
from .providers import OfflineProvider, get_provider
from .providers.gemini import GeminiProvider
from .providers.offline import build_answer, classify, route
from .tools import CoachContext, run_tool

SUGGESTED = {
    "How much did I spend on taxis last month?": "taxi",
    "Show my spending by basket": "baskets",
    "What is safe to spend this week?": "safe_to_spend",
    "What if I cut dining out by 20%?": "what_if",
    "What kind of spender am I?": "persona",
    "Am I ready to buy a home?": "home",
}


def fake_context(months=13):
    data = SimpleNamespace(
        customer=SimpleNamespace(customer_id="CUST99999"),
        txns=synthetic_txns(months=months),
        application=None,
        events=[],
    )
    return CoachContext(data)


def user(*texts):
    return [{"role": "user", "content": t} for t in texts]


def collect(events):
    return list(events)


def text_of(events):
    return "".join(e["text"] for e in events if e["type"] == "token")


class VocabTests(SimpleTestCase):
    def test_targets(self):
        self.assertEqual(vocab.find_targets("cut dining out"), ["Restaurants"])
        self.assertEqual(
            vocab.find_targets("eating out and fun"),
            [
                "Restaurants",
                "Entertainment",
            ],
        )
        self.assertEqual(vocab.find_targets("my groceries"), ["Groceries"])
        self.assertEqual(vocab.find_targets("shopping"), ["Lifestyle"])
        self.assertEqual(vocab.find_targets("uber rides"), ["Taxi"])
        self.assertEqual(vocab.find_targets("fast food"), ["Restaurants"])
        self.assertEqual(vocab.normalize_target("leakage"), "leakage")
        self.assertEqual(vocab.normalize_target("home & tech"), "Home & Tech")
        self.assertIsNone(vocab.normalize_target("unicorns"))

    def test_periods_and_months(self):
        self.assertEqual(vocab.find_period("in August"), "2026-08")
        self.assertEqual(vocab.find_period("in october"), "2025-10")
        self.assertEqual(vocab.find_period("last month"), "last_month")
        self.assertEqual(vocab.find_period("past three months"), "last_3_months")
        self.assertEqual(vocab.find_period("this year"), "last_12_months")
        self.assertIsNone(vocab.find_period("may I ask something"))
        self.assertEqual(
            vocab.find_months("compare june and august"),
            [
                "2026-06",
                "2026-08",
            ],
        )

    def test_numbers(self):
        self.assertEqual(vocab.find_percent("cut by 20%"), 20.0)
        self.assertEqual(vocab.find_percent("cut it in half"), 50.0)
        self.assertEqual(vocab.find_percent("15 percent less"), 15.0)
        self.assertEqual(vocab.find_percent("if I stopped taking taxis"), 100.0)
        self.assertIsNone(vocab.find_percent("how much on food"))
        self.assertEqual(vocab.find_years("over 10 years"), 10)
        self.assertEqual(vocab.eur(1234.5), "€1,234")
        self.assertEqual(vocab.eur(41.24), "€41.24")


class RouterTests(SimpleTestCase):
    def test_suggested_questions(self):
        for question, intent in SUGGESTED.items():
            with self.subTest(question=question):
                self.assertEqual(classify(question)[0], intent)

    def test_more_intents(self):
        cases = {
            "how much on groceries in August": "spending",
            "What were my biggest expenses?": "biggest",
            "compare last two months": "compare",
            "How am I doing?": "overview",
            "hi": "greeting",
            "help": "help",
            "thanks!": "thanks",
            "what is LTV?": "explain",
            "Should I buy bitcoin?": "invest_advice",
            "What if I cut taxis by 50%?": "what_if",
            "restaurant trend": "spending",
            "How has my spending changed over the last year?": "cashflow",
            "Where should I keep my spare cash?": "cash_buffer",
        }
        for question, intent in cases.items():
            with self.subTest(question=question):
                self.assertEqual(classify(question)[0], intent)

    def test_slots(self):
        intent, slots = classify("What if I cut dining out by 20%?")
        self.assertEqual(slots.targets, ["Restaurants"])
        self.assertEqual(slots.pct, 20.0)
        intent, slots = classify("how much on groceries in August")
        self.assertEqual(slots.targets, ["Groceries"])
        self.assertEqual(slots.period, "2026-08")
        self.assertTrue(classify("What is safe to spend this week?")[1].week)

    def test_follow_ups_reuse_context(self):
        intent, slots = route(user("How much did I spend on taxis?", "and in May?"))
        self.assertEqual(intent, "taxi")
        self.assertEqual(slots.period, "2026-05")
        intent, slots = route(
            user("What if I cut dining out by 20%?", "what about 50%?")
        )
        self.assertEqual(intent, "what_if")
        self.assertEqual(slots.targets, ["Restaurants"])
        self.assertEqual(slots.pct, 50.0)
        self.assertEqual(route(user("asdf qwerty"))[0], "fallback")


class ToolTests(SimpleTestCase):
    def setUp(self):
        self.ctx = fake_context()

    def test_every_tool_runs(self):
        args = {
            "spend_by_category": {"period": "last_month", "category": "food"},
            "category_trend": {"category": "dining out"},
            "taxi_stats": {"period": "last_month"},
            "what_if": {"target": "Restaurants", "pct": 20},
            "compare_months": {"month_a": "2026-08", "month_b": "2026-09"},
            "biggest_expenses": {"period": "last_month", "n": 3},
        }
        for name in tools.TOOLS:
            with self.subTest(tool=name):
                out = run_tool(self.ctx, name, args.get(name, {}))
                self.assertNotIn("error", out["data"])
                self.assertTrue(out["label"])
                json.dumps(out)  # JSON serialisable
                if out["chart"]:
                    self.assertIn(out["chart"]["kind"], {"bar", "line", "pie"})
                    self.assertTrue(out["chart"]["data"])

    def test_numbers_match_analytics(self):
        taxi = run_tool(self.ctx, "taxi_stats", {"period": "last_month"})["data"]
        self.assertEqual((taxi["rides"], taxi["total"]), (2, 40.0))
        what_if = run_tool(self.ctx, "what_if", {"target": "eating out", "pct": 20})
        self.assertEqual(what_if["data"]["target"], "Restaurants")
        self.assertAlmostEqual(what_if["data"]["monthly_saving"], 20.0)
        self.assertEqual(what_if["chart"]["kind"], "line")
        baskets = run_tool(self.ctx, "basket_breakdown")
        self.assertEqual(baskets["chart"]["kind"], "pie")
        self.assertEqual(baskets["concept"]["title"], "The three baskets")

    def test_bad_arguments(self):
        self.assertIn("error", run_tool(self.ctx, "nope")["data"])
        out = run_tool(self.ctx, "what_if", {"target": "unicorns", "pct": 10})
        self.assertIn("error", out["data"])
        out = run_tool(self.ctx, "spend_by_category", {"period": "someday"})
        self.assertIn("error", out["data"])

    def test_declarations(self):
        decls = tools.declarations()
        self.assertGreaterEqual(len(decls), 10)
        for d in decls:
            self.assertEqual(d["parameters"]["type"], "object")


@override_settings(COACH_TOKEN_DELAY=0)
class OfflineAnswerTests(SimpleTestCase):
    def setUp(self):
        self.ctx = fake_context()

    def test_suggested_questions_answer_with_real_numbers(self):
        for question in SUGGESTED:
            with self.subTest(question=question):
                ans = build_answer(self.ctx, user(question))
                self.assertTrue(ans.tools, "should call a tool")
                self.assertIn("**", ans.text)
                self.assertIn("**Tip:**", ans.text)
                self.assertGreaterEqual(len(ans.suggestions), 2)
                self.assertNotIn(question, ans.suggestions)

    def test_taxi_answer(self):
        ans = build_answer(self.ctx, user("How much did I spend on taxis last month?"))
        self.assertIn("**2 taxi rides**", ans.text)
        self.assertIn("**€40**", ans.text)
        self.assertEqual(ans.charts[0]["kind"], "bar")

    def test_what_if_answer(self):
        ans = build_answer(self.ctx, user("What if I cut dining out by 20%?"))
        self.assertIn("**€20 a month**", ans.text)
        self.assertIn("**€240 a year**", ans.text)
        self.assertEqual(ans.charts[0]["kind"], "line")
        self.assertEqual(ans.concept["title"], "Compound interest")

    def test_dashboard_insight_questions_are_understood(self):
        insights = a.insights(self.ctx.txns, self.ctx.today)
        for item in insights:
            with self.subTest(question=item["question"]):
                ans = build_answer(self.ctx, user(item["question"]))
                self.assertNotEqual(ans.intent, "fallback")
                self.assertTrue(ans.tools)

    def test_cashflow_answer(self):
        ans = build_answer(
            self.ctx, user("How has my spending changed over the last year?")
        )
        self.assertEqual(ans.tools[0][0], "monthly_cashflow")
        self.assertIn("Busiest month", ans.text)
        self.assertEqual(len(ans.charts[0]["data"]), 12)

    def test_stream_events(self):
        events = collect(OfflineProvider().stream(self.ctx, user("hello")))
        kinds = [e["type"] for e in events]
        self.assertEqual(kinds[0], "tool")
        self.assertIn("token", kinds)
        self.assertEqual(kinds[-1], "suggestions")
        self.assertIn("Money Coach", text_of(events))


def sse_events(response):
    body = b"".join(response.streaming_content).decode()
    chunks = [c for c in body.split("\n\n") if c.strip()]
    for chunk in chunks:
        assert chunk.startswith("data: "), chunk
    return [json.loads(c[len("data: ") :]) for c in chunks]


@override_settings(COACH_TOKEN_DELAY=0, GEMINI_API_KEY="")
class ChatViewTests(TestCase):
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

    def post(self, body):
        return self.client.post(
            reverse("chat"), data=json.dumps(body), content_type="application/json"
        )

    def test_stream_contract(self):
        res = self.post(
            {
                "customer_id": "CUST99999",
                "messages": user("Show my spending by basket"),
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/event-stream")
        self.assertEqual(res["Cache-Control"], "no-cache")
        self.assertEqual(res["X-Accel-Buffering"], "no")
        events = sse_events(res)
        kinds = [e["type"] for e in events]
        self.assertEqual(
            events[0], {"type": "meta", "provider": "offline", "model": None}
        )
        self.assertEqual(kinds[-1], "done")
        self.assertLess(kinds.index("tool"), kinds.index("token"))
        self.assertLess(kinds.index("token"), kinds.index("chart"))
        self.assertIn("concept", kinds)
        self.assertIn("suggestions", kinds)
        chart = next(e for e in events if e["type"] == "chart")["chart"]
        self.assertEqual(chart["kind"], "pie")
        self.assertIn("Must-pay bills", text_of(events))

    def test_unknown_customer(self):
        res = self.post({"customer_id": "NOPE", "messages": user("hi")})
        self.assertEqual(res.status_code, 404)
        events = sse_events(res)
        self.assertEqual([e["type"] for e in events], ["meta", "error", "done"])

    def test_validation(self):
        bad = [
            {},
            {"customer_id": "CUST99999"},
            {"customer_id": "CUST99999", "messages": []},
            {"customer_id": "CUST99999", "messages": [{"role": "x", "content": "a"}]},
            {"customer_id": "CUST99999", "messages": [{"role": "user"}]},
            {
                "customer_id": "CUST99999",
                "messages": [{"role": "assistant", "content": "hello"}],
            },
        ]
        for body in bad:
            with self.subTest(body=body):
                res = self.post(body)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(sse_events(res)[1]["type"], "error")
        res = self.client.post(
            reverse("chat"), data="not json", content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.get(reverse("chat")).status_code, 405)

    def test_long_history_is_trimmed(self):
        history = []
        for i in range(30):
            history += [
                {"role": "user", "content": "hi " * 2000},
                {"role": "assistant", "content": "hello"},
            ]
        history.append({"role": "user", "content": "How am I doing?"})
        events = sse_events(
            self.post({"customer_id": "CUST99999", "messages": history})
        )
        self.assertEqual(events[-1]["type"], "done")
        self.assertNotIn("error", [e["type"] for e in events])

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-test")
    def test_gemini_selected_when_key_set(self):
        fake = FakeClient([[text_response("Hello from **Gemini**.")]])
        self.assertIsInstance(get_provider(), GeminiProvider)
        with mock.patch("coach.providers.gemini.genai.Client", return_value=fake):
            events = sse_events(
                self.post({"customer_id": "CUST99999", "messages": user("hi")})
            )
        self.assertEqual(
            events[0], {"type": "meta", "provider": "gemini", "model": "gemini-test"}
        )
        self.assertEqual(text_of(events), "Hello from **Gemini**.")
        self.assertEqual(events[-1]["type"], "done")


# --- Gemini with a fake client ---------------------------------------------------


def response(*parts):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=list(parts)))
        ]
    )


def text_response(text):
    return response(types.Part.from_text(text=text))


def call_response(name, args, call_id="call-1"):
    return response(
        types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args))
    )


class FakeModels:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = []

    def generate_content_stream(self, *, model, contents, config):
        self.calls.append(
            {"model": model, "contents": list(contents), "config": config}
        )
        item = self.scripts.pop(0)
        if isinstance(item, Exception):
            raise item
        return iter(item)


class FakeClient:
    def __init__(self, scripts):
        self.models = FakeModels(scripts)


@override_settings(COACH_TOKEN_DELAY=0)
class GeminiLoopTests(SimpleTestCase):
    def setUp(self):
        self.ctx = fake_context()

    def provider(self, scripts):
        client = FakeClient(scripts)
        return GeminiProvider("key", "gemini-test", client=client), client

    def test_function_call_then_streamed_text(self):
        provider, client = self.provider(
            [
                [call_response("taxi_stats", {"period": "last_month"})],
                [
                    text_response("You took **2 taxi rides** "),
                    text_response("costing **€40**.\n\n**Tip:** walk more."),
                ],
            ]
        )
        events = collect(provider.stream(self.ctx, user("taxis last month?")))
        kinds = [e["type"] for e in events]
        self.assertEqual(kinds[0], "tool")
        self.assertEqual(events[0]["name"], "taxi_stats")
        self.assertEqual(events[0]["label"], tools.label_for("taxi_stats"))
        self.assertEqual(
            text_of(events),
            "You took **2 taxi rides** costing **€40**.\n\n**Tip:** walk more.",
        )
        self.assertLess(kinds.index("token"), kinds.index("chart"))
        chart = next(e for e in events if e["type"] == "chart")["chart"]
        self.assertEqual(chart["title"], "Taxi spend by month")
        self.assertEqual(kinds[-1], "suggestions")

        # Second request carries the model's call and our function response.
        self.assertEqual(len(client.models.calls), 2)
        first, second = client.models.calls
        self.assertEqual(first["model"], "gemini-test")
        config = first["config"]
        self.assertTrue(config.automatic_function_calling.disable)
        names = {f.name for f in config.tools[0].function_declarations}
        self.assertIn("what_if", names)
        model_turn, tool_turn = second["contents"][-2:]
        self.assertEqual(model_turn.role, "model")
        self.assertEqual(model_turn.parts[0].function_call.name, "taxi_stats")
        fr = tool_turn.parts[0].function_response
        self.assertEqual((fr.name, fr.id), ("taxi_stats", "call-1"))
        self.assertEqual(fr.response["result"]["rides"], 2)
        self.assertEqual(fr.response["result"]["total"], 40.0)

    def test_history_roles(self):
        provider, client = self.provider([[text_response("Sure.")]])
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "how am I doing?"},
        ]
        collect(provider.stream(self.ctx, messages))
        roles = [c.role for c in client.models.calls[0]["contents"]]
        self.assertEqual(roles, ["user", "model", "user"])
        prompt = client.models.calls[0]["config"].system_instruction
        self.assertIn("CUST99999", prompt)
        self.assertIn("2026-09-30", prompt)

    def test_tool_rounds_are_capped(self):
        loop = [[call_response("safe_to_spend", {}, f"c{i}")] for i in range(5)]
        provider, client = self.provider(loop + [[text_response("Done.")]])
        events = collect(provider.stream(self.ctx, user("safe to spend?")))
        self.assertEqual(len(client.models.calls), 6)
        final_config = client.models.calls[-1]["config"]
        self.assertEqual(final_config.tool_config.function_calling_config.mode, "NONE")
        self.assertEqual(text_of(events), "Done.")
        self.assertEqual(sum(e["type"] == "tool" for e in events), 5)
        self.assertEqual(sum(e["type"] == "chart" for e in events), 2)

    def test_bad_tool_args_are_reported_to_model(self):
        provider, client = self.provider(
            [
                [call_response("what_if", {"target": "unicorns", "pct": 10})],
                [text_response("I couldn't find that category.")],
            ]
        )
        collect(provider.stream(self.ctx, user("cut unicorns")))
        fr = client.models.calls[1]["contents"][-1].parts[0].function_response
        self.assertIn("error", fr.response["result"])

    def test_api_error_falls_back_to_offline(self):
        provider, _ = self.provider([RuntimeError("quota exceeded")])
        with self.assertLogs("coach.providers.gemini", "WARNING"):
            events = collect(
                provider.stream(self.ctx, user("What if I cut dining out by 20%?"))
            )
        self.assertEqual(events[0]["type"], "tool")
        self.assertEqual(events[0]["name"], "offline_fallback")
        self.assertIn("**€20 a month**", text_of(events))
        self.assertEqual(events[-1]["type"], "suggestions")

    def test_empty_answer_falls_back(self):
        provider, _ = self.provider([[response()]])
        with self.assertLogs("coach.providers.gemini", "WARNING"):
            events = collect(provider.stream(self.ctx, user("hello")))
        self.assertEqual(events[0]["name"], "offline_fallback")
        self.assertIn("Money Coach", text_of(events))

    def test_error_mid_answer_keeps_text(self):
        def broken():
            yield text_response("Partial answer")
            raise RuntimeError("connection reset")

        provider, _ = self.provider([broken()])
        with self.assertLogs("coach.providers.gemini", "WARNING"):
            events = collect(provider.stream(self.ctx, user("hello")))
        self.assertTrue(text_of(events).startswith("Partial answer"))
        self.assertNotIn("offline_fallback", [e.get("name") for e in events])


class ContextTests(SimpleTestCase):
    def test_today_default(self):
        self.assertEqual(fake_context().today, date(2026, 9, 30))
