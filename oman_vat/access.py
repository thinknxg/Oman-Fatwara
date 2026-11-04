import frappe
from frappe.utils import getdate


def require_manager(company):
    frappe.only_for("Accounts Manager")
    if not company:
        frappe.throw("Choose a company.")
    frappe.get_doc("Company", company).check_permission("read")


def settings_for(company):
    if not frappe.db.exists("Oman VAT Settings", company):
        frappe.throw("Create Oman VAT Settings for this company first.")
    settings = frappe.get_doc("Oman VAT Settings", company)
    if not settings.enabled:
        frappe.throw("Oman VAT Settings are not enabled.")
    info = frappe.db.get_value("Company", company, ["country", "default_currency"], as_dict=True)
    if info.country != "Oman" or info.default_currency != "OMR":
        frappe.throw("Oman VAT requires an Oman company with OMR as its company currency.")
    return settings


def lock_company(company):
    # Shared transaction lock: return filing and source submit/cancel are serialized.
    Company = frappe.qb.DocType("Company")
    frappe.qb.from_(Company).select(Company.name).where(Company.name == company).for_update().run()


def assert_open(company, tax_date):
    table = frappe.qb.DocType("Oman VAT Return")
    closed = (frappe.qb.from_(table).select(table.name)
              .where((table.company == company) & (table.docstatus == 1)
                     & (table.from_date <= tax_date) & (table.to_date >= tax_date))
              .for_update().run())
    if closed:
        frappe.throw("This date belongs to a submitted Oman VAT Return. Cancel that return before changing its sources.")


def has_submitted(company, doctypes):
    for doctype in doctypes:
        table = frappe.qb.DocType(doctype)
        condition = (table.company == company) & (table.docstatus == 1)
        if doctype in ("Sales Invoice", "Purchase Invoice"):
            condition &= table.custom_oman_vat_snapshot.isnotnull() & (table.custom_oman_vat_snapshot != "")
        if (frappe.qb.from_(table).select(table.name).where(condition).for_update().run()):
            return True
    return False


def date_range(company, start, end):
    if not start or not end or getdate(start) > getdate(end):
        frappe.throw("Enter a valid VAT date range.")
    settings = settings_for(company)
    if getdate(start) < getdate(settings.effective_from):
        frappe.throw("The return starts before Oman VAT activation. Migrate historical transactions first.")
    return settings
