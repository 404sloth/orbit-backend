import io
import json
import PyPDF2
from typing import Optional
from core.logger import logger

def parse_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"PDF parsing failed: {str(e)}")
        raise ValueError(f"Could not parse PDF: {str(e)}")

def parse_json(file_bytes: bytes) -> str:
    """Extract and format text from JSON bytes."""
    try:
        data = json.loads(file_bytes.decode("utf-8"))
        return json.dumps(data, indent=2)
    except Exception as e:
        logger.error(f"JSON parsing failed: {str(e)}")
        raise ValueError(f"Could not parse JSON: {str(e)}")

def parse_markdown(file_bytes: bytes) -> str:
    """Extract text from Markdown/Text bytes."""
    try:
        return file_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Text/MD parsing failed: {str(e)}")
        raise ValueError(f"Could not parse text file: {str(e)}")

def get_parser_for_filename(filename: str):
    """Return appropriate parser based on file extension."""
    ext = filename.split(".")[-1].lower()
    if ext == "pdf":
        return parse_pdf
    elif ext == "json":
        return parse_json
    elif ext in ["md", "txt", "markdown"]:
        return parse_markdown
    else:
        return None
