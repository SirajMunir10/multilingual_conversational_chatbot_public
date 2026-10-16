"""Exports the versioned catalogues (bank products, sample inventory) from backend/app/data/config
to data/*.xlsx and data/*.csv for business review. The JSON files remain the source of truth."""
import csv
import json
import os

import openpyxl
from openpyxl.styles import Font, PatternFill

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "backend", "app", "data", "config")
OUT = os.path.join(ROOT, "data")

PRODUCT_COLUMNS = ["product_id", "bank_name", "finance_type", "rate_type", "interest_rate", "max_ltv_national", "max_ltv_expat",
                   "min_salary_aed", "max_tenure_years", "processing_fee_pct", "valuation_fee_aed", "early_settlement_fee_pct"]
LISTING_COLUMNS = ["id", "title", "city", "community", "type", "beds", "baths", "sq_ft", "price", "developer", "status", "amenities"]


def load(name):
    with open(os.path.join(CONFIG, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def write(base, title, columns, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(columns)
    for c in ws[1]:
        c.font = Font(name="Arial", bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="5C039B")
    for r in rows:
        ws.append([", ".join(r[k]) if isinstance(r.get(k), list) else r.get(k) for k in columns])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(45, max(12, max(len(str(c.value or "")) for c in col) + 2))
    wb.save(os.path.join(OUT, f"{base}.xlsx"))
    with open(os.path.join(OUT, f"{base}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([", ".join(r[k]) if isinstance(r.get(k), list) else r.get(k) for k in columns])


def main():
    os.makedirs(OUT, exist_ok=True)
    products = load("bank_products")["products"]
    listings = load("inventory_sample")["listings"]
    write("uae_bank_mortgage_products", "Bank products (indicative)", PRODUCT_COLUMNS, products)
    write("uae_property_listings", "Sample ready listings", LISTING_COLUMNS, listings)
    print(f"Exported {len(products)} products and {len(listings)} sample listings to {OUT}")


if __name__ == "__main__":
    main()
