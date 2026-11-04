from oman_vat.reporting import collect


def execute(filters=None):
    filters = filters or {}
    rows = collect(filters.get("company"), filters.get("from_date"), filters.get("to_date"))
    for row in rows:
        for key in ("base", "output", "input_vat"):
            row[key] = float(row[key])
    columns = [
        dict(fieldname="posting_date", label="VAT Date", fieldtype="Date", width=110),
        dict(fieldname="source_type", label="Source Type", fieldtype="Link", options="DocType", width=140),
        dict(fieldname="source_name", label="Source", fieldtype="Dynamic Link", options="source_type", width=200),
        dict(fieldname="box", label="Box", fieldtype="Data", width=60),
    ]
    for name, label in (("base", "Taxable Value"), ("output", "Output VAT"), ("input_vat", "Input VAT")):
        columns.append(dict(fieldname=name, label=label, fieldtype="Currency", options="OMR", precision=3, width=140))
    return columns, rows
