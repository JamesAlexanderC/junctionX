"""Deterministic offline coach: intent router + number-rich templates.

Used when no Gemini key is configured (and as Gemini's fallback). It parses
the question (intent, categories, period, percentage), calls the same tools
the LLM would, and writes a short, personal answer with one practical tip.
"""

from __future__ import annotations

import math
import re
import time
import zlib
from dataclasses import dataclass, field, replace

from finance import analytics as a

from .. import vocab
from ..glossary import GLOSSARY, TERMS
from ..tools import cat_label, chart, run_tool
from .base import (
    Provider,
    chart_event,
    concept_event,
    stream_text,
    suggestions_event,
    token_delay,
    tool_event,
)

E = vocab.eur
P = vocab.pct


def b(x):
    return f"**{x}**"


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


# --- Intent classification ------------------------------------------------------

# intent -> [(regex, weight)]. The highest total wins; ties go to the intent
# listed first.
INTENT_PATTERNS = {
    "explain": [
        (
            r"\b(explain|meaning of|define|definition of)\b|"
            r"\bwhat does .{1,40} mean\b|\bwhat('?s| is) (an? |the )?"
            r"(ltv|loan.to.value|compound(ing| interest)|stress.test|"
            r"emergency fund|savings? rate|three baskets|leakage)\b",
            6,
        ),
    ],
    "invest_advice": [
        (
            r"\b(stocks?|shares|crypto|bitcoin|etfs?|index funds?|mutual funds?|"
            r"should i invest|invest in|best investment)\b",
            5,
        ),
    ],
    "cash_buffer": [
        (
            r"\b(idle|spare|extra|surplus) (cash|money)\b|"
            r"\bwhere should i (keep|put|park) my (money|savings|cash)\b|"
            r"\bhow much (cash|money) should i keep\b|"
            r"\bhow (big|much) should my (emergency fund|buffer) be\b",
            5,
        ),
    ],
    "what_if": [
        (r"\bwhat if\b|\bwhat would happen if\b|\bhow much would i save\b", 3),
        (
            r"\b(cut|cutting|reduce|reducing|lower|lowering|trim|halve|"
            r"spend less|stop|stopped|quit|skip|give up)\b",
            2,
        ),
        (r"\d+\s*(%|percent|per cent)", 1),
    ],
    "cashflow": [
        (
            r"\b(spending|money|finances) (has |have )?(changed|chang|trend)|"
            r"\bmonth by month\b|\bcash ?flow\b|\bspending trend\b|"
            r"\b(each|every) month\b.{0,20}\b(spend|spent|spending)\b",
            5,
        ),
    ],
    "taxi": [(r"\btax(i|is|ies)\b|\bcabs?\b|\buber\b|\bbolt\b|ride.?hailing", 4)],
    "safe_to_spend": [
        (r"\bsafe(ly)? to spend\b|\bsafe.to.spend\b", 5),
        (r"\bhow much can i spend\b|\bleft to spend\b|\bspending money\b", 4),
        (r"\bcan i afford\b|\buntil (my )?pay ?day\b|\bbefore pay ?day\b", 3),
        (r"\b(upcoming|next) bills\b|\bbills (are )?(coming|due)\b", 3),
        (r"\b(this|next|the) week\b|\bweekend\b|\bbudget\b", 1),
    ],
    "baskets": [
        (r"\bbaskets?\b", 4),
        (r"\bwhere (does|did) (all )?my money go\b|\bwhere my money goes\b", 4),
        (r"\bbreak ?down\b|\bspending by (type|group)\b", 2),
    ],
    "persona": [
        (
            r"\b(kind|type|sort) of (spender|saver|person)\b|\bspender am i\b|"
            r"\bpersona\b|\bspending (style|personality|type|habits?)\b|"
            r"\bmoney personality\b",
            5,
        ),
        (r"\bwho am i\b", 2),
    ],
    "home": [
        (
            r"\b(buy|buying|purchase|afford|ready for)\b.{0,25}"
            r"\b(home|house|flat|apartment|property)\b",
            5,
        ),
        (r"\bmortgage\b|\bhome loan\b|\bhousing loan\b|\bfirst home\b", 4),
        (r"\bready to buy\b|\bdeposit\b", 2),
        (r"\b(home|house|apartment|flat)\b", 1),
    ],
    "biggest": [
        (
            r"\b(biggest|largest|most expensive|top|big|largest single|major)\b"
            r".{0,20}\b(expenses?|purchases?|payments?|costs?|spends?|"
            r"transactions?|buys?)\b",
            5,
        ),
        (r"\bwhat did i spend the most on\b", 3),
    ],
    "compare": [
        (r"\bcompare\b|\bcomparison\b|\bcompared (to|with)\b", 3),
        (r"\bdifference between\b|\bversus\b|\bvs\.?\b", 2),
        (r"\b(last|past) (two|2) months\b|\bmonth (over|on|to) month\b", 3),
        (r"\bthan (last|the previous|previous) month\b", 3),
        (r"\bmonths?\b", 1),
    ],
    "overview": [
        (
            r"\bhow am i doing\b|\bhow('?s| is| are) my (money|finances|budget)\b|"
            r"\boverview\b|\bsummary\b|\bsummari[sz]e\b|\bhealth ?check\b|"
            r"\bfinancial health\b|\bmy finances\b|\bbig picture\b|\bcheck.?up\b",
            4,
        ),
        (r"\bam i saving\b|\bdo i save\b|\bsaving enough\b", 3),
        (r"\bsavings? rate\b|\bincome\b|\bhow much do i (earn|make)\b", 2),
    ],
    "spending": [
        (r"\bhow much\b", 1),
        (r"\bspen[dt]\b|\bspending\b|\bcosts?\b|\bpaid\b|\bpay for\b", 1),
        (
            r"\btrend\b|\bover time\b|\beach month\b|\bper month\b|\bmonthly\b|"
            r"\bcreeping\b|\bgoing up\b|\bincreas|\bdecreas",
            1,
        ),
    ],
    "help": [
        (
            r"\bhelp\b|\bwhat can you do\b|\bwhat can i ask\b|"
            r"\bhow does this work\b|\bwhat do you do\b|\bwho are you\b",
            3,
        ),
    ],
    "greeting": [
        (
            r"^\s*(hi|hello|hey|hiya|moi|terve|hei|yo|howdy|"
            r"good (morning|afternoon|evening))\b",
            2,
        ),
    ],
    "thanks": [
        (
            r"^\s*(thanks|thank you|thx|kiitos|cheers|great|perfect|awesome|"
            r"nice|ok(ay)?|cool|got it)\b",
            2,
        ),
    ],
}
_COMPILED = {
    intent: [(re.compile(p, re.IGNORECASE), w) for p, w in pats]
    for intent, pats in INTENT_PATTERNS.items()
}
SINGLE_MONTH = ("last_month", "this_month")
# Intents that can be continued by a short follow-up ("and in August?").
CONTINUABLE = {"what_if", "taxi", "spending", "biggest", "compare"}


@dataclass
class Slots:
    targets: list = field(default_factory=list)
    period: str | None = None
    months: list = field(default_factory=list)
    pct: float | None = None
    years: int | None = None
    week: bool = False
    term: str | None = None

    def empty(self):
        return not (self.targets or self.period or self.pct or self.years)


def parse_slots(text, today=None):
    t = text.lower()
    term = None
    for key, phrases in TERMS.items():
        if any(re.search(rf"\b{re.escape(p)}\b", t) for p in phrases):
            term = key
            break
    return Slots(
        targets=vocab.find_targets(text),
        period=vocab.find_period(text, today),
        months=vocab.find_months(text, today),
        pct=vocab.find_percent(text),
        years=vocab.find_years(text),
        week=bool(re.search(r"\bweek(end)?\b", t)),
        term=term,
    )


