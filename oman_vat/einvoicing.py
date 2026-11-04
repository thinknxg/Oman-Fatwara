"""Canonical Fawtara provider input, not a claim of PINT XML conformance.

The accredited provider adapter must render and validate PINT OM Billing / TDD,
apply the architecture's UUID, hash and QR requirements, and transmit securely.
"""
import json
import re

import frappe

from oman_vat.core import money
from oman_vat.lines import P
from oman_vat.transmission import document_uuid

CATEGORIES = {"Standard Rated": "S", "Zero Rated": "Z", "Export": "Z", "Exempt": "E", "Out of Scope": "O"}


def party_address(name):
    if not name:
        frappe.throw("Fawtara requires seller and buyer addresses on the invoice.")
    address = frappe.get_doc("Address", name)
    country_code = frappe.db.get_value("Country", address.country, "code")
    return dict(address_line1=address.address_line1, address_line2=address.address_line2,
                city=address.city, postal_code=address.pincode,
                country_code=(country_code or "").upper(), phone=address.phone)


def invoice_payload(doc, connector):
    if doc.doctype != "Sales Invoice" or doc.docstatus != 1:
        frappe.throw("Fawtara outbound submission requires a submitted Sales Invoice.")
    snapshot = json.loads(doc.get(P + "snapshot") or "{}")
    if snapshot.get("version") != 2:
        frappe.throw("Prepare this invoice with line VAT before e-invoicing. Historical invoices need a reviewed migration.")
    bitmap = doc.get("custom_fawtara_transaction_type") or ""
    if not re.fullmatch(r"[01]{20}", bitmap) or bitmap[:2] not in ("10", "01"):
        frappe.throw("Choose a valid 20-bit Oman transaction type with exactly one of Full or Simplified selected.")
    if doc.is_return and not doc.get("custom_fawtara_credit_reason_code"):
        frappe.throw("An electronic credit note requires an applicable Oman credit-note reason code.")
    seller = frappe.get_doc("Company", doc.company)
    if not re.fullmatch(r"OM\d{10}", seller.tax_id or ""):
        frappe.throw("Fawtara requires the seller VATIN in the format OM followed by 10 digits.")
    buyer = frappe.get_doc("Customer", doc.customer)
    seller_address = party_address(doc.company_address)
    buyer_address = party_address(doc.customer_address)
    original = None
    if doc.is_return:
        if not doc.return_against:
            frappe.throw("An electronic credit note requires its original invoice.")
        previous = frappe.get_doc("Sales Invoice", doc.return_against)
        original = dict(number=previous.name, issue_date=str(previous.posting_date),
                        uuid=document_uuid(seller.tax_id, previous.doctype, previous.name))
    frozen = {row["item_row"]: row for row in snapshot["lines"]}
    entries = snapshot["entries"]
    lines = []
    for item in doc.items:
        values = frozen[item.name]
        treatment = values["treatment"]
        reason = item.get("custom_fawtara_tax_reason_code")
        if treatment in ("Zero Rated", "Export") and not re.fullmatch(r"VATZR-OM-(0[1-9]|1[0-6])", reason or ""):
            frappe.throw(f"Row {item.idx}: choose an applicable Oman zero-rating reason code.")
        if treatment == "Exempt" and not re.fullmatch(r"VATEX-OM-(0[1-9]|1[0-2])", reason or ""):
            frappe.throw(f"Row {item.idx}: choose an applicable Oman exemption reason code.")
        if treatment in ("Standard Rated", "Out of Scope") and reason:
            frappe.throw(f"Row {item.idx}: this VAT category must not have an exemption code.")
        uom = item.get("custom_fawtara_uom_code")
        if not uom or not item.get("custom_fawtara_item_type"):
            frappe.throw(f"Row {item.idx}: enter the UNECE unit code and goods/services type.")
        sign = -1 if doc.is_return else 1
        vat = sum((money(row["output"]) for row in entries if row.get("item_row") == item.name), money(0))
        lines.append(dict(row_id=item.name, line_number=item.idx, item_code=item.item_code,
                          description=item.item_name, quantity=str(item.qty * sign), unit_code=uom,
                          item_type=item.get("custom_fawtara_item_type"),
                          classification_code=item.get("custom_fawtara_classification_code"),
                          vat_category=CATEGORIES[treatment], vat_rate="5" if treatment == "Standard Rated" else "0",
                          tax_reason_code=reason, net_amount=str(money(item.net_amount) * sign),
                          net_amount_omr=str(money(item.base_net_amount) * sign),
                          vat_amount_omr=str(vat * sign), net_unit_price=str(item.net_rate),
                          treatment=treatment))
    sign = -1 if doc.is_return else 1
    return dict(schema="oman_vat.fawtara.input.v1", source_type=doc.doctype, source_name=doc.name,
        company=doc.company, document_uuid=document_uuid(seller.tax_id, doc.doctype, doc.name),
        document_type="381" if doc.is_return else "380", issue_date=str(doc.posting_date),
        issue_time=str(doc.posting_time), currency=doc.currency, accounting_currency="OMR",
        exchange_rate=str(doc.conversion_rate), transaction_type=doc.get("custom_fawtara_transaction_type"),
        credit_note_reason_code=doc.get("custom_fawtara_credit_reason_code"), original_invoice=original,
        seller=dict(name=seller.company_name, vat_registration=seller.tax_id,
                    endpoint_id=connector.seller_endpoint, endpoint_scheme=connector.endpoint_scheme,
                    address=seller_address),
        buyer=dict(name=buyer.customer_name, vat_registration=doc.tax_id,
                   endpoint_id=doc.get("custom_fawtara_buyer_endpoint"),
                   endpoint_scheme=doc.get("custom_fawtara_buyer_endpoint_scheme"), address=buyer_address),
        lines=lines, vat_snapshot=snapshot,
        native_taxes=[dict(account=row.account_head, rate=str(row.rate),
                          tax_amount=str(row.tax_amount_after_discount_amount),
                          tax_amount_omr=str(row.base_tax_amount_after_discount_amount)) for row in doc.taxes],
        totals=dict(net_amount=str(money(doc.net_total) * sign),
                    gross_amount=str(money(doc.grand_total) * sign),
                    rounding_amount=str(money(doc.rounding_adjustment) * sign),
                    paid_amount=str(money(doc.paid_amount) * sign),
                    advance_amount=str(money(doc.total_advance) * sign),
                    payable_amount=str((money(doc.grand_total) + money(doc.rounding_adjustment)
                                        - money(doc.paid_amount) - money(doc.total_advance)) * sign)))
