"""Trusted installed apps register adapters; settings never contain Python import paths."""
import frappe


def adapter_for(settings, kind):
    key = settings.return_provider if kind == "VAT Return" else settings.einvoice_provider
    if not key:
        frappe.throw("No approved provider adapter is configured for this submission type.")
    registered = frappe.get_hooks("oman_tax_provider_adapters") or {}
    path = registered.get(key)
    if not path:
        frappe.throw("The configured tax provider adapter is not installed.")
    if isinstance(path, (list, tuple)):
        if len(path) != 1:
            frappe.throw("Provider adapter registration must be unique.")
        path = path[0]
    adapter = frappe.get_attr(path)()
    if kind not in adapter.capabilities:
        frappe.throw("This provider does not support the requested submission type.")
    if settings.environment == "Production" and not adapter.production_ready:
        frappe.throw("This adapter has not enabled production submission.")
    return adapter, key
