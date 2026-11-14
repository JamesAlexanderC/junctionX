# Gemini tools: reading inferences and changing user data

How the coach's model reaches the numbers Python computes, and how it changes
what the user has saved. Code lives in `backend/coach/gemini/`.

## Layout

| File | What it holds |
|---|---|
| `tools/declarations.py` | The function declarations Gemini sees, and argument checks |
| `tools/registry.py` | Tool name to function, availability gating, `call_tool` |
| `tools/read.py` | Single-purpose read tools (`get_safe_to_spend`, `get_baskets`, ...) |
| `tools/inference.py` | `list_inferences` and `get_inference` |
| `tools/goals.py` | `list_goals`, `create_goal`, `manage_goal`, `rate_goal`, `dismiss_suggestion` |
| `tools/loans.py` | `save_loan_details` |
| `tools/alerts.py` | The alert coach tools |
| `tools/context.py` | `ToolContext`, the propose and confirm helpers |
| `catalogue.py` | Every profile item `get_inference` can read |
| `cards.py` | The `send_reply` card payloads as pydantic models |
| `validate.py` | `send_reply` checks: numbers in the text and in the cards |

## Reading any inference

`list_inferences(section?)` lists every catalogue item with whether the
customer's data supports it (and why not). `get_inference(item, detail?)`
returns one item:

```json
{"available": true, "item": "income.stability", "inferences": [3],
 "about": "How steady income is month to month (variation and a label).",
 "data": {"cv": 0.06, "label": "Steady"}}
```

- The default `detail="summary"` turns lists of transaction ids into counts
  and keeps at most 12 rows of a long list. `detail="full"` returns
  everything.
- Chartable items also return `chart` and `chart_data` (`[{label, value}]`)
  to copy into a chart card.
- Unavailable items return `{"available": false, "reason": ...}`, never a
  default value.

## Charts

The app draws charts on the phone; Gemini only picks what to chart.
`get_chart(item)` takes any catalogue item with a `chart` spec and returns a
complete card that Gemini attaches to `send_reply` unchanged:

```json
{"available": true, "item": "baskets.totals", "inferences": [7, 8, 9, 10],
 "card": {"type": "chart", "kind": "bar", "title": "Spending by basket this month",
          "unit": "EUR", "data": [{"label": "essential", "value": 890.0}]}}
```

The frontend (`frontend/src/components/Chart.jsx`) draws `bar` as columns
from zero and `line` as a line with a light area. Tap, hover or the arrow keys
show the exact value of a point. To make an item chartable, give its `Entry` a
`Chart(kind, label_key, value_key, title, unit)`; `get_chart`, its enum and
`list_inferences` pick it up.

## Levels guidance

`get_level` returns the levels profile (#28 to #33) plus `card`, a ready
`level_progress` card for the level the user is working towards, with the
six-step ladder. The router's `wants_levels` spots saving and progress
questions ("How can I save more?") and adds a hint to that turn to answer
with `get_level` and its card, framed as the step to the next level.

### Exposing a new inference

Add one `Entry` to `_ENTRIES` in `catalogue.py`:

```python
Entry(
    "income.monthly_income_series",     # dotted path in the profile
    "Income for each month.",           # what Gemini reads in list_inferences
    gate="income.monthly_income",       # availability item, or None
    chart=Chart("bar", "month", "value"),
    keep="last",                        # long lists keep the newest rows
),
```

Without a `gate`, the item is unavailable when its value is empty and
returns `missing_reason`. `coach/tests/test_tools_inference.py` fails when a
catalogue path is missing from a built profile, or when an item in
`inferences/availability.py` has no entry (list deliberate exceptions in
`NOT_EXPOSED`).

## Changing user data

| Tool | What it does | Rules shared with |
|---|---|---|
| `create_goal` | New goal | REST goal form checks |
| `manage_goal` | `edit`, `pause`, `resume`, `complete`, `abandon`, `add_saved`, `check_step`, `undo` | `GoalSerializer` (`PATCH /api/goals/<id>/`) |
| `save_loan_details` | Loan balance, rate, years left | `LoanSerializer` (`POST /api/loans/`) |
| `dismiss_suggestion` | Hide a detected goal (`det-*`) for good | `DismissedSuggestion` model |
| `accept_plan` | Save an alert-coach plan as a checklist goal | |

**Propose, then confirm.** A write first returns
`{"status": "needs_confirmation", "proposal": ...}` and stores the proposal on
the chat turn. It runs only when the user's next message says yes and Gemini
sends the same proposal again. A changed request is proposed again.
`create_goal` executes the stored proposal even if model arguments drift;
`accept_plan` requires the exact proposed actions. Negative or ambiguous
messages do not confirm. Proposals are consumed atomically with the write,
so repeated tool calls and stale requests cannot execute them twice.

Monthly savings capacity uses the recurring Saver rate only. Available cash
today remains a one-off amount. Evaluated goals include `one_off_scenario`
with the optional contribution and resulting date; this does not change
recorded savings or make a recurring commitment affordable.

Slider cards receive `as_of` from the server's profile date after validation,
including cached replies. The frontend uses this date and the same nine-decimal
goal-month rounding as Python. Older cards without it do not show a goal date.

Planner scenarios keep one dated balance path: spending cuts reduce daily
outflows, cancelled subscriptions remove their actual scheduled payments, and
moving savings adds a one-off balance change. Month-end balance, danger days
and safe-to-save are derived from that path. Changes to the existing weekly
allowance use the extra pre-payday capacity, prorated over that pay cycle and
capped by current cash less the buffer. The uncertainty band is retained.

**`add_saved` fast path.** Recording money the user already put aside runs at
once when Python can see that:

1. the exact amount is in the user's message,
2. exactly one active goal fits (they have one, or they named it), and
3. it does not take the goal past its target.

Otherwise it is proposed like any other write. After a fast add, the next
message "Undo" (`manage_goal` with `action: "undo"`) reverses it.

## Checks on every reply

- Every number in the reply text, and in every card (except ids, slider
  settings and question options), must appear in a tool result from this turn
  or in the user's message.
- Each card must match its payload in `cards.py`; unknown fields are dropped
  and unknown card types are removed.
- Currency and percentage claims use separate source pools. Only fractional
  percentage fields permit scaling by 100. Dates and counts cannot justify
  euro amounts; the small-count allowance does not apply to currency cards.
- A failed check gets one retry, then the fallback reply.
- A turn has at most 5 rounds of tool calls and about 60,000 characters of
  tool results. A result past that budget is replaced by an error, and its
  numbers can't be quoted.

## Conversations and Overview refresh

`POST /api/chat/` accepts a UUID `conversation_id` and returns it with the
reply. A conversation belongs to the authenticated user and one customer;
foreign users or a different customer receive 404. The frontend creates a
new UUID when opening a customer and reuses it for subsequent messages.
Stored history, pending confirmations and demo caches are scoped to that
conversation. Client-supplied history is not used by the authenticated API.
Older clients without an id reuse that user's first conversation for the
customer. Existing unowned chat turns remain stored but are not imported
into owned conversations.

Replies include `state_changed`, determined by successful write tools rather
than model text. A successful write triggers an Overview reload, including
when a later model reply fails. Proposals and read tools do not trigger it.
The current Overview stays visible during refresh; errors offer a retry.
Write replies are never cached, so a cached reply cannot impersonate a write.

Apply migration 0004 with `python manage.py migrate` before running this build.
