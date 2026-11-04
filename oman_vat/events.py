import json

import frappe
from frappe.utils import getdate

from oman_vat.access import assert_open, lock_company, settings_for
from oman_vat.core import dec, expected_rates, invoice_entries, money

PREFIX = "custom_oman_vat_"


def before_submit(doc, method=None):
    # A company without settings is unaffected; setup explicitly opts in.
    if not frappe.db.exists("Oman VAT Settings", doc.company):
        return
    lock_company(doc.company)
    settings = settings_for(doc.company)
    if getdate(doc.posting_date) < getdate(settings.effective_from):
        frappe.throw("Invoices before Oman VAT activation require a historical migration process.")
    assert_open(doc.company, doc.posting_date)
    if doc.get("is_opening") == "Yes" or doc.get("is_internal_supplier") or doc.get("is_internal_customer"):
        frappe.throw("Opening and internal transfer invoices require a separately reviewed VAT treatment.")
    from oman_vat.lines import validate_lines, validate_return_lines
    line_mode = doc.get(PREFIX + "line_mode") or any(
        item.get(PREFIX + "treatment") or item.get(PREFIX + "override_recovery")
        or item.get(PREFIX + "capital_asset") for item in doc.items
    )
    if line_mode:
        try:
            snapshot = validate_lines(doc, settings)
            if doc.is_return:
                if not doc.return_against:
                    raise ValueError("Oman VAT returns require an original invoice reference")
                original = frappe.get_doc(doc.doctype, doc.return_against)
                if original.company != doc.company or original.docstatus != 1:
                    raise ValueError("The original invoice must be submitted in this company")
                validate_return_lines(doc, original)
        except ValueError as exc:
            frappe.throw(str(exc))
        doc.set(PREFIX + "snapshot", json.dumps(snapshot, sort_keys=True))
        return
    treatment = doc.get(PREFIX + "treatment")
    recovery = doc.get(PREFIX + "recovery_percent") if doc.doctype == "Purchase Invoice" else 100
    accounts = {"output": settings.output_account, "input": settings.input_account,
                "blocked": settings.blocked_account}
    try:
        rates = expected_rates(doc.doctype, treatment, recovery)
        amounts = validate_taxes(doc, accounts, rates)
        entries = invoice_entries(
            doc.doctype, treatment, doc.base_net_total,
            output=amounts.get("output", 0), input_vat=amounts.get("input", 0),
            capital=bool(doc.get(PREFIX + "capital_asset")), is_return=bool(doc.is_return),
        )
    except ValueError as exc:
        frappe.throw(str(exc))
    if doc.is_return:
        if not doc.return_against:
            frappe.throw("Oman VAT returns require an original invoice reference.")
        original = frappe.get_doc(doc.doctype, doc.return_against)
        if (original.company != doc.company or original.docstatus != 1
                or original.get(PREFIX + "treatment") != treatment):
            frappe.throw("The original invoice must be submitted, in this company, with the same VAT treatment.")
        if doc.doctype == "Purchase Invoice" and (
            dec(original.get(PREFIX + "recovery_percent")) != dec(recovery)
            or bool(original.get(PREFIX + "capital_asset")) != bool(doc.get(PREFIX + "capital_asset"))
        ):
            frappe.throw("Use the original invoice's input recovery and capital asset classification.")
    if treatment == "Export" and not doc.get(PREFIX + "evidence"):
        frappe.throw("Enter an export evidence reference.")
    doc.set(PREFIX + "snapshot", json.dumps({"version": 1, "entries": entries}, sort_keys=True))


def validate_taxes(doc, accounts, rates):
    """Reconcile native signed base taxes and rates; reject ambiguous mixed invoices."""
    amounts = {}
    seen = set()
    tolerance = dec("0.001") * (len(doc.items) + 2)
    for row in doc.get("taxes") or []:
        role = next((role for role, account in accounts.items() if row.account_head == account), None)
        if role is None or role not in rates:
            raise ValueError("Use only the applicable Oman VAT tax rows. Split additional charges into invoice items.")
        if role in seen:
            raise ValueError("Only one tax row per Oman VAT account is supported")
        seen.add(role)
        if row.charge_type != "On Net Total":
            raise ValueError("Invoice VAT rows must use On Net Total")
        if doc.doctype == "Purchase Invoice" and row.category != "Total":
            raise ValueError("Purchase VAT tax rows must use category Total")
        expected_direction = "Deduct" if role == "output" and doc.doctype == "Purchase Invoice" else "Add"
        if (row.get("add_deduct_tax") or "Add") != expected_direction:
            raise ValueError("Incorrect Add/Deduct direction for the VAT tax row")
        if dec(row.rate) != rates[role]:
            raise ValueError("VAT tax row rate does not match treatment and recovery percentage")
        for item in doc.items:
            overrides = json.loads(item.get("item_tax_rate") or "{}")
            if row.account_head in overrides and dec(overrides[row.account_head]) != rates[role]:
                raise ValueError("Mixed item VAT rates require separate invoices")
        amount = money(row.base_tax_amount_after_discount_amount)
        expected = money(dec(doc.base_net_total) * rates[role] / 100)
        if abs(amount - expected) > tolerance:
            raise ValueError("Calculated ERPNext VAT does not reconcile with the taxable base")
        amounts[role] = amount
    if seen != set(rates):
        raise ValueError("Apply the Oman VAT tax rows before submitting this invoice")
    return amounts


def before_cancel(doc, method=None):
    from oman_vat.dispatch import block_source_cancel
    block_source_cancel(doc)
    if not doc.get(PREFIX + "snapshot"):
        return
    lock_company(doc.company)
    assert_open(doc.company, doc.posting_date)


def journal_before_cancel(doc, method=None):
    lock_company(doc.company)
    table = frappe.qb.DocType("Oman VAT Entry")
    linked = (frappe.qb.from_(table).select(table.name)
              .where((table.journal_entry == doc.name) & (table.docstatus == 1)).for_update().run())
    if linked:
        frappe.throw("Cancel the linked Oman VAT Entry before cancelling this Journal Entry.")
