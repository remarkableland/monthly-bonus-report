import streamlit as st
import pandas as pd
from datetime import datetime
import io

st.set_page_config(
    page_title="Bonus Schedule Generator",
    page_icon="💰",
    layout="wide"
)

st.title("💰 Bonus Schedule Generator")
st.markdown("Generate bonus schedules from Close.com export data")

# Configuration Section
st.sidebar.header("Configuration")

# Month/Period Selection
month_ending = st.sidebar.date_input(
    "Month Ending Date",
    value=datetime.now().replace(day=1) if datetime.now().day == 1 else datetime.now()
)

# Team Member Names (for signatures)
st.sidebar.subheader("Team Members")
team_members = st.sidebar.text_area(
    "Enter team member names (one per line)",
    value="BF\nLF\nIM\nRD",
    height=150
)
team_list = [name.strip() for name in team_members.split('\n') if name.strip()]

# Prior Adjustment
prior_adjustment = st.sidebar.number_input(
    "Prior Adjustment Amount", 
    value=0.00,
    format="%.2f",
    help="Adjustments from previous bonus schedules"
)

# File Upload
uploaded_file = st.file_uploader(
    "Upload Close.com Export CSV", 
    type=['csv'],
    help="Upload your 'Selling_Land_leads' export from Close.com"
)

def extract_county_from_display_name(display_name):
    """Extract county from display name like 'TX Hidalgo Mujica...'"""
    if pd.isna(display_name):
        return "Unknown"
    parts = str(display_name).split()
    if len(parts) >= 2:
        return parts[1]  # Second word is typically the county
    return "Unknown"

def extract_grantor_from_display_name(display_name):
    """Extract grantor name from display name like 'OK McIntosh Engebretson...'"""
    if pd.isna(display_name):
        return "Unknown"
    parts = str(display_name).split()
    if len(parts) >= 3:
        return parts[2]  # Third word is typically the grantor
    return "Unknown"