def score_intents(text, slots):
    scores = {}
    for intent, pats in _COMPILED.items():
        scores[intent] = sum(w for rx, w in pats if rx.search(text))
    non_taxi = [x for x in slots.targets if x != vocab.TAXI]
    if non_taxi:
        scores["spending"] += 3
        scores["cashflow"] = 0
    if vocab.TAXI in slots.targets:
        scores["taxi"] = max(scores["taxi"], 4)
    if scores["spending"] and slots.period:
        scores["spending"] += 1
    if scores["explain"] and not slots.term:
        scores["explain"] = 0
    if scores["compare"] and not (len(slots.months) >= 2 or scores["compare"] >= 3):
        scores["compare"] = 0
    return scores


def classify(text, today=None):
    """Return ``(intent, slots)`` for one message; intent may be None."""
    slots = parse_slots(text, today)
    scores = score_intents(text, slots)
    best = max(scores.values())
    if best <= 0:
        return None, slots
    for intent in INTENT_PATTERNS:  # priority order on ties
        if scores[intent] == best:
            return intent, slots
    return None, slots  # pragma: no cover


def route(messages, today=None):
    """Pick the intent for the latest user message, using history for
    follow-ups such as "and in August?" or "what about 50%?"."""
    users = [m["content"] for m in messages if m.get("role") == "user"]
    if not users:
        return "help", Slots()
    intent, slots = classify(users[-1], today)
    previous = [classify(u, today) for u in users[-4:-1]]
    previous.reverse()
    if intent is None and not slots.empty():
        for prev_intent, prev_slots in previous:
            if prev_intent in CONTINUABLE:
                return prev_intent, _merge(slots, prev_slots)
        return "spending", slots
    if intent == "what_if" and not slots.targets:
        for prev_intent, prev_slots in previous:
            if prev_slots.targets:
                return intent, _merge(slots, prev_slots)
    return intent or "fallback", slots


def _merge(slots, prev):
    return replace(
        slots,
        targets=slots.targets or prev.targets,
        period=slots.period or prev.period,
        months=slots.months or prev.months,
        pct=slots.pct if slots.pct is not None else prev.pct,
        years=slots.years or prev.years,
    )


# --- Answer builder ---------------------------------------------------------------


class Answer:
    """Collects tool calls, text, chart, concept and follow-ups for one reply."""

    def __init__(self, ctx, question, seed):
        self.ctx = ctx
        self.question = question
        self.rng_seed = seed
        self.tools = []
        self.paragraphs = []
        self.charts = []
        self.concept = None
        self.suggestions = []

    def call(self, name, show_chart=True, show_concept=True, **args):
        res = run_tool(self.ctx, name, args)
        if name not in (t[0] for t in self.tools):
            self.tools.append((name, res["label"]))
        if show_chart and res.get("chart") and not self.charts:
            self.charts.append(res["chart"])
        if show_concept and res.get("concept") and self.concept is None:
            self.concept = res["concept"]
        return res["data"]

    def pick(self, *options):
        """Deterministic but varied choice (same question -> same wording)."""
        self.rng_seed = zlib.crc32(str(self.rng_seed).encode())
        return options[self.rng_seed % len(options)]

    def say(self, *sentences):
        text = " ".join(s for s in sentences if s)
        if text:
            self.paragraphs.append(text)

    def bullets(self, lines):
        lines = [f"- {line}" for line in lines if line]
        if lines:
            self.paragraphs.append("\n".join(lines))

    def tip(self, text):
        self.paragraphs.append(f"**Tip:** {text}")

    def suggest(self, *items):
        asked = self.question.strip().lower().rstrip("?")
        for item in items:
            if item and item.lower().rstrip("?") != asked:
                if item not in self.suggestions:
                    self.suggestions.append(item)

    @property
    def text(self):
        return "\n\n".join(self.paragraphs)


