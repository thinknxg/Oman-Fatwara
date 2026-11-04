from oman_vat.reporting import collect, summary_rows


def execute(filters=None):
    filters = filters or {}
    entries = collect(filters.get("company"), filters.get("from_date"), filters.get("to_date"))
    rows, output, inputs, net = summary_rows(entries)
    columns = [dict(fieldname="box", label="Box", fieldtype="Data", width=65),
               dict(fieldname="description", label="Description", fieldtype="Data", width=300)]
    for name, label in (("base", "Taxable Value"), ("output", "Output VAT"), ("input_vat", "Input VAT")):
        columns.append(dict(fieldname=name, label=label, fieldtype="Currency", options="OMR", precision=3, width=150))
    summary = [dict(label=label, value=float(value), datatype="Currency", currency="OMR")
               for label, value in (("Output VAT", output), ("Input VAT", inputs), ("Net VAT", net))]
    return columns, rows, "Working paper in OMR. Reconcile and file through the Tax Authority portal.", None, summary
