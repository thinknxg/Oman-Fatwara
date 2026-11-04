from urllib.parse import urlparse

import frappe
from frappe.model.document import Document

from oman_vat.providers import adapter_for


class OmanTaxConnector(Document):
    def validate(self):
        if self.endpoint_url:
            parsed = urlparse(self.endpoint_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                frappe.throw("Use an HTTPS provider URL without credentials or fragments.")
        if self.enabled:
            if self.auto_file_returns:
                adapter_for(self, "VAT Return")
            if self.auto_send_einvoices:
                adapter_for(self, "Fawtara Invoice")
                if not self.seller_endpoint or not self.endpoint_scheme:
                    frappe.throw("Enter the seller's registered Peppol endpoint and scheme.")
