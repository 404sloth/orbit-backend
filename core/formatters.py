"""
Data formatting and presentation utilities for the Orbit backend.
Transforms raw agent outputs into beautifully formatted, user-ready responses.

Handles:
- SQL table data → formatted tables
- RAG documents → organized summaries with citations
- Metrics → dashboard-ready KPIs
- Complex nested data → structured hierarchies
"""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime


class DataFormatter:
    """Formats various data types for presentation to users."""
    
    @staticmethod
    def format_sql_rows(rows: List[Dict[str, Any]], title: str = "") -> str:
        """
        Format database rows into a readable table.
        
        Args:
            rows: List of row dictionaries from SQL query
            title: Optional title for the table
            
        Returns:
            Formatted table as markdown string
        """
        if not rows:
            return "No data found."
        
        # Build markdown table
        lines = []
        
        if title:
            lines.append(f"\n### {title}\n")
        
        # Get column names from first row
        columns = list(rows[0].keys())
        
        # Header
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("|" + "|".join(["---" for _ in columns]) + "|")
        
        # Rows
        for row in rows:
            values = []
            for col in columns:
                val = row.get(col, "")
                # Format None/null values
                if val is None:
                    val = "-"
                # Format numbers with commas
                elif isinstance(val, (int, float)):
                    if isinstance(val, float):
                        val = f"{val:.2f}"
                    else:
                        val = f"{val:,}"
                # Truncate long strings
                elif isinstance(val, str) and len(val) > 50:
                    val = val[:47] + "..."
                values.append(str(val))
            lines.append("| " + " | ".join(values) + " |")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_sql_summary(rows: List[Dict[str, Any]]) -> str:
        """
        Format database rows into a key-value summary (for small result sets).
        
        Args:
            rows: List of row dictionaries
            
        Returns:
            Formatted summary as markdown string
        """
        if not rows:
            return "No data found."
        
        if len(rows) == 1:
            # Single row - format as key-value pairs
            row = rows[0]
            lines = ["\n**Summary**\n"]
            for key, value in row.items():
                # Format the key (convert snake_case to Title Case)
                display_key = key.replace("_", " ").title()
                # Format the value
                if value is None:
                    display_val = "-"
                elif isinstance(value, (int, float)):
                    if isinstance(value, float):
                        display_val = f"{value:.2f}"
                    else:
                        display_val = f"{value:,}"
                else:
                    display_val = str(value)
                lines.append(f"- **{display_key}**: {display_val}")
            return "\n".join(lines)
        else:
            # Multiple rows - format as table
            return DataFormatter.format_sql_rows(rows)
    
    @staticmethod
    def format_sql_metrics(rows: List[Dict[str, Any]]) -> str:
        """
        Format database rows as KPI/metric cards (for dashboard metrics).
        
        Args:
            rows: List of metric dictionaries with keys like: value, status, label
            
        Returns:
            Formatted metrics as markdown cards
        """
        if not rows:
            return "No metrics available."
        
        lines = ["\n### Key Metrics\n"]
        
        for row in rows:
            value = row.get("value", "-")
            status = row.get("status", "").upper()
            label = row.get("label", "Metric")
            
            # Format value
            if isinstance(value, (int, float)):
                if isinstance(value, float):
                    formatted_val = f"{value:.2f}"
                else:
                    formatted_val = f"{value:,}"
            else:
                formatted_val = str(value)
            
            # Add status indicator
            status_indicator = {
                "AT RISK": "[AT RISK]",
                "WARNING": "[WARNING]",
                "ON TRACK": "[ON TRACK]",
                "DELAYED": "[DELAYED]",
                "COMPLETE": "[COMPLETE]"
            }.get(status, "[UNKNOWN]")
            
            lines.append(f"**{label}**: `{formatted_val}` {status_indicator} _{status}_")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_rag_results(results: List[Dict[str, str]]) -> str:
        """
        Format RAG search results with proper citations.
        
        Args:
            results: List of document dicts with 'source' and 'content'
            
        Returns:
            Formatted results with citations
        """
        if not results:
            return "No relevant documents found."
        
        lines = ["\n### Knowledge Base Results\n"]
        
        for i, result in enumerate(results, 1):
            source = result.get("source", "Unknown Source")
            content = result.get("content", "")
            
            # Truncate content if too long
            if len(content) > 200:
                content = content[:200] + "..."
            
            lines.append(f"\n**[{i}] {source}**")
            lines.append(f"> {content}")
        
        lines.append("\n")
        return "\n".join(lines)
    
    @staticmethod
    def format_rag_summary(results: List[Dict[str, str]]) -> str:
        """
        Format RAG results as a narrative summary with citations.
        
        Args:
            results: List of document dicts with 'source' and 'content'
            
        Returns:
            Narrative summary with inline citations
        """
        if not results:
            return "No relevant documents found."
        
        lines = ["\n### Summary from Knowledge Base\n"]
        
        # Group by source
        sources = {}
        for result in results:
            source = result.get("source", "Unknown")
            content = result.get("content", "")
            if source not in sources:
                sources[source] = []
            sources[source].append(content)
        
        # Format with citations
        for source, contents in sources.items():
            lines.append(f"\n**From {source}:**")
            for content in contents:
                # Truncate if needed
                if len(content) > 300:
                    content = content[:300] + "..."
                lines.append(f"- {content}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_list(items: List[str], title: str = "") -> str:
        """
        Format a simple list as bullet points.
        
        Args:
            items: List of items to format
            title: Optional title
            
        Returns:
            Formatted list
        """
        if not items:
            return "No items found."
        
        lines = []
        if title:
            lines.append(f"\n### {title}\n")
        
        for item in items:
            lines.append(f"- {item}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_hierarchical_data(data: Dict[str, Any], indent: int = 0) -> str:
        """
        Format nested/hierarchical data nicely.
        
        Args:
            data: Nested dictionary to format
            indent: Current indentation level
            
        Returns:
            Formatted hierarchical string
        """
        lines = []
        indent_str = "  " * indent
        
        for key, value in data.items():
            # Format key
            display_key = key.replace("_", " ").title()
            
            if isinstance(value, dict):
                lines.append(f"{indent_str}**{display_key}:**")
                lines.append(DataFormatter.format_hierarchical_data(value, indent + 1))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                lines.append(f"{indent_str}**{display_key}:**")
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        lines.append(f"{indent_str}  - **Item {i+1}:**")
                        lines.append(DataFormatter.format_hierarchical_data(item, indent + 2))
                    else:
                        lines.append(f"{indent_str}  - {item}")
            elif isinstance(value, list):
                lines.append(f"{indent_str}**{display_key}:**")
                for item in value:
                    lines.append(f"{indent_str}  - {item}")
            else:
                # Format value
                if value is None:
                    val_str = "-"
                elif isinstance(value, (int, float)):
                    val_str = str(value)
                else:
                    val_str = str(value)
                lines.append(f"{indent_str}**{display_key}**: {val_str}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_comparison_table(data: List[Dict[str, Any]], title: str = "") -> str:
        """
        Format data as a comparison table.
        
        Args:
            data: List of dictionaries to compare
            title: Optional title
            
        Returns:
            Formatted comparison table
        """
        if not data:
            return "No data to compare."
        
        return DataFormatter.format_sql_rows(data, title)
    
    @staticmethod
    def format_time_series(data: List[Dict[str, Any]], date_col: str = "date", 
                          value_col: str = "value") -> str:
        """
        Format time series data for trend display.
        
        Args:
            data: List of time series dictionaries
            date_col: Column name for dates
            value_col: Column name for values
            
        Returns:
            Formatted time series string
        """
        if not data:
            return "No time series data."
        
        lines = ["\n### Time Series Data\n"]
        
        # Find the columns
        cols = list(data[0].keys())
        if date_col not in cols:
            date_col = cols[0]
        if value_col not in cols:
            value_col = cols[-1] if len(cols) > 1 else cols[0]
        
        # Build simple ASCII chart representation
        lines.append("```")
        for row in data:
            date = row.get(date_col, "")
            value = row.get(value_col, 0)
            
            # Create simple bar
            if isinstance(value, (int, float)):
                bar_length = max(1, int(value / 10))  # Scale to reasonable length
                bar = "█" * bar_length
                lines.append(f"{str(date):20s} {bar} {value}")
        lines.append("```")
        
        # Also add as table
        lines.append("\n")
        lines.append(DataFormatter.format_sql_rows(data))
        
        return "\n".join(lines)


class ResponseFormatter:
    """Formats complete agent responses for presentation."""
    
    @staticmethod
    def format_sql_answer(query_result: List[Dict[str, Any]], 
                         answer_text: str, 
                         title: str = "Query Results") -> str:
        """
        Format a complete SQL agent response.
        
        Args:
            query_result: The raw query results
            answer_text: The agent's interpretation/summary
            title: Title for the results
            
        Returns:
            Formatted response
        """
        lines = []
        lines.append("\n## Data Analysis\n")
        
        # Add the agent's interpretation
        if answer_text and answer_text != "[AGENT_COMPLETE]":
            lines.append(f"{answer_text}\n")
        
        # Add the data visualization
        if len(query_result) <= 5:
            # Use summary format for small datasets
            lines.append(DataFormatter.format_sql_summary(query_result))
        elif len(query_result) <= 20:
            # Use table format for medium datasets
            lines.append(DataFormatter.format_sql_rows(query_result, title))
        else:
            # For large datasets, show summary + table
            lines.append(f"**Found {len(query_result)} records**\n")
            lines.append(DataFormatter.format_sql_rows(query_result[:10], f"{title} (First 10)"))
        
        return "\n".join(lines)
    
    @staticmethod
    def format_rag_answer(documents: List[Dict[str, str]], 
                         answer_text: str) -> str:
        """
        Format a complete RAG agent response.
        
        Args:
            documents: The retrieved documents
            answer_text: The agent's summary/answer
            
        Returns:
            Formatted response
        """
        lines = []
        lines.append("\n## Knowledge Base Result\n")
        
        # Add the agent's answer/summary
        if answer_text and answer_text != "[AGENT_COMPLETE]":
            lines.append(f"{answer_text}\n")
        
        # Add the source documents
        if documents:
            lines.append(DataFormatter.format_rag_results(documents))
        else:
            lines.append("No relevant documents found.")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_error_response(error: str, context: str = "") -> str:
        """
        Format an error response nicely.
        
        Args:
            error: The error message
            context: Optional context about what was attempted
            
        Returns:
            Formatted error message
        """
        lines = ["\n## Error\n"]
        
        if context:
            lines.append(f"**Context**: {context}\n")
        
        lines.append(f"**Error**: {error}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_success_response(message: str, data: Optional[Any] = None) -> str:
        """
        Format a success response.
        
        Args:
            message: Success message
            data: Optional data to include
            
        Returns:
            Formatted success message
        """
        lines = ["\n## Success\n"]
        lines.append(message)
        
        if data:
            lines.append("")
            if isinstance(data, dict):
                lines.append(DataFormatter.format_hierarchical_data(data))
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                lines.append(DataFormatter.format_sql_rows(data))
            else:
                lines.append(str(data))
        
        return "\n".join(lines)


class MessageEnhancer:
    """Enhances agent messages with better formatting and structure."""
    
    @staticmethod
    def enhance_agent_message(content: str, data_type: str = "general") -> str:
        """
        Enhance an agent's message with better formatting.
        
        Args:
            content: Original message content
            data_type: Type of data (sql, rag, general, etc.)
            
        Returns:
            Enhanced message
        """
        if not content:
            return ""
        
        # Remove system markers
        if content.startswith("[SYSTEM]"):
            return ""
        if content.startswith("[AGENT_COMPLETE]"):
            return ""
        
        # Add formatting based on content patterns
        lines = []
        paragraphs = content.split("\n\n")
        
        for para in paragraphs:
            # Detect lists
            if para.strip().startswith("- "):
                lines.append(para)
            # Detect headers
            elif para.startswith("#"):
                lines.append(para)
            # Regular text
            else:
                lines.append(para.strip())
        
        return "\n\n".join(lines)
    
    @staticmethod
    def add_data_context(message: str, data_source: str, 
                        record_count: int = 0) -> str:
        """
        Add contextual information to a message.
        
        Args:
            message: Original message
            data_source: Where the data came from (table name, document type, etc.)
            record_count: Number of records/items
            
        Returns:
            Enhanced message with context
        """
        context = f"\n_Data from: **{data_source}**"
        if record_count > 0:
            context += f" ({record_count} records)"
        context += "_"
        
        return f"{message}{context}"
