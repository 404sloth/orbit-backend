import os
import uuid
import time
import zipfile
from typing import Dict, Any, List
from html2image import Html2Image
from langchain_core.messages import AIMessage
from core.state import GraphState
from core.logger import logger
from core.session import session_data, REPORTS_TEMP_DIR

def image_node(state: GraphState, config: Dict[str, Any]) -> dict:
    """
    Image Agent node with Multi-page support and Premium aesthetics.
    """
    session_id = config.get("configurable", {}).get("thread_id", "default_session")
    user_id = config.get("configurable", {}).get("user_id", "unknown")
    
    logger.info("Image Agent invoked", session_id=session_id)
    
    if session_id not in session_data:
        return {"messages": [AIMessage(content="No report data found for this session. Please generate a report first.")]}
    
    cache = session_data[session_id]
    data = cache["data"]
    title = cache.get("query", "Executive Data Report")
    
    try:
        if not data:
            return {"messages": [AIMessage(content="Cached data is empty. Cannot generate image.")]}
            
        headers_list = list(data[0].keys())
        rows_per_page = 15
        pages = [data[i:i + rows_per_page] for i in range(0, len(data), rows_per_page)]
        
        generated_files = []
        hti = Html2Image(output_path=REPORTS_TEMP_DIR, custom_flags=['--no-sandbox', '--disable-gpu', '--hide-scrollbars'])
        
        for p_idx, page_data in enumerate(pages):
            headers_html = "".join([f"<th>{str(h).replace('_', ' ').upper()}</th>" for h in headers_list])
            rows_html = ""
            for r_idx, row in enumerate(page_data):
                row_html = "".join([f"<td>{row.get(h, '')}</td>" for h in headers_list])
                rows_html += f"<tr>{row_html}</tr>"
            
            # Premium HTML Template with Executive Light theme
            html_content = f"""
            <html>
            <head>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
            <style>
                body {{ 
                    font-family: 'Inter', sans-serif; 
                    margin: 0; 
                    background: #f1f5f9; 
                    display: flex; 
                    justify-content: center; 
                    padding: 8px;
                }}
                .report-card {{ 
                    background: #ffffff; 
                    border: 1px solid #e2e8f0; 
                    padding: 30px; 
                    border-radius: 12px; 
                    width: 1000px;
                    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
                    position: relative;
                }}
                .header {{ 
                    border-bottom: 2px solid #f1f5f9; 
                    padding-bottom: 15px; 
                    margin-bottom: 20px; 
                    display: flex; 
                    justify-content: space-between; 
                    align-items: center;
                }}
                .title-area h1 {{ 
                    color: #0f172a; 
                    margin: 0; 
                    font-size: 24px; 
                    font-weight: 600; 
                    letter-spacing: -0.5px;
                }}
                .title-area p {{ 
                    color: #c5a572; 
                    margin: 2px 0 0 0; 
                    font-size: 11px; 
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 1.5px;
                }}
                .page-badge {{ 
                    background: #f8fafc; 
                    color: #64748b; 
                    padding: 6px 12px; 
                    border-radius: 6px; 
                    font-size: 10px; 
                    font-weight: 600; 
                    border: 1px solid #e2e8f0;
                }}
                table {{ 
                    width: 100%; 
                    border-collapse: collapse;
                    color: #334155;
                }}
                th {{ 
                    text-align: left; 
                    padding: 10px 12px; 
                    font-size: 10px; 
                    color: #64748b; 
                    font-weight: 600; 
                    text-transform: uppercase;
                    letter-spacing: 1px; 
                    background: #f8fafc;
                    border-bottom: 1px solid #e2e8f0;
                }}
                td {{ 
                    padding: 12px 12px; 
                    font-size: 13px; 
                    border-bottom: 1px solid #f1f5f9; 
                }}
                tr:last-child td {{ border-bottom: none; }}
                tr:nth-child(even) {{ background: #fafafa; }}
                .footer {{ 
                    margin-top: 30px; 
                    font-size: 10px; 
                    color: #94a3b8; 
                    display: flex; 
                    justify-content: space-between; 
                    padding-top: 15px;
                    border-top: 1px solid #f1f5f9;
                }}
                .summary-stats {{
                    display: flex;
                    gap: 20px;
                    margin-bottom: 25px;
                }}
                .stat-box {{
                    flex: 1;
                    background: #f8fafc;
                    padding: 15px;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                }}
                .stat-label {{ font-size: 9px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
                .stat-value {{ font-size: 18px; color: #0f172a; font-weight: 600; }}
            </style>
            </head>
            <body>
            <div class="report-card">
                <div class="header">
                    <div class="title-area">
                        <p>Executive Strategic Insight</p>
                        <h1>Data Intelligence Report</h1>
                    </div>
                    <div class="page-badge">SECURE DATA VIEW | PAGE {p_idx + 1} OF {len(pages)}</div>
                </div>
                
                <div class="summary-stats">
                    <div class="stat-box">
                        <div class="stat-label">Analysis Subject</div>
                        <div class="stat-value">{title[:40]}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Total Records</div>
                        <div class="stat-value">{len(data)}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Generation Date</div>
                        <div class="stat-value">{time.strftime("%d %b %Y")}</div>
                    </div>
                </div>
 
                <table>
                    <thead><tr>{headers_html}</tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
                
                <div class="footer">
                    <span>ORBIT | Strategic Intelligence Engine</span>
                    <span>CONFIDENTIAL • {time.strftime("%H:%M UTC")}</span>
                </div>
            </div>
            </body>
            </html>
            """
            
            p_filename = f"{user_id}_report_p{p_idx+1}_{session_id[:8]}_{int(time.time())}.png"
            hti.screenshot(html_str=html_content, save_as=p_filename, size=(1100, 850))
            generated_files.append(p_filename)

        # Handle multiple pages with a ZIP file
        zip_filename = None
        if len(generated_files) > 1:
            zip_filename = f"{user_id}_report_bundle_{session_id[:8]}_{int(time.time())}.zip"
            zip_path = os.path.join(REPORTS_TEMP_DIR, zip_filename)
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file in generated_files:
                    zipf.write(os.path.join(REPORTS_TEMP_DIR, file), arcname=file)
            
            download_url = f"http://localhost:8000/reports/download/{zip_filename}"
            label = "Download All Images (ZIP)"
            report_type = "image_bundle"
        else:
            download_url = f"http://localhost:8000/reports/download/{generated_files[0]}"
            label = "Download Report Image"
            report_type = "image"

        # Construct hidden metadata for the UI but clean text for the chat
        # Using a special HTML comment tag that the stream parser will see but markdown renderer won't show
        hidden_metadata = f"<!-- REPORT_URL: {download_url} | FILENAME: {zip_filename or generated_files[0]} | TYPE: {report_type} -->"
        
        response_text = f"🎨 **Premium Visualization Generated**\n\n"
        response_text += f"I have rendered the report data into {len(generated_files)} high-resolution executive summary cards.\n\n"
        
        if len(generated_files) > 1:
            response_text += f"The data was spread across {len(generated_files)} pages due to its size.\n\n"
        
        # We still need the link in the stream for the backend 'main.py' to detect it, 
        # but we'll wrap it in a hidden HTML comment to hide it from the chat bubble.
        response_text += f"You can view and download the full visual report in the **Reports Panel** on the right.\n\n"
        response_text += hidden_metadata

        logger.info("Image(s) generated successfully", count=len(generated_files))
        
        return {
            "messages": [AIMessage(content=response_text)],
            "next_node": "FINISH"
        }
        
    except Exception as e:
        logger.error("Error generating image", error=str(e))
        return {"messages": [AIMessage(content=f"Error generating visual report: {str(e)}")]}
