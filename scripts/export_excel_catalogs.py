import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Ensure backend imports work
import sys
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.gateways.mortgage_rules_gateway import MortgageRulesGateway
from app.gateways.inventory_gateway import PropertyInventoryGateway

# Styling definitions (XOTO Luxury Navy & Gold)
NAVY_HEADER_FILL = PatternFill(start_color="0A192F", end_color="0A192F", fill_type="solid")
GOLD_HEADER_FILL = PatternFill(start_color="172A45", end_color="172A45", fill_type="solid")
ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

ISLAMIC_BADGE_FILL = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
CONV_BADGE_FILL = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="D4AF37")
SUBHEADER_FONT = Font(name="Calibri", size=10, bold=True, color="64B5F6")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="0A192F")
REGULAR_FONT = Font(name="Calibri", size=10, bold=False, color="1E293B")
BOLD_FONT = Font(name="Calibri", size=10, bold=True, color="0F172A")

THIN_BORDER_SIDE = Side(border_style="thin", color="CBD5E1")
GRID_BORDER = Border(
    left=THIN_BORDER_SIDE,
    right=THIN_BORDER_SIDE,
    top=THIN_BORDER_SIDE,
    bottom=THIN_BORDER_SIDE
)

def autofit_columns(ws, min_col=1, max_col=None):
    if max_col is None:
        max_col = ws.max_column
    for col in range(min_col, max_col + 1):
        col_letter = get_column_letter(col)
        max_len = 0
        for cell in ws[col_letter]:
            val = cell.value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

