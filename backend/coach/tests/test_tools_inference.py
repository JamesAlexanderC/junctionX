"""list_inferences / get_inference: every computed inference reachable by Gemini.

The catalogue (coach/gemini/catalogue.py) is the single list of profile items
Gemini can read. These tests also guard against drift: an availability item
added to inferences/availability.py without a catalogue entry fails here.
"""

import pytest

from coach import services
from coach.gemini.catalogue import CATALOGUE, NOT_EXPOSED, MISSING, get_path
from coach.gemini.tools import DECLARATIONS, TOOLS, ToolContext, call_tool
from coach.gemini.tools.inference import MAX_LIST_ITEMS, chart_data, trim
from inferences.availability import RULES


def _call(customer, name, **args):
    return call_tool(ToolContext(customer), name, args)


# --- catalogue integrity -------------------------------------------------------


def test_every_catalogue_path_exists_in_a_built_profile(aino):
    profile = services.get_profile(aino)
    missing = [
        item for item, e in CATALOGUE.items() if get_path(profile, e.path) is MISSING
    ]
    assert missing == []


def test_every_gate_is_a_real_availability_item():
    bad = [
        i for i, e in CATALOGUE.items() if e.gate is not None and e.gate not in RULES
    ]
    assert bad == []


def test_every_availability_item_is_exposed_or_explained():
    covered = set(CATALOGUE) | {e.gate for e in CATALOGUE.values() if e.gate}
    assert set(RULES) - covered - set(NOT_EXPOSED) == set()


def test_new_tools_are_declared_and_registered():
    names = {d["name"] for d in DECLARATIONS}
    assert {"list_inferences", "get_inference"} <= names
    assert {"list_inferences", "get_inference"} <= set(TOOLS)


def test_item_enum_matches_catalogue():
    decl = next(d for d in DECLARATIONS if d["name"] == "get_inference")
    assert set(decl["parameters"]["properties"]["item"]["enum"]) == set(CATALOGUE)


# --- list_inferences -----------------------------------------------------------


def test_list_inferences_reports_availability_with_reasons(aino):
    out = _call(aino, "list_inferences")
    by_item = {row["item"]: row for row in out["items"]}
    assert set(by_item) == set(CATALOGUE)
    assert by_item["baskets.totals"]["available"] is True
    readiness = by_item["mortgage.readiness"]
    assert readiness["available"] is False and readiness["reason"]
    assert "reason" not in by_item["baskets.totals"]


def test_list_inferences_section_filter(aino):
    out = _call(aino, "list_inferences", section="income")
    assert out["items"]
    assert all(row["item"].startswith("income.") for row in out["items"])


def test_list_inferences_marks_chartable_items(aino):
    by_item = {r["item"]: r for r in _call(aino, "list_inferences")["items"]}
    assert by_item["forecast.daily_path"]["chart"] == "line"
    assert "chart" not in by_item["income.stability"]


# --- get_inference -------------------------------------------------------------


def test_get_inference_returns_profile_value(aino):
    profile = services.get_profile(aino)
    out = _call(aino, "get_inference", item="income.monthly_income")
    assert out["available"] is True
    assert out["data"] == profile["income"]["monthly_income"]
    assert out["inferences"] == [2]


def test_get_inference_respects_availability_gate(aino):
    out = _call(aino, "get_inference", item="mortgage.readiness")
    assert out["available"] is False
    assert out["item"] == "mortgage.readiness"
    assert out["reason"]
    assert "data" not in out


def test_get_inference_ungated_empty_value_is_unavailable(aino):
    # No loan details were entered for Aino.
    out = _call(aino, "get_inference", item="mortgage.loan_details")
    assert out["available"] is False
    assert out["reason"] == CATALOGUE["mortgage.loan_details"].missing_reason


def test_get_inference_summary_drops_transaction_ids(aino):
    out = _call(aino, "get_inference", item="income.bills")
    bill = out["data"][0]
    assert "tx_ids" not in bill
    assert bill["tx_ids_count"] == 4


def test_get_inference_full_keeps_transaction_ids(aino):
    out = _call(aino, "get_inference", item="income.bills", detail="full")
    assert len(out["data"][0]["tx_ids"]) == 4


def test_get_inference_series_has_chart_data(aino):
    profile = services.get_profile(aino)
    out = _call(aino, "get_inference", item="forecast.daily_path")
    path = profile["forecast"]["daily_path"]
    assert out["chart"] == {"kind": "line"}
    # FC-2: forecast points also carry the band and, on marked days, a flag.
    assert [
        (d["label"], d["value"], d["low"], d["high"]) for d in out["chart_data"]
    ] == [(p["date"], p["expected"], p["low"], p["high"]) for p in path]
    assert {d.get("flag") for d in out["chart_data"]} <= {
        None,
        "danger",
        "bill",
        "payday",
    }


def test_get_inference_dict_has_chart_data(aino):
    profile = services.get_profile(aino)
    out = _call(aino, "get_inference", item="baskets.totals")
    totals = profile["baskets"]["totals"]
    assert out["chart_data"] == [{"label": k, "value": v} for k, v in totals.items()]


def test_get_inference_unknown_item_is_an_error(aino):
    out = _call(aino, "get_inference", item="not.a.thing")
    assert "error" in out


def test_get_inference_bad_detail_is_an_error(aino):
    out = _call(aino, "get_inference", item="balance", detail="everything")
    assert "error" in out


# --- trimming and chart helpers (pure) -----------------------------------------


def test_trim_caps_long_lists_and_reports_it():
    value, trimmed = trim(list(range(30)))
    assert value == list(range(MAX_LIST_ITEMS))
    assert trimmed is True


def test_trim_keep_last_keeps_most_recent():
    value, _ = trim(list(range(30)), keep="last")
    assert value == list(range(30 - MAX_LIST_ITEMS, 30))


def test_trim_leaves_short_values_alone():
    data = {"a": 1, "b": [1, 2], "c": {"d": None}}
    value, trimmed = trim(data)
    assert value == data and trimmed is False


def test_trim_replaces_id_lists_with_counts_without_mutating():
    data = {"evidence_tx_ids": ["x", "y"], "nested": [{"tx_ids": ["a"]}]}
    value, trimmed = trim(data)
    assert value == {"evidence_tx_ids_count": 2, "nested": [{"tx_ids_count": 1}]}
    assert trimmed is False  # replacing ids is not a loss of insight data
    assert data["evidence_tx_ids"] == ["x", "y"]


@pytest.mark.parametrize(
    "item, value, expected",
    [
        (
            "income.monthly_income_series",
            [{"month": "2026-08", "value": 10.0}, {"month": "2026-09", "value": 12.5}],
            [{"label": "2026-08", "value": 10.0}, {"label": "2026-09", "value": 12.5}],
        ),
        (
            "whatif.category_means",
            {"groceries": 240.0, "coffee": None},
            [{"label": "groceries", "value": 240.0}],
        ),
    ],
)
def test_chart_data_skips_missing_values(item, value, expected):
    assert chart_data(CATALOGUE[item], value) == expected
