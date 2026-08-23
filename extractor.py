import re
import os
import pdfplumber
from pypdf import PdfReader

def clean_amount(val_str):
    """Cleans currency strings, removes commas, spaces, and currency symbols."""
    if not val_str:
        return 0.0
    # Remove currency symbol, commas, and strip whitespace
    cleaned = re.sub(r"[^\d\.\-]", "", val_str)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def clean_gst_rate(rate_str):
    """Converts a rate string like '9%' or '9.0%' or '18' to a clean float/integer."""
    if not rate_str:
        return 0.0
    cleaned = re.sub(r"[^\d\.]", "", rate_str)
    try:
        val = float(cleaned)
        # Convert float like 9.0 to 9 for clean display
        return int(val) if val.is_integer() else val
    except ValueError:
        return 0.0

def extract_invoice_metadata(pdf_path):
    """
    Scans the PDF to locate the main Invoice page and extracts metadata.
    Does not assume page position.
    """
    metadata = {
        "vendor_name": "JTB India Private Limited", # Default if not found
        "vendor_gstin": "",
        "buyer_name": "MSD Pharmaceuticals Private Limited", # Default if not found
        "buyer_gstin": "",
        "invoice_no": "",
        "invoice_date": "",
        "invoice_type": "Tax Invoice",
        "tax_structure": {"cgst": 0.0, "sgst": 0.0, "igst": 0.0}
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
                
            # Detect if this is the main Invoice page
            # Main invoice page always has "Tax Invoice", "Credit Note", or "Debit Note"
            # and keywords like "Invoice No" and JTB header markers
            is_invoice_page = False
            
            # 1. Detect Invoice Type & Page Validity
            type_match = re.search(r"\b(Tax Invoice|Credit Note|Debit Note)\b", text, re.IGNORECASE)
            if type_match:
                # Extra check to ensure it's not a supporting document vendor invoice
                if "JTB" in text:
                    is_invoice_page = True
                    metadata["invoice_type"] = type_match.group(1).title()
            
            # Fallback check if JTB is mentioned along with invoice structure
            if not is_invoice_page and "JTB" in text and ("Invoice No" in text or "Invoice No." in text):
                is_invoice_page = True
            
            if is_invoice_page:
                # 2. Extract Invoice No
                inv_match = re.search(r"Invoice\s*No\.?\s*:\s*([A-Z0-9]+)", text, re.IGNORECASE)
                if inv_match:
                    metadata["invoice_no"] = inv_match.group(1).strip()
                else:
                    # Alternative pattern
                    inv_match = re.search(r"Invoice\s*Ref\s*No\.?\s*-\s*([A-Z0-9]+)", text, re.IGNORECASE)
                    if inv_match:
                        metadata["invoice_no"] = inv_match.group(1).strip()
                
                # 3. Extract Invoice Date
                date_match = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
                if date_match:
                    metadata["invoice_date"] = date_match.group(1).strip()
                else:
                    # Try other formats e.g. DD-MM-YYYY
                    date_match = re.search(r"Date\s*:\s*(\d{2}-\d{2}-\d{4})", text, re.IGNORECASE)
                    if date_match:
                        metadata["invoice_date"] = date_match.group(1).strip()
                
                # 4. Extract Vendor GSTIN
                # First find Vendor Name and its GSTIN block
                # JTB's GST is typically near the top: "GST No. : 29AACCJ6982F1Z6"
                vendor_gst_match = re.search(r"GST\s*No\.?\s*:\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})", text, re.IGNORECASE)
                if vendor_gst_match:
                    metadata["vendor_gstin"] = vendor_gst_match.group(1).strip()
                
                # 5. Extract Buyer GSTIN
                # MSD's GSTIN is typically labeled as "GST No" under "Bill To"
                # e.g., "GST No : 29AAECM1106C1Z1"
                buyer_gst_matches = re.findall(r"GST\s*No\s*:\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})", text, re.IGNORECASE)
                if buyer_gst_matches:
                    # The second one is usually the buyer if both supplier and buyer are listed
                    if len(buyer_gst_matches) > 1:
                        metadata["buyer_gstin"] = buyer_gst_matches[1].strip()
                        # If vendor wasn't captured, use first one
                        if not metadata["vendor_gstin"]:
                            metadata["vendor_gstin"] = buyer_gst_matches[0].strip()
                    else:
                        metadata["buyer_gstin"] = buyer_gst_matches[0].strip()
                
                # If buyer gstin is still empty, scan the text around "Bill To"
                if not metadata["buyer_gstin"]:
                    bill_to_section = re.search(r"Bill\s*To\s*:([\s\S]+?)Invoice\s*No", text, re.IGNORECASE)
                    if bill_to_section:
                        section_text = bill_to_section.group(1)
                        gst_match = re.search(r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})", section_text)
                        if gst_match:
                            metadata["buyer_gstin"] = gst_match.group(1).strip()

                # 6. Extract Tax Rates from Tax Table
                # S.No HSN/TCS Code Taxable Amount Tax Rate CGST SGST IGST Tax Total
                # 1 998596 28,180.00 18% 2,536.20 2,536.20 0.00 5,072.40
                tax_table_match = re.search(r"CGST\s+SGST\s+IGST\s+Tax\s+Total[\s\S]+?(\d+)\s+(\d+)\s+([\d,\.]+)\s+(\d+%)\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)", text, re.IGNORECASE)
                if tax_table_match:
                    cgst_val = clean_amount(tax_table_match.group(5))
                    sgst_val = clean_amount(tax_table_match.group(6))
                    igst_val = clean_amount(tax_table_match.group(7))
                    tax_rate_str = tax_table_match.group(4) # e.g. "18%"
                    total_rate = clean_gst_rate(tax_rate_str)
                    
                    if igst_val > 0:
                        metadata["tax_structure"] = {"cgst": 0.0, "sgst": 0.0, "igst": total_rate}
                    else:
                        metadata["tax_structure"] = {"cgst": total_rate / 2, "sgst": total_rate / 2, "igst": 0.0}
                else:
                    # Let's inspect the tax breakdown structure in GST rate column or totals table
                    # Fallback check for SGST/CGST/IGST text
                    if "IGST" in text and not ("CGST" in text or "SGST" in text):
                        # Inter-state
                        metadata["tax_structure"] = {"cgst": 0.0, "sgst": 0.0, "igst": 18.0}
                    else:
                        # Intra-state default
                        metadata["tax_structure"] = {"cgst": 9.0, "sgst": 9.0, "igst": 0.0}
                
                # Once we extract successfully from the main invoice page, we break
                break
                
    return metadata

