import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def custom_fields():
    common = [
        dict(fieldname="custom_oman_vat_section", fieldtype="Section Break", label="Oman VAT", insert_after="tax_category"),
        dict(fieldname="custom_oman_vat_treatment", fieldtype="Select", label="Oman VAT Treatment",
             options="\nStandard Rated\nZero Rated\nExempt\nExport\nReverse Charge\nOut of Scope",
             insert_after="custom_oman_vat_section", no_copy=0),
        dict(fieldname="custom_oman_vat_evidence", fieldtype="Small Text", label="VAT Evidence Reference",
             insert_after="custom_oman_vat_treatment"),
        dict(fieldname="custom_oman_vat_snapshot", fieldtype="Long Text", label="Oman VAT Snapshot",
             hidden=1, read_only=1, no_copy=1, insert_after="custom_oman_vat_evidence"),
        dict(fieldname="custom_oman_vat_line_mode", fieldtype="Check", label="Line VAT Enabled",
             read_only=1, insert_after="custom_oman_vat_snapshot"),
    ]
    purchase = [dict(row) for row in common] + [
        dict(fieldname="custom_oman_vat_recovery_percent", fieldtype="Percent", label="Recoverable Input VAT %",
             default="100", insert_after="custom_oman_vat_treatment"),
        dict(fieldname="custom_oman_vat_capital_asset", fieldtype="Check", label="Capital Asset",
             insert_after="custom_oman_vat_recovery_percent"),
    ]
    line_common = [
        dict(fieldname="custom_oman_vat_treatment", fieldtype="Select", label="Oman VAT Treatment",
             options="\nStandard Rated\nZero Rated\nExempt\nExport\nReverse Charge\nOut of Scope",
             insert_after="item_tax_template", in_list_view=1,
             description="Blank inherits the invoice treatment."),
        dict(fieldname="custom_oman_vat_evidence", fieldtype="Small Text", label="VAT Evidence Reference",
             insert_after="custom_oman_vat_treatment"),
    ]
    line_purchase = [dict(row) for row in line_common] + [
        dict(fieldname="custom_oman_vat_override_recovery", fieldtype="Check", label="Override Input Recovery",
             insert_after="custom_oman_vat_evidence"),
        dict(fieldname="custom_oman_vat_recovery_percent", fieldtype="Percent", label="Line Recoverable Input VAT %",
             default="100", insert_after="custom_oman_vat_override_recovery",
             depends_on="eval:doc.custom_oman_vat_override_recovery"),
        dict(fieldname="custom_oman_vat_capital_asset", fieldtype="Check", label="Capital Asset",
             insert_after="custom_oman_vat_recovery_percent"),
    ]
    fawtara_header = [
        dict(fieldname="custom_fawtara_section", fieldtype="Section Break", label="Fawtara e-Invoicing",
             insert_after="custom_oman_vat_line_mode"),
        dict(fieldname="custom_fawtara_transaction_type", fieldtype="Data", label="Oman Transaction Type Bitmap",
             default="10000000000000000000", insert_after="custom_fawtara_section",
             description="20-bit transaction type from PINT OM. Default is a full tax invoice; review the business case."),
        dict(fieldname="custom_fawtara_buyer_endpoint", fieldtype="Data", label="Buyer Peppol Endpoint",
             insert_after="custom_fawtara_transaction_type"),
        dict(fieldname="custom_fawtara_buyer_endpoint_scheme", fieldtype="Data", label="Buyer Endpoint Scheme",
             insert_after="custom_fawtara_buyer_endpoint"),
        dict(fieldname="custom_fawtara_credit_reason_code", fieldtype="Data", label="Credit Note Reason Code",
             insert_after="custom_fawtara_buyer_endpoint_scheme"),
    ]
    fawtara_line = [
        dict(fieldname="custom_fawtara_tax_reason_code", fieldtype="Data", label="Oman VAT Reason Code",
             insert_after="custom_oman_vat_evidence", description="Applicable VATEX-OM or VATZR-OM code."),
        dict(fieldname="custom_fawtara_uom_code", fieldtype="Data", label="UNECE Unit Code",
             insert_after="custom_fawtara_tax_reason_code"),
        dict(fieldname="custom_fawtara_item_type", fieldtype="Select", label="Fawtara Item Type",
             options="\nGoods\nServices", insert_after="custom_fawtara_uom_code"),
        dict(fieldname="custom_fawtara_classification_code", fieldtype="Data", label="Oman HS / Service Classification",
             insert_after="custom_fawtara_item_type"),
    ]
    return {"Sales Invoice": common + fawtara_header, "Purchase Invoice": purchase,
            "Sales Invoice Item": line_common + fawtara_line, "Purchase Invoice Item": line_purchase}


def after_install():
    after_migrate()


def after_migrate():
    # Stable names make repeated installs/migrations idempotent.
    create_custom_fields(custom_fields(), update=True)
