import fitz  # PyMuPDF
import re
from openai import OpenAI
from fpdf import FPDF

# --- 1. CONFIGURATION ---
# strict structural headers that are unlikely to be false positives.
HEADER_MAP = {
    "ABSTRACT": "ABSTRACT",
    "INTRODUCTION": "INTRODUCTION",
    "RELATED WORK": "RELATED WORK",
    "LITERATURE REVIEW": "RELATED WORK",
    "BACKGROUND": "RELATED WORK",
    "REFERENCES": "REFERENCES",
    "BIBLIOGRAPHY": "REFERENCES",
    "ACKNOWLEDGMENT": "ACKNOWLEDGMENT",
    "ACKNOWLEDGEMENTS": "ACKNOWLEDGMENT",
    "APPENDIX": "APPENDIX",
    "APPENDICES": "APPENDIX",
    "DECLARATION": "DECLARATION"
}

# --- 2. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)

# --- 3. HELPER FUNCTIONS ---
def roman_to_int(s):
    """Converts Roman numerals to integers."""
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper()
    total = 0
    prev_value = 0
    try:
        for char in reversed(s):
            if char not in roman_map: return None
            value = roman_map[char]
            if value < prev_value: total -= value
            else: total += value
            prev_value = value
        return total
    except: return None

def _parse_header_components(text):
    """
    Parses a line into (Number String, Phrase).
    Matches: "1. Introduction", "IV Results", etc.
    """
    pattern = re.compile(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)\s+([A-Z].*)$")
    match = pattern.match(text)
    if match:
        return match.group(1), match.group(3).strip