def extract_invoice_annexure_lines(pdf_path, invoice_no=""):
    """
    Scans the PDF to locate the Invoice Annexure page and extracts line items.
    Supports table-based extraction for high reliability with multi-line wrapped cells.
    """
    line_items = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Check if this page is the Annexure and contains "JTB"
            if "INVOICE ANNEXURE" in text and "JTB" in text:
                # If invoice_no is provided, check if it matches to prevent cross-document leakage
                if invoice_no:
                    ref_match = re.search(r"Invoice\s*Ref\s*No\.?\s*-\s*([A-Z0-9]+)", text, re.IGNORECASE)
                    if ref_match and ref_match.group(1).strip() != invoice_no:
                        continue
                
                # 1. Try table-based extraction first (highly robust for new and old JTB formats)
                tables = page.extract_tables()
                parsed_via_table = False
                
                for table in tables:
                    header_row_idx = -1
                    for r_idx, row in enumerate(table):
                        cleaned_row = [str(cell).strip().lower() if cell else "" for cell in row]
                        if "description" in cleaned_row and "amount" in cleaned_row:
                            header_row_idx = r_idx
                            break
                    
                    if header_row_idx != -1:
                        parsed_via_table = True
                        for r_idx in range(header_row_idx + 1, len(table)):
                            row = table[r_idx]
                            if not row or len(row) < 2:
                                continue
                            
                            desc = str(row[0] or "").strip()
                            amount_val = str(row[-1] or "").strip()
                            
                            if not desc:
                                continue
                                
                            # Split description by newline and take the first line to handle wraps
                            # e.g., 'Management Fees\nHSN/SAC Code - 998596' -> 'Management Fees'
                            desc_lines = [l.strip() for l in desc.split('\n') if l.strip()]
                            if not desc_lines:
                                continue
                            
                            actual_desc = desc_lines[0]
                            
                            # Skip totals, subtotals, or tax headers
                            if actual_desc.lower() in ["sub total", "subtotal", "grand total", "balance receivable", "taxable value", "total"] or any(x in actual_desc.lower() for x in ["cgst", "sgst", "igst"]):
                                continue
                                
                            # Skip HSN code rows if they appear as standalone rows
                            if "hsn/sac code" in actual_desc.lower() or "hsn/tcs code" in actual_desc.lower():
                                continue
                            
                            if not amount_val or amount_val == "-":
                                continue
                            
                            # Clean amount string by removing spaces (e.g. "3 7,249" -> "37249")
                            cleaned_amt_str = re.sub(r"\s+", "", amount_val)
                            amount = clean_amount(cleaned_amt_str)
                            
                            if amount > 0:
                                line_items.append({
                                    "description": actual_desc,
                                    "taxable_amount": amount
                                })
                        break # Successfully processed JTB table
                
                if parsed_via_table:
                    break
                
                # 2. Text-based fallback (original regex) if table extraction failed
                lines = text.split('\n')
                start_parsing = False
                for line in lines:
                    if "Description" in line and ("Amount" in line or "Unit Price" in line):
                        start_parsing = True
                        continue
                    if "Sub Total" in line or "SubTotal" in line:
                        start_parsing = False
                        break
                    if start_parsing:
                        row_match = re.search(r"^(.*?)\s+₹?\s*([\d,]+\.?\d*)\s+(\d+)\s+₹?\s*([\d,]+\.?\d*)", line.strip())
                        if row_match:
                            desc = row_match.group(1).strip()
                            amount = clean_amount(row_match.group(4))
                            line_items.append({
                                "description": desc,
                                "taxable_amount": amount
                            })
                break
                
    return line_items

