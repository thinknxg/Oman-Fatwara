# VAT portal filing and Fawtara integration

## What this release can do

The app prepares mixed-line VAT data and provides two distinct outbound flows:

| Flow | Source | Export | Remote operation |
|---|---|---|---|
| VAT return filing | Submitted Oman VAT Return | `oman_vat.return.v1` JSON | Approved VAT-return filing adapter |
| Fawtara e-invoicing | Submitted Sales Invoice / linked return | `oman_vat.fawtara.input.v1` JSON | Accredited service-provider adapter |

Exports are canonical application data for a connector to map. They are not represented as a portal-upload format, PINT XML, a Tax Data Document (TDD), a signed invoice or an official receipt.

No production adapter is included. No API URL, authentication method, taxpayer credential or provider was supplied. The public sources reviewed establish a VAT portal and Fawtara/Peppol specifications; they do not establish an unauthenticated or public VAT-return submission API. The app therefore cannot perform live filing immediately after installation.

## Connection setup

1. Obtain supported VAT-return API access or an approved filing-provider contract. For Fawtara, onboard with an accredited service provider and obtain its sandbox specification, credentials, participant identifiers and callback/status requirements.
2. Implement and install the trusted adapter described below. Run all provider and Authority acceptance checks, including PINT OM XML/TDD validation and receipt handling.
3. As System Manager, create **Oman Tax Connector** for the company. Choose Sandbox, enter the registered adapter keys, approved HTTPS provider URL, API secret, and seller Peppol endpoint/scheme. The API secret is a Frappe Password field at permission level 1; Accounts Managers cannot read that field.
4. Enable the connector. Keep automatic options off while manually checking sandbox transmissions.
5. Verify receipts and idempotency, then configure Production with production-ready adapters. Enable automatic return/invoice queuing only after the production configuration is verified.

The VAT-return and invoice adapters may be different. The settings have one optional shared provider URL/secret for simple deployments; adapters needing separate OAuth credentials, certificates, or multiple endpoints must use protected site configuration or their own integration DocTypes. Never store secrets in provider payloads or plain text settings.

## Adapter contract

An installed Frappe integration app registers a key in its `hooks.py`:

```python
oman_tax_provider_adapters = {
    "your_provider": "your_integration.oman.adapter.OmanAdapter"
}
```

The class has these members:

```python
capabilities = {"VAT Return", "Fawtara Invoice"}  # Include only supported flows.
production_ready = False  # Set True only after actual integration acceptance.

def validate(self, payload, connector):
    # Render and validate without issuing or filing anything remotely.
    # Run applicable schema, Schematron, code-list and provider checks.
    return {"valid": True}

def submit(self, payload, connector, idempotency_key):
    # Perform the documented provider request with a bounded timeout.
    # Preserve idempotency at the provider, including after a worker crash.
    # A provider job acknowledgement is Pending, not Authority acceptance.
    return {"status": "Pending", "provider_reference": "provider-job-reference"}

def lookup(self, idempotency_key, provider_reference, connector):
    # Query only. Never re-submit from this method.
    # Report Accepted only after verifying the correct Authority receipt.
    return {
        "status": "Accepted",
        "provider_reference": "provider-job-reference",
        "authority_reference": "verified-authority-reference",
        "receipt_reference": "private-archived-receipt-reference",
    }
```

The values shown are contract examples, not real provider endpoints or receipts. `connector.get_password("api_secret")` is available to trusted server-side adapter code; it must never return or log the secret. Keep provider exception messages and raw HTTP responses out of the outbox. Preserve signed XML, delivery receipts, validation reports and other evidence as private records/files with appropriate retention. `receipt_reference` should identify that archive.

`Rejected` must mean definitively not accepted. Network timeouts, invalid acknowledgements, incomplete receipts or unknown remote outcomes must remain `Unknown`. A status lookup that returns an ambiguous not-found result must also remain Unknown. Lookup must verify payload/source, taxpayer, environment and receipt references before reporting acceptance. HTTPS validation, authentication, XML signing, webhook signature verification and receipt verification belong in the actual provider adapter.

## Queue behavior

- Queuing occurs in the source transaction; dispatch is enqueued after commit. A scheduler also resumes committed Queued records.
- A stable idempotency key is derived from company, source, flow and environment. One source has one record per environment. Repeated queue actions return the same record.
- Provider payload, endpoint URL and SHA-256 are frozen. The worker checks the provider/environment/endpoint binding, validates the payload, commits Sending, then performs the external request. It does not hold a database transaction open across transmission.
- Queued records can be cancelled before transmission. Uncertain submissions are never automatically re-posted. Pending/Unknown records are polled using read-only lookup.
- Crashed Sending jobs become Unknown after 30 minutes. This does not establish remote failure. A late reply is handled through reconciliation rather than overwriting a later result.
- Accepted requires both an Authority reference and a receipt reference. Production VAT-return acceptance copies the Authority reference to the internal return's portal-reference field.
- Queued, unresolved or accepted production submissions prevent local source cancellation. Correct issued invoices through the applicable credit-note process and filed returns through the approved amendment process. Sandbox records do not block local source cancellation.
- A rejected frozen payload is retained for audit. Fix source-data errors by cancelling/amending the source where legally appropriate. The release has no automated re-filing or remote cancellation operation.

## Fawtara mapping responsibilities

The local export contains seller/buyer/address data, Peppol identifiers, issue date/time, a deterministic local UUIDv5, document type 380 or 381, original-invoice references, native totals, per-line VAT categories S/Z/E/O, OMR VAT amounts, quantity/unit, goods/services type and supplied classification/reason codes. It validates the bitmap shape, seller VATIN format, applicable reason-code families and basic required metadata. It does not validate every PINT OM business rule.

The adapter must map those values to the current **PINT OM Billing** syntax and **Oman TDD** requirements. This includes correct transaction-type combinations, addresses and subentity codes, endpoint schemes, HS/service classifications, reason-code semantics, original UUID references, currency/exchange-rate details, prepayments, discounts, rounding, UUID/hash generation rules and any QR payload required for the human-readable invoice. The app's local UUID namespace is not asserted to be the Authority's namespace; preserve a verified local-to-provider UUID mapping if the provider requires another algorithm.

The provider must perform complete schema/Schematron/code-list validation and reject unsupported scenarios. The source uses ERPNext OMR precision; PINT OM has field-specific rounding constraints. Do not silently alter ledger totals to make an export pass. Resolve differences through the supported invoice/correction process. Purchase self-billing, B2C QR rendering, inbound network messages and direct access-point operation are not implemented by the core app.

## Official references reviewed

- [Oman Tax Authority VAT return service](https://tms.taxoman.gov.om/portal/web/taxportal/returns)
- [Oman Tax Authority e-services](https://tms.taxoman.gov.om/portal/e-services)
- [Fawtara manuals and Oman SMP API specification](https://tms.taxoman.gov.om/portal/web/taxportal/e-invoicing-manual-guide)
- [Accredited Fawtara service providers](https://fawtara.taxoman.gov.om/accredited-service-providers)
- [OpenPeppol Oman specifications: billing, self-billing and TDD](https://docs.peppol.eu/poac/om/)
- [PINT OM Billing v1.0.1](https://docs.peppol.eu/poac/om/pint-om/)
- [Oman-specific PINT rules](https://docs.peppol.eu/poac/om/pint-om/trn-invoice/rule/PINT-jurisdiction-aligned-rules/)

Reviewed 4 November 2026. Provider onboarding and the applicable production specification must be confirmed for the actual taxpayer before activation.
