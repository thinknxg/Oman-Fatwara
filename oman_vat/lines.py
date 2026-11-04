"""Line VAT classification using ERPNext v16's native item-wise tax breakdown."""
import hashlib
import json

import frappe

from oman_vat.core import Q, dec, expected_rates, invoice_entries, money

P = "custom_oman_vat_"


def profile(doc, item):
    treatment = item.get(P + "treatment") or doc.get(P + "treatment")
    recovery = 100
    if doc.doctype == "Purchase Invoice":
        recovery = (item.get(P + "recovery_percent") if item.get(P + "override_recovery")
                    else doc.get(P + "recovery_percent"))
        if recovery is None:
            recovery = 100
        if dec(recovery) != dec(recovery).quantize(dec("0.01")):
            raise ValueError("Use recovery percentages with at most two decimal places")
    capital = bool(item.get(P + "capital_asset") or doc.get(P + "capital_asset"))
    rates = expected_rates(doc.doctype, treatment, recovery)
    return dict(treatment=treatment, recovery=str(dec(recovery)), capital=capital, rates=rates)


def roles_for(doc):
    return ("output",) if doc.doctype == "Sales Invoice" else ("input", "blocked", "output")


def accounts_for(settings):
    return {role: settings.get(role + "_account") for role in ("input", "blocked", "output")}


def template_for(company, accounts, rates, roles):
    """Create immutable-by-content native templates, respecting normal setup permissions."""
    mapping = {accounts[role]: str(dec(rates.get(role, 0)).normalize()) for role in roles}
    digest = hashlib.sha256(json.dumps([company, mapping], sort_keys=True).encode()).hexdigest()[:20]
    title = "Oman VAT " + digest
    name = frappe.db.get_value("Item Tax Template", {"title": title, "company": company})
    if name:
        template = frappe.get_doc("Item Tax Template", name)
        template.check_permission("read")
        actual = {row.tax_type: dec(row.tax_rate) for row in template.taxes if not row.get("not_applicable")}
        if template.disabled or len(template.taxes) != len(mapping) or actual != {k: dec(v) for k, v in mapping.items()}:
            frappe.throw("An Oman VAT template was changed. Restore it or provision a new reviewed template.")
        return name, mapping
    frappe.has_permission("Item Tax Template", "create", throw=True)
    template = frappe.get_doc(dict(doctype="Item Tax Template", title=title, company=company,
        taxes=[dict(tax_type=account, tax_rate=float(dec(rate))) for account, rate in mapping.items()]))
    template.insert()
    return template.name, mapping


def make_plan(doc, settings):
    accounts = accounts_for(settings)
    roles = roles_for(doc)
    items = []
    for item in doc.items:
        values = profile(doc, item)
        template, mapping = template_for(doc.company, accounts, values["rates"], roles)
        items.append(dict(name=item.name, item_tax_template=template, item_tax_rate=json.dumps(mapping)))
    taxes = []
    for role in roles:
        tax = dict(charge_type="On Net Total", account_head=accounts[role],
                   description="Oman VAT " + role, rate=5)
        if doc.doctype == "Purchase Invoice":
            tax.update(category="Total", add_deduct_tax="Deduct" if role == "output" else "Add")
        taxes.append(tax)
    return dict(taxes=taxes, items=items)


