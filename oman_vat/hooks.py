app_name = "oman_vat"
app_title = "Oman VAT"
app_publisher = "Oman VAT contributors"
app_description = "Oman VAT controls and return preparation for ERPNext v16"
app_email = ""
app_license = "MIT"
required_apps = ["erpnext"]
after_install = "oman_vat.install.after_install"
after_migrate = "oman_vat.install.after_migrate"
doctype_js = {
    "Sales Invoice": "public/js/invoice.js",
    "Purchase Invoice": "public/js/invoice.js",
}
doc_events = {
    "Sales Invoice": {
        "before_submit": "oman_vat.events.before_submit",
        "before_cancel": "oman_vat.events.before_cancel",
        "on_submit": "oman_vat.dispatch.automatic_submit",
    },
    "Purchase Invoice": {
        "before_submit": "oman_vat.events.before_submit",
        "before_cancel": "oman_vat.events.before_cancel",
    },
    "Journal Entry": {"before_cancel": "oman_vat.events.journal_before_cancel"},
    "Oman VAT Return": {"on_submit": "oman_vat.dispatch.automatic_submit"},
}
scheduler_events = {"cron": {"*/10 * * * *": ["oman_vat.dispatch.recover_outbox"]}}
