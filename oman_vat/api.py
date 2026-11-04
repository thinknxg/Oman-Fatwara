import frappe

from oman_vat.access import require_manager, settings_for
from oman_vat.core import expected_rates


@frappe.whitelist()
def invoice_plan(document):
    from oman_vat.lines import make_plan
    data = frappe.parse_json(document)
    if data.get("doctype") not in ("Sales Invoice", "Purchase Invoice"):
        frappe.throw("Choose a Sales or Purchase Invoice.")
    doc = frappe.get_doc(data)
    if doc.docstatus != 0:
        frappe.throw("Apply VAT only to draft invoices.")
    if not doc.is_new() and frappe.db.exists(doc.doctype, doc.name):
        saved = frappe.get_doc(doc.doctype, doc.name)
        saved.check_permission("write")
    else:
        frappe.has_permission(doc.doctype, "create", throw=True)
    frappe.get_doc("Company", doc.company).check_permission("read")
    try:
        return make_plan(doc, settings_for(doc.company))
    except ValueError as exc:
        frappe.throw(str(exc))


@frappe.whitelist()
def tax_rows(company, invoice_type, treatment, recovery_percent=100):
    # Users can prepare invoices with their ordinary invoice permission.
    frappe.has_permission(invoice_type, "create", throw=True)
    frappe.get_doc("Company", company).check_permission("read")
    settings = settings_for(company)
    try:
        rates = expected_rates(invoice_type, treatment, recovery_percent)
    except ValueError as exc:
        frappe.throw(str(exc))
    rows = []
    for role, rate in rates.items():
        row = {"charge_type": "On Net Total", "account_head": getattr(settings, role + "_account"),
               "description": "Oman VAT " + role, "rate": float(rate)}
        if invoice_type == "Purchase Invoice":
            row.update(category="Total", add_deduct_tax="Deduct" if role == "output" else "Add")
        rows.append(row)
    return rows