def validate_lines(doc, settings):
    accounts = accounts_for(settings)
    roles = roles_for(doc)
    items = list(doc.items)
    by_name = {item.name: item for item in items}
    if len(by_name) != len(items):
        raise ValueError("Invoice items must have unique row identifiers")
    profiles = {item.name: profile(doc, item) for item in items}
    if abs(sum((money(item.base_net_amount) for item in items), money(0)) - money(doc.base_net_total)) > Q:
        raise ValueError("Item taxable values do not reconcile with invoice net total")
    taxes = {}
    for tax in doc.get("taxes") or []:
        role = next((r for r in roles if accounts[r] == tax.account_head), None)
        if not role or role in taxes:
            raise ValueError("Use one native Oman VAT tax row per applicable account")
        direction = "Deduct" if doc.doctype == "Purchase Invoice" and role == "output" else "Add"
        if tax.charge_type != "On Net Total" or (tax.get("add_deduct_tax") or "Add") != direction:
            raise ValueError("Incorrect Oman VAT charge type or Add/Deduct direction")
        if doc.doctype == "Purchase Invoice" and tax.category != "Total":
            raise ValueError("Purchase VAT rows must use category Total")
        if dec(tax.rate) != 5:
            raise ValueError("Line VAT uses 5% header rates with explicit per-item template overrides")
        taxes[role] = tax
    if set(taxes) != set(roles):
        raise ValueError("Apply Oman VAT to prepare all required line tax rows")
    for item in items:
        mapping = json.loads(item.get("item_tax_rate") or "{}")
        for role in roles:
            expected = profiles[item.name]["rates"].get(role, 0)
            if accounts[role] not in mapping or dec(mapping[accounts[role]]) != expected:
                raise ValueError(f"Row {item.idx}: item tax template does not match its VAT treatment/recovery")
    # Native v16 details are in OMR and include the Add/Deduct sign.
    amounts = {item.name: {role: money(0) for role in roles} for item in items}
    seen = set()
    for detail in doc.get("_item_wise_tax_details") or []:
        item, tax = detail.get("item"), detail.get("tax")
        if item is None or tax is None or item.name not in by_name:
            raise ValueError("Unrecognized native item tax breakdown")
        role = next((r for r, row in taxes.items() if row is tax), None)
        if role is None:
            raise ValueError("Native tax breakdown contains an unexpected tax row")
        key = (item.name, role)
        if key in seen:
            raise ValueError("Duplicate native item tax breakdown")
        seen.add(key)
        expected_rate = profiles[item.name]["rates"].get(role, 0)
        if dec(detail.get("rate")) != expected_rate:
            raise ValueError("Native item tax rate differs from its VAT classification")
        multiplier = -1 if tax.get("add_deduct_tax") == "Deduct" else 1
        amount = money(dec(detail.get("amount")) * multiplier)
        if not expected_rate and amount:
            raise ValueError("Zero-rate item tax must be exactly zero")
        expected = money(dec(item.base_net_amount) * dec(expected_rate) / 100)
        # Error diffusion in ERPNext may move a rounding unit across item rows.
        if abs(amount - expected) > Q * 2:
            raise ValueError("Native item VAT amount does not reconcile with the item taxable value")
        amounts[item.name][role] = amount
    if len(seen) != len(items) * len(roles):
        raise ValueError("Native v16 item-wise tax breakdown is incomplete; recalculate and save the invoice")
    for role, tax in taxes.items():
        total = sum((values[role] for values in amounts.values()), money(0))
        if total != money(tax.base_tax_amount_after_discount_amount):
            raise ValueError("Item VAT does not reconcile exactly with the native VAT account total")
    entries = []
    classifications = []
    for item in items:
        values = profiles[item.name]
        if values["treatment"] == "Export" and not (item.get(P + "evidence") or doc.get(P + "evidence")):
            raise ValueError(f"Row {item.idx}: enter an export evidence reference")
        line_entries = invoice_entries(doc.doctype, values["treatment"], item.base_net_amount,
            amounts[item.name].get("output", 0), amounts[item.name].get("input", 0),
            values["capital"], bool(doc.is_return))
        entries.extend({**row, "item_row": item.name, "item_code": item.item_code,
                        "treatment": values["treatment"]} for row in line_entries)
        classifications.append({"item_row": item.name, "treatment": values["treatment"],
                                "recovery": values["recovery"], "capital": values["capital"]})
    return dict(version=2, entries=entries, lines=classifications)


def validate_return_lines(doc, original):
    references = {item.name: item for item in original.items}
    source_field = "sales_invoice_item" if doc.doctype == "Sales Invoice" else "purchase_invoice_item"
    frozen = {}
    if original.get(P + "snapshot"):
        frozen = {row["item_row"]: row for row in json.loads(original.get(P + "snapshot")).get("lines", [])}
    for item in doc.items:
        source = references.get(item.get(source_field))
        if source is None:
            candidates = [row for row in original.items if row.item_code == item.item_code]
            if len(candidates) != 1:
                raise ValueError("Return rows with repeated item codes must link to the original invoice item row")
            source = candidates[0]
        if item.item_code != source.item_code:
            raise ValueError("Return item does not match its original item row")
        values = profile(doc, item)
        old = frozen.get(source.name) or profile(original, source)
        if any(values[key] != old[key] for key in ("treatment", "capital")) or dec(values["recovery"]) != dec(old["recovery"]):
            raise ValueError("Each return row must preserve its original VAT treatment, recovery and capital classification")
