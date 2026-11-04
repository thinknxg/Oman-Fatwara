"""Company-wide VAT reports: Accounts Manager role and Company permission required."""
import json

import frappe

from oman_vat.access import date_range, require_manager
from oman_vat.core import BOXES, summarize


def collect(company, start, end, locking=False):
    require_manager(company)
    date_range(company, start, end)
    entries = []
    for doctype, snapshot_field in (
        ("Sales Invoice", "custom_oman_vat_snapshot"),
        ("Purchase Invoice", "custom_oman_vat_snapshot"),
        ("Oman VAT Entry", "snapshot"),
    ):
        table = frappe.qb.DocType(doctype)
        query = (frappe.qb.from_(table)
                 .select(table.name, table.posting_date, table[snapshot_field])
                 .where((table.company == company) & (table.docstatus == 1)
                        & (table.posting_date >= start) & (table.posting_date <= end))
                 .orderby(table.name))
        if locking:
            query = query.for_update()
        for source in query.run(as_dict=True):
            snapshot = source.get(snapshot_field)
            if not snapshot:
                frappe.throw(f"{doctype} {source.name} has no Oman VAT snapshot. Review historical coverage before preparing a return.")
            data = json.loads(snapshot)
            if data.get("version") not in (1, 2):
                frappe.throw("Unsupported Oman VAT snapshot version.")
            for row in data["entries"]:
                entries.append({**row, "source_type": doctype, "source_name": source.name,
                                "posting_date": source.posting_date})
    return entries


def summary_rows(entries):
    totals, output, inputs, net = summarize(entries)
    rows = [{"box": box, "description": label, **{k: float(v) for k, v in totals[box].items()}}
            for box, label in BOXES.items()]
    return rows, output, inputs, net
