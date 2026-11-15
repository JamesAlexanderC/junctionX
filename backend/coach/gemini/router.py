"""Depth router: keyword rules first, Flash-Lite only when no rule matches."""

import logging
import re

log = logging.getLogger(__name__)

# Order matters: deeper intents win over "how much" inside "help me plan".
RULES = [
    (4, re.compile(r"\b(help me|plan|i want|buy a|save for|clear my)\b", re.I)),
    (
        3,
        re.compile(
            r"\b(what if|what would|could i save|can i save|save more|"
            r"spend less|cancel|cut)\b",
            re.I,
        ),
    ),
    (2, re.compile(r"\b(why|explain|what kind|what's my|what is my)\b", re.I)),
    (1, re.compile(r"\b(how much|when|kuinka paljon|milloin|paljonko)\b", re.I)),
]

ROUTER_PROMPT = (
    "Classify the money question by depth. Reply with one digit only: "
    "1 = a fact, 2 = explain, 3 = what-if, 4 = coach or plan.\nQuestion: "
)


# Saving or progress questions get the user's level in the answer (#28-#33).
# Only questions about getting better or the level itself; plain "save" in a
# fact, goal or bonus question is not one (live tests: the level card was
# attached to unrelated answers).
LEVELS_RE = re.compile(
    r"\b(how (can|do|could) i save|save more|saving more|spend less|levels?|"
    r"next step|doing well|how am i doing|improve|miten säästä\w*|taso\w*)\b",
    re.I,
)

LEVELS_HINT = (
    "This is about saving or progress: call get_level, attach its card, and "
    "frame the answer as the step to the next level."
)


# Accounts at other banks (MULTIBANK_PLAN.md MB-7), in en / fi / sv.
MULTIBANK_RE = re.compile(
    r"\b(other bank|another bank|second bank|other accounts?|all my accounts|"
    r"all accounts|nordea|op|danske|aktia|ålandsbanken|alandsbanken|"
    r"toinen pankki|toisen pankin|toiseen pankkiin|kaikki tilit|annan pankin|"
    r"annan bank|andra banken?|alla mina konton|connect\w*|yhdistä\w*|psd2)\b",
    re.I,
)
MULTIBANK_HINT = (
    "Other banks may matter here (simulated PSD2). If other_banks is set, "
    "also call get_multibank_insights for income, safe to spend, bills, loans "
    "or buffer questions, and name the bank each number comes from (loans: "
    "bank, day_of_month and amount; take a loan's date from "
    "get_multibank_insights, not from upcoming bills). Use "
    "get_accounts_overview for accounts "
    "and compare_linked_view for what changed."
)


def wants_multibank(message):
    return bool(MULTIBANK_RE.search(message or ""))


def wants_levels(message):
    return bool(LEVELS_RE.search(message or ""))


def rule_depth(message):
    for depth, pattern in RULES:
        if pattern.search(message):
            return depth
    return None


def route(message, client=None, model=None):
    """Return depth 1-4 for ``message``."""
    depth = rule_depth(message)
    if depth is not None or client is None:
        return depth or 2
    try:
        resp = client.models.generate_content(
            model=model, contents=ROUTER_PROMPT + message
        )
        match = re.search(r"[1-4]", resp.text or "")
        return int(match.group()) if match else 2
    except Exception:  # noqa: BLE001 - router must never break chat
        log.exception("router failed, defaulting to depth 2")
        return 2


# --- conversation C: small talk is answered directly, in one round ---------------

CHAT_RE = re.compile(
    r"\b(thanks?|thank you|thx|kiitos|cheers|hi|hello|hey|moi|terve|"
    r"good (morning|evening|night)|ok(ay)?|cool|great|nice|got it|i see|"
    r"makes sense|fair enough|all good|no worries|never ?mind|familiar|"
    r"that was me|that's me|it was me|died|passed away|funeral|sad|stressed|"
    r"anxious|worried|upset|lonely|depressed|heartbroken|lost my job|"
    r"break ?up|divorce|sick)\b",
    re.I,
)
DATA_RE = re.compile(
    r"€|\b(money|spend\w*|spent|sav\w+|euros?|eur|budget|pay\w*|bills?|"
    r"afford\w*|loans?|mortgage|goals?|balance|income|salary|costs?|prices?|"
    r"how much|levels?|charts?|baskets?|alerts?|plan|cut|cancel|"
    r"rahaa?|säästä\w*)\b",
    re.I,
)
QUESTION_RE = re.compile(
    r"\?|^\s*(what|why|how|when|where|which|who|can|could|should|would|do|does|"
    r"did|is|are|will|show|explain|tell)\b",
    re.I,
)
# One-word answers that drive a flow (confirm, undo, question-card options).
REPLY_WORDS = {
    "yes",
    "yeah",
    "yep",
    "no",
    "nope",
    "sure",
    "undo",
    "high",
    "medium",
    "low",
    "kyllä",
    "joo",
}


def is_conversational(message):
    """True for thanks, greetings, acknowledgements ("looks familiar") and
    feelings ("my dog died"): no question, no money words, no flow answer."""
    text = (message or "").strip()
    if not text or text.lower().strip(" .!") in REPLY_WORDS:
        return False
    if QUESTION_RE.search(text) or DATA_RE.search(text):
        return False
    return bool(CHAT_RE.search(text))