def find_column(df, candidates):
    """Find the first matching column name from a list of candidates (case-insensitive)"""
    df_cols_lower = {col.lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
        if candidate.lower() in df_cols_lower:
            return df_cols_lower[candidate.lower()]
    return None

def process_close_export(df, month_ending_date):
    """Process Close.com export and extract relevant fields"""

    # Map expected field names to possible column name variants
    col_map = {}
    field_candidates = {
        'primary_opportunity_date_won': ['primary_opportunity_date_won', 'Opportunity Date Won'],
        'primary_opportunity_status_label': ['primary_opportunity_status_label', 'Opportunity Status Label', 'primary_opportunity_status'],
        'custom.Asset_Date_Sold': ['custom.Asset_Date_Sold', 'Asset Date Sold', 'Asset_Date_Sold', 'custom.Asset Date Sold'],
        'custom.All_State': ['custom.All_State', 'All State', 'All_State', 'custom.All State'],
        'custom.All_APN': ['custom.All_APN', 'All APN', 'All_APN', 'custom.All APN'],
        'custom.Asset_Gross_Sales_Price': ['custom.Asset_Gross_Amount_to_Seller', 'Asset_Gross_Amount_to_Seller', 'custom.Gross Amount to Seller', 'Gross Amount to Seller', 'custom.Gross_Amount_to_Seller', 'custom.Asset_Gross_Sales_Price', 'Asset Gross Sales Price', 'Asset_Gross_Sales_Price', 'custom.Asset Gross Sales Price'],
        'custom.Asset_Closing_Costs': ['custom.Asset_Closing_Costs', 'Asset Closing Costs', 'Asset_Closing_Costs', 'custom.Asset Closing Costs'],
        'custom.Asset_Cost_Basis': ['custom.Asset_Cost_Basis', 'Asset Cost Basis', 'Asset_Cost_Basis', 'custom.Asset Cost Basis'],
        'display_name': ['display_name', 'Display Name'],
    }

    missing_cols = []
    for key, candidates in field_candidates.items():
        found = find_column(df, candidates)
        if found:
            col_map[key] = found
        else:
            missing_cols.append(key)

    if missing_cols:
        raise KeyError(f"Could not find columns: {', '.join(missing_cols)}. Available columns: {', '.join(df.columns.tolist())}")

    # Filter for sold properties in the specified month
    df['primary_opportunity_date_won'] = pd.to_datetime(df[col_map['primary_opportunity_date_won']], errors='coerce')
    
    # Filter by month and year
    month_start = pd.Timestamp(month_ending_date.replace(day=1))
    if month_ending_date.month == 12:
        month_end = pd.Timestamp(month_ending_date.replace(year=month_ending_date.year + 1, month=1, day=1))
    else:
        month_end = pd.Timestamp(month_ending_date.replace(month=month_ending_date.month + 1, day=1))
    
    df_filtered = df[
        (df['primary_opportunity_date_won'] >= month_start) &
        (df['primary_opportunity_date_won'] < month_end) &
        (df[col_map['primary_opportunity_status_label']] == 'Sold')
    ].copy()
    
    if len(df_filtered) == 0:
        return None
    
    # Extract required fields
    results = []
    for _, row in df_filtered.iterrows():
        # Extract data from available fields using mapped column names
        date_sold_val = row[col_map['custom.Asset_Date_Sold']]
        funding_date = pd.to_datetime(date_sold_val).strftime('%m/%d/%y') if pd.notna(date_sold_val) else ''
        funding_date_sort = pd.to_datetime(date_sold_val) if pd.notna(date_sold_val) else pd.Timestamp('1900-01-01')
        state = row[col_map['custom.All_State']] if pd.notna(row[col_map['custom.All_State']]) else ''
        county = extract_county_from_display_name(row[col_map['display_name']])
        grantor = extract_grantor_from_display_name(row[col_map['display_name']])
        apn = row[col_map['custom.All_APN']] if pd.notna(row[col_map['custom.All_APN']]) else ''

        # Financial data
        gsp_val = row[col_map['custom.Asset_Gross_Sales_Price']]
        cc_val = row[col_map['custom.Asset_Closing_Costs']]
        cb_val = row[col_map['custom.Asset_Cost_Basis']]
        contract_price = float(gsp_val) if pd.notna(gsp_val) else 0.0
        closing_costs = float(cc_val) if pd.notna(cc_val) else 0.0
        cost_basis = float(cb_val) if pd.notna(cb_val) else 0.0
        
        # Calculate derived values (no MLS cost added)
        reductions = closing_costs
        cash_to_seller = contract_price - reductions
        asset_cost = cost_basis  # No MLS cost adjustment
        gross_profit = cash_to_seller - asset_cost
        
        results.append({
            'Funding Date': funding_date,
            'Funding Date Sort': funding_date_sort,
            'State': state,
            'County': county,
            'Grantor': grantor,
            'APN': apn,
            'Gross Sales Price': contract_price,
            'Closing Costs': reductions,
            'Cash to Seller': cash_to_seller,
            'Asset Cost': asset_cost,
            'Gross Profit': gross_profit
        })
    
    df_result = pd.DataFrame(results)
    
    # Sort by date ascending
    df_result = df_result.sort_values('Funding Date Sort', ascending=True)
    
    # Remove the sort column before returning
    df_result = df_result.drop('Funding Date Sort', axis=1)
    
    return df_result

def format_currency(value):
    """Format number as currency"""
    return f"${value:,.2f}"

def create_bonus_schedule_dataframe(processed_df):
    """Create formatted bonus schedule dataframe"""
    # Create a copy to avoid modifying original
    display_df = processed_df.copy()
    
    # Format currency columns - handle both numeric and string values
    currency_columns = ['Gross Sales Price', 'Closing Costs', 'Cash to Seller', 'Asset Cost', 'Gross Profit']
    for col in currency_columns:
        display_df[col] = display_df[col].apply(lambda x: format_currency(float(x)) if pd.notna(x) else "$0.00")
    
    return display_df

def export_to_excel(processed_df, month_ending_date, subtotal, prior_adj, total):
    """Export bonus schedule to Excel with formatting"""
    output = io.BytesIO()
    
    # Create Excel writer
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Write main data
        processed_df.to_excel(writer, sheet_name='Bonus Schedule', index=False, startrow=2)
        
        # Get workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['Bonus Schedule']
        
        # Add header
        worksheet['A1'] = f'Remarkable Land® Bonus Schedule'
        worksheet['A2'] = f'Month Ending: {month_ending_date.strftime("%m/%d/%Y")}'
        
        # Add totals
        last_row = len(processed_df) + 4
        worksheet[f'I{last_row}'] = 'SUBTOTAL'
        worksheet[f'J{last_row}'] = subtotal
        
        worksheet[f'I{last_row+1}'] = 'PRIOR ADJUSTMENT'
        worksheet[f'J{last_row+1}'] = prior_adj
        
        worksheet[f'I{last_row+2}'] = 'TOTAL'
        worksheet[f'J{last_row+2}'] = total
        
        # Bold the header
        from openpyxl.styles import Font, Alignment
        worksheet['A1'].font = Font(bold=True, size=14)
        worksheet['A2'].font = Font(bold=True)
        
        # Bold totals
        for row_num in [last_row, last_row+1, last_row+2]:
            worksheet[f'I{row_num}'].font = Font(bold=True)
            worksheet[f'J{row_num}'].font = Font(bold=True)
        
        # Adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    return output

def export_to_pdf(processed_df, month_ending_date, subtotal, prior_adj, total, team_members):
    """Export bonus schedule to PDF with signature lines"""
    try:
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        return None
    
    buffer = io.BytesIO()
    
    # Create PDF in LANDSCAPE orientation with narrower margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.3*inch,
        leftMargin=0.3*inch,
        topMargin=0.3*inch,
        bottomMargin=0.3*inch
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Subtitle style
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    # Add title
    elements.append(Paragraph("Remarkable Land® Bonus Schedule", title_style))
    elements.append(Paragraph(f"Month Ending: {month_ending_date.strftime('%B %d, %Y')}", subtitle_style))
    
    # Calculate column totals from numeric data
    total_gross_sales = processed_df['Gross Sales Price'].sum()
    total_closing_costs = processed_df['Closing Costs'].sum()
    total_cash_to_seller = processed_df['Cash to Seller'].sum()
    total_asset_cost = processed_df['Asset Cost'].sum()
    total_gross_profit = processed_df['Gross Profit'].sum()
    
    # Prepare table data
    table_data = []
    
    # Header row - use Paragraph objects for wrapping
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.whitesmoke,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=10
    )
    
    headers = [Paragraph(str(col), header_style) for col in processed_df.columns]
    table_data.append(headers)
    
    # Data rows - format currency for display
    for _, row in processed_df.iterrows():
        formatted_row = [
            row['Funding Date'],
            row['State'],
            row['County'],
            row['Grantor'],
            row['APN'],
            format_currency(row['Gross Sales Price']),
            format_currency(row['Closing Costs']),
            format_currency(row['Cash to Seller']),
            format_currency(row['Asset Cost']),
            format_currency(row['Gross Profit'])
        ]
        table_data.append(formatted_row)
    
    # Add column totals row
    totals_row = [
        'TOTALS',
        '',
        '',
        '',
        '',
        format_currency(total_gross_sales),
        format_currency(total_closing_costs),
        format_currency(total_cash_to_seller),
        format_currency(total_asset_cost),
        format_currency(total_gross_profit)
    ]
    table_data.append(totals_row)
    
    # Add empty row for spacing
    table_data.append([''] * len(headers))
    
    # Add summary totals rows
    empty_cols = [''] * (len(headers) - 2)
    table_data.append(empty_cols + ['SUBTOTAL:', subtotal])
    table_data.append(empty_cols + ['PRIOR ADJUSTMENT:', prior_adj])
    table_data.append(empty_cols + ['TOTAL:', total])
    table_data.append(empty_cols + ['Properties Sold:', str(len(processed_df))])
    
    # Create table with adjusted column widths for landscape
    col_widths = [
        0.75*inch,  # Funding Date
        0.5*inch,   # State
        0.85*inch,  # County
        1.0*inch,   # Grantor
        2.0*inch,   # APN
        1.15*inch,  # Gross Sales Price
        0.8*inch,   # Closing Costs
        1.15*inch,  # Cash to Seller
        0.95*inch,  # Asset Cost
        0.95*inch   # Gross Profit
    ]
    
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Calculate row indices for styling
    data_end_row = len(processed_df) + 1  # +1 for header row
    totals_row_idx = data_end_row  # Column totals row
    
    # Table style
    table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, totals_row_idx-1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, totals_row_idx-1), 8),
        ('ALIGN', (0, 1), (4, totals_row_idx-1), 'LEFT'),
        ('ALIGN', (5, 1), (-1, totals_row_idx-1), 'RIGHT'),
        ('GRID', (0, 0), (-1, totals_row_idx), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, totals_row_idx-1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, totals_row_idx-1), 4),
        
        # Alternate row colors (data rows only)
        ('ROWBACKGROUNDS', (0, 1), (-1, totals_row_idx-1), [colors.white, colors.HexColor('#f0f0f0')]),
        
        # Column totals row styling
        ('FONTNAME', (0, totals_row_idx), (-1, totals_row_idx), 'Helvetica-Bold'),
        ('FONTSIZE', (0, totals_row_idx), (-1, totals_row_idx), 9),
        ('ALIGN', (0, totals_row_idx), (-1, totals_row_idx), 'RIGHT'),
        ('LINEABOVE', (0, totals_row_idx), (-1, totals_row_idx), 1.5, colors.black),
        ('BACKGROUND', (0, totals_row_idx), (-1, totals_row_idx), colors.HexColor('#e8e8e8')),
        
        # Summary totals rows (bold and right-aligned)
        ('FONTNAME', (0, totals_row_idx+2), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, totals_row_idx+2), (-1, -1), 10),
        ('ALIGN', (0, totals_row_idx+2), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, totals_row_idx+2), (-1, totals_row_idx+2), 1.5, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Notes section
    notes_style = ParagraphStyle(
        'Notes',
        parent=styles['Normal'],
        fontSize=8,
        leftIndent=0.2*inch,
        spaceAfter=4
    )
    
    notes_title_style = ParagraphStyle(
        'NotesTitle',
        parent=styles['Heading3'],
        fontSize=10,
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )
    
    elements.append(Paragraph("Notes:", notes_title_style))
    elements.append(Paragraph(
        "<b>Funding Date:</b> Date funds were available for withdrawal from our account. "
        "\"Pending\" funds are not available for withdrawal. Accounting will confirm funding.",
        notes_style
    ))
    elements.append(Paragraph(
        "<b>Reconciliation:</b> All data is subject to a post-payment audit and reconciliation. "
        "Future Bonuses will be adjusted accordingly, as required.",
        notes_style
    ))
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Signature section
    sig_title_style = ParagraphStyle(
        'SigTitle',
        parent=styles['Heading3'],
        fontSize=11,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    elements.append(Paragraph("Signatures:", sig_title_style))
    
    # Create signature table - 2 signatures per row for landscape
    if team_members and len(team_members) > 0:
        num_rows = (len(team_members) + 1) // 2
        
        sig_data = []
        for i in range(num_rows):
            row = []
            
            # First signature in row
            if i * 2 < len(team_members):
                name = team_members[i * 2]
                row.append(f"{name}")
                row.append("_" * 35)
            else:
                row.append("")
                row.append("")
            
            # Add spacing column
            row.append("    ")
            
            # Second signature in row
            if i * 2 + 1 < len(team_members):
                name = team_members[i * 2 + 1]
                row.append(f"{name}")
                row.append("_" * 35)
            else:
                row.append("")
                row.append("")
            
            sig_data.append(row)
        
        sig_table = Table(sig_data, colWidths=[1.8*inch, 2.5*inch, 0.4*inch, 1.8*inch, 2.5*inch])
        sig_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),
            ('ALIGN', (4, 0), (4, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(sig_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Main Processing
if uploaded_file is not None:
    try:
        # Read the CSV
        df = pd.read_csv(uploaded_file)
        
        st.success(f"✅ Loaded {len(df)} records from Close.com export")
        
        # Process the data
        with st.spinner("Processing sales data..."):
            processed_df = process_close_export(df, month_ending)
        
        if processed_df is None or len(processed_df) == 0:
            st.warning(f"⚠️ No sold properties found for {month_ending.strftime('%B %Y')}")
        else:
            # Calculate totals BEFORE formatting
            subtotal = processed_df['Gross Profit'].sum()
            total = subtotal + prior_adjustment
            
            # Now format for display
            display_df = create_bonus_schedule_dataframe(processed_df)
            
            # Display Summary
            st.header("📊 Bonus Schedule Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Properties Sold", len(processed_df))
            with col2:
                st.metric("Subtotal", format_currency(subtotal))
            with col3:
                st.metric("Prior Adjustment", format_currency(prior_adjustment))
            with col4:
                st.metric("Gross Profit Eligible for Bonus", format_currency(total))
            
            st.divider()
            
            # Display the bonus schedule
            st.header("💰 Bonus Schedule Details")
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )
            
            # Add column totals row
            st.markdown("---")
            col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1.5, 1.2, 1.2])
            with col1:
                st.markdown("**COLUMN TOTALS:**")
            with col2:
                st.markdown(f"**Gross Sales:** {format_currency(processed_df['Gross Sales Price'].sum())}")
            with col3:
                st.markdown(f"**Closing Costs:** {format_currency(processed_df['Closing Costs'].sum())}")
            with col4:
                st.markdown(f"**Cash to Seller:** {format_currency(processed_df['Cash to Seller'].sum())}")
            with col5:
                st.markdown(f"**Asset Cost:** {format_currency(processed_df['Asset Cost'].sum())}")
            with col6:
                st.markdown(f"**Gross Profit:** {format_currency(processed_df['Gross Profit'].sum())}")
            
            st.markdown("---")
            
            # Add summary totals
            col1, col2, col3 = st.columns([2, 1, 1])
            with col2:
                st.markdown("**SUBTOTAL:**")
                st.markdown("**PRIOR ADJUSTMENT:**")
                st.markdown("**TOTAL:**")
            with col3:
                st.markdown(f"**{format_currency(subtotal)}**")
                st.markdown(f"**{format_currency(prior_adjustment)}**")
                st.markdown(f"**{format_currency(total)}**")
            
            st.divider()
            
            # Notes Section
            st.header("📝 Notes")
            st.markdown("""
            **Funding Date:** Date funds were available for withdrawal from our account. 
            "Pending" funds are not available for withdrawal. Accounting will confirm funding.
            
            **Reconciliation:** All data is subject to a post-payment audit and reconciliation. 
            Future Bonuses will be adjusted accordingly, as required.
            """)
            
            # Signature Section
            st.header("✍️ Signatures")
            
            # Create signature placeholders
            num_cols = min(len(team_list), 4)
            if num_cols > 0:
                cols = st.columns(num_cols)
                for idx, name in enumerate(team_list):
                    with cols[idx % num_cols]:
                        st.markdown(f"**{name}** ☐")
            
            st.divider()
            
            # Export Options
            st.header("📥 Download Options")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # PDF Export with signatures - PASS UNFORMATTED DATA
                pdf_data = export_to_pdf(
                    processed_df.copy(),  # Pass unformatted numeric data
                    month_ending,
                    format_currency(subtotal),
                    format_currency(prior_adjustment),
                    format_currency(total),
                    team_list
                )
                
                if pdf_data:
                    pdf_filename = f"{month_ending.strftime('%Y%m%d')}_Remarkable_Land_Bonus_Schedule.pdf"
                    
                    st.download_button(
                        label="📄 Download PDF",
                        data=pdf_data,
                        file_name=pdf_filename,
                        mime="application/pdf",
                        help="Professional PDF with signature lines"
                    )
                else:
                    st.info("📦 Install reportlab for PDF export: `pip install reportlab`")
            
            with col2:
                # Excel Export
                excel_data = export_to_excel(
                    display_df.copy(), 
                    month_ending, 
                    format_currency(subtotal),
                    format_currency(prior_adjustment),
                    format_currency(total)
                )
                
                filename = f"{month_ending.strftime('%Y%m%d')}_Remarkable_Land_Bonus_Schedule.xlsx"
                
                st.download_button(
                    label="📊 Download Excel",
                    data=excel_data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col3:
                # CSV Export
                csv = display_df.to_csv(index=False)
                csv_filename = f"{month_ending.strftime('%Y%m%d')}_Remarkable_Land_Bonus_Schedule.csv"
                
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name=csv_filename,
                    mime="text/csv"
                )
    
    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")
        st.exception(e)

