import unittest
from decimal import Decimal

from oman_vat.core import dec, entry, expected_rates, invoice_entries, manual_entries, money, percent, summarize


class CalculationTests(unittest.TestCase):
    def test_omr_rounding(self):
        self.assertEqual(money("1.2345"), Decimal("1.235"))
        self.assertEqual(money("-1.2345"), Decimal("-1.235"))

    def test_nonfinite_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                dec(value)

    def test_recovery_bounds(self):
        for value in (-1, 101):
            with self.assertRaises(ValueError):
                percent(value)
        self.assertEqual(percent(0), 0)

    def test_standard_sale(self):
        self.assertEqual(invoice_entries("Sales Invoice", "Standard Rated", 100, 5), [entry("1a", 100, 5)])

    def test_nonstandard_sales(self):
        for treatment, box in (("Zero Rated", "1b"), ("Exempt", "1c"), ("Export", "3a")):
            with self.subTest(treatment=treatment):
                self.assertEqual(invoice_entries("Sales Invoice", treatment, 100), [entry(box, 100)])

    def test_out_of_scope_excluded(self):
        for side in ("Sales Invoice", "Purchase Invoice"):
            self.assertEqual(invoice_entries(side, "Out of Scope", 100), [])

    def test_sales_credit_note_adjustment(self):
        self.assertEqual(invoice_entries("Sales Invoice", "Standard Rated", -100, -5, is_return=True),
                         [entry("5b", output=-5)])

    def test_zero_sale_return_reduces_value(self):
        self.assertEqual(invoice_entries("Sales Invoice", "Zero Rated", -100, is_return=True), [entry("1b", -100)])

    def test_domestic_purchase(self):
        self.assertEqual(invoice_entries("Purchase Invoice", "Standard Rated", 100, input_vat=5),
                         [entry("6a", 100, input_vat=5)])

    def test_capital_purchase(self):
        self.assertEqual(invoice_entries("Purchase Invoice", "Standard Rated", 100, input_vat=5, capital=True),
                         [entry("6c", input_vat=5)])

    def test_purchase_return(self):
        self.assertEqual(invoice_entries("Purchase Invoice", "Standard Rated", -100, input_vat=-5, is_return=True),
                         [entry("6d", input_vat=-5)])

    def test_rcm_both_sides(self):
        rows = invoice_entries("Purchase Invoice", "Reverse Charge", 100, 5, 2.5)
        self.assertEqual(rows, [entry("2b", 100, 5), entry("6a", 100, input_vat=2.5)])
        self.assertEqual(summarize(rows)[3], Decimal("2.500"))

    def test_rcm_return(self):
        rows = invoice_entries("Purchase Invoice", "Reverse Charge", -100, -5, -2.5, is_return=True)
        self.assertEqual(rows, [entry("5b", output=-5), entry("6d", input_vat=-2.5)])

    def test_recovery_rates(self):
        self.assertEqual(expected_rates("Purchase Invoice", "Reverse Charge", 40),
                         dict(input=Decimal(2), blocked=Decimal(3), output=Decimal(5)))

    def test_zero_recovery(self):
        self.assertEqual(expected_rates("Purchase Invoice", "Standard Rated", 0), dict(blocked=Decimal(5)))

    def test_invalid_side_treatment(self):
        for side, treatment in (("Sales Invoice", "Reverse Charge"), ("Purchase Invoice", "Export"),
                                ("POS Invoice", "Standard Rated"), ("Sales Invoice", "")):
            with self.subTest(side=side, treatment=treatment), self.assertRaises(ValueError):
                expected_rates(side, treatment)

    def test_invalid_signs(self):
        with self.assertRaises(ValueError):
            invoice_entries("Sales Invoice", "Standard Rated", -100, -5)
        with self.assertRaises(ValueError):
            invoice_entries("Sales Invoice", "Standard Rated", 100, 5, is_return=True)

    def test_customs_paid(self):
        rows = manual_entries("Customs Paid Import", 1000, 50, recovery=60)
        self.assertEqual(rows, [entry("4b", 1000), entry("6b", 1000, input_vat=30)])
        self.assertEqual(summarize(rows)[3], Decimal(-30))

    def test_postponed_import(self):
        rows = manual_entries("Postponed Import", 1000, 50, recovery=50)
        self.assertEqual(rows, [entry("4a", 1000, 50), entry("6b", 1000, input_vat=25)])

    def test_capital_import(self):
        rows = manual_entries("Postponed Import", 1000, 50, capital=True)
        self.assertEqual(rows[1], entry("6c", input_vat=50))

    def test_zero_and_exempt_import(self):
        self.assertEqual(manual_entries("Customs Paid Import", 1000, 0, standard=False), [entry("4b", 1000)])

    def test_invalid_imports(self):
        for args, kwargs in [(("Postponed Import", -100, -5), {}),
                             (("Customs Paid Import", 100, 4), {}),
                             (("Postponed Import", 100, 0), dict(standard=False)),
                             (("Customs Paid Import", 100, 5), dict(standard=False))]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                manual_entries(*args, **kwargs)

    def test_adjustments(self):
        self.assertEqual(manual_entries("Output Adjustment", 0, -5), [entry("5b", output=-5)])
        self.assertEqual(manual_entries("Input Adjustment", 0, -3), [entry("6d", input_vat=-3)])

    def test_unknown_manual_type(self):
        with self.assertRaises(ValueError):
            manual_entries("Anything", 0, 0)

    def test_unknown_box(self):
        with self.assertRaises(ValueError):
            summarize([dict(box="1d")])

    def test_full_return_net(self):
        rows = (invoice_entries("Sales Invoice", "Standard Rated", 2000, 100)
                + invoice_entries("Sales Invoice", "Standard Rated", -100, -5, is_return=True)
                + invoice_entries("Purchase Invoice", "Standard Rated", 1000, input_vat=50)
                + invoice_entries("Purchase Invoice", "Reverse Charge", 200, 10, 5)
                + manual_entries("Postponed Import", 400, 20))
        self.assertEqual(summarize(rows)[1:], (Decimal(125), Decimal(75), Decimal(50)))

    def test_empty_return(self):
        self.assertEqual(summarize([])[1:], (Decimal(0), Decimal(0), Decimal(0)))


if __name__ == "__main__":
    unittest.main()
