# Oman VAT for ERPNext v16

Source repository: [thinknxg/Oman-Fatwara](https://github.com/thinknxg/Oman-Fatwara). The Frappe app name is `oman_vat`.

Frappe application source, version **0.2.0**. Targets **Frappe and ERPNext 16.50 or later within v16**, using their Python 3.14 runtime. No core patches or controller replacements.

This release adds **multiple VAT treatments on one invoice** and **VAT-return/Fawtara transmission infrastructure**. No approved VAT filing API or accredited-provider connection was supplied, so no live transmission adapter is bundled. Automatic transmission remains disabled until that integration is installed and configured. See [integration requirements](docs/INTEGRATIONS.md).

## Included

- Company-specific activation and VAT account configuration.
- Sales and Purchase Invoice line VAT classification and submission checks, with header defaults.
- 5% standard VAT, zero rate, exempt, export and out of scope treatments.
- Purchase reverse charge, partial input recovery and blocked VAT expense posting through native ERPNext tax rows.
- Capital asset input VAT classification.
- Customs-paid and postponed imports, with evidence and matching submitted Journal Entries.
- Signed input/output adjustment records and linked credit/debit notes.
- OMR return working boxes, source register and downloadable reports through Frappe's normal export controls.
- Submitted return snapshots, overlap protection and period locks on source submission/cancellation.
- Per-line input recovery and capital asset classification, using native Item Tax Templates and v16 item-wise tax amounts.
- Separate return filing and Fawtara queues, frozen provider payloads, idempotency keys, receipt/status tracking, background dispatch and status reconciliation.
- Fawtara metadata fields and a canonical provider-data export for invoices/credit notes. Final PINT OM XML, TDD, signing/hash/QR and network delivery are the connected adapter's responsibility.

**Release status:** calculation and adapter unit tests pass locally. This package has not been installed on a running Frappe site in the authoring environment. Complete [the acceptance checks](docs/ACCEPTANCE.md) on a disposable ERPNext v16 site before deployment.

## Install

Use a Linux bench with supported Frappe/ERPNext v16 already installed. Back up the target site before installing. Extract this package so the directory containing `pyproject.toml` is `/srv/packages/oman_vat`, then run from your bench directory:

```sh
git -C /srv/packages/oman_vat init
git -C /srv/packages/oman_vat add .
git -C /srv/packages/oman_vat commit -m "Import Oman VAT 0.2.0"
bench get-app /srv/packages/oman_vat
bench --site your-site.example install-app oman_vat
bench --site your-site.example migrate
bench build --app oman_vat
bench restart
```

The archive's top-level directory is `oman_vat`. The first three commands make the extracted source a local Git repository so `bench get-app` can clone it; Git must have your usual author identity configured. Alternatively publish this directory to your own Git repository and use its repository URL. Do not run `bench new-app` over the supplied source. Production bench updates should use your maintained remote repository.

## Configure and use

1. Company must have Country **Oman**, company currency **OMR**, and its VAT registration number in **Tax ID**. Set OMR currency precision to three decimal places in ERPNext; confirm invoice totals use three decimals.
2. Create three enabled, non-group OMR accounts: **Input VAT** and **Output VAT** with account type **Tax**, plus **Blocked VAT Expense** with root type **Expense** and account type **Expense Account**. The account type is needed by ERPNext's native item tax template validation. Keep these accounts dedicated to VAT.
3. As Accounts Manager, open **Oman VAT Settings** through Desk search. Select the company, accounts, activation date, and Enabled. Activation is the start of the reporting coverage; historical submitted invoices on or after that date must be reviewed before return preparation. Configuration becomes locked once submitted VAT-classified transactions exist.
4. On a Sales or Purchase Invoice, choose a default **Oman VAT Treatment**, or choose treatments on each item row. Blank row treatments inherit the header. On purchase rows select **Override Input Recovery** to set a different recovery percentage, including 0%; select Capital Asset on capital rows. For mixed capital/expense invoices leave the header Capital Asset unchecked. Click **Apply Oman VAT**, review tax templates, rows and totals, then submit. The action replaces existing tax rows and item tax templates after confirmation. First-time template creation requires normal Item Tax Template create permission, usually Accounts Manager. Invoice clerks can reuse provisioned templates. ERPNext performs the accounting; the module validates its native item-wise amounts.
5. Record customs imports or exceptional adjustments as **Oman VAT Entry**, linking a matching submitted Journal Entry and supporting evidence. See [accounting examples](docs/ACCOUNTING.md).
6. Open **Oman VAT Summary** and **Oman VAT Register**, choose company and dates, and reconcile with the ledger. These reports are company-wide tax working papers restricted to Accounts Managers with access to that company.
7. Create **Oman VAT Return**, choose the period, save and review its boxes and totals. Submit only after the period ends. Submission freezes the working figures and locks the period against source submission/cancellation. With no connector, export the filing data and file in the portal. With a configured adapter, use **Queue Portal Filing** or enable automatic queuing. A source's ERPNext Submitted status does not establish remote acceptance: check its **Oman Tax Submission** status and Authority reference.
8. For Fawtara, complete the sales invoice transaction bitmap, buyer endpoint, each item's UNECE unit code, goods/services type, classification and applicable zero/exempt reason code. Credit notes require the original invoice and an Oman reason code. Export the provider data or use **Queue Fawtara Invoice** after configuring an accredited provider adapter. A System Manager manages **Oman Tax Connector** settings; automatic options are off by default.

The reporting date is the invoice or Journal Entry **posting date**. Arrange postings to reflect the correct legal tax point; advance payments and other tax-point differences need a reviewed adjustment process. An invoice cancellation within a submitted period requires cancelling the internal VAT Return first. Cancelling that document does not cancel a return already filed with the Authority.

## Scope of this release

- Multiple VAT treatments, recovery percentages and capital/expense classifications per invoice are supported in line mode. Recovery percentages have up to two decimal places. Each return row must preserve its original row's VAT classification; repeated item codes need an explicit original-row link.
- Invoice VAT rows must use **On Net Total**. Purchase tax rows must use category **Total**. Additional charges should be invoice items with their own VAT treatment. Generated Item Tax Templates carry explicit zero overrides to prevent standard tax from spilling onto exempt/zero lines. ERPNext Item/Item Group tax rules must permit the chosen templates; conflicting master rules are rejected at submission.
- Foreign transaction currencies are supported through ERPNext's company-currency amounts. The company itself must use OMR. Import values are the customs taxable value, which may differ from a supplier invoice.
- Zero rated/exempt imports have value-only import records. Import supplier invoices should be classified **Out of Scope** for this working paper when their customs declaration is reported separately; this avoids duplicate purchase values. Confirm the treatment of each actual supply before applying this workflow.
- Purchase blocked VAT is expensed by the module's native tax-row setup. Inventory or fixed assets requiring capitalization of irrecoverable VAT need a reviewed capitalization adjustment outside this release.
- Standard-rated returns affect output adjustment box 5b; purchase VAT returns affect input adjustment box 6d. Negative original invoices and unlinked returns are rejected.
- Inactive GCC boxes, profit margin schemes, deemed supplies without invoices, automated partial-exemption annual true-up, registration threshold monitoring, legacy backfill, POS Invoice/consolidation, advance VAT automation and Arabic statutory print layouts remain outside this release. Fawtara self-billing, inbound invoice processing, a built-in PINT serializer/validator and direct Peppol access-point operation are also outside this release. Use ordinary Sales Invoice for outbound sales.
- The return export is this app's JSON working data, not a claimed portal-upload format. The Fawtara export is canonical provider input, not certified PINT OM XML. Adapter onboarding, credentials and successful sandbox validation are required before either service can transmit.
- No automatic GL reconciliation of unrelated Journal Entries, VAT payments, or opening balances. Imports and adjustments are checked against their linked Journal Entry; managers must reconcile the complete period ledger separately. A snapshot hash detects accidental changes when compared independently; it is not a digital signature.
- No silent reclassification of existing submitted documents. A return fails when an in-period submitted invoice has no generated VAT snapshot. Use an audited migration for historical data.
- Framework Administrator access and direct database changes can bypass application controls, as with other Frappe apps.

## Validation and sources

Run the independent tests from this directory:

```sh
python -m unittest discover -s tests -v
```

The tests cover monetary rounding, signed notes, mixed-line box arithmetic, reverse charge, partial recovery, imports, native tax-row checks, Fawtara provider-payload mapping, acknowledgements and dispatch failure handling. They do not verify Frappe installation, browser behavior, database locking, actual ledger posting or a live remote connection. See [validation details](docs/VALIDATION.md).

## Upgrade from 0.1.0

Back up the site, replace/update the app source, then run `bench --site your-site.example migrate`, `bench build --app oman_vat` and restart. Confirm the blocked VAT expense account has account type Expense Account before creating line templates. Existing version-1 VAT snapshots remain readable and unchanged. Existing invoice-level workflows remain supported until Apply Oman VAT switches a draft to line mode. Historical submitted invoices are not silently rewritten. The new transmission features need a separately installed adapter, and old submitted invoices need a reviewed migration before Fawtara export.

Rules and return working boxes were checked against the Oman Tax Authority's [VAT return filing guide](https://tms.taxoman.gov.om/portal/documents/20126/1414820/VAT%2BTaxpayer%2BGuide%2B-%2BVAT%2BReturn%2BFiling.pdf/fae31d0c-e7e7-0014-9f28-a4c506b36614?t=1733169613409), its [VAT guidelines](https://tms.taxoman.gov.om/portal/vat-guidelines), and the Frappe/ERPNext **version-16** [framework hooks](https://docs.frappe.io/framework/user/en/python-api/hooks), [script reports](https://docs.frappe.io/framework/user/en/desk/reports/script-report), and [tax calculation implementation](https://github.com/frappe/erpnext/blob/version-16/erpnext/controllers/taxes_and_totals.py). The return guide is dated June 2021; mapping follows that published guide and needs review against the live portal before filing. Source review date: **4 November 2026**.

MIT licensed. See `license.txt`.
