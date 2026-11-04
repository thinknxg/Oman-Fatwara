import importlib
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from test_tax_validation import Row


class EInvoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(sys.modules, {"frappe": types.ModuleType("frappe")}):
            cls.module = importlib.import_module("oman_vat.einvoicing")

    def setUp(self):
        self.item = Row(name="I-1", idx=1, item_code="ITEM", item_name="Widget", qty=1, net_amount=100,
                        base_net_amount=100, net_rate=100, custom_fawtara_uom_code="H87",
                        custom_fawtara_item_type="Goods", custom_fawtara_tax_reason_code="")
        snapshot = dict(version=2, lines=[dict(item_row="I-1", treatment="Standard Rated")],
                        entries=[dict(item_row="I-1", output="5.000")])
        self.doc = Row(doctype="Sales Invoice", name="INV-1", company="Test", customer="Buyer", docstatus=1,
            custom_oman_vat_snapshot=json.dumps(snapshot), custom_fawtara_transaction_type="10000000000000000000",
            company_address="Seller Address", customer_address="Buyer Address", is_return=False,
            items=[self.item], posting_date="2026-10-01", posting_time="10:00:00", currency="OMR", conversion_rate=1,
            tax_id="OM9876543210", net_total=100, grand_total=105, rounding_adjustment=0, paid_amount=0,
            total_advance=0, outstanding_amount=105,
            taxes=[Row(account_head="Output", rate=5, tax_amount_after_discount_amount=5,
                       base_tax_amount_after_discount_amount=5)])
        self.frappe = MagicMock()
        def throw(message):
            raise ValueError(message)
        self.frappe.throw.side_effect = throw
        seller = Row(company_name="Seller", tax_id="OM1234567890")
        buyer = Row(customer_name="Buyer")
        address = Row(address_line1="Street", address_line2="Area", city="Muscat", pincode="100", country="Oman", phone="123")
        previous = Row(doctype="Sales Invoice", name="INV-0", posting_date="2026-09-01")
        self.frappe.get_doc.side_effect = lambda dt, name: {"Company": seller, "Customer": buyer,
                                                          "Address": address, "Sales Invoice": previous}[dt]
        self.frappe.db.get_value.return_value = "om"
        self.connector = Row(seller_endpoint="TEST", endpoint_scheme="TEST")
        patcher = patch.object(self.module, "frappe", self.frappe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_standard_invoice_provider_payload(self):
        result = self.module.invoice_payload(self.doc, self.connector)
        self.assertEqual(result["schema"], "oman_vat.fawtara.input.v1")
        self.assertEqual(result["lines"][0]["vat_category"], "S")
        self.assertEqual(result["lines"][0]["vat_amount_omr"], "5.000")
        self.assertEqual(result["totals"]["payable_amount"], "105.000")

    def test_later_outstanding_does_not_change_issue_payable(self):
        self.doc.outstanding_amount = 0
        self.assertEqual(self.module.invoice_payload(self.doc, self.connector)["totals"]["payable_amount"], "105.000")

    def test_credit_note_positive_values_and_reference(self):
        self.doc.is_return = True
        self.doc.return_against = "INV-0"
        self.doc.custom_fawtara_credit_reason_code = "1"
        self.doc.net_total, self.doc.grand_total = -100, -105
        self.item.qty, self.item.net_amount, self.item.base_net_amount = -1, -100, -100
        snapshot = json.loads(self.doc.custom_oman_vat_snapshot)
        snapshot["entries"][0]["output"] = "-5.000"
        self.doc.custom_oman_vat_snapshot = json.dumps(snapshot)
        result = self.module.invoice_payload(self.doc, self.connector)
        self.assertEqual(result["document_type"], "381")
        self.assertEqual(result["lines"][0]["quantity"], "1")
        self.assertEqual(result["lines"][0]["net_amount"], "100.000")
        self.assertEqual(result["original_invoice"]["number"], "INV-0")

    def test_invalid_bitmap(self):
        self.doc.custom_fawtara_transaction_type = "11000000000000000000"
        with self.assertRaisesRegex(ValueError, "transaction type"):
            self.module.invoice_payload(self.doc, self.connector)

    def test_credit_note_reason_required(self):
        self.doc.is_return = True
        with self.assertRaisesRegex(ValueError, "reason"):
            self.module.invoice_payload(self.doc, self.connector)

    def test_zero_rate_reason_required(self):
        snapshot = json.loads(self.doc.custom_oman_vat_snapshot)
        snapshot["lines"][0]["treatment"] = "Zero Rated"
        self.doc.custom_oman_vat_snapshot = json.dumps(snapshot)
        with self.assertRaisesRegex(ValueError, "zero-rating"):
            self.module.invoice_payload(self.doc, self.connector)

    def test_unit_code_required(self):
        self.item.custom_fawtara_uom_code = ""
        with self.assertRaisesRegex(ValueError, "unit code"):
            self.module.invoice_payload(self.doc, self.connector)
