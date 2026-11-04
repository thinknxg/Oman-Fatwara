import frappe
from frappe.model.document import Document


class OmanVATSettings(Document):
    def validate(self):
        info = frappe.db.get_value("Company", self.company, ["country", "default_currency", "tax_id"], as_dict=True)
        if info.country != "Oman" or info.default_currency != "OMR":
            frappe.throw("Choose an Oman company with OMR as its company currency.")
        if not info.tax_id:
            frappe.throw("Enter the company's VAT registration number in Company > Tax ID.")
        accounts = [self.input_account, self.output_account, self.blocked_account]
        if len(set(accounts)) != 3:
            frappe.throw("Input VAT, output VAT and blocked VAT require separate accounts.")
        for field in ("input_account", "output_account", "blocked_account"):
            account = frappe.get_doc("Account", self.get(field))
            if account.company != self.company or account.is_group or account.disabled or account.account_currency != "OMR":
                frappe.throw("VAT accounts must be enabled OMR ledger accounts of this company.")
            if field == "blocked_account":
                if account.root_type != "Expense" or account.account_type != "Expense Account":
                    frappe.throw("Blocked VAT requires an Expense account with account type Expense Account for native item tax templates.")
            elif account.account_type != "Tax":
                frappe.throw("Input and output VAT accounts must have account type Tax.")
        old = self.get_doc_before_save()
        if old and any(old.get(field) != self.get(field) for field in (
            "company", "enabled", "effective_from", "input_account", "output_account", "blocked_account"
        )):
            from oman_vat.access import has_submitted, lock_company
            lock_company(old.company)
            used = has_submitted(old.company, (
                "Sales Invoice", "Purchase Invoice", "Oman VAT Entry", "Oman VAT Return"
            ))
            if used:
                frappe.throw("VAT configuration is locked after submitted transactions exist. Use a reviewed migration to change it.")

    def on_trash(self):
        from oman_vat.access import has_submitted, lock_company
        lock_company(self.company)
        if has_submitted(self.company, (
            "Sales Invoice", "Purchase Invoice", "Oman VAT Entry", "Oman VAT Return"
        )):
            frappe.throw("Cannot delete VAT settings with submitted transactions.")
