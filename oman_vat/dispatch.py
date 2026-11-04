"""Durable tax outbox. External side effects run only in background jobs."""
import json

import frappe
from frappe.utils import add_to_date, now_datetime

from oman_vat.access import lock_company, require_manager
from oman_vat.providers import adapter_for
from oman_vat.transmission import acknowledgement, canonical, payload_hash, return_payload, submission_key


def connector_for(company):
    if not frappe.db.exists("Oman Tax Connector", company):
        frappe.throw("Configure an Oman Tax Connector first.")
    settings = frappe.get_doc("Oman Tax Connector", company)
    if not settings.enabled:
        frappe.throw("The Oman Tax Connector is disabled.")
    return settings


def source_for(source_type, source_name):
    if source_type not in ("Sales Invoice", "Oman VAT Return"):
        frappe.throw("Unsupported tax submission source.")
    doc = frappe.get_doc(source_type, source_name)
    require_manager(doc.company)
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw("Only submitted documents can be transmitted.")
    return doc


def make_payload(doc, connector):
    if doc.doctype == "Oman VAT Return":
        vat_id = frappe.db.get_value("Company", doc.company, "tax_id")
        return return_payload(doc, vat_id)
    from oman_vat.einvoicing import invoice_payload
    return invoice_payload(doc, connector)


@frappe.whitelist()
def export_payload(source_type, source_name):
    doc = source_for(source_type, source_name)
    if source_type == "Oman VAT Return":
        return make_payload(doc, None)
    connector = frappe.get_doc("Oman Tax Connector", doc.company)
    return make_payload(doc, connector)


@frappe.whitelist()
def queue_submission(source_type, source_name):
    return queue_document(source_for(source_type, source_name))


def queue_document(doc):
    """Called by authorized UI actions or by explicitly enabled source hooks."""
    lock_company(doc.company)
    if doc.docstatus != 1:
        frappe.throw("Only submitted sources can be queued.")
    table = frappe.qb.DocType(doc.doctype)
    state = (frappe.qb.from_(table).select(table.docstatus).where(table.name == doc.name).for_update().run())
    if not state or state[0][0] != 1:
        frappe.throw("Source is no longer submitted.")
    connector = connector_for(doc.company)
    kind = "VAT Return" if doc.doctype == "Oman VAT Return" else "Fawtara Invoice"
    adapter, key = adapter_for(connector, kind)
    name = submission_key(doc.company, doc.doctype, doc.name, kind, connector.environment)
    if frappe.db.exists("Oman Tax Submission", name):
        return name
    payload = make_payload(doc, connector)
    record = frappe.get_doc(dict(doctype="Oman Tax Submission", name=name, company=doc.company,
        source_type=doc.doctype, source_name=doc.name, kind=kind, environment=connector.environment,
        provider=key, endpoint_url=connector.endpoint_url, status="Queued",
        payload=canonical(payload), payload_hash=payload_hash(payload),
        idempotency_key=name, attempt_count=0))
    record.flags.internal_tax_update = True
    record.insert(ignore_permissions=True)
    frappe.enqueue("oman_vat.dispatch.process_submission", submission=name, enqueue_after_commit=True, queue="long")
    return name


def automatic_submit(doc, method=None):
    if not frappe.db.exists("Oman Tax Connector", doc.company):
        return
    connector = frappe.get_doc("Oman Tax Connector", doc.company)
    flag = "auto_file_returns" if doc.doctype == "Oman VAT Return" else "auto_send_einvoices"
    if connector.enabled and connector.get(flag):
        queue_document(doc)


def lock_submission(name):
    table = frappe.qb.DocType("Oman Tax Submission")
    (frappe.qb.from_(table).select(table.name).where(table.name == name).for_update().run())
    return frappe.get_doc("Oman Tax Submission", name)


def update(record, **values):
    for key, value in values.items():
        record.set(key, value)
    record.flags.internal_tax_update = True
    record.save(ignore_permissions=True)


def verified_context(record):
    connector = connector_for(record.company)
    adapter, key = adapter_for(connector, record.kind)
    if (key != record.provider or connector.environment != record.environment
            or connector.endpoint_url != record.endpoint_url):
        frappe.throw("Connector changed after this submission was queued.")
    payload = json.loads(record.payload)
    if payload_hash(payload) != record.payload_hash:
        frappe.throw("Tax submission payload integrity check failed.")
    return connector, adapter, payload