def extract_main_invoice_lines_as_fallback(pdf_path):
    """
    Parses the main invoice page (page 1) to extract service rows when no Annexure page exists.
    Extracts the 'Description' and 'Amount' values directly from the main items table.
    """
    line_items = []
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()
        for table in tables:
            header_row_idx = -1
            desc_col_idx = -1
            amt_col_idx = -1
            
            for r_idx, row in enumerate(table):
                cleaned_row = [str(cell).strip().lower() if cell else "" for cell in row]
                if "item" in cleaned_row and "description" in cleaned_row and "gross amt" in cleaned_row:
                    header_row_idx = r_idx
                    # Find column indices dynamically
                    desc_col_idx = cleaned_row.index("description")
                    # 'amount' column index is preferred, otherwise fallback to rate/gross
                    if "amount" in cleaned_row:
                        amt_col_idx = cleaned_row.index("amount")
                    else:
                        amt_col_idx = cleaned_row.index("gross amt") - 2 # usually rate or amount is adjacent
                    break
            
            if header_row_idx != -1:
                # Parse rows below the header row
                for r_idx in range(header_row_idx + 1, len(table)):
                    row = table[r_idx]
                    if not row or len(row) < max(desc_col_idx, amt_col_idx) + 1:
                        continue
                    
                    item_type = str(row[0] or "").strip()
                    desc = str(row[desc_col_idx] or "").strip()
                    amt_str = str(row[amt_col_idx] or "").strip()
                    
                    # Stop parsing once we hit the "Total:" row
                    if item_type.lower().startswith("total"):
                        break
                    
                    if not desc or not amt_str:
                        continue
                    
                    # Flatten the description text by replacing newlines with spaces
                    clean_desc = " ".join([l.strip() for l in desc.split("\n") if l.strip()])
                    
                    amount = clean_amount(amt_str)
                    if amount > 0:
                        line_items.append({
                            "description": clean_desc,
                            "taxable_amount": amount
                        })
                break
    return line_items

def parse_invoice_pdf(pdf_path):
    """
    Parses a single PDF package file.
    Returns metadata and list of row items ready for Excel.
    """
    file_name = os.path.basename(pdf_path)
    
    # 1. Extract Main Invoice details
    meta = extract_invoice_metadata(pdf_path)
    
    # 2. Extract Annexure details
    items = extract_invoice_annexure_lines(pdf_path, meta["invoice_no"])
    
    # Fallback: if no Annexure was found, extract lines from the main invoice page instead
    if not items:
        items = extract_main_invoice_lines_as_fallback(pdf_path)
            
    # 3. Calculate GST and Totals for each line item
    final_rows = []
    
    cgst_rate = meta["tax_structure"]["cgst"]
    sgst_rate = meta["tax_structure"]["sgst"]
    igst_rate = meta["tax_structure"]["igst"]
    
    for item in items:
        taxable = item["taxable_amount"]
        
        # Calculations (rounded to 2 decimal places)
        cgst_amt = round(taxable * (cgst_rate / 100), 2)
        sgst_amt = round(taxable * (sgst_rate / 100), 2)
        igst_amt = round(taxable * (igst_rate / 100), 2)
        total_amt = round(taxable + cgst_amt + sgst_amt + igst_amt, 2)
        
        final_rows.append({
            "File name": file_name,
            "Vendor Name": meta["vendor_name"],
            "Vendor GSTIN": meta["vendor_gstin"],
            "Buyer Name": meta["buyer_name"],
            "Buyer GSTIN": meta["buyer_gstin"],
            "Nature of Service": item["description"],
            "Invoice Type": meta["invoice_type"],
            "Invoice No.": meta["invoice_no"],
            "Invoice Date": meta["invoice_date"],
            "Taxable Amount": taxable,
            "IGST rate": igst_rate,
            "CGST rate": cgst_rate,
            "SGST rate": sgst_rate,
            "IGST Amount": igst_amt,
            "CGST Amount": cgst_amt,
            "SGST Amount": sgst_amt,
            "Total invoice amount": total_amt
        })
        
    return final_rows
