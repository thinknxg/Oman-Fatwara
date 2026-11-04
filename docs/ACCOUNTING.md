# Accounting workflows

All figures below are OMR. Invoice values are VAT exclusive unless stated otherwise. Use only the company's configured VAT accounts.

## Native invoice rows

| Scenario, base 100 | Input VAT row | Blocked expense row | Output VAT row | Supplier/customer total |
|---|---:|---:|---:|---:|
| Standard sale | — | — | Add 5% | 105 |
| Standard purchase, full recovery | Add 5% | — | — | 105 |
| Standard purchase, 50% recovery | Add 2.5% | Add 2.5% | — | 105 |
| Reverse charge, full recovery | Add 5% | — | Deduct 5% | 100 |
| Reverse charge, 50% recovery | Add 2.5% | Add 2.5% | Deduct 5% | 100 |
| Reverse charge, no recovery | — | Add 5% | Deduct 5% | 100 |

Input VAT and expense additions debit their accounts on purchases. The reverse charge deduction credits Output VAT and keeps the foreign supplier payable unchanged. ERPNext handles return signs; do not manually negate the VAT rates. Changing recovery or treatment requires applying/reviewing tax rows again.

Tax-inclusive sales may use ERPNext's Included in Print Rate setting. A gross 105 invoice at 5% should produce base 100 and VAT 5. Verify rounding and discount behavior on the target site. Do not use the Apply button after configuring inclusivity unless you intend to replace those rows.

## Customs-paid import

Goods customs taxable value 1,000, import VAT 50, recovery 60%:

- Supplier invoice: separately record the goods cost. Classify Out of Scope in this working paper if its customs value is reported through Oman VAT Entry.
- Customs VAT Journal Entry: debit Input VAT 30, debit Blocked VAT Expense 20, credit customs/bank/payable clearing 50.
- Oman VAT Entry: Customs Paid Import, base 1,000, VAT 50, recovery 60%, same date and company as the Journal Entry. Attach the customs reference.
- Working paper: value 1,000 in 4b and standard import value 1,000/input VAT 30 in 6b. The import tax is paid to customs and does not add to output VAT due.

Do not include other input/output VAT postings in the linked Journal Entry. One Journal Entry can support one submitted Oman VAT Entry; cancelled entries may be amended or replaced.

## Postponed import

Goods customs taxable value 1,000, VAT 50, recovery 50%:

- Journal Entry: debit Input VAT 25, debit Blocked VAT Expense 25, credit Output VAT 50.
- Oman VAT Entry: Postponed Import, base 1,000, VAT 50, recovery 50%.
- Working paper: 4a base 1,000/output VAT 50; 6b base 1,000/input VAT 25.

Only use postponed treatment where the taxpayer has the required authorization. For capital assets, select Capital Asset: eligible input is put in 6c instead of 6b; the import value remains in 4a/4b.

## Adjustments

An Output Adjustment with VAT -5 requires a linked Journal Entry with a net debit 5 to Output VAT. An Input Adjustment with VAT -3 requires net credit 3 to Input VAT. Set taxable base to zero for adjustments. Offsetting accounts and evidence depend on the underlying correction. These records do not decide whether a legal correction belongs in the current return or requires amendment of an earlier filing.

Credit/debit notes created as linked ERPNext return invoices already contribute their tax adjustments. Do not also create a manual VAT adjustment for the same note.

## Return totals

The summary displays the transaction boxes supported by the release. Output VAT before adjustments (5a) equals output from 1a + 2b + 4a. Output due (7a) adds 5b. Input credit (7b) sums 6a, 6b, 6c and 6d. Net payable (7c) is 7a minus 7b; a negative amount is a credit. It does not automatically include prior credit carryforward or payments.

The module reports real ERPNext VAT amounts. The portal may calculate 5% from aggregated taxable values and round differently. Reconcile any difference and document any necessary adjustment before filing.