else:
    # Instructions
    st.info("👆 Upload your Close.com 'Selling_Land_leads' export CSV to generate the bonus schedule")
    
    st.markdown("""
    ### 📋 Instructions:
    
    1. **Export from Close.com:**
       - Go to the "Selling Land" organization
       - Select the "📊 Bonus Report" smartview 👉 https://app.close.com/leads/save_vSNvWdZP7NWNkQ0vNKMy1mtCEoyaycVXti3YLvT9p21/
       - Export as "All Fields"
    
    2. **Configure Settings:**
       - Set the month ending date (left sidebar)
       - Adjust team member names for signatures
       - Set any prior adjustments if needed
    
    3. **Upload & Generate:**
       - Upload your CSV file
       - Review the generated bonus schedule
       - Download as PDF (with signatures), Excel, or CSV
    
    4. **Circulate for Electronic Signature**
    
    5. **Email the Signed Report to Accounting**
    
    ### 💡 Tips:
    - The app automatically filters for properties sold in the selected month
    - Asset Cost = Cost Basis (no additional costs added)
    - Gross Profit = Cash to Seller - Asset Cost
    - All currency values are formatted automatically
    - **PDF includes signature lines** for all team members
    - PDF table is sorted by date (oldest first)
    - Column totals provided for all financial columns
    """)
    
    # Sample data structure
    with st.expander("📊 Expected CSV Structure"):
        st.markdown("""
        The CSV should contain these key columns:
        - `primary_opportunity_date_won` - Closing date
        - `custom.Asset_Date_Sold` - Funding date
        - `custom.All_State` - Property state
        - `custom.All_APN` - Property APN
        - `custom.Gross Amount to Seller` - Contract price
        - `custom.Asset_Closing_Costs` - Reductions/costs
        - `custom.Asset_Cost_Basis` - Original cost basis
        - `display_name` - Property name (contains county and grantor)
        """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    Bonus Schedule Generator v1.2
    </div>
    """,
    unsafe_allow_html=True
)
