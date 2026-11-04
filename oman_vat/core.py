"""Pure calculation rules. All monetary amounts are OMR Decimal values.

No ledger posting occurs here. Invoice VAT must already have been calculated
by ERPNext; these rules validate and classify its signed company amounts.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

Q = Decimal("0.001")
RATE = Decimal("5")
TREATMENTS = ("Standard Rated", "Zero Rated", "Exempt", "Export", "Reverse Charge", "Out of Scope")
BOXES = {
    "1a": "Domestic standard supplies", "1b": "Domestic zero rate supplies",
    "1c": "Exempt supplies", "2b": "Reverse charge purchases",
    "3a": "Exports", "4a": "Postponed imports", "4b": "Other goods imports",
    "5b": "Output VAT adjustments", "6a": "Non-import purchases",
    "6b": "Standard goods imports: input", "6c": "Capital assets: input",
    "6d": "Input VAT adjustments",
}


def dec(value):
    try:
        result = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid numeric amount") from None
    if not result.is_finite():
        raise ValueError("Amounts must be finite")
    return result


def money(value):
    return dec(value).quantize(Q, rounding=ROUND_HALF_UP)


def percent(value):
    result = dec(value)
    if not 0 <= result <= 100:
        raise ValueError("Input recovery percentage must be between 0 and 100")
    return result


def entry(box, base=0, output=0, input_vat=0):
    if box not in BOXES:
        raise ValueError("Unknown VAT return box")
    return {"box": box, "base": str(money(base)), "output": str(money(output)),
            "input_vat": str(money(input_vat))}


def expected_rates(side, treatment, recovery=100):
    if treatment not in TREATMENTS:
        raise ValueError("Choose an Oman VAT treatment")
    if side not in ("Sales Invoice", "Purchase Invoice"):
        raise ValueError("Unsupported invoice type")
    if side == "Sales Invoice":
        if treatment == "Reverse Charge":
            raise ValueError("Reverse charge treatment is available on purchases only")
        return {"output": RATE} if treatment == "Standard Rated" else {}
    if treatment == "Export":
        raise ValueError("Export treatment is available on sales only")
    recovery = percent(recovery)
    if treatment not in ("Standard Rated", "Reverse Charge"):
        return {}
    rates = {"input": RATE * recovery / 100, "blocked": RATE * (100 - recovery) / 100}
    if treatment == "Reverse Charge":
        rates["output"] = RATE
    return {key: value for key, value in rates.items() if value}


def invoice_entries(side, treatment, base, output=0, input_vat=0, capital=False, is_return=False):
    expected_rates(side, treatment)
    base, output, input_vat = map(money, (base, output, input_vat))
    if is_return and (base > 0 or output > 0 or input_vat > 0):
        raise ValueError("Return invoices must have negative base and VAT amounts")
    if not is_return and (base < 0 or output < 0 or input_vat < 0):
        raise ValueError("Use a return invoice for negative VAT amounts")
    if treatment == "Out of Scope":
        return []
    if side == "Sales Invoice":
        if is_return and treatment == "Standard Rated":
            return [entry("5b", 0, output)]
        box = {"Standard Rated": "1a", "Zero Rated": "1b", "Exempt": "1c", "Export": "3a"}[treatment]
        return [entry(box, base, output)]
    result = []
    if treatment == "Reverse Charge":
        result.append(entry("5b" if is_return else "2b", 0 if is_return else base, output))
    if is_return:
        # Returns are tax adjustments; do not count their value again in 6a/6c.
        if input_vat:
            result.append(entry("6d", input_vat=input_vat))
    else:
        result.append(entry("6c" if capital else "6a", 0 if capital else base, input_vat=input_vat))
    return result


def manual_entries(kind, base, vat, recovery=100, capital=False, standard=True):
    base, vat = money(base), money(vat)
    recoverable = money(vat * percent(recovery) / 100)
    if kind in ("Customs Paid Import", "Postponed Import"):
        if base < 0 or vat < 0:
            raise ValueError("Imports require nonnegative amounts; use adjustment entries for corrections")
        if standard and abs(vat - money(base * RATE / 100)) > Q:
            raise ValueError("Standard imports must carry 5% VAT on the customs taxable value")
        if not standard and vat:
            raise ValueError("Zero rated or exempt imports must have no VAT")
        if kind == "Postponed Import" and not standard:
            raise ValueError("Use Customs Paid Import for zero rated or exempt goods")
        result = [entry("4a" if kind == "Postponed Import" else "4b", base,
                        vat if kind == "Postponed Import" else 0)]
        if standard:
            result.append(entry("6c" if capital else "6b", 0 if capital else base, input_vat=recoverable))
        return result
    if kind == "Output Adjustment":
        return [entry("5b", output=vat)]
    if kind == "Input Adjustment":
        return [entry("6d", input_vat=vat)]
    raise ValueError("Unknown manual entry type")


def summarize(entries):
    totals = {box: {"base": Decimal(0), "output": Decimal(0), "input_vat": Decimal(0)} for box in BOXES}
    for row in entries:
        if row["box"] not in totals:
            raise ValueError("Unknown VAT return box")
        for key in ("base", "output", "input_vat"):
            totals[row["box"]][key] += money(row.get(key, 0))
    output = sum((row["output"] for row in totals.values()), Decimal(0))
    inputs = sum((row["input_vat"] for row in totals.values()), Decimal(0))
    return totals, money(output), money(inputs), money(output - inputs)