def process_submission(submission):
    """Worker-only. Persist Sending before the network call; never resend ambiguity."""
    record = lock_submission(submission)
    if record.status != "Queued":
        return
    try:
        connector, adapter, payload = verified_context(record)
        table = frappe.qb.DocType(record.source_type)
        state = (frappe.qb.from_(table).select(table.docstatus).where(table.name == record.source_name).for_update().run())
        if not state or state[0][0] != 1:
            raise ValueError("SOURCE_NOT_SUBMITTED")
        validation = adapter.validate(payload, connector)
        if not isinstance(validation, dict) or validation.get("valid") is not True:
            update(record, status="Rejected", error_code="PROVIDER_VALIDATION_FAILED")
            frappe.db.commit()
            return
    except Exception:
        update(record, status="Rejected", error_code="LOCAL_VALIDATION_FAILED")
        frappe.db.commit()
        return
    update(record, status="Sending", attempt_count=(record.attempt_count or 0) + 1,
           last_attempt_at=now_datetime(), error_code="")
    frappe.db.commit()
    try:
        result = acknowledgement(adapter.submit(payload, connector, record.idempotency_key))
    except Exception:
        result = dict(status="Unknown", error_code="SUBMISSION_OUTCOME_UNCERTAIN")
    record = lock_submission(submission)
    if record.status != "Sending":
        # A slow response cannot overwrite another worker's reconciliation result.
        frappe.db.rollback()
        return
    update(record, **result)
    if record.kind == "VAT Return" and record.environment == "Production" and record.status == "Accepted":
        frappe.db.set_value("Oman VAT Return", record.source_name, "portal_reference", record.authority_reference)
    frappe.db.commit()


@frappe.whitelist()
def check_status(submission):
    record = frappe.get_doc("Oman Tax Submission", submission)
    require_manager(record.company)
    record.check_permission("read")
    if record.status not in ("Pending", "Unknown"):
        return record.status
    frappe.enqueue("oman_vat.dispatch.reconcile_submission", submission=submission, enqueue_after_commit=True)
    return "Status check queued"


def reconcile_submission(submission):
    record = lock_submission(submission)
    if record.status not in ("Pending", "Unknown"):
        return
    update(record, last_checked_at=now_datetime())
    frappe.db.commit()
    try:
        connector, adapter, payload = verified_context(record)
        result = acknowledgement(adapter.lookup(record.idempotency_key, record.provider_reference, connector))
    except Exception:
        return  # Status lookup is read-only and can be attempted again later.
    current = lock_submission(submission)
    if current.status in ("Pending", "Unknown"):
        update(current, **result)
        if current.kind == "VAT Return" and current.environment == "Production" and current.status == "Accepted":
            frappe.db.set_value("Oman VAT Return", current.source_name, "portal_reference", current.authority_reference)
        frappe.db.commit()


@frappe.whitelist()
def cancel_queued(submission):
    record = frappe.get_doc("Oman Tax Submission", submission)
    require_manager(record.company)
    record.check_permission("read")
    lock_company(record.company)
    record = lock_submission(submission)
    if record.status != "Queued":
        frappe.throw("Only an unsent Queued submission can be cancelled locally.")
    update(record, status="Rejected", error_code="CANCELLED_BEFORE_TRANSMISSION")
    return record.name


def recover_outbox():
    """Resume committed Queued records; poll receipts; expire crashed Sending jobs."""
    cutoff = add_to_date(now_datetime(), minutes=-30)
    for row in frappe.get_all("Oman Tax Submission", filters={"status": "Sending", "last_attempt_at": ["<", cutoff]}, pluck="name"):
        record = lock_submission(row)
        if record.status == "Sending":
            update(record, status="Unknown", error_code="WORKER_INTERRUPTED")
            frappe.db.commit()
    for state, target in (("Queued", "process_submission"), ("Pending", "reconcile_submission"), ("Unknown", "reconcile_submission")):
        for row in frappe.get_all("Oman Tax Submission", filters={"status": state}, pluck="name",
                                 order_by="last_checked_at asc, creation asc", limit_page_length=100):
            frappe.enqueue("oman_vat.dispatch." + target, submission=row, enqueue_after_commit=True)


def block_source_cancel(doc, method=None):
    lock_company(doc.company)
    table = frappe.qb.DocType("Oman Tax Submission")
    records = (frappe.qb.from_(table).select(table.name)
        .where((table.source_type == doc.doctype) & (table.source_name == doc.name)
               & (table.environment == "Production") & (table.status != "Rejected")).for_update().run())
    if records:
        frappe.throw("This document has a queued, unresolved or accepted tax submission. Resolve its status and use the required amendment/credit-note process.")
