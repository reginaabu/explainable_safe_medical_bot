"""
utils/phi_scrub.py — HIPAA Safe Harbour PHI scrubbing for user queries.

Replaces the HIPAA Safe Harbour identifiers that can appear in free-text
medical questions with neutral placeholders before any text is sent to an
external API or retrieval index.

Covered identifier categories (regex):
  SSN, PHONE, FAX, EMAIL, IP, URL, ZIP, DATE, AGE>89, MRN, NAME (via
  name-prefix patterns), DEVICE ID / LICENSE / ACCOUNT numbers.

Optional NER pass: if spaCy en_core_web_sm is installed, PERSON / GPE / LOC
entities are also replaced. The NER pass degrades silently if the model is
not available — regex scrubbing still runs.

Usage:
    from utils.phi_scrub import scrub

    result = scrub("My name is John Smith, DOB 12/03/1981, phone 555-123-4567")
    # result.text  -> "[NAME], DOB [DATE], phone [PHONE]"
    # result.found -> ["NAME", "DATE", "PHONE"]
"""
import re
from typing import NamedTuple


class ScrubResult(NamedTuple):
    text: str          # scrubbed version, safe to send to external APIs
    found: list        # list of category strings that were detected, e.g. ["PHONE", "EMAIL"]


# ── Placeholder tokens ────────────────────────────────────────────────────────
_PH = {
    "SSN":    "[SSN]",
    "PHONE":  "[PHONE]",
    "EMAIL":  "[EMAIL]",
    "IP":     "[IP_ADDR]",
    "URL":    "[URL]",
    "ZIP":    "[ZIP]",
    "DATE":   "[DATE]",
    "AGE":    "[AGE]",
    "MRN":    "[MRN]",
    "NAME":   "[NAME]",
    "ID":     "[ID]",
    "PERSON": "[PERSON]",
    "GPE":    "[LOCATION]",
    "LOC":    "[LOCATION]",
    "FAC":    "[LOCATION]",
}

# ── Ordered regex patterns ─────────────────────────────────────────────────────
# Order matters: more-specific patterns first to prevent partial replacements.
_PATTERNS: list[tuple[str, re.Pattern]] = [

    # 1. Social Security Numbers  NNN-NN-NNNN  or  NNNNNNNNN
    ("SSN", re.compile(
        r'\b\d{3}[-\s]\d{2}[-\s]\d{4}\b'
        r'|\b\d{9}\b',          # 9-digit run (broad — order before phone)
    )),

    # 2. Phone / Fax  (US formats + international with country code)
    ("PHONE", re.compile(
        r'\b(?:\+?1[-.\s]?)?'
        r'(?:\(?\d{3}\)?[-.\s]?)'
        r'\d{3}[-.\s]?\d{4}\b',
    )),

    # 3. Email addresses
    ("EMAIL", re.compile(
        r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
    )),

    # 4. IPv4 addresses
    ("IP", re.compile(
        r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
        r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
    )),

    # 5. URLs
    ("URL", re.compile(
        r'https?://[^\s]+|www\.[^\s]+',
        re.IGNORECASE,
    )),

    # 6. Dates  — MM/DD/YYYY, DD-MM-YYYY, YYYY-MM-DD, "March 5 1992", "5th Jan 1990"
    ("DATE", re.compile(
        r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b'
        r'|\b\d{4}[-/]\d{2}[-/]\d{2}\b'
        r'|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?'
        r'|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?'
        r'|\b\d{1,2}(?:st|nd|rd|th)?\s+'
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?'
        r'|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\.?(?:,?\s+\d{4})?',
        re.IGNORECASE,
    )),

    # 7. Ages over 89  (HIPAA Safe Harbour: exact ages >89 are identifying)
    ("AGE", re.compile(
        r'\b(?:age[d]?\s+(?:of\s+)?|(?:I\s+am|he\s+is|she\s+is|they\s+are)\s+)'
        r'(9\d|[1-9]\d{2,})\s*(?:years?\s*(?:old)?|y\.?o\.?|yrs?\.?)',
        re.IGNORECASE,
    )),

    # 8. US ZIP codes  (5-digit or ZIP+4); placed after SSN to avoid collision
    ("ZIP", re.compile(
        r'\b\d{5}(?:-\d{4})?\b',
    )),

    # 9. Medical Record / Patient ID numbers (MRN)
    ("MRN", re.compile(
        r'\b(?:MRN|patient\s*(?:id|number|#)|medical\s*record\s*(?:number|#|no\.?))'
        r'\s*[:#]?\s*[A-Z0-9]{4,20}\b',
        re.IGNORECASE,
    )),

    # 10. Device serials, license numbers, account numbers
    ("ID", re.compile(
        r'\b(?:serial\s*(?:number|#|no\.?)|license\s*(?:number|#|no\.?)|'
        r'device\s*(?:id|serial)|account\s*(?:number|#|no\.?)|'
        r'policy\s*(?:number|#|no\.?))'
        r'\s*[:#]?\s*[A-Z0-9\-]{4,20}\b',
        re.IGNORECASE,
    )),

    # 11. Free-text names introduced by common prefix phrases
    #     e.g.  "My name is John Smith"  "patient: Jane Doe"  "I am Mary Johnson"
    ("NAME", re.compile(
        r'(?:my name is|I am|patient(?:\s*name)?[:\s]+|name[:\s]+|for\s+)'
        r'\s*([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})',
        re.IGNORECASE,
    )),
]


# ── Optional spaCy NER pass ───────────────────────────────────────────────────
def _spacy_pass(text: str, found: list) -> str:
    """
    Replace PERSON / GPE / LOC / FAC / DATE entities using spaCy en_core_web_sm.
    Degrades silently if the model is not installed.
    """
    try:
        import spacy
        nlp = spacy.load(
            "en_core_web_sm",
            disable=["tok2vec", "tagger", "parser", "senter",
                     "attribute_ruler", "lemmatizer"],
        )
        doc = nlp(text)
        # Build replacements in reverse order so char offsets stay valid
        replacements = sorted(
            [
                (ent.start_char, ent.end_char, ent.label_)
                for ent in doc.ents
                if ent.label_ in _PH and ent.text not in _PH.values()
            ],
            reverse=True,
        )
        for start, end, label in replacements:
            ph = _PH[label]
            if ph not in text[max(0, start - 1):end + 1]:   # avoid double-replacing
                text = text[:start] + ph + text[end:]
                if label not in found:
                    found.append(label)
    except Exception:
        pass   # model not installed — regex scrubbing already ran
    return text


# ── Public API ────────────────────────────────────────────────────────────────
def scrub(text: str) -> ScrubResult:
    """
    Scan *text* for HIPAA Safe Harbour identifiers and replace with placeholders.

    Returns a ScrubResult(text, found) where:
      - text  : scrubbed string, safe to transmit to external APIs
      - found : list of detected category names (empty ⇒ no PHI detected)

    The function is side-effect free: the original string is never modified.
    """
    if not text or not text.strip():
        return ScrubResult(text=text, found=[])

    scrubbed = text
    found: list[str] = []

    for label, pattern in _PATTERNS:
        replaced = pattern.sub(_PH.get(label, f"[{label}]"), scrubbed)
        if replaced != scrubbed:
            if label not in found:
                found.append(label)
            scrubbed = replaced

    # Optional NER enrichment (PERSON, GPE, LOC)
    scrubbed = _spacy_pass(scrubbed, found)

    return ScrubResult(text=scrubbed, found=found)
