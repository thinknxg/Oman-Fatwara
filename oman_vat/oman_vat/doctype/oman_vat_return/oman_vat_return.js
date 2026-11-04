frappe.ui.form.on("Oman VAT Return", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;
        frm.add_custom_button(__("Export Filing Data"), async () => {
            const result = await frappe.call({method: "oman_vat.dispatch.export_payload",
                args: {source_type: frm.doc.doctype, source_name: frm.doc.name}});
            const blob = new Blob([JSON.stringify(result.message, null, 2)], {type: "application/json"});
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = frm.doc.name + ".json";
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        frm.add_custom_button(__("Queue Portal Filing"), async () => {
            const result = await frappe.call({method: "oman_vat.dispatch.queue_submission",
                args: {source_type: frm.doc.doctype, source_name: frm.doc.name}});
            frappe.set_route("Form", "Oman Tax Submission", result.message);
        });
    }
});
