for (const doctype of ["Sales Invoice", "Purchase Invoice"]) {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (frm.doc.docstatus === 1 && frm.doc.doctype === "Sales Invoice") {
                frm.add_custom_button(__("Queue Fawtara Invoice"), async () => {
                    const result = await frappe.call({method: "oman_vat.dispatch.queue_submission",
                        args: {source_type: frm.doc.doctype, source_name: frm.doc.name}});
                    frappe.set_route("Form", "Oman Tax Submission", result.message);
                });
                frm.add_custom_button(__("Export Fawtara Provider Data"), async () => {
                    const result = await frappe.call({method: "oman_vat.dispatch.export_payload",
                        args: {source_type: frm.doc.doctype, source_name: frm.doc.name}});
                    const blob = new Blob([JSON.stringify(result.message, null, 2)], {type: "application/json"});
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = frm.doc.name + "-fawtara.json";
                    link.click();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                });
            }
            if (frm.doc.docstatus !== 0 || !frm.doc.company) return;
            frm.add_custom_button(__("Apply Oman VAT"), async () => {
                if (!frm.doc.items?.length || frm.doc.items.some(row =>
                    !row.custom_oman_vat_treatment && !frm.doc.custom_oman_vat_treatment)) {
                    frappe.msgprint(__("Choose VAT treatments on the invoice or each item row."));
                    return;
                }
                const apply = async () => {
                    const result = await frappe.call({
                        method: "oman_vat.api.invoice_plan",
                        args: {document: JSON.stringify(frm.doc)}
                    });
                    await frm.set_value("taxes_and_charges", "");
                    frm.clear_table("taxes");
                    for (const row of result.message.taxes) frm.add_child("taxes", row);
                    for (const planned of result.message.items) {
                        const row = frm.doc.items.find(item => item.name === planned.name);
                        if (row) {
                            row.item_tax_template = planned.item_tax_template;
                            row.item_tax_rate = planned.item_tax_rate;
                        }
                    }
                    await frm.set_value("custom_oman_vat_line_mode", 1);
                    frm.refresh_field("items");
                    frm.refresh_field("taxes");
                    await frm.trigger("calculate_taxes_and_totals");
                    frm.dirty();
                };
                if (frm.doc.taxes?.length) {
                    frappe.confirm(__("Replace tax rows and item tax templates with Oman VAT settings? Review each item's treatment and recovery before submitting."), apply);
                } else await apply();
            });
        }
    });
}
