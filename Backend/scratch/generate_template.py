from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
import os

def set_cell_background(cell, fill, color=None, val=None):
    """
    @param cell:  docx.table._Cell object
    @param fill:  hex string without #, e.g. '000000'
    """
    shading_elm = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), fill))
    cell._tc.get_or_add_tcPr().append(shading_elm)

def create_branded_template(report_key, title):
    doc = Document()
    
    # --- PAGE 1: COVER PAGE ---
    section = doc.sections[0]
    section.left_margin = Inches(1.5)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)

    # Logo
    logo_path = os.path.join("report_templates", "assets", "adept_logo.jpg")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if os.path.exists(logo_path):
        run = p.add_run()
        run.add_picture(logo_path, width=Inches(3.0))
    
    doc.add_paragraph("\n\n\n")

    # Large Title
    main_title = doc.add_paragraph(title.upper())
    main_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = main_title.runs[0]
    run.font.size = Pt(36)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1D, 0x4E, 0x89)

    doc.add_paragraph("\n")

    # Date / Subtitle
    date_p = doc.add_paragraph("{{ currentDate }}")
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = date_p.runs[0]
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Footer on Cover
    footer_img_path = os.path.join("report_templates", "assets", "adept_footer.png")
    if os.path.exists(footer_img_path):
        # We'll put it in the footer of this section
        footer = section.footer
        footer_para = footer.paragraphs[0]
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = footer_para.add_run()
        run.add_picture(footer_img_path, width=Inches(6.5))

    doc.add_page_break()

    # --- PAGE 2: TABLE OF CONTENTS ---
    toc_title = doc.add_paragraph("TABLE OF CONTENTS")
    toc_title.style = 'Heading 1'
    run = toc_title.runs[0]
    run.font.color.rgb = RGBColor(0x1D, 0x4E, 0x89)

    doc.add_paragraph("Table of Contents will be generated here. (Right-click and select 'Update Field' in Word)")
    # Note: Adding a real TOC field requires complex XML. 
    # For now, we provide the instruction.

    doc.add_page_break()

    # --- PAGE 3+: CONTENT ---
    # Underlined Header for First Page of Content
    header_title = doc.add_paragraph(title)
    header_title.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header_title.runs[0]
    run.font.size = Pt(18)
    run.font.bold = True
    run.underline = True
    run.font.color.rgb = RGBColor(0x1D, 0x4E, 0x89)

    doc.add_paragraph("\n")

    # SUMMARY BOXES (If Sprint Report)
    if report_key == 'sprint':
        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        table.columns[0].width = Inches(4.0)
        table.columns[1].width = Inches(2.2)

        # Left Box (Orange)
        cell_l = table.rows[0].cells[0]
        set_cell_background(cell_l, "E67E22") # Adept Orange-ish
        p_l = cell_l.paragraphs[0]
        run_l = p_l.add_run("This Sprint's Summary:")
        run_l.font.bold = True
        run_l.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
        p_l2 = cell_l.add_paragraph("• Status: {{ sections.status.formData.status_rating }}\n• Summary: {{ sections.status.formData.summary_text }}\n• Timeline: {{ sections.status.formData.timeline }}\n• Time Spent: {{ sections.status.formData.time_spent }}")
        p_l2.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p_l2.runs[0].font.size = Pt(9)

        # Right Box (Teal)
        cell_r = table.rows[0].cells[1]
        set_cell_background(cell_r, "0080A0") # Adept Teal-ish
        p_r = cell_r.paragraphs[0]
        run_r = p_r.add_run("Project Info:")
        run_r.font.bold = True
        run_r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
        p_r2 = cell_r.add_paragraph("Project: {{ sections.metadata.formData.project_name }}\nContent: {{ title }}\nBy: {{ sections.metadata.formData.report_by }}")
        p_r2.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p_r2.runs[0].font.size = Pt(9)

    doc.add_paragraph("\n")

    # Sections Loop (Remaining)
    doc.add_paragraph("{% for id, section in sections.items() %}")
    doc.add_paragraph("{% if id != 'metadata' %}") # Skip metadata as it's handled
    
    # Section Title
    sec_title = doc.add_paragraph("{{ section.title }}")
    sec_title.style = 'Heading 1'
    run = sec_title.runs[0]
    run.font.color.rgb = RGBColor(0x1D, 0x4E, 0x89)
    
    # Section Content
    doc.add_paragraph("{{ section.aiDraft if section.aiDraft else section.userOverride }}")
    
    doc.add_paragraph("\n")
    doc.add_paragraph("{% endif %}")
    doc.add_paragraph("{% endfor %}")

    # Save
    filename = f"{report_key}_report.docx"
    output_path = os.path.join("report_templates", filename)
    doc.save(output_path)
    print(f"Template saved: {output_path}")

if __name__ == "__main__":
    templates = {
        "sprint": "Sprint Report",
        "marketing": "Marketing Performance Report",
        "weekly": "Weekly Activity Report",
        "monthly": "Monthly Strategic Overview"
    }
    
    for key, name in templates.items():
        create_branded_template(key, name)
