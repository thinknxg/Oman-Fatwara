import json

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from oman_vat.access import assert_open, lock_company, require_manager, settings_for
from oman_vat.core import manual_entries, money, summarize


class OmanVATEntry(Document):
    def validate(self):
        require_manager(self.company)
        settings = settings_for(self.company)
        if getdate(self.posting_date) < getdate(settings.effective_from):
            frappe.throw("VAT entry date cannot precede activation.")
        if self.kind in ("Input Adjustment", "Output Adjustment") and money(self.taxable_base):
            frappe.throw("Tax adjustments must have zero taxable base.")
        try:
            entries = manual_entries(self.kind, self.taxable_base, self.vat_amount,
                                     self.recovery_percent, bool(self.capital_asset),
                                     self.import_treatment == "Standard Rated")
        except ValueError as exc:
            frappe.throw(str(exc))
        self.snapshot = json.dumps({"version": 1, "entries": entries}, sort_keys=True)

    def before_submit(self):
        lock_company(self.company)
        assert_open(self.company, self.posting_date)
        settings = settings_for(self.company)
        # One submitted VAT record per Journal Entry. Lock company before reading it.
        table = frappe.qb.DocType("Oman VAT Entry")
        duplicate = (frappe.qb.from_(table).select(table.name)
                     .where((table.journal_entry == self.journal_entry) & (table.docstatus == 1))
                     .for_update().run())
        if duplicate:
            frappe.throw("This Journal Entry already has a submitted Oman VAT Entry.")
        je = frappe.qb.DocType("Journal Entry")
        state = (frappe.qb.from_(je).select(je.docstatus, je.company, je.posting_date)
                 .where(je.name == self.journal_entry).for_update().run(as_dict=True))
        if (not state or state[0].docstatus != 1 or state[0].company != self.company
                or getdate(state[0].posting_date) != getdate(self.posting_date)):
            frappe.throw("Use a submitted Journal Entry from this company with the same posting date.")
        journal = frappe.get_doc("Journal Entry", self.journal_entry)
        journal.check_permission("read")
        if journal.docstatus != 1 or journal.company != self.company or getdate(journal.posting_date) != getdate(self.posting_date):
            frappe.throw("Use a submitted Journal Entry from this company with the same posting date.")
        _, output, inputs, _ = summarize(json.loads(self.snapshot)["entries"])
        ledger_output = sum((money(row.credit) - money(row.debit) for row in journal.accounts
                             if row.account == settings.output_account), money(0))
        ledger_input = sum((money(row.debit) - money(row.credit) for row in journal.accounts
                            if row.account == settings.input_account), money(0))
        if ledger_output != output or ledger_input != inputs:
            frappe.throw("VAT record must match the Journal Entry's input and output VAT ledger amounts exactly.")

    def before_cancel(self):
        lock_company(self.company)
        assert_open(self.company, self.posting_date)
