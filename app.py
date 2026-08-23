import streamlit as st
import pandas as pd
import os
import glob
import shutil
import tempfile
from extractor import parse_invoice_pdf
from excel_exporter import export_to_excel

# Page configuration
st.set_page_config(
    page_title="FinExtract Pro - Intelligent Invoice Parser",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Teal theme & styling
st.markdown("""
<style>
    /* Main Layout Accent */
    .stApp {
        background-color: #FAFAFA;
    }
    
    /* Headers & Text colors */
    h1, h2, h3 {
        color: #004D40 !important;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Streamlit sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #004D40;
        color: #FFFFFF;
    }
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #FFFFFF !important;
    }
    
    /* Metrics block */
    .metric-container {
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border-left: 5px solid #008B9B;
        margin-bottom: 20px;
    }
    
    .metric-title {
        font-size: 14px;
        color: #666666;
        text-transform: uppercase;
        font-weight: bold;
    }
    
    .metric-value {
        font-size: 24px;
        color: #004D40;
        font-weight: bold;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar UI
with st.sidebar:
    st.image("https://img.icons8.com/color/96/microsoft-excel-2019--v1.png", width=70)
    st.markdown("# FinExtract Pro")
    st.markdown("### Smart Invoice & Annexure Auditor")
    st.write("---")
    
    st.markdown("#### 📖 How to use the Tool:")
    st.markdown("""
    * **Folder Mode**: Paste the path to a folder on your computer containing all PDFs (perfect for 1,000+ files).
    * **Upload Mode**: Drag & drop files for quick audits of small batches.
    * **Review**: Double-click any cell to adjust values in the preview table.
    * **Export**: Click the **Download Excel Report** button.
    """)
    
    st.write("---")
    st.markdown("#### 💻 Enterprise Grade")
    st.info("Designed for high-throughput batch auditing. Processes thousands of multi-page invoices with low memory overhead.")

# Header Section
st.title("📊 FinExtract Pro: Invoice Parser")
st.write("Extract invoice details and detailed annexure line items into styled corporate Excel sheets instantly.")
st.write("---")

# Setup Tabs for Folder mode vs Upload mode
tab1, tab2 = st.tabs(["📁 Folder Batch Processing (Recommended for 1000+ files)", "📤 Drag & Drop Upload (For Small Batches)"])

all_extracted_rows = []
skipped_files = []

with tab1:
    st.subheader("Process a Local Folder")
    st.write("Enter the absolute path to the folder on your computer where your PDFs are stored.")
    
    folder_path = st.text_input(
        "Folder Path", 
        value="", 
        placeholder="e.g. C:\\Users\\KhandelwalLakshya(KC\\Documents\\JTB_Invoices",
        help="Paste the path to your Windows folder containing the PDFs."
    )
    
    process_folder_button = st.button("🚀 Process Folder", use_container_width=True)
    
    if process_folder_button and folder_path:
        if not os.path.exists(folder_path):
            st.error(f"The folder path `{folder_path}` does not exist. Please check the path and try again.")
        else:
            pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
            num_files = len(pdf_files)
            
            if num_files == 0:
                st.warning(f"No PDF files found in `{folder_path}`.")
            else:
                st.info(f"Found {num_files} PDF files to process. Starting batch conversion...")
                
                # Setup UI progress indicators
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process sequentially to prevent memory overload
                for idx, pdf_file in enumerate(pdf_files):
                    file_name = os.path.basename(pdf_file)
                    status_text.text(f"Processing ({idx+1}/{num_files}): {file_name}")
                    
                    try:
                        rows = parse_invoice_pdf(pdf_file)
                        if rows:
                            all_extracted_rows.extend(rows)
                        else:
                            skipped_files.append((file_name, "No JTB invoice or annexure format detected."))
                    except Exception as e:
                        skipped_files.append((file_name, f"Error: {str(e)}"))
                        
                    progress_bar.progress((idx + 1) / num_files)
                    
                status_text.text(f"✅ Processed {num_files} files successfully!")
                st.balloons()

with tab2:
    st.subheader("Upload PDF Files")
    uploaded_files = st.file_uploader(
        "Choose PDF files...", 
        type=["pdf"], 
        accept_multiple_files=True,
        key="file_uploader"
    )
    
    if uploaded_files:
        num_files = len(uploaded_files)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, file in enumerate(uploaded_files):
            status_text.text(f"Processing ({idx+1}/{num_files}): {file.name}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(file, tmp)
                tmp_path = tmp.name
                
            try:
                rows = parse_invoice_pdf(tmp_path)
                if rows:
                    all_extracted_rows.extend(rows)
                else:
                    skipped_files.append((file.name, "No JTB invoice or annexure format detected."))
            except Exception as e:
                skipped_files.append((file.name, f"Error: {str(e)}"))
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
            progress_bar.progress((idx + 1) / num_files)
            
        status_text.text(f"✅ Uploaded and processed {num_files} files successfully!")

# Display extracted data and metrics
if all_extracted_rows:
    df_display = pd.DataFrame(all_extracted_rows)
    
    # Calculate totals
    total_taxable = df_display["Taxable Amount"].sum()
    total_cgst = df_display["CGST Amount"].sum()
    total_sgst = df_display["SGST Amount"].sum()
    total_igst = df_display["IGST Amount"].sum()
    total_gst = total_cgst + total_sgst + total_igst
    total_gross = df_display["Total invoice amount"].sum()
    unique_invoices = df_display["Invoice No."].nunique()
    
    # Metrics
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-title">Invoices Processed</div>
            <div class="metric-value">{unique_invoices} Invoice(s)</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-title">Total Taxable Value</div>
            <div class="metric-value">₹ {total_taxable:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-title">Total GST Amount</div>
            <div class="metric-value">₹ {total_gst:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-title">Total Invoice Amount</div>
            <div class="metric-value">₹ {total_gross:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("📝 Live Audit & Review Data Editor")
    st.write("Double-click any cell to edit the text or numbers directly in your browser. Changes are kept in your Excel export.")
    
    # Data Editor
    edited_df = st.data_editor(
        df_display,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Taxable Amount": st.column_config.NumberColumn(format="₹ %.2f"),
            "IGST Amount": st.column_config.NumberColumn(format="₹ %.2f"),
            "CGST Amount": st.column_config.NumberColumn(format="₹ %.2f"),
            "SGST Amount": st.column_config.NumberColumn(format="₹ %.2f"),
            "Total invoice amount": st.column_config.NumberColumn(format="₹ %.2f"),
            "Invoice Date": st.column_config.TextColumn(),
            "Invoice No.": st.column_config.TextColumn(),
        }
    )
    
    # Export Options
    st.write("---")
    st.subheader("📥 Export Finalized Report")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_xlsx:
        export_path = tmp_xlsx.name
        
    try:
        edited_rows = edited_df.to_dict('records')
        export_to_excel(edited_rows, export_path)
        
        with open(export_path, "rb") as f:
            xlsx_data = f.read()
            
        st.download_button(
            label="📥 Download Excel Register (.xlsx)",
            data=xlsx_data,
            file_name="Invoice_Register_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Failed to generate Excel file: {str(e)}")
    finally:
        if os.path.exists(export_path):
            os.remove(export_path)

# Display skipped files/warnings
if skipped_files:
    st.warning("Some files were skipped or encountered warnings during processing:")
    for name, reason in skipped_files:
        st.write(f"⚠️ **{name}**: {reason}")
