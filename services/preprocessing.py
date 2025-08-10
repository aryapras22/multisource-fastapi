from __future__ import annotations

import html
import re
import unicodedata
from typing import Literal, Optional, TypeAlias

# ---------- Low-level building blocks ----------
NormalizationForm: TypeAlias = Literal["NFC", "NFD", "NFKC", "NFKD"]


def normalize_unicode(text: str, *, form: NormalizationForm = "NFKC") -> str:
    """
    Normalize Unicode and unescape HTML entities.

    - Applies `unicodedata.normalize(form, text)`
    - Unescapes HTML entities (&amp;, &quot;, etc.)
    - Standardizes whitespace: convert newlines/tabs to space -> collapse spaces -> strip

    Example:
        >>> normalize_unicode("A\u00a0B &amp; C\\n\\t")
        'A B & C'
    """
    text = html.unescape(text or "")
    text = unicodedata.normalize(form, text)
    text = re.sub(r"[\r\n\t]", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """
    Remove crude HTML tags (if you fed raw HTML).

    Example:
        >>> strip_html("<p>Hello <b>world</b></p>")
        'Hello world'
    """
    return HTML_TAG_RE.sub(" ", text)


URL_RE = re.compile(
    r"""
    \b
    (?:https?://|www\.)                 # http(s):// or www.
    [^\s<>")]+                          # run of non-space/closing tokens
    """,
    flags=re.X | re.I,
)


def remove_urls(text: str) -> str:
    """
    Remove URLs.

    Example:
        >>> remove_urls("See https://example.com and www.foo.bar!")
        'See  and !'
    """
    return URL_RE.sub(" ", text)


EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b")


def remove_emails(text: str) -> str:
    """
    Remove emails.

    Example:
        >>> remove_emails("Contact me at john.doe@mail.com please")
        'Contact me at  please'
    """
    return EMAIL_RE.sub(" ", text)


# Phone numbers: keep it robust but conservative.
# Strategy: replace spans that contain at least 7 digits possibly separated by () - . spaces
PHONE_SPAN_RE = re.compile(
    r"""
    (?<!\w)                             # left boundary
    (?:
        (?:\+?\d{1,3}[\s().-]*)?        # optional country code
        (?:\d[\s().-]*){6,}             # at least 6 more digits w/ separators (>=7 total)
    )
    (?!\w)                              # right boundary
    """,
    flags=re.X,
)


def remove_phone_numbers(text: str) -> str:
    """
    Remove phone-like sequences (>=7 digits across separators).

    Example:
        >>> remove_phone_numbers("Call +62 812-3456-7890 or (021) 555-1234.")
        'Call  or .'
    """
    return PHONE_SPAN_RE.sub(" ", text)


# Emoji / pictographs / dingbats. Broad but safe ranges.
EMOJI_RE = re.compile(
    "["  # start char class
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f700-\U0001f77f"  # alchemical
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001faff"
    "\U00002700-\U000027bf"  # dingbats
    "\U00002600-\U000026ff"  # misc symbols
    "\U00002b00-\U00002bff"  # arrows etc.
    "]+",
    flags=re.UNICODE,
)


def remove_emojis(text: str) -> str:
    """
    Remove emojis and pictographs.

    Example:
        >>> remove_emojis("So happy 😄🚀!")
        'So happy !'
    """
    return EMOJI_RE.sub(" ", text)


def collapse_whitespace(text: str) -> str:
    """
    Collapse multiple spaces and trim ends.

    Example:
        >>> collapse_whitespace("  a   b  ")
        'a b'
    """
    return re.sub(r"\s{2,}", " ", text).strip()


# Punctuation / numbers / special chars
PUNCT_NUM_SYM_RE = re.compile(r"[^A-Za-z\s]")


def remove_punct_numbers_symbols(text: str) -> str:
    """
    Remove everything except letters and whitespace (English A–Z),
    then collapse whitespace.

    Example:
        >>> remove_punct_numbers_symbols("Hello, 2025—OK?! :)")
        'Hello OK'
    """
    return collapse_whitespace(PUNCT_NUM_SYM_RE.sub("", text))


# ---------- Language detection ----------


def is_english(
    text: str, *, min_chars: int = 20, threshold_ratio: float = 0.85
) -> bool:
    """
    True if text is English (best-effort).
    - If `langdetect` is available, use it.
    - Else fallback: ratio of ASCII letters/space vs. all letters >= threshold_ratio.

    Parameters:
        min_chars: too-short texts default to True (can't reliably detect).
        threshold_ratio: fallback heuristic threshold.

    Examples (heuristic fallback shown):
        >>> is_english("I love clean NLP pipelines.")  # doctest: +SKIP
        True
        >>> is_english("Saya sangat menyukai pemrosesan bahasa alami.")  # doctest: +SKIP
        False
    """
    t = (text or "").strip()
    if len(t) < min_chars:
        return True
    try:
        from langdetect import detect  # type: ignore

        # langdetect can throw if text is weird; wrap in try/except
        try:
            return detect(t) == "en"
        except Exception:
            pass
    except Exception:
        pass

    letters = re.findall(r"[A-Za-z]", t)
    if not letters:
        return False
    ascii_letters_or_space = re.findall(r"[A-Za-z\s]", t)
    return (len(ascii_letters_or_space) / max(len(t), 1)) >= threshold_ratio


# ---------- Domain-specific helpers ----------

# News boilerplate patterns: datelines + newsroom phrases
NEWS_DATELINE_RE = re.compile(
    r"""(?ix)
    ^                                   # start of text
    (?:[A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)*)  # CITY or CITY CITY
    \s*\([A-Za-z .&-]+\)\s*-\s*         # (Reuters) -  /  (AP) -  etc.
    """
)

NEWS_TRAILER_RE = re.compile(
    r"""(?xi)
    (?:^|\s)(?:Reporting\s+by|Edited\s+by|Writing\s+by|With\s+reporting\s+by|Additional\s+reporting\s+by)
    [^.]*\.
    """
)

NEWS_SOURCE_PHRASES = (
    "— reuters",
    "— ap",
    "— associated press",
    "— cnn",
    "— bbc",
    "— bloomberg",
    "(reuters)",
    "(ap)",
    "(afp)",
    "(antaranews)",
    "source: reuters",
    "source: ap",
    "copyright",
    "all rights reserved",
)


def remove_news_boilerplate(text: str) -> str:
    """
    Remove common news datelines and boilerplate/trailer credits.

    Examples:
        >>> remove_news_boilerplate("JAKARTA (Reuters) - Govt acts. Reporting by John Doe.")
        'Govt acts.'
        >>> remove_news_boilerplate("The story — Reuters")
        'The story'
    """
    t = NEWS_DATELINE_RE.sub("", text)
    t = NEWS_TRAILER_RE.sub(" ", t)
    # drop simple phrases
    lowered = t.lower()
    for phrase in NEWS_SOURCE_PHRASES:
        lowered = lowered.replace(phrase, " ")
    return collapse_whitespace(lowered)


# ---------- Tweet-specific helpers ----------

MENTION_RE = re.compile(r"(?<!\w)@\w+")
HASHTAG_RE = re.compile(r"(?<!\w)#(\w+)")
CASHTAG_RE = re.compile(r"(?<!\w)\$\w+")
RT_RE = re.compile(r"(?i)^\s*RT\s+:?\s*")


def clean_tweet_text(text: str, *, lower: bool = False) -> str:
    """
    Clean tweets:
      - Unicode/HTML normalize
      - Remove URLs, emails, phone numbers
      - Remove RT prefix, mentions, cashtags
      - Convert hashtags to plain words (keep the keyword)
      - Remove emojis
      - Remove remaining punctuation/numbers/symbols
      - Collapse whitespace

    Example:
        >>> clean_tweet("RT @user: Check $TSLA 🚀 https://x.com #AI #NLP!!!")
        'Check TSLA AI NLP'
    """
    t = normalize_unicode(text)
    t = remove_urls(t)
    t = remove_emails(t)
    t = remove_phone_numbers(t)
    t = RT_RE.sub("", t)
    t = MENTION_RE.sub(" ", t)
    t = CASHTAG_RE.sub(lambda m: " " + m.group(0)[1:] + " ", t)  # keep ticker as token
    t = HASHTAG_RE.sub(lambda m: " " + m.group(1) + " ", t)  # keep hashtag word
    t = remove_emojis(t)
    t = remove_punct_numbers_symbols(t)
    if lower:
        t = t.lower()
    return collapse_whitespace(t)


# ---------- Pipelines ----------


def clean_news_content(text: str) -> str:
    """
    Clean news text:
      1) Unicode/HTML normalize
      2) Strip crude HTML tags (if any)
      3) Remove URLs, emails, phone numbers
      4) Remove news boilerplate/datelines
      5) Remove punctuation, numbers, special chars
      6) Collapse whitespace

    Example:
        >>> s = "JAKARTA (Reuters) - Govt plans 2025. Read: https://ex.com. Reporting by Jane."
        >>> clean_news(s)
        'Govt plans Read'
    """
    t = normalize_unicode(text)
    t = strip_html(t)
    t = remove_urls(t)
    t = remove_emails(t)
    t = remove_phone_numbers(t)
    t = remove_news_boilerplate(t)
    t = remove_punct_numbers_symbols(t)
    return collapse_whitespace(t)


def clean_review(text: str) -> Optional[str]:
    """
    Clean app review text (English only):
      - If not English (best-effort), return None (signal: skip)
      - Normalize, remove URLs/emails/phones/emojis
      - Remove punctuation/numbers/symbols
      - Collapse whitespace

    Example:
        >>> clean_app_review("Love this app!!! 10/10 😍  Visit: https://ex.com")
        'Love this app'
        >>> clean_app_review("Aplikasinya bagus sekali")  # non-English -> None
        None
    """
    if not is_english(text):
        return None
    t = normalize_unicode(text)
    t = remove_urls(t)
    t = remove_emails(t)
    t = remove_phone_numbers(t)
    t = remove_emojis(t)
    t = remove_punct_numbers_symbols(t)
    return collapse_whitespace(t)
