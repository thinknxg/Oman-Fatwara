"""Pure payload integrity and remote acknowledgement rules for tax outbox records."""
import hashlib
import json
import uuid

from oman_vat.core import summarize

STATES = ("Queued", "Sending", "Pending", "Accepted", "Rejected", "Unknown")


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def payload_hash(payload):
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def document_uuid(vatin, document_type, name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"oman-vat:{vatin}:{document_type}:{name}"))


def submission_key(company, source_type, source_name, kind, environment):
    return payload_hash([company, source_type, source_name, kind, environment])


def acknowledgement(result):
    if not isinstance(result, dict) or result.get("status") not in ("Pending", "Accepted", "Rejected", "Unknown"):
        raise ValueError("Provider returned an invalid acknowledgement")
    if result["status"] == "Accepted" and not str(result.get("authority_reference") or "").strip():
        raise ValueError("Acceptance requires a Tax Authority reference")
    if result["status"] == "Accepted" and not str(result.get("receipt_reference") or "").strip():
        raise ValueError("Acceptance requires a receipt reference")
    if result["status"] == "Pending" and not str(result.get("provider_reference") or "").strip():
        raise ValueError("Pending status requires a provider reference")
    # Do not persist unfiltered HTTP responses, credentials or arbitrary remote fields.
    return {key: str(result.get(key) or "").strip()[:140 if key in ("authority_reference", "provider_reference") else 2000] for key in (
        "status", "authority_reference", "provider_reference", "receipt_reference", "error_code"
    ) if key in result or key in ("status", "error_code")}


def return_payload(doc, vatin):
    if hashlib.sha256(doc.source_snapshot.encode()).hexdigest() != doc.snapshot_hash:
        raise ValueError("VAT return source snapshot integrity check failed")
    snapshot = json.loads(doc.source_snapshot)
    totals, output, inputs, net = summarize(snapshot)
    return dict(schema="oman_vat.return.v1", source_type=doc.doctype, source_name=doc.name,
                company=doc.company, vat_registration=vatin, currency="OMR",
                period=dict(start=str(doc.from_date), end=str(doc.to_date)),
                snapshot_hash=doc.snapshot_hash,
                boxes={box: {key: str(value) for key, value in values.items()} for box, values in totals.items()},
                totals={"5a": str(output - totals["5b"]["output"]), "7a": str(output),
                        "7b": str(inputs), "7c": str(net)})
