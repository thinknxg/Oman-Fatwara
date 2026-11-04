import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from test_tax_validation import Row


class Record(Row):
    def __init__(self, **values):
        super().__init__(**values)
        self.flags = Row()

    def set(self, key, value):
        setattr(self, key, value)

    def save(self, **kwargs):
        pass


class DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe = types.ModuleType("frappe")
        frappe.whitelist = lambda: lambda fn: fn
        utils = types.ModuleType("frappe.utils")
        utils.getdate = lambda value: value
        utils.add_to_date = lambda value, **kw: value
        utils.now_datetime = lambda: "2026-11-04 12:00:00"
        with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
            cls.module = importlib.import_module("oman_vat.dispatch")

    def setUp(self):
        self.record = Record(name="SUB-1", company="Test", source_type="Sales Invoice", source_name="INV-1",
            kind="Fawtara Invoice", environment="Sandbox", status="Queued", attempt_count=0,
            idempotency_key="KEY-1", provider="test")
        self.frappe = MagicMock()
        self.frappe.qb.from_.return_value.select.return_value.where.return_value.for_update.return_value.run.return_value = [(1,)]
        self.adapter = MagicMock()
        self.adapter.validate.return_value = dict(valid=True)
        self.adapter.submit.return_value = dict(status="Pending", provider_reference="P-1")
        self.patchers = [patch.object(self.module, "frappe", self.frappe),
            patch.object(self.module, "lock_submission", return_value=self.record),
            patch.object(self.module, "verified_context", return_value=(Row(), self.adapter, {"value": 1}))]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_sending_is_committed_before_transmission(self):
        def submit(*args):
            self.assertEqual(self.record.status, "Sending")
            self.frappe.db.commit.assert_called()
            self.assertEqual(args[2], "KEY-1")
            return dict(status="Pending", provider_reference="P-1")
        self.adapter.submit.side_effect = submit
        self.module.process_submission("SUB-1")
        self.assertEqual(self.record.status, "Pending")
        self.assertEqual(self.record.attempt_count, 1)

    def test_timeout_is_unknown_without_resubmission(self):
        self.adapter.submit.side_effect = TimeoutError("No receipt")
        self.module.process_submission("SUB-1")
        self.assertEqual(self.record.status, "Unknown")
        self.module.process_submission("SUB-1")
        self.adapter.submit.assert_called_once()

    def test_reject_invalid_payload_before_network(self):
        self.adapter.validate.return_value = dict(valid=False)
        self.module.process_submission("SUB-1")
        self.assertEqual(self.record.status, "Rejected")
        self.adapter.submit.assert_not_called()

    def test_invalid_acceptance_is_uncertain(self):
        self.adapter.submit.return_value = dict(status="Accepted", provider_reference="JOB-1")
        self.module.process_submission("SUB-1")
        self.assertEqual(self.record.status, "Unknown")

    def test_valid_acceptance_requires_authority_and_receipt(self):
        self.adapter.submit.return_value = dict(status="Accepted", authority_reference="A-1", receipt_reference="R-1")
        self.module.process_submission("SUB-1")
        self.assertEqual(self.record.status, "Accepted")
        self.assertEqual(self.record.authority_reference, "A-1")

    def test_rejected_record_is_not_automatically_retried(self):
        self.record.status = "Rejected"
        self.module.process_submission("SUB-1")
        self.adapter.submit.assert_not_called()

    def test_invalid_context_does_not_send(self):
        with patch.object(self.module, "verified_context", side_effect=ValueError("Changed config")):
            self.module.process_submission("SUB-1")
        self.assertEqual(self.record.status, "Rejected")
        self.adapter.submit.assert_not_called()

    def test_lookup_resolves_pending_without_resending(self):
        self.record.status = "Pending"
        self.record.provider_reference = "P-1"
        self.adapter.lookup.return_value = dict(status="Accepted", authority_reference="A-1", receipt_reference="R-1")
        self.module.reconcile_submission("SUB-1")
        self.assertEqual(self.record.status, "Accepted")
        self.assertEqual(self.record.provider_reference, "P-1")
        self.adapter.submit.assert_not_called()

    def test_lookup_failure_preserves_unknown(self):
        self.record.status = "Unknown"
        self.record.provider_reference = "P-1"
        self.adapter.lookup.side_effect = TimeoutError()
        self.module.reconcile_submission("SUB-1")
        self.assertEqual(self.record.status, "Unknown")
        self.assertIsNotNone(self.record.last_checked_at)
        self.adapter.submit.assert_not_called()

    def test_accepted_record_is_not_polled(self):
        self.record.status = "Accepted"
        self.module.reconcile_submission("SUB-1")
        self.adapter.lookup.assert_not_called()
