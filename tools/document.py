"""
Executive Document Generation Tool.
Creates premium, well-formatted PDFs for Meeting Summaries, RFPs, and SOWs.
Uses fpdf2 for high-quality executive layouts.
"""
import os
import uuid
import datetime
from fpdf import FPDF
from langchain_core.tools import tool
from core.schemas import GenerateReportSchema
from core.logger import logger
from core.config import settings
from core.session import REPORTS_TEMP_DIR

class ExecutivePDF(FPDF):
    def header(self):
        # Premium Gold/Charcoal Header
        self.set_font("helvetica", "B", 8)
        self.set_text_color(197, 165, 114) # Gold
        self.cell(0, 10, "ORBIT | STRATEGIC INTELLIGENCE ENGINE", ln=True, align="R")
        self.ln(5)
        
    def footer(self):
        # Executive Footer
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        self.cell(0, 10, f"CONFIDENTIAL - EXECUTIVE EYES ONLY | Generated: {date_str} | Page {self.page_no()}/{{nb}}", align="C")

@tool(args_schema=GenerateReportSchema)
def generate_executive_report(doc_type: str, title: str, content_markdown: str, subtitle: str = None) -> str:
    """
    Generates a premium, well-formatted PDF document for executive review.
    Use this for: Meeting Summaries, RFPs, SOWs, or Strategic Briefs.
    
    Input:
        doc_type: One of ['Meeting Summary', 'RFP', 'SOW', 'Project Brief']
        title: Descriptive title
        content_markdown: The body text in Markdown format (supports # for headers)
        subtitle: Optional secondary header
        
    Output:
        A JSON string with the download URL for the generated PDF.
    """
    try:
        # 1. Setup PDF
        pdf = ExecutivePDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        
        # 2. Cover Section
        pdf.set_font("helvetica", "B", 24)
        pdf.set_text_color(30, 42, 56) # Charcoal
        pdf.ln(20)
        pdf.multi_cell(0, 15, title.upper(), align="L")
        
        if subtitle:
            pdf.set_font("helvetica", "B", 14)
            pdf.set_text_color(197, 165, 114) # Gold
            pdf.cell(0, 10, subtitle, ln=True, align="L")
            
        pdf.ln(5)
        pdf.set_draw_color(197, 165, 114) # Gold line
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
        pdf.ln(10)
        
        # 3. Content Parsing (Simplified Markdown)
        lines = content_markdown.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue
                
            if line.startswith("###"):
                pdf.set_font("helvetica", "B", 12)
                pdf.set_text_color(30, 42, 56)
                pdf.ln(4)
                pdf.multi_cell(0, 10, line.replace("###", "").strip())
                pdf.ln(2)
            elif line.startswith("##"):
                pdf.set_font("helvetica", "B", 14)
                pdf.set_text_color(30, 42, 56)
                pdf.ln(6)
                pdf.multi_cell(0, 10, line.replace("##", "").strip())
                pdf.set_draw_color(226, 232, 240)
                pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 40, pdf.get_y())
                pdf.ln(4)
            elif line.startswith("#"):
                pdf.set_font("helvetica", "B", 16)
                pdf.set_text_color(197, 165, 114)
                pdf.ln(8)
                pdf.multi_cell(0, 12, line.replace("#", "").strip())
                pdf.ln(4)
            elif line.startswith("-") or line.startswith("*"):
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(30, 42, 56)
                # Proper bullet point handling
                current_y = pdf.get_y()
                pdf.set_x(20) # Explicit indent
                pdf.cell(5, 7, "-", ln=0)
                pdf.multi_cell(0, 7, line[1:].strip())
            else:
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(30, 42, 56)
                pdf.multi_cell(0, 7, line)
                
        # 4. Save File
        output_dir = REPORTS_TEMP_DIR
        os.makedirs(output_dir, exist_ok=True)
        
        safe_title = "".join(x for x in title if x.isalnum() or x in " -_").strip().replace(" ", "_")
        filename = f"{safe_title}_{uuid.uuid4().hex[:6]}.pdf"
        filepath = os.path.join(output_dir, filename)
        
        pdf.output(filepath)
        
        # 5. Return Download URL
        download_url = f"http://localhost:8000/reports/download/{filename}"
        
        logger.info("Premium document generated", doc_type=doc_type, title=title, url=download_url)
        
        return f"""[STRATEGIC_DOCUMENT_READY]
A premium {doc_type} has been generated: **{title}**.

Download Link: [Download PDF]({download_url})

This document contains a professional executive summary with strategic insights and action items."""

    except Exception as e:
        logger.error("Document Generation Failed", error=str(e))
        return f"Error generating document: {str(e)}"
