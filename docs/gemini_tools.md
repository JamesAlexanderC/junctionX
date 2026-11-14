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
(`create_goal` and `accept_plan` accept any yes after a proposal of their
kind.)

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
- A failed check gets one retry, then the fallback reply.
- A turn has at most 8 rounds of tool calls and about 60,000 characters of
  tool results. A result past that budget is replaced by an error, and its
  numbers can't be quoted.
