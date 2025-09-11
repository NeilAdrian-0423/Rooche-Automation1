"""Helper utility functions."""
import re
import logging
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton
from PyQt6.QtGui import QFont

def extract_notion_url(description_text):
    """Extract Notion page ID from p= parameter or URL structure."""
    if not description_text:
        return ""
    
    # Remove HTML tags and decode entities
    clean_text = description_text.replace('<a href="', '').replace('">', '').replace('</a>', '')
    clean_text = clean_text.replace('&amp;', '&')
    
    logging.debug(f"[URL Extract] Processing description: {clean_text[:150]}...")
    
    # Find Notion URLs first
    notion_url_patterns = [
        r'https://www\.notion\.so/[^\s<>"]+',
        r'https://notion\.so/[^\s<>"]+',
    ]
    
    notion_url = None
    for pattern in notion_url_patterns:
        matches = re.findall(pattern, clean_text)
        if matches:
            # Get the last/longest match
            notion_url = matches[-1]
            logging.debug(f"[URL Extract] Found Notion URL: {notion_url}")
            break
    
    if notion_url:
        # First priority: Look for p= parameter (this contains the actual page ID)
        p_param_match = re.search(r'[?&]p=([a-f0-9]{32})', notion_url, re.IGNORECASE)
        if p_param_match:
            page_id = p_param_match.group(1)
            clean_url = f"https://www.notion.so/{page_id}"
            logging.debug(f"[URL Extract] Found page ID in p= parameter: {page_id}")
            logging.debug(f"[URL Extract] Created clean Notion URL: {clean_url}")
            return clean_url
        
        # Second priority: Look for page ID directly in path (like /rooche/32chars)
        path_match = re.search(r'/[^/]+/([a-f0-9]{32})', notion_url, re.IGNORECASE)
        if path_match:
            page_id = path_match.group(1)
            clean_url = f"https://www.notion.so/{page_id}"
            logging.debug(f"[URL Extract] Found page ID in URL path: {page_id}")
            logging.debug(f"[URL Extract] Created clean Notion URL: {clean_url}")
            return clean_url
        
        # Third priority: Any 32-char hex string in the URL (use the first one found)
        hex_matches = re.findall(r'[a-f0-9]{32}', notion_url, re.IGNORECASE)
        if hex_matches:
            # Use the first one found (usually the main page ID)
            page_id = hex_matches[0]
            clean_url = f"https://www.notion.so/{page_id}"
            logging.debug(f"[URL Extract] Found page ID as first hex string: {page_id}")
            logging.debug(f"[URL Extract] Created clean Notion URL: {clean_url}")
            return clean_url
    
    # Final fallback: look for any 32-character hex string in the entire text
    hex_pattern = r'[a-f0-9]{32}'
    hex_matches = re.findall(hex_pattern, clean_text, re.IGNORECASE)
    
    if hex_matches:
        # Use the first one found
        page_id = hex_matches[0]
        clean_url = f"https://www.notion.so/{page_id}"
        logging.debug(f"[URL Extract] Final fallback: Created clean Notion URL: {clean_url}")
        return clean_url
    
    logging.warning(f"[URL Extract] No valid Notion page ID found in: {clean_text}")
    return clean_text.strip()

def create_labeled_input(layout, label_text, default_text="", read_only=False, max_width=None):
    layout.addWidget(QLabel(label_text))
    input_field = QLineEdit()
    input_field.setFont(QFont("Arial", 9))
    input_field.setText(default_text)
    if read_only:
        input_field.setReadOnly(True)
    if max_width:
        input_field.setMaximumWidth(max_width)
    layout.addWidget(input_field)
    return input_field

def create_styled_button(text, bg_color, hover_color, disabled_style=None):
    button = QPushButton(text)
    style = f"""
        QPushButton {{
            background-color: {bg_color};
            color: white;
            font-size: 10pt;
            padding: 5px;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
    """
    if disabled_style:
        style += f"QPushButton:disabled {{ {disabled_style}; }}"
    button.setStyleSheet(style)
    return button