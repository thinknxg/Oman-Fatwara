import importlib
import json
import sys
import types
import unittest
from decimal import Decimal
from unittest.mock import patch

from oman_vat.core import expected_rates, summarize
from test_tax_validation import Row


class LineVATTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(sys.modules, {"frappe": types.ModuleType("frappe")}):
            cls.module = importlib.import_module("oman_vat.lines")

    def fixture(self, side, rows, is_return=False):
        self.settings = Row(input_account="Input", output_account="Output", blocked_account="Blocked")
        roles = ("output",) if side == "Sales Invoice" else ("input", "blocked", "output")
        accounts = dict(input="Input", output="Output", blocked="Blocked")
        taxes = {role: Row(name="T-" + role, rate=5, charge_type="On Net Total", account_head=accounts[role],
                          category="Total", add_deduct_tax="Deduct" if side == "Purchase Invoice" and role == "output" else "Add",
                          base_tax_amount_after_discount_amount=0) for role in roles}
        items, details = [], []
        for idx, (treatment, base, vat, recovery, capital) in enumerate(rows, 1):
            rates = expected_rates(side, treatment, recovery)
            item = Row(name="I-" + str(idx), idx=idx, item_code="SAME-ITEM",
                       base_net_amount=base, custom_oman_vat_treatment=treatment,
                       custom_oman_vat_override_recovery=1, custom_oman_vat_recovery_percent=recovery,
                       custom_oman_vat_capital_asset=capital, custom_oman_vat_evidence="DOC-123",
                       item_tax_rate=json.dumps({accounts[r]: float(rates.get(r, 0)) for r in roles}))
            items.append(item)
            for role, tax in taxes.items():
                amount = vat.get(role, 0)
                tax.base_tax_amount_after_discount_amount += amount
                multiplier = -1 if tax.add_deduct_tax == "Deduct" else 1
                details.append(Row(item=item, tax=tax, rate=float(rates.get(role, 0)), amount=amount * multiplier))
        return Row(doctype=side, company="Test", items=items, taxes=list(taxes.values()),
                   base_net_total=sum(row[1] for row in rows), is_return=is_return,
                   _item_wise_tax_details=details, custom_oman_vat_recovery_percent=100)

    def validate(self, doc):
        return self.module.validate_lines(doc, self.settings)

    def test_mixed_sale(self):
        doc = self.fixture("Sales Invoice", [
            ("Standard Rated", 100, {"output": 5}, 100, False),
            ("Zero Rated", 50, {}, 100, False), ("Exempt", 25, {}, 100, False),
            ("Export", 200, {}, 100, False), ("Out of Scope", 30, {}, 100, False)])
        result = self.validate(doc)
        self.assertEqual([r["box"] for r in result["entries"]], ["1a", "1b", "1c", "3a"])
        self.assertEqual(summarize(result["entries"])[1], Decimal(5))
        self.assertEqual(len(result["lines"]), 5)

    def test_mixed_purchase_recovery_and_capital(self):
        doc = self.fixture("Purchase Invoice", [
            ("Standard Rated", 100, {"input": 2.5, "blocked": 2.5}, 50, False),
            ("Reverse Charge", 200, {"input": 10, "output": 10}, 100, False),
            ("Exempt", 50, {}, 100, False),
            ("Standard Rated", 1000, {"input": 50}, 100, True)])
        result = self.validate(doc)
        totals, output, inputs, net = summarize(result["entries"])
        self.assertEqual((output, inputs, net), (Decimal(10), Decimal("62.5"), Decimal("-52.5")))
        self.assertEqual(totals["6a"]["base"], Decimal(350))
        self.assertEqual(totals["6c"]["input_vat"], Decimal(50))

    def test_zero_recovery_override(self):
        doc = self.fixture("Purchase Invoice", [("Standard Rated", 100, {"blocked": 5}, 0, False)])
        doc.custom_oman_vat_recovery_percent = 80
        self.assertEqual(summarize(self.validate(doc)["entries"])[2], Decimal(0))

    def test_partial_mixed_credit_note(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", -100, {"output": -5}, 100, False),
                                             ("Zero Rated", -20, {}, 100, False)], is_return=True)
        self.assertEqual([r["box"] for r in self.validate(doc)["entries"]], ["5b", "1b"])

    def test_duplicate_codes_stay_separate(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False),
                                             ("Zero Rated", 100, {}, 100, False)])
        self.assertEqual([r["item_row"] for r in self.validate(doc)["entries"]], ["I-1", "I-2"])

    def test_template_override_mismatch(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False)])
        doc.items[0].item_tax_rate = '{"Output":0}'
        with self.assertRaisesRegex(ValueError, "template"):
            self.validate(doc)

    def test_detail_total_mismatch(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False)])
        doc.taxes[0].base_tax_amount_after_discount_amount = 5.001
        with self.assertRaisesRegex(ValueError, "exactly"):
            self.validate(doc)

    def test_missing_native_details(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False)])
        doc._item_wise_tax_details = []
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.validate(doc)

    def test_duplicate_native_details(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False)])
        doc._item_wise_tax_details.append(doc._item_wise_tax_details[0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.validate(doc)

    def test_zero_rate_contamination_rejected(self):
        doc = self.fixture("Sales Invoice", [("Zero Rated", 100, {"output": .001}, 100, False)])
        with self.assertRaisesRegex(ValueError, "exactly zero"):
            self.validate(doc)

    def test_export_evidence_required(self):
        doc = self.fixture("Sales Invoice", [("Export", 100, {}, 100, False)])
        doc.items[0].custom_oman_vat_evidence = ""
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.validate(doc)

    def test_header_default_inherited(self):
        doc = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False)])
        doc.items[0].custom_oman_vat_treatment = ""
        doc.custom_oman_vat_treatment = "Standard Rated"
        self.assertEqual(self.validate(doc)["lines"][0]["treatment"], "Standard Rated")

    def test_recovery_precision(self):
        doc = Row(doctype="Purchase Invoice", custom_oman_vat_recovery_percent=33.333)
        with self.assertRaisesRegex(ValueError, "decimal places"):
            self.module.profile(doc, Row(custom_oman_vat_treatment="Standard Rated"))

    def test_return_must_preserve_source_row_profile(self):
        original = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False),
                                                   ("Zero Rated", 100, {}, 100, False)])
        returned = self.fixture("Sales Invoice", [("Zero Rated", -100, {}, 100, False)], is_return=True)
        returned.items[0].sales_invoice_item = "I-1"
        with self.assertRaisesRegex(ValueError, "preserve"):
            self.module.validate_return_lines(returned, original)

    def test_ambiguous_return_row_rejected(self):
        original = self.fixture("Sales Invoice", [("Standard Rated", 100, {"output": 5}, 100, False),
                                                   ("Zero Rated", 100, {}, 100, False)])
        returned = self.fixture("Sales Invoice", [("Zero Rated", -100, {}, 100, False)], is_return=True)
        with self.assertRaisesRegex(ValueError, "original invoice item row"):
            self.module.validate_return_lines(returned, original)
