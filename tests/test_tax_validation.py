"""Test real adapter validation using small invoice-shaped objects, without Frappe."""
import importlib
import sys
import types
import unittest
from unittest.mock import patch

from oman_vat.core import expected_rates


class Row:
    def __init__(self, **values):
        self.__dict__.update(values)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def update(self, **values):
        self.__dict__.update(values)

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value


class TaxValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe = types.ModuleType("frappe")
        utils = types.ModuleType("frappe.utils")
        utils.getdate = lambda x: x
        with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
            cls.events = importlib.import_module("oman_vat.events")

    def setUp(self):
        self.accounts = dict(input="Input", output="Output", blocked="Blocked")
        self.doc = Row(doctype="Sales Invoice", base_net_total=100,
                       items=[Row(item_tax_rate="{}")], taxes=[self.tax("Output", 5, 5)])

    def tax(self, account, rate, amount, direction="Add", category="Total"):
        return Row(account_head=account, rate=rate, base_tax_amount_after_discount_amount=amount,
                   charge_type="On Net Total", add_deduct_tax=direction, category=category)

    def check(self, treatment="Standard Rated", recovery=100):
        return self.events.validate_taxes(self.doc, self.accounts,
            expected_rates(self.doc.doctype, treatment, recovery))

    def test_sales_tax_reconciles(self):
        self.assertEqual(self.check()["output"], 5)

    def test_incorrect_amount_rejected(self):
        self.doc.taxes[0].update(base_tax_amount_after_discount_amount=4.9)
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_tax_rejected(self):
        self.doc.taxes = []
        self.doc["taxes"] = []
        with self.assertRaises(ValueError):
            self.check()

    def test_unrelated_charges_rejected(self):
        self.doc.taxes.append(self.tax("Freight", 10, 10))
        with self.assertRaises(ValueError):
            self.check()

    def test_item_override_rejected(self):
        self.doc.items[0]["item_tax_rate"] = '{"Output":0}'
        with self.assertRaises(ValueError):
            self.check()

    def test_rcm_partial_recovery_reconciles(self):
        self.doc.update(doctype="Purchase Invoice", taxes=[self.tax("Input", 2.5, 2.5),
                        self.tax("Blocked", 2.5, 2.5), self.tax("Output", 5, 5, "Deduct")])
        self.assertEqual(self.check("Reverse Charge", 50), dict(input=2.5, blocked=2.5, output=5))

    def test_wrong_rcm_direction_rejected(self):
        self.doc.update(doctype="Purchase Invoice", taxes=[self.tax("Input", 5, 5), self.tax("Output", 5, 5)])
        with self.assertRaises(ValueError):
            self.check("Reverse Charge")

    def test_valuation_only_rejected(self):
        self.doc.update(doctype="Purchase Invoice", taxes=[self.tax("Input", 5, 5, category="Valuation")])
        with self.assertRaises(ValueError):
            self.check()

    def test_duplicate_accounts_rejected(self):
        self.doc.taxes.append(self.tax("Output", 5, 5))
        with self.assertRaises(ValueError):
            self.check()

    def test_actual_charge_type_rejected(self):
        self.doc.taxes[0]["charge_type"] = "Actual"
        with self.assertRaises(ValueError):
            self.check()

    def test_zero_rate_without_tax_rows(self):
        self.doc["taxes"] = []
        self.assertEqual(self.check("Zero Rated"), {})

    def test_foreign_invoice_uses_base_currency(self):
        self.doc.update(base_net_total=385, taxes=[self.tax("Output", 5, 19.25)], currency="USD", conversion_rate=.385)
        self.assertEqual(self.check()["output"], 19.25)

    def test_credit_note_sign_preserved(self):
        self.doc.update(base_net_total=-100, taxes=[self.tax("Output", 5, -5)])
        self.assertEqual(self.check()["output"], -5)

    def test_wrong_rate_rejected(self):
        self.doc.taxes[0]["rate"] = 15
        with self.assertRaises(ValueError):
            self.check()
