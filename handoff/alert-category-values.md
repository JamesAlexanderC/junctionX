# Handoff: alert category, MCC and transaction-type values

## What is missing
The alert rules in `backend/inferences/alerts.py` classify transactions using
guessed sets in `backend/inferences/alert_thresholds.py`:

| Constant | Used by | Current guess |
|---|---|---|
| `OWN_TRANSFER_TYPES` | #94, #95, all spend totals | own_transfer, transfer_own, internal_transfer, savings_transfer |
| `LOAN_CATEGORIES`, `LOAN_MCCS` | #76-#84 | loan, mortgage, credit, bnpl...; MCC 6012, 6051, 6141 |
| `FEE_CATEGORIES`, `FEE_MCCS` | #86 | fee, late_fee, collection...; MCC 7322 |
| `ATM_MCC`, `GAMBLING_MCC` | #96, #98 | 6011, 7995 |

## Why it was not done here
The real CSVs (`tx_junction_transactions.csv`, Git LFS) are not in the repo and
the README lists no category or transaction_type values. Only P1.1 exploration
plus the S-Bank data scientist can confirm them (context.md, "The data").

## Next steps
1. Run P1.1 (`docs/data_profile.md`): list every unique `category`,
   `transaction_type` and top `mcc_code`.
2. Ask the S-Bank mentors which values mark own-account / savings transfers,
   loan repayments, credit-card bills and fees.
3. Update the sets in `alert_thresholds.py` (and the matching
   `OWN_TRANSFER_TYPES` in `inferences/thresholds.py` once A1's module exists;
   then dedupe so there is one source of truth).
4. If no loan payments exist in the data, loan alerts #76-#84 stay silent by
   design; #77/#82 still work from the "Add loan details" form (`loans` ctx).
5. Re-run `pytest inferences/tests/test_alerts.py` and check alerts on each
   demo customer for false positives.
