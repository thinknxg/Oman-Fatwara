import unittest
import uuid
import hashlib
import json
from types import SimpleNamespace

from oman_vat.transmission import acknowledgement, document_uuid, payload_hash, return_payload, submission_key


class TransmissionTests(unittest.TestCase):
    def test_payload_hash_is_canonical(self):
        self.assertEqual(payload_hash(dict(a=1, b=2)), payload_hash(dict(b=2, a=1)))
        self.assertNotEqual(payload_hash(dict(a=1)), payload_hash(dict(a=2)))

    def test_key_separates_environment_and_document(self):
        args = ("Company", "Sales Invoice", "INV-1", "Fawtara Invoice")
        self.assertNotEqual(submission_key(*args, "Sandbox"), submission_key(*args, "Production"))
        self.assertNotEqual(submission_key(*args, "Sandbox"), submission_key("Other", *args[1:], "Sandbox"))

    def test_uuid_stable_version5(self):
        value = document_uuid("OM1234567890", "Sales Invoice", "INV-1")
        self.assertEqual(uuid.UUID(value).version, 5)
        self.assertEqual(value, document_uuid("OM1234567890", "Sales Invoice", "INV-1"))

    def test_provider_ack_not_authority_acceptance(self):
        with self.assertRaises(ValueError):
            acknowledgement(dict(status="Accepted", provider_reference="JOB-1"))

    def test_accepted_requires_receipt(self):
        with self.assertRaises(ValueError):
            acknowledgement(dict(status="Accepted", authority_reference="AUTH-1"))

    def test_accepted_receipt(self):
        result = acknowledgement(dict(status="Accepted", authority_reference="AUTH-1", receipt_reference="RECEIPT-1"))
        self.assertEqual(result["status"], "Accepted")

    def test_pending_requires_provider_id(self):
        with self.assertRaises(ValueError):
            acknowledgement(dict(status="Pending"))

    def test_pending_valid(self):
        self.assertEqual(acknowledgement(dict(status="Pending", provider_reference="JOB-1"))["provider_reference"], "JOB-1")

    def test_invalid_states(self):
        for result in (None, {"status": "Success"}, {"status": "Queued"}):
            with self.assertRaises(ValueError):
                acknowledgement(result)

    def test_raw_responses_not_stored(self):
        result = acknowledgement(dict(status="Unknown", raw_response="secret", api_key="secret"))
        self.assertNotIn("raw_response", result)
        self.assertNotIn("api_key", result)

    def test_whitespace_reference_rejected(self):
        with self.assertRaises(ValueError):
            acknowledgement(dict(status="Accepted", authority_reference="  ", receipt_reference="R"))

    def test_return_export_matches_frozen_totals(self):
        snapshot = json.dumps([dict(box="1a", base="100.000", output="5.000", input_vat="0.000"),
                               dict(box="5b", base="0.000", output="-1.000", input_vat="0.000")])
        doc = SimpleNamespace(doctype="Oman VAT Return", name="RET-1", company="Test", from_date="2026-07-01",
            to_date="2026-09-30", source_snapshot=snapshot, snapshot_hash=hashlib.sha256(snapshot.encode()).hexdigest())
        result = return_payload(doc, "OM1234567890")
        self.assertEqual(result["totals"], {"5a": "5.000", "7a": "4.000", "7b": "0.000", "7c": "4.000"})
        doc.source_snapshot = "[]"
        with self.assertRaisesRegex(ValueError, "integrity"):
            return_payload(doc, "OM1234567890")
