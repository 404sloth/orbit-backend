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
            
            # Premium HTML Template with Indigo/Glass theme
            html_content = f"""
            <html>
            <head>
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
            <style>
                body {{ 
                    font-family: 'Outfit', sans-serif; 
                    margin: 0; 
                    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); 
                    display: flex; 
                    justify-content: center; 
                    padding: 40px;
                }}
                .report-card {{ 
                    background: rgba(255, 255, 255, 0.03); 
                    backdrop-filter: blur(10px); 
                    border: 1px solid rgba(255, 255, 255, 0.1); 
                    padding: 40px; 
                    border-radius: 24px; 
                    width: 1000px;
                    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                }}
                .header {{ 
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1); 
                    padding-bottom: 20px; 
                    margin-bottom: 30px; 
                    display: flex; 
                    justify-content: space-between; 
                    align-items: flex-end;
                }}
                .title-area h1 {{ 
                    color: #fff; 
                    margin: 0; 
                    font-size: 28px; 
                    font-weight: 600; 
                    letter-spacing: -0.5px;
                }}
                .title-area p {{ 
                    color: #94a3b8; 
                    margin: 5px 0 0 0; 
                    font-size: 14px; 
                }}
                .page-badge {{ 
                    background: #6366f1; 
                    color: white; 
                    padding: 4px 12px; 
                    border-radius: 100px; 
                    font-size: 12px; 
                    font-weight: 600; 
                }}
                table {{ 
                    border-collapse: separate; 
                    border-spacing: 0; 
                    width: 100%; 
                    color: #e2e8f0;
                }}
                th {{ 
                    text-align: left; 
                    padding: 12px 16px; 
                    font-size: 11px; 
                    color: #818cf8; 
                    font-weight: 600; 
                    letter-spacing: 1px; 
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                td {{ 
                    padding: 14px 16px; 
                    font-size: 14px; 
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05); 
                }}
                tr:last-child td {{ border-bottom: none; }}
                tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
                .footer {{ 
                    margin-top: 30px; 
                    font-size: 11px; 
                    color: #475569; 
                    display: flex; 
                    justify-content: space-between; 
                }}
                .summary-stats {{
                    display: flex;
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                .stat-box {{
                    background: rgba(255, 255, 255, 0.02);
                    padding: 12px 20px;
                    border-radius: 12px;
                    border: 1px solid rgba(255, 255, 255, 0.05);
                }}
                .stat-label {{ font-size: 10px; color: #64748b; text-transform: uppercase; }}
                .stat-value {{ font-size: 16px; color: #f8fafc; font-weight: 600; }}
            </style>
            </head>
            <body>
            <div class="report-card">
                <div class="header">
                    <div class="title-area">
                        <h1>Executive Report</h1>
                        <p>{title}</p>
                    </div>
                    <div class="page-badge">PAGE {p_idx + 1} OF {len(pages)}</div>
                </div>
                
                <div class="summary-stats">
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
                    <span>Generated by Orbit Intelligence Platform</span>
                    <span>Confidential • {time.strftime("%H:%M:%S UTC")}</span>
                </div>
            </div>
            </body>
            </html>
            """
            
            p_filename = f"report_p{p_idx+1}_{session_id[:8]}_{int(time.time())}.png"
            hti.screenshot(html_str=html_content, save_as=p_filename, size=(1100, 850))
            generated_files.append(p_filename)

        # Handle multiple pages with a ZIP file
        zip_filename = None
        if len(generated_files) > 1:
            zip_filename = f"report_bundle_{session_id[:8]}_{int(time.time())}.zip"
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
