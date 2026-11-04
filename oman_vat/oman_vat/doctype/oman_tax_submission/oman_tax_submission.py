import frappe
from frappe.model.document import Document


class OmanTaxSubmission(Document):
    def validate(self):
        if not self.flags.internal_tax_update:
            frappe.throw("Tax submission records are managed by the filing queue.")

    def on_trash(self):
        frappe.throw("Tax submission records form the transmission audit trail and cannot be deleted.")