def join(items):
    """'a', 'a and b', 'a, b and c'."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def in_period(label):
    if label.startswith("last "):
        return f"over the {label}"
    if label == "all time":
        return "in total"
    return f"in {label}"


def period_months(period):
    return {
        "last_3_months": 3,
        "last_6_months": 6,
        "last_12_months": 12,
    }.get(period, 1)


def biggest_leak(ctx):
    """``(category, monthly_avg)`` of the largest everyday-leakage category."""
    leak = next(x for x in ctx.baskets() if x["key"] == "leakage")
    if leak["top_categories"]:
        top = leak["top_categories"][0]
        return top["category"], top["monthly_avg"]
    return "Restaurants", 0.0


def compare_word(value, average, tolerance=0.15):
    """'about your usual', '35% above' or '20% below'."""
    if average <= 0:
        return None
    change = (value - average) / average
    if abs(change) < tolerance:
        return "about the same as your usual"
    if change >= 1:
        return f"about {value / average:.0f} times"
    return f"{P(abs(change))} {'above' if change > 0 else 'below'}"


CATEGORY_TIPS = {
    "Restaurants": (
        "pick one or two eat-out nights a week and bring lunch from home on "
        "the other days. It's the easiest way to trim dining out without "
        "feeling it."
    ),
    "Groceries": (
        "plan the week's meals and shop with a list. Checking the weekly "
        "offers and buying store-brand basics often saves 10-15%."
    ),
    "Entertainment": (
        "go through last month's subscriptions and tickets and cancel the "
        "ones you didn't really use."
    ),
    "Lifestyle": (
        "try a 48-hour rule: leave non-essential buys in the basket for two "
        "days. Most impulse purchases don't survive the wait."
    ),
    "Transportation": (
        "if you travel the same routes often, a monthly public transport "
        "pass usually pays for itself within a couple of weeks."
    ),
    vocab.TAXI: (
        "swap short taxi hops for public transport or a city bike, and save "
        "taxis for late nights and heavy bags."
    ),
    "Housing": (
        "housing is hard to change quickly, but it's worth checking your home "
        "insurance and electricity contract once a year for a better deal."
    ),
    "Utilities": (
        "compare electricity contracts once a year; switching to a cheaper "
        "spot or fixed price deal takes ten minutes online."
    ),
    "Health": (
        "health costs are lumpy, so a small monthly pot for them stops a "
        "dentist bill from wrecking your budget."
    ),
    "Home & Tech": (
        "big tech purchases are easier with a sinking fund: set aside a "
        "little every month instead of paying it all at once."
    ),
    "Travel": (
        "book trips earlier and save for them in a separate travel pot, so "
        "holidays never come out of your everyday money."
    ),
    "leakage": (
        "set a weekly 'fun money' amount and move it to a separate pot on "
        "payday. When it's gone, it's gone."
    ),
}


def _sentence(text):
    return text[:1].upper() + text[1:]


def category_tip(target):
    return CATEGORY_TIPS.get(
        target,
        "set up an automatic transfer to savings on payday, so money you don't "
        "spend actually gets saved.",
    )


# --- Handlers -----------------------------------------------------------------------


def h_taxi(ans, s):
    period = s.period or "last_month"
    d = ans.call("taxi_stats", period=period)
    rides, total, avg12 = d["rides"], d["total"], d["monthly_avg_last_12"]
    when = in_period(d["period"])
    six_rides = sum(m["rides"] for m in d["monthly"])
    six_total = sum(m["amount"] for m in d["monthly"])
    if rides:
        per_ride = f" (about {b(E(d['avg_per_ride']))} a ride)" if rides > 1 else ""
        ans.say(
            ans.pick("You took", "You had", "I count"),
            f"{b(plural(rides, 'taxi ride'))} {when}, costing {b(E(total))} in "
            f"total{per_ride}.",
        )
        if period in SINGLE_MONTH or len(period) == 7:
            cmp = compare_word(total, avg12)
            if cmp and cmp.startswith("about the same"):
                ans.say(f"That's {cmp} {b(E(avg12))} a month.")
            elif cmp:
                ans.say(f"That's {cmp} your 12-month average of {b(E(avg12))}.")
            busiest = max(d["monthly"], key=lambda m: m["amount"])
            if six_rides > rides:
                ans.say(
                    f"Over the last 6 months you took {plural(six_rides, 'ride')} "
                    f"for {b(E(six_total))}, with "
                    f"{vocab.month_label(busiest['month'], False)} the busiest "
                    f"({E(busiest['amount'])})."
                )
    else:
        ans.say(
            ans.pick("Good news:", "Nice one:", "Easy answer:"),
            f"there were {b('no taxi rides')} {when}.",
        )
        if six_rides >= 4:
            ans.say(
                f"That's a quiet month for you, though: over the last 6 months "
                f"you took {plural(six_rides, 'ride')} costing "
                f"{b(E(six_total))}."
            )
        elif six_rides:
            ans.say(
                f"Over the last 6 months you took {plural(six_rides, 'ride')} "
                f"costing {b(E(six_total))}, so taxis are an occasional thing "
                "for you."
            )
        else:
            ans.say("In fact I don't see a single taxi ride in the last 6 months.")
    other = [
        t
        for t in d["transport_types"]
        if t["label"] != a.MCC_LABELS[a.TAXI_MCC] and t["amount"] >= 1
    ]
    if d["transport_total"] - total >= 5 and other:
        parts = join(f"{t['label'].lower()} {E(t['amount'])}" for t in other[:2])
        ans.say(
            f"Your wider transport spending {when} was "
            f"{b(E(d['transport_total']))} ({parts})."
        )
    yearly = avg12 * 12
    if yearly >= 300:
        ans.tip(
            f"over the last 12 months taxis cost you about {b(E(yearly))}. "
            "Swapping every other ride for public transport would save around "
            f"{b(E(yearly / 2))} a year."
        )
    elif rides or six_rides:
        ans.tip(category_tip(vocab.TAXI))
    else:
        ans.tip(
            "keep a public transport ticket app on your phone for late nights. "
            "It's the easiest way to keep taxi spending this low."
        )
    ans.suggest(
        "What if I cut taxis by 50%?",
        "How much do I spend on transport?",
        "Show my spending by basket",
    )


def h_baskets(ans, s):
    d = ans.call("basket_breakdown")
    baskets = {x["key"]: x for x in d["baskets"]}
    ans.say(
        ans.pick(
            f"In a typical month you spend {b(E(d['spend_monthly_avg']))}. "
            "Here's how it splits across your three baskets (12-month average):",
            f"Here's where your money goes. Of the {b(E(d['spend_monthly_avg']))} "
            "you spend in an average month:",
        )
    )
    lines = []
    for x in d["baskets"]:
        tops = ", ".join(
            f"{vocab.display(c['category'])} {E(c['monthly_avg'])}"
            for c in x["top_categories"][:2]
            if c["monthly_avg"] >= 1
        )
        lines.append(
            f"{b(x['label'] + ': ' + E(x['monthly_avg']))} ({P(x['share'])})"
            + (f", mostly {tops}" if tops else "")
        )
    ans.bullets(lines)
    leak = baskets["leakage"]
    if leak["share"] >= 0.35:
        ans.say(
            f"Everyday leakage is a big slice at {b(P(leak['share']))}. That's "
            "good news in a way: none of it is a bill, so it's the easiest "
            "basket to trim."
        )
    elif leak["share"] <= 0.15:
        ans.say(
            f"Your everyday leakage is low at {b(P(leak['share']))} of spending, "
            "so most of your money goes on things you genuinely need."
        )
    else:
        ans.say(f"Leakage is a moderate {b(P(leak['share']))} of your spending.")
    last = d["last_month"]
    month = vocab.month_label(last["month"], False)
    lm = last["baskets"]["leakage"]
    cmp = compare_word(lm, leak["monthly_avg"])
    if lm < 1 and leak["monthly_avg"] >= 1:
        ans.say(
            f"In {month} you had {b('no everyday leakage at all')}, against "
            f"your usual {E(leak['monthly_avg'])} a month."
        )
    elif cmp:
        ans.say(
            f"In {month} your leakage was {b(E(lm))}, "
            + (
                f"{cmp} {E(leak['monthly_avg'])}."
                if cmp.startswith("about the same")
                else f"{cmp} your average of {E(leak['monthly_avg'])}."
            )
        )
    cat, monthly = biggest_leak(ans.ctx)
    surprise = baskets["mandatory_irregular"]["monthly_avg"]
    if leak["share"] > 0.15 and monthly > 0:
        ans.tip(
            f"your biggest leak is {vocab.display(cat)} at about "
            f"{b(E(monthly))} a month. Cutting it by 20% frees up "
            f"{b(E(monthly * 0.2 * 12))} a year."
        )
    elif surprise >= 20:
        ans.tip(
            f"put about {b(E(surprise))} a month into a separate 'surprise "
            "essentials' pot, so a dentist bill or a new laptop never hits "
            "your everyday account."
        )
    else:
        ans.tip(category_tip(None))
    ans.suggest(
        f"What if I cut {vocab.display(cat)} by 20%?",
        "What is safe to spend this week?",
        "What kind of spender am I?",
    )


def _bill_lines(bills):
    lines = []
    for bill in bills:
        if "spread over" in bill["label"]:
            name = bill["label"].replace(" (spread over the month)", "")
            lines.append(f"{name}: {b(E(bill['amount']))} spread over the period")
        else:
            lines.append(
                f"{bill['label']}: {b(E(bill['amount']))} due "
                f"{vocab.day_label(bill['due'])}"
            )
    return lines


def _idle_tip(cash):
    return (
        f"keep about three months of spending ({b(E(cash['buffer']))}) in your "
        f"account and move the rest, roughly {b(E(cash['idle']))}, to savings. "
        f"At 3% that's about {b(E(cash['interest']))} a year of interest."
    )


def _safe_well_covered(ans, s, d, payday):
    """Safe to spend for someone whose free money dwarfs their daily spend.

    A "€3,888 a day" figure is meaningless here, so talk about the total and
    the customer's normal pace instead.
    """
    typical = d["typical_spend_per_day"]
    ans.say(
        f"You're well covered{' this week' if s.week else ''}.",
        f"After the bills due before payday on {b(payday)} and a "
        f"{b(E(d['reserve']))} safety reserve, {b(E(d['amount']))} of your "
        f"{E(d['balance'])} balance is free to spend.",
    )
    ans.say("Already set aside for bills:")
    ans.bullets(_bill_lines(d["upcoming_bills"]))
    if typical >= 1:
        ans.say(
            f"Your everyday spending usually runs about "
            f"{b(E(typical * 7) + ' a week')}, so you can carry on as normal and "
            "still have plenty left on payday."
        )
    cash = a.idle_cash(d["balance"], d["spend_monthly_avg"])
    if cash["worth_moving"]:
        ans.tip(_idle_tip(cash))
    else:
        ans.tip(
            "check this number before bigger purchases. It already sets aside "
            "your upcoming bills."
        )
    cat, _ = biggest_leak(ans.ctx)
    ans.suggest(
        "Where should I keep my spare cash?",
        "Show my spending by basket",
        f"What if I cut {vocab.display(cat)} by 20%?",
    )


def h_cash_buffer(ans, s):
    d = ans.call("get_overview_summary", show_chart=False, show_concept=False)
    cash = d["idle_cash"]
    balance = d["balance"]
    ans.concept = GLOSSARY["emergency_fund"]
    ans.say(
        "A good rule of thumb is to keep about three months of spending in an "
        f"easy-to-reach emergency fund. For you that's {b(E(cash['buffer']))}."
    )
    if cash["worth_moving"]:
        ans.say(
            f"Your balance today is {b(E(balance))}, so about "
            f"{b(E(cash['idle']))} is sitting idle above that buffer. In a "
            f"savings account at 3% it would earn about "
            f"{b(E(cash['interest']) + ' a year')}."
        )
        ans.charts.append(
            chart(
                "bar",
                f"Your {E(balance)} balance",
                [
                    {"label": "3-month buffer", "value": cash["buffer"]},
                    {"label": "Idle cash", "value": cash["idle"]},
                ],
            )
        )
        ans.tip(
            "keep the buffer in your everyday account and move the rest in one "
            "go. If you'd like to invest part of it, S-Pankki's advisers can "
            "help you choose."
        )
    elif balance >= cash["buffer"]:
        ans.say(
            f"Your balance today is {b(E(balance))}, so your buffer is in place "
            "with a little to spare."
        )
        ans.tip(
            "keep it topped up with a small standing transfer on payday, so a "
            "surprise bill never eats into it for long."
        )
    else:
        short = cash["buffer"] - max(0.0, balance)
        ans.say(
            f"Your balance today is {b(E(balance))}, so you're about "
            f"{b(E(short))} short of a full buffer. There's no spare cash to "
            "move yet."
        )
        ans.tip(
            "build the buffer first: a standing transfer on payday, even a small "
            "one, gets you there without having to think about it."
        )
    ans.suggest(
        "What kind of spender am I?",
        "Am I ready to buy a home?",
        "What is safe to spend this week?",
    )


def h_safe_to_spend(ans, s):
    d = ans.call("safe_to_spend")
    amount, per_day, days = d["amount"], d["per_day"], d["days_until_payday"]
    payday = vocab.day_label(d["next_payday"])
    typical = d["typical_spend_per_day"]
    if d.get("well_covered"):
        return _safe_well_covered(ans, s, d, payday)
    if amount > 0:
        if s.week:
            ans.say(
                f"You can safely spend about {b(E(d['week_amount']))} over the "
                f"next {plural(d['week_days'], 'day')}, which is "
                f"{b(E(per_day) + ' a day')} until payday on {b(payday)}."
            )
        else:
            ans.say(
                f"You have {b(E(amount))} safe to spend until payday on "
                f"{b(payday)}, about {b(E(per_day) + ' a day')} for the next "
                f"{plural(days, 'day')}."
            )
        ans.say(
            f"That's your balance of {b(E(d['balance']))}, minus the bills due "
            f"before payday and a {b(E(d['reserve']))} safety reserve:"
        )
        ans.bullets(_bill_lines(d["upcoming_bills"]))
        spend = d["spend_monthly_avg"]
        if typical > 0 and per_day > 4 * typical:
            ans.say(
                f"Your everyday spending is usually only about "
                f"{b(E(typical) + ' a day')}, so you have plenty of headroom."
            )
            cash = a.idle_cash(d["balance"], spend)
            if cash["worth_moving"]:
                ans.tip(_idle_tip(cash))
            else:
                ans.tip(category_tip(None))
        elif typical > 0 and per_day < typical:
            ans.say(
                f"That's below your usual {b(E(typical) + ' a day')} of everyday "
                "spending, so it's worth easing off a little until salary day."
            )
            ans.tip(
                "plan a couple of no-spend days each week until payday. Every "
                "day you skip leaves more room for the rest."
            )
        else:
            ans.say(
                f"That's comfortably above your usual {b(E(typical) + ' a day')}, "
                "so you're on track."
            )
            ans.tip(
                "check this number before bigger purchases. It already sets "
                "aside your upcoming bills."
            )
    else:
        ans.say(
            ans.pick("Honestly, things are tight right now:", "I'll be straight:"),
            f"there's {b('nothing safe to spend')} before payday on {b(payday)}.",
        )
        ans.say(
            f"Your balance is {b(E(d['balance']))}, and "
            f"{b(E(d['bills_total']))} of bills are due before then:"
        )
        ans.bullets(_bill_lines(d["upcoming_bills"]))
        gap = d["bills_total"] - d["balance"]
        if gap > 0:
            ans.say(
                f"That leaves you about {b(E(gap))} short of covering the bills "
                f"themselves, before the {E(d['reserve'])} buffer I like to keep."
            )
        else:
            ans.say(
                f"After the bills, the {b(E(-gap))} left is less than the "
                f"{b(E(d['reserve']))} safety buffer I like to keep."
            )
        if typical > 0:
            ans.tip(
                f"stick to essentials for the next {plural(days, 'day')}. You "
                f"usually spend about {b(E(typical) + ' a day')} on everyday "
                f"things; halving that until payday keeps around "
                f"{b(E(typical * days / 2))} in your account."
            )
        else:
            ans.tip("stick to essentials until payday.")
    cat, _ = biggest_leak(ans.ctx)
    ans.suggest(
        "Show my spending by basket",
        f"What if I cut {vocab.display(cat)} by 20%?",
        "How am I doing overall?",
    )


def h_what_if(ans, s):
    leak_cat, _ = biggest_leak(ans.ctx)
    target = s.targets[0] if s.targets else leak_cat
    pct = s.pct if s.pct else 20.0
    years = s.years or 5
    d = ans.call("what_if", target=target, pct=pct, years=years)
    if d.get("error"):
        target = leak_cat
        d = ans.call("what_if", target=target, pct=pct, years=years)
    if d["current_monthly"] <= 0:
        ans.say(
            f"You haven't spent anything on {vocab.display(target)} in the last "
            "12 months, so there's nothing to cut there."
        )
        if target == leak_cat:
            return
        target = leak_cat
        ans.charts.clear()
        d = ans.call("what_if", target=target, pct=pct, years=years)
        ans.say(f"Your biggest everyday leak is {vocab.display(target)} instead:")
    name = vocab.display(target)
    ms, ys = d["monthly_saving"], d["yearly_saving"]
    total = d["total_with_interest"]
    saved = d["projection"][-1]["saved"]
    cut = (
        f"If you stopped spending on {b(name)} altogether"
        if pct >= 100
        else f"If you cut {b(name)} by {b(f'{pct:g}%')}"
    )
    ans.say(
        f"{cut}, you'd save about {b(E(ms) + ' a month')}, or "
        f"{b(E(ys) + ' a year')}.",
        f"Right now you spend around {E(d['current_monthly'])} a month on it.",
    )
    ans.say(
        ans.pick("Put that aside", "Move that saving into a savings account"),
        f"at 3% interest and after {b(plural(years, 'year'))} you'd have "
        f"{b(E(total))}: {E(saved)} of your own money plus "
        f"{b(E(total - saved))} of interest.",
    )
    margin = d["monthly_margin"]
    if 0 < ms < 15:
        ans.say(
            f"{_sentence(name)} is already a small part of your budget, so this "
            "is a modest win rather than a game changer."
        )
    if margin < 0 and ms > 0:
        if ms >= -margin:
            ans.say(
                f"Right now you spend about {E(-margin)} a month more than you "
                "earn, so this one change would close that gap completely."
            )
        else:
            ans.say(
                f"Right now you spend about {b(E(-margin))} a month more than "
                f"you earn, so this change alone would close {b(P(ms / -margin))} "
                "of that gap."
            )
    elif margin > 0 and ms > 0:
        ans.say(
            f"Added to the {E(margin)} you already keep each month, that's "
            f"{b(E(margin + ms))} a month you could put towards your goals."
        )
    ans.tip(category_tip(target))
    other = 50 if pct < 50 else 20
    ans.suggest(
        f"What if I cut {name} by {other}%?",
        "Am I ready to buy a home?",
        "Show my spending by basket",
    )


PERSONA_INTRO = {
    "comfortable": "Your spender type is {}.",
    "paycheck_to_paycheck": "Right now you're living {}.",
    "investor": "You're an {}.",
}


def _comfortable_tip(f):
    cash = a.idle_cash(f["balance_now"], f["spend"])
    if cash["worth_moving"]:
        return _idle_tip(cash)
    return (
        "your cushion is healthy. A standing transfer on payday keeps it "
        "growing without any effort."
    )


PERSONA_TIPS = {
    "comfortable": _comfortable_tip,
    "steady_saver": lambda f: (
        f"automate it. A standing transfer of "
        f"{b(E(round((f['income'] - f['spend']) * 0.5, -1)))} on payday locks in "
        "half of what you already save before it can be spent."
    ),
    "weekend_spender": lambda f: (
        f"set a weekend budget of about "
        f"{b(E(round(f['spend'] * f['leakage_share'] / 4.3 * 0.8, -1)))} (20% "
        "less than now) and move it to a separate pot on Friday. When it's "
        "gone, it's gone."
    ),
    "paycheck_to_paycheck": lambda f: (
        f"start a small buffer: even {b('€50')} moved to savings right after "
        "payday, every month, means the next surprise bill doesn't push you "
        "below zero."
    ),
    "investor": lambda f: (
        f"keep investing steadily, but make sure you also hold about "
        f"{b(E(3 * f['spend']))} (three months of spending) in cash for "
        "emergencies."
    ),
    "balanced": lambda f: (
        f"aim to save 10% of your income, about {b(E(0.1 * f['income']))} a "
        "month. An automatic transfer on payday makes it painless."
    ),
}


def h_persona(ans, s):
    d = ans.call("get_persona")
    sig = d["signals"]
    intro = PERSONA_INTRO.get(d["key"], "Your spender type is {}.")
    ans.say(intro.format(b(d["label"])), d["description"])
    ans.say("Here's what that's based on:")
    ans.bullets(d["traits"])
    flow = d["last_6_months"]
    negative = [m for m in flow if m["net"] < 0]
    avg_net = sum(m["net"] for m in flow) / len(flow) if flow else 0
    if not negative and avg_net > 0:
        ans.say(
            f"You ended every one of the last 6 months with money left over, "
            f"{b(E(avg_net))} on average."
        )
    elif negative:
        ans.say(
            f"In {b(f'{len(negative)} of the last 6 months')} you spent more than "
            "came in."
        )
    if d["key"] != "weekend_spender" and sig["weekend_leakage_share"] >= 0.55:
        ans.say(
            f"Also, {b(P(sig['weekend_leakage_share']))} of your everyday "
            "leakage happens Friday to Sunday."
        )
    tip = PERSONA_TIPS.get(d["key"], PERSONA_TIPS["balanced"])
    ans.tip(tip(sig))
    cat, _ = biggest_leak(ans.ctx)
    ans.suggest(
        f"What if I cut {vocab.display(cat)} by 20%?",
        "Show my spending by basket",
        "Am I ready to buy a home?",
    )


REASON_TIPS = {
    "insufficient_income": (
        "look at homes closer to {price}, or apply together with a co-borrower "
        "so the bank can count two incomes."
    ),
    "insufficient_equity": (
        "grow the deposit first. A standing order into a separate home "
        "savings account on payday is the most reliable way to do it."
    ),
    "existing_debt": (
        "pay down existing loans before reapplying. Every euro of debt cleared "
        "raises how much the bank will lend you."
    ),
    "insufficient_collateral": (
        "consider a cheaper property, or ask the bank about extra collateral "
        "such as a state guarantee for first-home loans."
    ),
}


def h_home(ans, s):
    d = ans.call("home_readiness")
    app = d["application"]
    mp, deposit = d["max_property_price"], d["deposit_needed"]
    saved, months = d["deposit_saved_estimate"], d["months_to_deposit"]
    income, margin = d["income_monthly_avg"], d["monthly_margin"]
    if app and app["decision"] == "approved":
        fin = app["final"]
        took = (
            f", {app['days_to_decision']} days after you started it"
            if app.get("days_to_decision")
            else ""
        )
        ans.say(
            ans.pick("Good news!", "Great news!"),
            f"Your mortgage application was {b('approved')}"
            + (f" on {b(vocab.full_date(app['decided']))}" if app["decided"] else "")
            + f"{took}.",
        )
        ans.say(
            f"The bank agreed a loan of {b(E(fin['loan']))} towards a "
            f"{b(E(fin['property_price']))} home, with {b(E(fin['equity']))} of "
            f"your own money. That's a loan-to-value of "
            f"{b(P(fin['loan_to_value']))}, inside the 90% limit for first-time "
            "buyers.",
        )
        if app.get("properties_considered") or app.get("contacts"):
            ans.say(
                f"Along the way you looked at "
                f"{plural(app['properties_considered'], 'property', 'properties')} "
                f"and were in touch with the bank "
                f"{plural(app['contacts'], 'time')}."
            )
        if app.get("stress_payment") and income:
            share = app["stress_payment"] / income
            ans.say(
                f"If rates rose to 6%, the payment would be about "
                f"{b(E(app['stress_payment']) + ' a month')}, which is "
                f"{b(P(share))} of your average income of {E(income)}"
                + (
                    ", above the 35% comfort line, so keep a buffer."
                    if share >= 0.355
                    else (
                        ", right at the 35% comfort line, so keep a buffer."
                        if share > 0.335
                        else ", within the 35% comfort line."
                    )
                )
            )
        spend = d["spend_monthly_avg"]
        ans.tip(
            f"keep about {b(E(3 * spend))} (three months of spending) as an "
            "emergency fund once you move in. New homes always come with "
            "surprise costs."
        )
    elif app:
        fin = app["final"]
        when = f" on {vocab.full_date(app['decided'])}" if app["decided"] else ""
        reason = app.get("rejection_text") or "of the bank's assessment"
        ans.say(
            f"Your mortgage application was {b('declined')}{when} because {reason}."
        )
        ans.say(
            f"You applied for {b(E(fin['loan']))} towards a "
            f"{b(E(fin['property_price']))} home with {b(E(fin['equity']))} of "
            f"your own money (loan-to-value {P(fin['loan_to_value'])})."
        )
        debt = d.get("existing_debt_monthly") or 0
        if d.get("capped_by_application"):
            basis = (
                "The bank's own check was stricter than my rule of thumb, so "
                f"aim below what was declined: a loan of about "
                f"{b(E(d['max_loan']))} means a home around {b(E(mp))}"
            )
        elif debt:
            basis = (
                f"The bank also counted the {b(E(debt) + ' a month')} you "
                f"already pay on loans. On your income of about {E(income)} a "
                f"month that leaves room for a payment of {E(d['max_payment'])}, "
                f"so a realistic target is a home around {b(E(mp))}"
            )
        else:
            basis = (
                f"Based on your income of about {b(E(income))} a month, a "
                f"realistic target is a home around {b(E(mp))}"
            )
        ans.say(
            f"{basis}, which needs a deposit of about {b(E(deposit))}. I "
            f"estimate you have {b(E(saved))} towards it."
        )
        usable = saved - a.idle_cash(saved, d["spend_monthly_avg"])["buffer"]
        if usable > 2 * deposit and d["max_loan"] > 0:
            ans.say(
                f"You could also put more of your savings in: with "
                f"{E(usable)} as deposit (keeping a three-month buffer), the "
                f"same loan stretches to a home of about "
                f"{b(E(d['max_loan'] + usable))}."
            )
        tip = REASON_TIPS.get(
            app.get("rejection_reason"), REASON_TIPS["insufficient_equity"]
        )
        if debt and app.get("rejection_reason") in (
            "insufficient_income",
            "existing_debt",
        ):
            tip = (
                f"paying off the existing loan is the biggest lever: it would "
                f"free up {E(debt)} a month for a mortgage payment. A "
                "co-borrower's income would also count."
            )
        ans.tip(tip.format(price=E(mp)))
    else:
        if months == 0:
            ans.say(
                "On paper, you look ready.",
                f"With an income of about {b(E(income))} a month you could "
                f"afford a home up to around {b(E(mp))}, and the 10% deposit of "
                f"{b(E(deposit))} is already covered: I estimate you have "
                f"{b(E(saved))} saved.",
            )
        elif months is not None:
            when = (
                plural(months, "month")
                if months < 24
                else f"about {round(months / 12)} years"
            )
            ans.say(
                "You're on your way.",
                f"With an income of about {b(E(income))} a month, a home up to "
                f"around {b(E(mp))} looks affordable. It needs a 10% deposit of "
                f"{b(E(deposit))}, you have roughly {b(E(saved))} so far, and at "
                f"your current pace of {E(margin)} a month you'd get there in "
                f"{b(when)}.",
            )
        else:
            ans.say(
                "Not yet, honestly.",
                f"On your income a home up to about {b(E(mp))} would be "
                f"realistic, which needs a deposit of around {b(E(deposit))}. "
                f"You have about {b(E(saved))} set aside, and right now you spend "
                f"{b(E(-margin))} a month more than you earn, so the deposit "
                "can't grow yet.",
            )
        ans.say(
            f"That estimate keeps the loan payment under 35% of your income "
            f"({E(d['max_payment'])} a month) even if interest rose to 6%."
        )
        cat, monthly = biggest_leak(ans.ctx)
        extra = monthly * 0.2
        if months is None and monthly > 0:
            ans.tip(
                f"first get back to break-even. Your biggest leak is "
                f"{vocab.display(cat)} at {b(E(monthly))} a month; cutting it by "
                f"20% saves {b(E(extra))} a month towards closing the gap."
            )
        elif (
            months
            and extra >= 10
            and margin > 0
            and math.ceil((deposit - saved) / (margin + extra)) < months
        ):
            faster = math.ceil((deposit - saved) / (margin + extra))
            ans.tip(
                f"cutting {vocab.display(cat)} by 20% adds {b(E(extra))} a month "
                f"to your savings and gets you there in {plural(faster, 'month')} "
                f"instead of {months}."
            )
        else:
            ans.tip(
                "open a separate home savings account so the deposit can't "
                "quietly get spent."
            )
    cat, _ = biggest_leak(ans.ctx)
    ans.suggest(
        "What kind of spender am I?",
        f"What if I cut {vocab.display(cat)} by 20%?",
        "How am I doing overall?",
    )


def h_spending(ans, s):
    targets = [t for t in s.targets if t != vocab.TAXI]
    if not targets and vocab.TAXI in s.targets:
        return h_taxi(ans, s)
    period = s.period or "last_month"
    if len(targets) >= 2:
        return _spending_many(ans, targets, period)
    if not targets:
        return _spending_period(ans, period)
    target = targets[0]
    name = vocab.display(target)
    d = ans.call("spend_by_category", show_chart=False, period=period, category=target)
    if d.get("error"):
        return h_fallback(ans, s)
    t = ans.call("category_trend", category=target, months=12)
    f = d["focus"]
    when = in_period(d["period"])
    if f["amount"] > 0:
        ans.say(
            ans.pick("You spent", "You put", "That came to"),
            f"{b(E(f['amount']))} on {name} {when}, across "
            f"{plural(f['count'], 'payment')}."
            + (
                f" That's {b(P(f['share']))} of everything you spent."
                if f["share"] >= 0.01
                else ""
            ),
        )
    else:
        ans.say(f"You didn't spend anything on {name} {when}.")
    avg = t["monthly_avg"]
    n = period_months(period)
    if period in SINGLE_MONTH or len(period) == 7:
        cmp = compare_word(f["amount"], avg)
        if cmp and f["amount"] > 0:
            if cmp.startswith("about the same"):
                ans.say(f"That's {cmp} {b(E(avg))} a month.")
            else:
                ans.say(f"That's {cmp} your 12-month average of {b(E(avg))}.")
    elif n > 1 and f["amount"] > 0:
        ans.say(f"That works out at about {b(E(f['amount'] / n))} a month.")
    types = [m for m in f.get("merchant_types", []) if m["amount"] >= 1]
    if len(types) >= 2:
        parts = join(f"{m['label'].lower()} ({E(m['amount'])})" for m in types[:3])
        ans.say(f"Most of it went to {parts}.")
    quiet = sum(1 for m in t["months"] if m["amount"] <= 0)
    if f["amount"] <= 0 and avg > 0:
        if quiet >= 4:
            ans.say(
                f"Your {name} spending comes in bursts: it averages "
                f"{b(E(avg))} a month, but {quiet} of the last 12 months had "
                "none."
            )
        else:
            ans.say(f"That's unusual for you: you average {b(E(avg))} a month.")
    change = t["change_pct"]
    months = [m["amount"] for m in t["months"]]
    recent, before = sum(months[-3:]) / 3, sum(months[-6:-3]) / 3
    if change is not None and abs(change) >= 0.15 and avg >= 10:
        if recent <= 0:
            ans.say(
                f"There's been no {name} spending at all in the last 3 months, "
                f"after about {b(E(before))} a month in the 3 months before."
            )
        elif change > 1:
            ans.say(
                f"Over the last 3 months you averaged {b(E(recent))} a month on "
                f"{name}, up from {E(before)} a month in the 3 months before."
            )
        else:
            ans.say(
                f"Over the last 3 months your {name} spending is "
                f"{'up' if change > 0 else 'down'} {b(P(abs(change)))} on the 3 "
                "months before."
            )
    ans.tip(category_tip(target))
    ans.suggest(
        f"What if I cut {name} by 20%?",
        "Compare my last two months",
        "Show my spending by basket",
    )


def _spending_many(ans, targets, period):
    d = ans.call("spend_by_category", period=period)
    cats = {c["category"]: c for c in d["categories"]}
    lines = []
    for target in targets[:4]:
        if target in a.BASKETS:
            amount = sum(c["amount"] for c in cats.values() if c["basket"] == target)
        else:
            amount = cats.get(target, {}).get("amount", 0.0)
        lines.append(f"{vocab.display(target).capitalize()}: {b(E(amount))}")
    ans.say(f"Here's the split {in_period(d['period'])}:")
    ans.bullets(lines)
    ans.say(f"Your total spending in that time was {b(E(d['total']))}.")
    ans.tip(category_tip(targets[0]))
    ans.suggest(
        f"What if I cut {vocab.display(targets[0])} by 20%?",
        "Show my spending by basket",
        "What are my biggest expenses?",
    )


def _spending_period(ans, period):
    d = ans.call("spend_by_category", period=period)
    when = in_period(d["period"])
    if not d["categories"]:
        ans.say(f"I don't see any spending {when}.")
        ans.suggest("How am I doing overall?", "Show my spending by basket")
        return
    ans.say(f"You spent {b(E(d['total']))} {when}. The biggest categories:")
    ans.bullets(
        f"{cat_label(c['category'])}: {b(E(c['amount']))} ({P(c['share'])})"
        for c in d["categories"][:4]
    )
    leak = sum(c["amount"] for c in d["categories"] if c["basket"] == "leakage")
    if d["total"]:
        ans.say(
            f"Of that, {b(E(leak))} ({P(leak / d['total'])}) was everyday "
            "leakage: eating out, fun, shopping and transport."
        )
    top_leak = next(
        (c["category"] for c in d["categories"] if c["basket"] == "leakage"), None
    )
    ans.tip(category_tip(top_leak or "leakage"))
    ans.suggest(
        "Compare my last two months",
        "What are my biggest expenses?",
        "Show my spending by basket",
    )


def h_biggest(ans, s):
    period = s.period or "last_month"
    d = ans.call("biggest_expenses", period=period, n=5)
    when = in_period(d["period"])
    items = d["items"]
    if not items:
        ans.say(f"I couldn't find any spending {when}.")
        ans.suggest("How am I doing overall?", "Show my spending by basket")
        return
    ans.say(f"Your biggest payments {when}:")
    lines = []
    for i in items:
        kind = i.get("merchant_type")
        extra = (
            f", {kind.lower()}"
            if kind and kind.lower() != i["category"].lower()
            else ""
        )
        lines.append(
            f"{b(E(i['amount']))} on {vocab.display(i['category'])}{extra} "
            f"({vocab.day_label(i['date'])})"
        )
    ans.bullets(lines)
    leak = [i for i in items if i["basket"] == "leakage"]
    surprise = [i for i in items if i["basket"] == "mandatory_irregular"]
    if leak:
        ans.say(
            f"{plural(len(leak), 'of these was', 'of these were')} everyday "
            f"leakage ({E(sum(i['amount'] for i in leak))}), the easiest kind of "
            "spending to dial back."
        )
    elif all(i["basket"] == "mandatory_regular" for i in items):
        ans.say(
            "These are all must-pay bills, which are hard to change quickly, so "
            "your bigger wins are in the smaller everyday payments."
        )
    if surprise:
        total = sum(i["amount"] for i in surprise)
        ans.tip(
            f"surprise essentials like {surprise[0]['category'].lower()} "
            f"({E(total)} here) are easier with a sinking fund: put "
            f"{b(E(total / 12))} a month aside and next year's bill is covered."
        )
    else:
        ans.tip(
            "before any one-off purchase over €100, check your safe-to-spend "
            "figure first. It already sets aside upcoming bills."
        )
    ans.suggest(
        "Compare my last two months",
        "Show my spending by basket",
        "What is safe to spend this week?",
    )


def h_compare(ans, s):
    latest = a.last_months(ans.ctx.today, 2)
    months = list(s.months)
    if len(months) >= 2:
        a_key, b_key = months[0], months[1]
    elif len(months) == 1:
        a_key = months[0]
        b_key = latest[1] if a_key != latest[1] else latest[0]
    else:
        a_key, b_key = latest
    d = ans.call("compare_months", month_a=a_key, month_b=b_key)
    same_year = d["month_a"][:4] == d["month_b"][:4]
    la = vocab.month_label(d["month_a"], not same_year)
    lb = vocab.month_label(d["month_b"], not same_year)
    diff = d["diff"]
    if abs(diff) < 1:
        ans.say(
            f"You spent {b(E(d['total_b']))} in {lb}, almost exactly the same "
            f"as in {la}."
        )
    else:
        ans.say(
            f"You spent {b(E(d['total_b']))} in {lb}, {b(E(abs(diff)))} "
            f"{'more' if diff > 0 else 'less'} than in {la} "
            f"({E(d['total_a'])})."
        )
    rows = d["categories"][:4]
    if rows:
        ans.say("The biggest changes:")
        ans.bullets(
            f"{cat_label(r['category'])}: {'up' if r['diff'] > 0 else 'down'} "
            f"{b(E(abs(r['diff'])))} ({E(r['a'])} → {E(r['b'])})"
            for r in rows
        )
    ups = [r for r in rows if r["diff"] > 0]
    if ups and ups[0]["category"] in a.LEAKAGE_CATEGORIES:
        ans.tip(
            f"{vocab.display(ups[0]['category'])} grew the most. "
            + _sentence(category_tip(ups[0]["category"]))
        )
    elif diff < 0:
        ans.tip(
            f"you spent {E(abs(diff))} less in {lb}. Move that difference to "
            "savings now, before it quietly gets spent."
        )
    else:
        ans.tip(category_tip(ups[0]["category"] if ups else None))
    ans.suggest(
        "What are my biggest expenses?",
        "Show my spending by basket",
        "How am I doing overall?",
    )


def h_overview(ans, s):
    d = ans.call("get_overview_summary")
    rate, margin = d["savings_rate"], d["monthly_margin"]
    ans.say(
        ans.pick(
            "Here's your quick money check-up",
            "Here's the big picture",
            "Here's how you're doing",
        )
        + f", based on your account up to {vocab.full_date(d['as_of'])}:"
    )
    keep = (
        f"You keep {b(P(rate))} of your income ({E(margin)} a month)"
        if margin >= 0
        else f"You spend {b(E(-margin))} a month more than you earn"
    )
    ans.bullets(
        [
            f"Income: {b(E(d['income_monthly_avg']))} a month on average",
            f"Spending: {b(E(d['spend_monthly_avg']))} a month",
            keep,
            f"Balance today: {b(E(d['balance']))}",
            f"Spender type: {b(d['persona']['label'])}",
        ]
    )
    skip = {"Strong saver", "Spending more than you earn", "Thin margin"}
    notes = [i for i in d["insights"] if i["title"] not in skip][:2]
    if notes:
        ans.say("Worth knowing: " + " ".join(i["text"] for i in notes))
    if margin < 0:
        cat, monthly = biggest_leak(ans.ctx)
        ans.tip(
            f"closing a {E(-margin)} monthly gap starts with the easy wins. "
            f"Your biggest leak is {vocab.display(cat)} at {b(E(monthly))} a "
            "month."
        )
    elif rate < 0.10:
        gap = 0.10 * d["income_monthly_avg"] - margin
        ans.tip(
            f"saving 10% of your income would mean {b(E(gap))} more a month. "
            "An automatic transfer on payday is the easiest way to get there."
        )
    else:
        ans.tip(
            "you're saving well. Make it automatic with a standing transfer on "
            "payday, so the habit runs itself."
        )
    ans.suggest(
        "Show my spending by basket",
        "What is safe to spend this week?",
        "What kind of spender am I?",
    )


def h_explain(ans, s):
    key = s.term or "three_baskets"
    entry = GLOSSARY[key]
    ans.say(f"{b(entry['title'])}: {entry['text']}")
    if key == "savings_rate":
        d = ans.call("get_overview_summary", show_chart=False)
        ans.say(f"Yours is {b(P(d['savings_rate']))} over the last 12 months.")
    elif key == "safe_to_spend":
        d = ans.call("safe_to_spend", show_chart=False)
        if d["amount"] > 0:
            ans.say(
                f"Right now yours is {b(E(d['amount']))}, about "
                f"{b(E(d['per_day']))} a day until payday."
            )
        else:
            ans.say(
                f"Right now yours is {b('€0')}: the bills due before payday "
                "take up your whole balance."
            )
    elif key == "emergency_fund":
        d = ans.call("get_overview_summary", show_chart=False)
        target = 3 * d["spend_monthly_avg"]
        ans.say(
            f"For you that's about {b(E(target))}; your balance today is "
            f"{b(E(d['balance']))}."
        )
    elif key in ("ltv", "stress_test"):
        d = ans.call("home_readiness", show_chart=False)
        ans.say(
            f"On your income, the stress test allows a payment of about "
            f"{b(E(d['max_payment']))} a month, which points to a home of around "
            f"{b(E(d['max_property_price']))} with a {E(d['deposit_needed'])} "
            "deposit."
        )
    elif key == "compound_interest":
        proj = a.project_savings(100, 10)
        ans.say(
            f"For example, saving {b('€100 a month')} for 10 years at 3% gives "
            f"{b(E(proj[-1]['with_interest']))}, of which "
            f"{E(proj[-1]['with_interest'] - proj[-1]['saved'])} is interest."
        )
    else:
        ans.call("basket_breakdown")
    ans.concept = None  # the definition is already in the text
    ans.suggest(
        "Show my spending by basket",
        "What is safe to spend this week?",
        "What if I cut dining out by 20%?",
    )


def h_invest_advice(ans, s):
    d = ans.call("get_overview_summary", show_chart=False, show_concept=False)
    ans.say(
        "I can't recommend specific investments like stocks, funds or crypto. "
        "This isn't investment advice, and S-Pankki's advisers can help you "
        "with that."
    )
    margin = d["monthly_margin"]
    if margin > 0:
        ans.say(
            f"What I can tell you is how much room you have: you keep about "
            f"{b(E(margin))} a month, and your balance is {b(E(d['balance']))}."
        )
        ans.tip(
            f"before investing, keep about {b(E(3 * d['spend_monthly_avg']))} "
            "(three months of spending) as an emergency fund."
        )
    else:
        ans.say(
            f"Right now you spend about {b(E(-margin))} a month more than you "
            "earn, so building a cash buffer comes before investing."
        )
        ans.tip("start with a small automatic transfer to savings on payday.")
    ans.suggest(
        "What if I cut dining out by 20%?",
        "How am I doing overall?",
        "What kind of spender am I?",
    )


def h_cashflow(ans, s):
    d = ans.call("monthly_cashflow")
    avg, hi, lo = d["spend_monthly_avg"], d["highest"], d["lowest"]
    ans.say(
        f"Over the last 12 months you spent {b(E(avg))} a month on average "
        f"and took in {E(d['income_monthly_avg'])}."
    )
    ans.bullets(
        [
            f"Busiest month: {b(vocab.month_label(hi['month']))} at "
            f"{b(E(hi['spend']))}",
            f"Lightest month: {b(vocab.month_label(lo['month']))} at "
            f"{b(E(lo['spend']))}",
            f"Months with money left over: {b(str(d['months_in_green']) + ' of 12')}",
        ]
    )
    recent, before = d["recent_3_avg"], d["previous_3_avg"]
    if before > 0:
        change = (recent - before) / before
        if abs(change) < 0.05:
            trend = "about the same as the 3 months before"
        elif change > 1:
            trend = f"up from {E(before)} a month in the 3 months before"
        else:
            trend = (
                f"{'up' if change > 0 else 'down'} {P(abs(change))} on the 3 "
                "months before"
            )
        ans.say(
            f"Lately you've averaged {b(E(recent))} a month over the last 3 "
            f"months, {trend}."
        )
    if hi["spend"] > 1.4 * avg:
        ans.tip(
            f"{vocab.month_label(hi['month'], False)} was "
            f"{E(hi['spend'] - avg)} above your usual month. Putting a little "
            "aside every month for big one-offs keeps months like that from "
            "hurting."
        )
    else:
        ans.tip(
            "your spending is fairly steady month to month, which makes it easy "
            "to automate saving: set a standing transfer for payday."
        )
    ans.suggest(
        "Compare my last two months",
        "What are my biggest expenses?",
        "Show my spending by basket",
    )


def h_greeting(ans, s):
    d = ans.call("get_overview_summary", show_chart=False, show_concept=False)
    keep = (
        f"over the past year you've kept {b(P(d['savings_rate']))} of your income"
        if d["monthly_margin"] >= 0
        else f"over the past year you've spent {b(E(-d['monthly_margin']))} a "
        "month more than came in"
    )
    ans.say(
        ans.pick("Hi! I'm your Money Coach.", "Hello! Money Coach here."),
        f"I can see your account up to {vocab.full_date(d['as_of'])}: your "
        f"balance is {b(E(d['balance']))} and {keep}.",
    )
    ans.say(
        "Ask me where your money goes, what's safe to spend this week, or how a "
        "small cut adds up over time."
    )
    ans.suggest(
        "What is safe to spend this week?",
        "Show my spending by basket",
        "What kind of spender am I?",
    )


CAPABILITIES = [
    '**Spending**: by category, month or basket ("how much on groceries in '
    'August?")',
    "**Safe to spend**: what you can spend until payday",
    '**What-ifs**: "what if I cut dining out by 20%?"',
    '**Trends and comparisons**: "compare my last two months"',
    "**Your spender type** and **home-buying readiness**",
]


def h_help(ans, s):
    ans.say(
        "I'm your Money Coach. I read your own transactions and answer with "
        "real numbers. I can help with:"
    )
    ans.bullets(CAPABILITIES)
    ans.say("Just ask in your own words.")
    ans.suggest(
        "How am I doing overall?",
        "What is safe to spend this week?",
        "Am I ready to buy a home?",
    )


def h_thanks(ans, s):
    ans.say(
        ans.pick(
            "You're welcome! Anything else you'd like to look at?",
            "Happy to help. What would you like to check next?",
        )
    )
    ans.suggest(
        "What is safe to spend this week?",
        "What kind of spender am I?",
        "Am I ready to buy a home?",
    )


def h_fallback(ans, s):
    ans.say(
        "I'm not sure I understood that one. I'm best with questions about your "
        "own money, for example:"
    )
    ans.bullets(CAPABILITIES)
    ans.suggest(
        "How am I doing overall?",
        "Show my spending by basket",
        "What is safe to spend this week?",
    )


HANDLERS = {
    "taxi": h_taxi,
    "cashflow": h_cashflow,
    "cash_buffer": h_cash_buffer,
    "baskets": h_baskets,
    "safe_to_spend": h_safe_to_spend,
    "what_if": h_what_if,
    "persona": h_persona,
    "home": h_home,
    "spending": h_spending,
    "biggest": h_biggest,
    "compare": h_compare,
    "overview": h_overview,
    "explain": h_explain,
    "invest_advice": h_invest_advice,
    "greeting": h_greeting,
    "help": h_help,
    "thanks": h_thanks,
    "fallback": h_fallback,
}

# Follow-up chips for the Gemini provider, keyed by the tool it used last.
TOOL_INTENTS = {
    "get_overview_summary": "overview",
    "spend_by_category": "spending",
    "category_trend": "spending",
    "taxi_stats": "taxi",
    "what_if": "what_if",
    "safe_to_spend": "safe_to_spend",
    "compare_months": "compare",
    "biggest_expenses": "biggest",
    "get_persona": "persona",
    "home_readiness": "home",
    "basket_breakdown": "baskets",
    "monthly_cashflow": "cashflow",
}


def build_answer(ctx, messages):
    """Route the conversation and build an :class:`Answer`."""
    intent, slots = route(messages, ctx.today)
    question = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )
    seed = f"{ctx.customer_id}:{question.strip().lower()}"
    ans = Answer(ctx, question, seed)
    ans.intent = intent
    HANDLERS[intent](ans, slots)
    return ans


def suggestions_for_tools(ctx, tool_names, question=""):
    """Follow-up questions after a Gemini answer that used ``tool_names``."""
    intent = TOOL_INTENTS.get(tool_names[-1]) if tool_names else None
    ans = Answer(ctx, question, "suggest")
    if intent:
        dummy = Answer(ctx, question, "suggest")
        HANDLERS[intent](dummy, Slots())
        ans.suggestions = dummy.suggestions
    else:
        h_help(ans, Slots())
    return ans.suggestions[:3]


class OfflineProvider(Provider):
    name = "offline"
    model = None

    def stream(self, ctx, messages):
        ans = build_answer(ctx, messages)
        delay = token_delay()
        for name, label in ans.tools:
            yield tool_event(name, label)
            if delay:
                time.sleep(min(0.25, delay * 20))
        yield from stream_text(ans.text, delay)
        for chart in ans.charts:
            yield chart_event(chart)
        if ans.concept:
            yield concept_event(ans.concept)
        if ans.suggestions:
            yield suggestions_event(ans.suggestions)
