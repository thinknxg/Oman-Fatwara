import hashlib
import json

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from oman_vat.access import date_range, lock_company, require_manager
from oman_vat.reporting import collect, summary_rows


class OmanVATReturn(Document):
    def validate(self):
        require_manager(self.company)
        date_range(self.company, self.from_date, self.to_date)
        # Always replace client-provided calculated fields.
        self.build_snapshot()

    def build_snapshot(self, locking=False):
        entries = collect(self.company, self.from_date, self.to_date, locking=locking)
        rows, output, inputs, net = summary_rows(entries)
        self.set("boxes", [])
        for row in rows:
            self.append("boxes", row)
        self.output_vat, self.input_vat, self.net_vat = float(output), float(inputs), float(net)
        self.source_snapshot = json.dumps(entries, sort_keys=True, default=str)
        self.snapshot_hash = hashlib.sha256(self.source_snapshot.encode()).hexdigest()

    def before_submit(self):
        lock_company(self.company)
        if getdate(self.to_date) >= getdate(nowdate()):
            frappe.throw("Submit a VAT return only after its period has ended.")
        table = frappe.qb.DocType("Oman VAT Return")
        overlaps = (frappe.qb.from_(table).select(table.name)
                    .where((table.company == self.company) & (table.docstatus == 1)
                           & (table.from_date <= self.to_date) & (table.to_date >= self.from_date))
                    .for_update().run())
        if overlaps:
            frappe.throw("A submitted Oman VAT Return overlaps this period.")
        self.build_snapshot(locking=True)

    def before_cancel(self):
        require_manager(self.company)
        lock_company(self.company)
        from oman_vat.dispatch import block_source_cancel
        block_source_cancel(self)
