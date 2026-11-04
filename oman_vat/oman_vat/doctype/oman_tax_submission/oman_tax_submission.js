frappe.ui.form.on("Oman Tax Submission", {
    refresh(frm) {
        if (frm.doc.status === "Queued") {
            frm.add_custom_button(__("Cancel Unsent Submission"), async () => {
                await frappe.call({method: "oman_vat.dispatch.cancel_queued", args: {submission: frm.doc.name}});
                await frm.reload_doc();
            });
        }
        if (["Pending", "Unknown"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Check Provider Status"), async () => {
                await frappe.call({method: "oman_vat.dispatch.check_status", args: {submission: frm.doc.name}});
                frappe.show_alert(__("Status check queued."));
            });
        }
    }
});
