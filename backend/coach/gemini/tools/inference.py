"""list_inferences / get_inference: read any item in the catalogue.

Results are summaries by default so tool results stay small: lists of
transaction ids become counts and long lists keep MAX_LIST_ITEMS rows.
``detail="full"`` returns the stored value as it is. Chartable items also
carry ``chart_data`` ready for a chart card, so every charted number comes
from this tool result.
"""

import copy

from inferences.availability import available

from ..catalogue import CATALOGUE, MISSING, Entry, get_path
from ..catalogue import section as section_of
from .context import ToolError, _missing, unavailable

MAX_LIST_ITEMS = 12
MAX_CHART_POINTS = 36
ID_SUFFIX = "tx_ids"
SECTIONS = sorted({section_of(item) for item in CATALOGUE})


def trim(value, keep: str = "first"):
    """(summary copy of value, True when a list lost rows). Never mutates."""
    if isinstance(value, dict):
        out, lost = {}, False
        for key, item in value.items():
            if key.endswith(ID_SUFFIX) and isinstance(item, list):
                out[f"{key}_count"] = len(item)
                continue
            out[key], item_lost = trim(item, keep)
            lost = lost or item_lost
        return out, lost
    if isinstance(value, list):
        lost = len(value) > MAX_LIST_ITEMS
        if lost:
            value = (
                value[-MAX_LIST_ITEMS:] if keep == "last" else value[:MAX_LIST_ITEMS]
            )
        rows = [trim(item, keep) for item in value]
        return [row for row, _ in rows], lost or any(cut for _, cut in rows)
    return value, False


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def chart_data(entry: Entry, value) -> list[dict]:
    """[{label, value}] for a chart card; rows without a number are skipped."""
    chart = entry.chart
    if chart is None:
        return []
    if isinstance(value, dict):
        pairs = list(value.items())
    elif isinstance(value, list):
        pairs = [
            (row.get(chart.label_key), row.get(chart.value_key))
            for row in value
            if isinstance(row, dict)
        ]
    else:
        return []
    points = [{"label": str(k), "value": v} for k, v in pairs if _is_number(v)]
    return points[-MAX_CHART_POINTS:]


def chart_card(entry: Entry, value) -> dict | None:
    """A complete chart card for a chartable entry, or None without data."""
    data = chart_data(entry, value)
    if not data:
        return None
    card = {
        "type": "chart",
        "kind": entry.chart.kind,
        "title": entry.chart.title or entry.about,
        "data": data,
    }
    if entry.chart.unit:
        card["unit"] = entry.chart.unit
    return card


def _status(profile: dict, entry: Entry):
    """(available, reason, inference numbers) for one entry."""
    value = get_path(profile, entry.path)
    numbers = list(entry.inferences)
    if entry.gate is not None:
        stored = (profile.get("availability") or {}).get(entry.gate) or {}
        numbers = list(stored.get("inferences") or numbers)
        if not available(profile, entry.gate):
            return False, stored.get("reason") or entry.missing_reason, numbers
        if value is MISSING or value is None:
            return False, entry.missing_reason, numbers
        return True, None, numbers
    if value is MISSING or _missing(value):
        return False, entry.missing_reason, numbers
    return True, None, numbers


def list_inferences(ctx, section=None):
    """Every catalogue item with its availability for this customer."""
    wanted = section
    if wanted is not None and wanted not in SECTIONS:
        raise ToolError(f"section must be one of {SECTIONS}")
    rows = []
    for item, entry in CATALOGUE.items():
        if wanted is not None and section_of(item) != wanted:
            continue
        ok, reason, _ = _status(ctx.profile, entry)
        row = {"item": item, "about": entry.about, "available": ok}
        if not ok:
            row["reason"] = reason
        if entry.chart is not None:
            row["chart"] = entry.chart.kind
        rows.append(row)
    return {"items": rows}


def get_inference(ctx, item, detail="summary"):
    """One catalogue item: its data (summary or full) and chart data."""
    entry = CATALOGUE.get(item)
    if entry is None:
        raise ToolError(f"Unknown item {item}; call list_inferences")
    ok, reason, numbers = _status(ctx.profile, entry)
    if not ok:
        return unavailable(reason, item=item)
    raw = get_path(ctx.profile, entry.path)
    if detail == "full":
        data, lost = copy.deepcopy(raw), False
    else:
        data, lost = trim(raw, entry.keep)
    out = {
        "available": True,
        "item": item,
        "about": entry.about,
        "inferences": numbers,
        "data": data,
    }
    if lost:
        out["note"] = "Some lists were shortened; use detail='full' for all rows."
    if entry.chart is not None:
        out["chart"] = {"kind": entry.chart.kind}
        out["chart_data"] = chart_data(entry, raw)
    return out


CHARTABLE = [item for item, entry in CATALOGUE.items() if entry.chart is not None]


def get_chart(ctx, item):
    """A ready chart card for one chartable item: attach it to send_reply as is.

    Python picks the chart kind, title, unit and points, so every charted
    number comes straight from the profile.
    """
    entry = CATALOGUE.get(item)
    if entry is None or entry.chart is None:
        raise ToolError(f"{item} cannot be charted; chartable items: {CHARTABLE}")
    ok, reason, numbers = _status(ctx.profile, entry)
    if not ok:
        return unavailable(reason, item=item)
    card = chart_card(entry, get_path(ctx.profile, entry.path))
    if card is None:
        return unavailable("There are no numbers to chart yet.", item=item)
    return {"available": True, "item": item, "inferences": numbers, "card": card}