def create_bank_workbook(output_path: str):
    wb = openpyxl.Workbook()
    # Sheet 1: Master
    ws_all = wb.active
    ws_all.title = "All UAE Bank Products"
    
    # Sheet 2: Islamic
    ws_islamic = wb.create_sheet(title="Islamic Home Finance")
    
    # Sheet 3: Conventional
    ws_conv = wb.create_sheet(title="Conventional Mortgages")

    headers = [
        "Product ID",
        "Bank / Financial Institution",
        "Finance Type",
        "Contract / Rate Type",
        "Profit / Interest Rate",
        "Max LTV (UAE National)",
        "Max LTV (Expat)",
        "Min Monthly Salary",
        "Max Tenure",
        "Processing Fee",
        "Valuation Fee",
        "Early Settlement Fee",
        "System Version"
    ]

    all_products = MortgageRulesGateway._products
    islamic_products = [p for p in all_products if p.finance_type == "islamic"]
    conv_products = [p for p in all_products if p.finance_type == "conventional"]

    sheets_data = [
        (ws_all, "XOTO UAE Bank Mortgage & Home Finance Rate Sheets (All 14 Products)", all_products),
        (ws_islamic, "XOTO Sharia-Compliant Islamic Home Finance Rate Sheets (11 Products)", islamic_products),
        (ws_conv, "XOTO Conventional Bank Mortgage Rate Sheets (3 Products)", conv_products)
    ]

    for ws, title_text, products in sheets_data:
        # Title Block
        ws.merge_cells("A1:M1")
        title_cell = ws["A1"]
        title_cell.value = title_text
        title_cell.font = TITLE_FONT
        title_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 28

        # Metadata Subtitle
        ws.merge_cells("A2:M2")
        meta_cell = ws["A2"]
        meta_cell.value = "Source: XOTO Admin-Managed Mortgage Rules Gateway (v1.2.0) | Compliant with UAE Central Bank Lending Regulations"
        meta_cell.font = Font(name="Calibri", size=9, italic=True, color="64748B")
        meta_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 18

        # Headers on Row 4
        ws.row_dimensions[4].height = 26
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=h)
            cell.font = HEADER_FONT
            cell.fill = NAVY_HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = GRID_BORDER

        # Data Rows starting on Row 5
        for r_idx, p in enumerate(products, 5):
            ws.row_dimensions[r_idx].height = 20
            row_fill = ZEBRA_FILL if r_idx % 2 == 0 else WHITE_FILL

            row_values = [
                p.product_id,
                p.bank_name,
                p.finance_type.upper(),
                p.rate_type,
                p.interest_rate / 100.0,  # Formatted as %
                p.max_ltv_national / 100.0,
                p.max_ltv_expat / 100.0,
                p.min_salary_aed,
                f"{p.max_tenure_years} Years",
                p.processing_fee_pct / 100.0,
                p.valuation_fee_aed,
                p.early_settlement_fee_pct / 100.0,
                p.version
            ]

            for c_idx, val in enumerate(row_values, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = REGULAR_FONT
                cell.fill = row_fill
                cell.border = GRID_BORDER

                # Formatting
                if c_idx in [5, 6, 7, 10, 12]:  # Percentages
                    cell.number_format = "0.00%"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif c_idx in [8, 11]:  # Currency AED
                    cell.number_format = '#,##0 "AED"'
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif c_idx == 3:  # Badge styling for Finance Type
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = BOLD_FONT
                    cell.fill = ISLAMIC_BADGE_FILL if "ISLAMIC" in str(val) else CONV_BADGE_FILL
                elif c_idx in [1, 9, 13]:  # IDs, Years, Version
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        autofit_columns(ws)

    wb.save(output_path)
    print(f"Bank workbook created at: {output_path}")

def create_properties_workbook(output_path: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Active Property Listings"

    headers = [
        "Property ID",
        "Property Title",
        "City",
        "Community / Location",
        "Property Type",
        "Bedrooms",
        "Bathrooms",
        "Built-Up Area (Sq Ft)",
        "Price (AED)",
        "Transaction Purpose",
        "Master Developer",
        "Construction Status",
        "Key Amenities",
        "Listing Portal URL"
    ]

    # Title
    ws.merge_cells("A1:N1")
    title_cell = ws["A1"]
    title_cell.value = "XOTO UAE Live Property Inventory Catalog (Active Listings)"
    title_cell.font = TITLE_FONT
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    # Subtitle
    ws.merge_cells("A2:N2")
    meta_cell = ws["A2"]
    meta_cell.value = "Source: XOTO Property Inventory Gateway | Prime Residential & Investment Assets in Dubai"
    meta_cell.font = Font(name="Calibri", size=9, italic=True, color="64748B")
    meta_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 18

    # Headers on Row 4
    ws.row_dimensions[4].height = 26
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = NAVY_HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = GRID_BORDER

    inventory = PropertyInventoryGateway._inventory
    for r_idx, prop in enumerate(inventory, 5):
        ws.row_dimensions[r_idx].height = 22
        row_fill = ZEBRA_FILL if r_idx % 2 == 0 else WHITE_FILL

        row_values = [
            prop.id,
            prop.title,
            prop.city,
            prop.community,
            prop.type.capitalize(),
            prop.beds,
            prop.baths,
            prop.sq_ft,
            prop.price,
            prop.purpose.upper(),
            prop.developer,
            prop.status.capitalize(),
            ", ".join(prop.amenities),
            prop.listing_url
        ]

        for c_idx, val in enumerate(row_values, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = REGULAR_FONT
            cell.fill = row_fill
            cell.border = GRID_BORDER

            # Specific formatting
            if c_idx == 9:  # Price
                cell.number_format = '#,##0 "AED"'
                cell.font = BOLD_FONT
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx == 8:  # Sq Ft
                cell.number_format = '#,##0 "sq ft"'
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx in [6, 7]:  # Beds, Baths
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif c_idx in [1, 3, 5, 10, 12]:  # ID, City, Type, Purpose, Status
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_columns(ws)
    wb.save(output_path)
    print(f"Property workbook created at: {output_path}")

def create_master_combined_workbook(output_path: str):
    wb = openpyxl.Workbook()
    # Sheet 1: Banks
    ws_banks = wb.active
    ws_banks.title = "Bank Mortgage Rate Sheets"

    # Sheet 2: Properties
    ws_props = wb.create_sheet(title="Property Inventory")

    # 1. Fill Banks
    bank_headers = [
        "Product ID", "Bank / Financial Institution", "Finance Type", "Contract / Rate Type",
        "Profit / Interest Rate", "Max LTV (National)", "Max LTV (Expat)", "Min Salary",
        "Max Tenure", "Processing Fee", "Valuation Fee", "Early Settlement Fee", "Version"
    ]
    ws_banks.merge_cells("A1:M1")
    t1 = ws_banks["A1"]
    t1.value = "XOTO Master System Catalog — UAE Bank Mortgage & Home Finance Products"
    t1.font = TITLE_FONT
    ws_banks.row_dimensions[1].height = 28

    ws_banks.row_dimensions[3].height = 24
    for c_idx, h in enumerate(bank_headers, 1):
        cell = ws_banks.cell(row=3, column=c_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = NAVY_HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = GRID_BORDER

    for r_idx, p in enumerate(MortgageRulesGateway._products, 4):
        ws_banks.row_dimensions[r_idx].height = 20
        row_fill = ZEBRA_FILL if r_idx % 2 == 0 else WHITE_FILL
        vals = [
            p.product_id, p.bank_name, p.finance_type.upper(), p.rate_type,
            p.interest_rate / 100.0, p.max_ltv_national / 100.0, p.max_ltv_expat / 100.0,
            p.min_salary_aed, f"{p.max_tenure_years} Years", p.processing_fee_pct / 100.0,
            p.valuation_fee_aed, p.early_settlement_fee_pct / 100.0, p.version
        ]
        for c_idx, val in enumerate(vals, 1):
            cell = ws_banks.cell(row=r_idx, column=c_idx, value=val)
            cell.font = REGULAR_FONT
            cell.fill = row_fill
            cell.border = GRID_BORDER
            if c_idx in [5, 6, 7, 10, 12]:
                cell.number_format = "0.00%"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx in [8, 11]:
                cell.number_format = '#,##0 "AED"'
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx == 3:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = BOLD_FONT
                cell.fill = ISLAMIC_BADGE_FILL if "ISLAMIC" in str(val) else CONV_BADGE_FILL
            elif c_idx in [1, 9, 13]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
    autofit_columns(ws_banks)

    # 2. Fill Properties
    prop_headers = [
        "Property ID", "Property Title", "City", "Community", "Type",
        "Bedrooms", "Bathrooms", "Area (Sq Ft)", "Price (AED)", "Purpose",
        "Developer", "Status", "Amenities", "Listing URL"
    ]
    ws_props.merge_cells("A1:N1")
    t2 = ws_props["A1"]
    t2.value = "XOTO Master System Catalog — UAE Real Estate Inventory"
    t2.font = TITLE_FONT
    ws_props.row_dimensions[1].height = 28

    ws_props.row_dimensions[3].height = 24
    for c_idx, h in enumerate(prop_headers, 1):
        cell = ws_props.cell(row=3, column=c_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = NAVY_HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = GRID_BORDER

    for r_idx, prop in enumerate(PropertyInventoryGateway._inventory, 4):
        ws_props.row_dimensions[r_idx].height = 20
        row_fill = ZEBRA_FILL if r_idx % 2 == 0 else WHITE_FILL
        vals = [
            prop.id, prop.title, prop.city, prop.community, prop.type.capitalize(),
            prop.beds, prop.baths, prop.sq_ft, prop.price, prop.purpose.upper(),
            prop.developer, prop.status.capitalize(), ", ".join(prop.amenities), prop.listing_url
        ]
        for c_idx, val in enumerate(vals, 1):
            cell = ws_props.cell(row=r_idx, column=c_idx, value=val)
            cell.font = REGULAR_FONT
            cell.fill = row_fill
            cell.border = GRID_BORDER
            if c_idx == 9:
                cell.number_format = '#,##0 "AED"'
                cell.font = BOLD_FONT
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx == 8:
                cell.number_format = '#,##0 "sq ft"'
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx in [6, 7]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif c_idx in [1, 3, 5, 10, 12]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
    autofit_columns(ws_props)

    wb.save(output_path)
    print(f"Master combined workbook created at: {output_path}")

def export_csv_catalogs(target_dir: str):
    import csv

    # 1. Properties CSV
    prop_csv = os.path.join(target_dir, "uae_property_listings.csv")
    prop_headers = [
        "Property ID", "Title", "City", "Community", "Type",
        "Beds", "Baths", "Sq Ft", "Price (AED)", "Purpose",
        "Developer", "Status", "Amenities", "Listing URL"
    ]
    with open(prop_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(prop_headers)
        for p in PropertyInventoryGateway._inventory:
            writer.writerow([
                p.id, p.title, p.city, p.community, p.type,
                p.beds, p.baths, p.sq_ft, p.price, p.purpose,
                p.developer, p.status, "; ".join(p.amenities), p.listing_url
            ])
    print(f"Properties CSV created at: {prop_csv}")

    # 2. Bank Mortgage CSV
    bank_csv = os.path.join(target_dir, "uae_bank_mortgage_products.csv")
    bank_headers = [
        "Product ID", "Bank Name", "Finance Type", "Rate Type",
        "Profit / Interest Rate", "Max LTV National", "Max LTV Expat",
        "Min Monthly Salary (AED)", "Max Tenure (Years)", "Processing Fee",
        "Valuation Fee (AED)", "Early Settlement Fee", "Version"
    ]
    with open(bank_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(bank_headers)
        for b in MortgageRulesGateway._products:
            writer.writerow([
                b.product_id, b.bank_name, b.finance_type.upper(), b.rate_type,
                f"{b.interest_rate:.2f}%", f"{int(b.max_ltv_national)}%",
                f"{int(b.max_ltv_expat)}%", b.min_salary_aed, b.max_tenure_years,
                f"{b.processing_fee_pct:.2f}%", b.valuation_fee_aed,
                f"{b.early_settlement_fee_pct:.2f}%", b.version
            ])
    print(f"Bank products CSV created at: {bank_csv}")

if __name__ == "__main__":
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    os.makedirs(target_dir, exist_ok=True)
    
    bank_file = os.path.join(target_dir, "uae_bank_mortgage_products.xlsx")
    prop_file = os.path.join(target_dir, "uae_property_listings.xlsx")
    master_file = os.path.join(target_dir, "XOTO_System_Catalog_Master.xlsx")

    create_bank_workbook(bank_file)
    create_properties_workbook(prop_file)
    create_master_combined_workbook(master_file)
    export_csv_catalogs(target_dir)
