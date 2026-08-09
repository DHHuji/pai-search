# ═══════════════════════════════════════════════════════════════════════════════
#  PAI Corpus – Pattern Search Interface  v3
#  Sources docs from the Recordings sheet in Google Sheets.
#  Searches only italic text runs (the actual transcription).
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import streamlit.components.v1 as components
import re
import io
import html as html_lib
import unicodedata
import json
import time
import threading
import faulthandler
import sys
from pathlib import Path

# If the process ever segfaults again, dump whatever Python stack each thread
# was on to stderr (visible in the Streamlit Cloud logs) *before* the crash
# takes the process down. Without this, a native crash leaves zero trace —
# which is exactly what happened previously: the logs showed nothing but
# "Segmentation fault" with no indication of which thread/call caused it.
faulthandler.enable(file=sys.stderr, all_threads=True)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# ── Declare bridge component (zero-height iframe that relays right-click tags) ─
_TAG_BRIDGE = components.declare_component(
    "pai_tag_bridge",
    path=str(Path(__file__).parent / "tagbridge"),
)

# ── Declare search-bar component (input + PAI keyboard) ───────────────────────
_SEARCH_BAR = components.declare_component(
    "pai_search_bar",
    path=str(Path(__file__).parent / "searchbar"),
)

st.set_page_config(page_title="PAI Corpus Search", layout="wide", page_icon="◌")

# ── CSS ─────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Source+Serif+4:ital,wght@0,300;0,600;1,300&display=swap');

:root {
  --sky-50:  #f0f8ff;
  --sky-100: #daeeff;
  --sky-200: #b8deff;
  --sky-400: #60aee8;
  --sky-600: #2075c7;
  --sky-800: #0d3f75;
  --ink:     #1a2b3c;
}

html, body, .stApp { background: var(--sky-50) !important; }

/* ── Radio button labels ── */
div[data-testid="stRadio"] label p,
div[data-testid="stRadio"] label span {
  color: var(--ink) !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.9rem !important;
  font-weight: 500 !important;
}

/* ── Header ── */
.pai-header { text-align: center; padding: 2.5rem 0 1rem; }
.pai-header .title {
  font-family: 'Source Serif 4', serif;
  font-size: 2.6rem; font-weight: 600;
  color: var(--sky-800); letter-spacing: -0.02em;
}
.pai-header .subtitle {
  font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem;
  color: var(--sky-600); letter-spacing: 0.14em; margin-top: 0.4rem; text-transform: uppercase;
}

/* ── Legend pills ── */
.legend-row { display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:1.2rem; justify-content:center; }
.legend-pill {
  background: var(--sky-100); border: 1px solid var(--sky-200);
  border-radius: 999px; padding: 0.25rem 0.9rem;
  font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; color: var(--sky-800);
}
.legend-pill b { color: var(--sky-600); }

/* ── Main search input ── */
div[data-testid="stTextInput"] input {
  border-radius: 12px !important; border: 2px solid var(--sky-200) !important;
  padding: 0.7rem 1.2rem !important;
  font-family: 'IBM Plex Mono', monospace !important; font-size: 1.15rem !important;
  background: var(--sky-50) !important; color: var(--ink) !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
}
div[data-testid="stTextInput"] input:focus {
  border-color: var(--sky-600) !important;
  box-shadow: 0 0 0 3px rgba(32,117,199,0.12) !important;
  background: white !important;
}

/* ── Feature value chips ──
   Mirrors how Google Sheets renders a native multi-select cell, so a value
   tagged in the sheet and the same value shown in the app look alike. */
.val-chip {
  display: inline-block; background: #eef4fb; border: 1px solid #b8deff;
  border-radius: 999px; padding: 1px 10px; margin: 1px 2px;
  font-family: 'IBM Plex Mono', monospace; font-size: .8rem;
  color: #0d3f75; white-space: nowrap; line-height: 1.6;
}
.val-chip.is-empty {
  background: #f5f5f5; border-color: #ddd; color: #999; font-style: italic;
}

/* ── Active-filter banner (shown when filters are set) ── */
.filter-banner {
  background: #e3f2fd; border: 1.5px solid #90caf9; border-radius: 10px;
  padding: 7px 14px; margin: 2px 0 8px;
  font-family: 'IBM Plex Mono', monospace; font-size: .86rem;
  color: #0d3f75; line-height: 1.5;
}
.filter-banner b { color: #1565c0; }

/* ── Collapsible "more wildcards" block inside the legend row ── */
details.legend-more { display: inline-block; vertical-align: top; }
details.legend-more > summary {
  display: inline-block; cursor: pointer; list-style: none;
  background: #eef4fb; border: 1px solid #b8deff; border-radius: 999px;
  padding: 3px 12px; font-family: 'IBM Plex Mono', monospace;
  font-size: .78rem; color: #0d3f75; user-select: none;
}
details.legend-more > summary::-webkit-details-marker { display: none; }
details.legend-more > summary:hover { background: #daeeff; }
details.legend-more[open] > summary { background: #daeeff; }
details.legend-more .legend-more-body {
  display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px;
}

/* ── Advanced options expander ── */
div[data-testid="stExpander"] > details {
  background: var(--sky-100) !important;
  border: 1.5px solid var(--sky-200) !important;
  border-radius: 12px !important;
}
div[data-testid="stExpander"] > details > summary {
  background: var(--sky-100) !important;
  color: var(--sky-800) !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.88rem !important;
}
/* Streamlit newer versions nest the label inside spans/p — force color */
div[data-testid="stExpander"] > details > summary *,
div[data-testid="stExpander"] > details > summary span,
div[data-testid="stExpander"] > details > summary p,
div[data-testid="stExpander"] > details > summary svg {
  color: var(--sky-800) !important;
  fill:  var(--sky-800) !important;
}
div[data-testid="stExpander"] > details[open] > div {
  background: var(--sky-50) !important;
  border-top: 1px solid var(--sky-200) !important;
  padding: 1rem 1.2rem !important;
}
/* Radio labels inside advanced panel */
div[data-testid="stExpander"] label,
div[data-testid="stExpander"] p {
  color: var(--ink) !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.85rem !important;
}

/* ── Search button ── */
div[data-testid="stButton"] button[kind="primary"] {
  background: var(--sky-600) !important; color: white !important;
  border-radius: 12px !important; font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.9rem !important; border: none !important; padding: 0.6rem 1.5rem !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
  background: var(--sky-800) !important;
}
/* ── Secondary / Clear button ── */
div[data-testid="stButton"] button[kind="secondary"] {
  background: var(--sky-600) !important; color: white !important;
  border: none !important; border-radius: 12px !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.9rem !important; padding: 0.6rem 1.5rem !important;
}
div[data-testid="stButton"] button[kind="secondary"]:hover {
  background: var(--sky-800) !important;
}

/* ── Result expanders ── */
div[data-testid="stExpander"].result-expander > details {
  background: white !important;
  border: 1.5px solid var(--sky-200) !important;
  border-radius: 12px !important;
  margin-bottom: 0.5rem !important;
  box-shadow: 0 2px 8px rgba(32,117,199,0.08) !important;
}
div[data-testid="stExpander"].result-expander > details > summary svg {
  display: none !important;
}

/* ── Badges ── */
.doc-card-meta {
  font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem;
  color: var(--sky-600); display: flex; gap: 1.2rem; flex-wrap: wrap; margin-bottom: 0.7rem;
}
.badge { background: var(--sky-100); border-radius: 999px; padding: 0.15rem 0.7rem; color: var(--sky-800); font-weight: 600; }
.badge-green { background: #d4f7e0; color: #1a6e38; border-radius: 999px; padding: 0.15rem 0.7rem; font-weight: 600; }

/* ── Word chips ── */
.word-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
.word-chip {
  background: var(--sky-50); border: 1px solid var(--sky-200); border-radius: 8px;
  padding: 0.25rem 0.7rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem; color: var(--ink);
}
.word-chip mark { background: #b6f2c8; border-radius: 2px; padding: 0 1px; font-weight: 700; color: #0d4a22; }

/* ── Full document viewer ── */
.full-doc {
  background: white; border: 1px solid var(--sky-200); border-radius: 12px;
  padding: 1.6rem 2rem; margin-top: 0.5rem;
  font-family: 'Source Serif 4', serif; font-size: 0.97rem; line-height: 1.9; color: var(--ink);
  box-shadow: 0 2px 10px rgba(32,117,199,0.07);
  max-height: 65vh; overflow-y: auto; word-break: break-word;
}
.full-doc p { margin: 0.35rem 0; }
.full-doc mark { background: #b6f2c8; border-radius: 3px; padding: 0 2px; font-weight: 700; color: #0d4a22; }
.full-doc .doc-header-section {
  color: #8899aa; font-size: 0.88rem;
  border-bottom: 1px solid var(--sky-100); margin-bottom: 1rem; padding-bottom: 0.8rem;
}
.full-doc .doc-header-section p { margin: 0.1rem 0; }
.italic-run { font-style: italic; }
.body-label { color: #556677; font-weight: 600; font-style: normal; font-size: 0.9rem; margin-top: 0.6rem; }

/* ── Stats bar ── */
.stats-bar {
  background: var(--sky-100); border: 1px solid var(--sky-200); border-radius: 10px;
  padding: 0.6rem 1.2rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem;
  color: var(--sky-800); margin-bottom: 1rem; display: flex; gap: 1.5rem;
}

#MainMenu, footer { visibility: hidden; }

/* ── Ensure all Streamlit alert boxes always have readable dark text ── */
div[data-testid="stAlert"],
div[data-testid="stAlert"] p,
div[data-testid="stAlert"] span,
div[data-testid="stAlert"] li,
div[data-testid="stAlert"] strong,
div[data-testid="stAlert"] em {
  color: #1a2b3c !important;
}
/* Warning specifically — yellow bg, force dark text */
div[data-testid="stAlert"][data-baseweb="notification"] {
  color: #1a2b3c !important;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
#  LINGUISTIC SETS  (from official PAI transcription table)
# ════════════════════════════════════════════════════════════════════════════════

CONSONANTS: set = {
    'b','t','ṯ','ǧ','ž','ḥ','x','d','ḏ','r','z','s','š','ṣ','ḍ','ẓ','ṭ',
    'ġ','f','q','g','k','č','ḳ','l','m','n','h','w','y','ʿ','ʾ','p',
    # Velarised / emphatic variants. These MUST be here: without them the 'C'
    # (any consonant) wildcard silently skipped every word containing one, so
    # a pattern like 'CvC' returned no match for 'ḅal', 'ṃan', 'ḷaw', 'ṛas'.
    # They are also members of BILABIALS / LAMNR / EMPHATICS below, and every
    # member of those sets must be a consonant.
    'ḅ','ṃ','ḷ','ṛ','ḏ̣',
}
SHORT_VOWELS: set = {'a', 'e', 'i', 'u', 'o', 'ə'}
LONG_VOWELS:  set = {'ā', 'ē', 'ī', 'ō', 'ū', 'ā̈', 'ɑ̄'}  # ɑ̄ = variant encoding of ā̈
VOWELS:       set = SHORT_VOWELS | LONG_VOWELS
DIPHTHONGS: list = ['aw','ay','ōw','ēy']

GUTTURALS: set  = {'h','x','ḥ','ʿ','ġ','q'}          # G wildcard
EMPHATICS: set  = {'ḍ','ḏ̣','ẓ','ṣ'}                  # E wildcard
BILABIALS: set  = {'b','ḅ','m','ṃ','f'}               # B wildcard (bilabials)
LAMNR:     set  = {'l','ḷ','m','ṃ','r','ṛ','n'}       # L wildcard (liquids + nasals)
#  NOTE: '(' / ')' are intentionally excluded — the transcription convention
#  uses them for inline optional/elided sounds glued directly onto a word
#  with no space, e.g. "(yi)twaṣṣafiš" or "(i)lli". Treating them as
#  delimiters split these into two separate words ("i" + "lli") instead of
#  the single intended word.
WORD_DELIM = re.compile(r'[\s,.:;!?\[\]{}"\'—–#]+|ʿ\u203Fʿ')


def _alts(items) -> str:
    return '(?:' + '|'.join(re.escape(c) for c in sorted(items, key=len, reverse=True)) + ')'

_C     = _alts(CONSONANTS)
_V     = _alts(VOWELS)
_S     = _alts(SHORT_VOWELS)   # v  = short vowel wildcard
_L     = _alts(LONG_VOWELS)    # v̄  = long  vowel wildcard (v + combining macron)
_D     = _alts(DIPHTHONGS)
_G     = _alts(GUTTURALS)
_E     = _alts(EMPHATICS)
_B     = _alts(BILABIALS)       # B  = bilabial wildcard
_LAMNR = _alts(LAMNR)           # L  = liquids + nasals (lmnr) wildcard


def _pattern_char_to_regex(ch: str) -> str:
    """Convert a single pattern character/wildcard to a regex fragment."""
    if   ch == 'C': return _C
    elif ch == 'V': return _V
    elif ch == 'v': return _S   # v  = short vowel  (was S)
    # Note: v̄ (long vowel) is two code points (v + combining macron) and is
    # handled by the caller (_tok_to_regex / pattern_to_regex loop) before
    # this function is reached, so it never arrives here as a bare 'v'.
    elif ch == 'D': return _D
    elif ch == 'G': return _G
    elif ch == 'E': return _E
    elif ch == 'B': return _B       # B  = bilabials (b ḅ m ṃ f)
    elif ch == 'L': return _LAMNR   # L  = liquids + nasals (l ḷ m ṃ r ṛ n)
    elif ch == '$': return '.*?'
    else:           return re.escape(ch)


def _tok_to_regex(s: str) -> str:
    """
    Convert an arbitrary token string (a single character or an alternatives-
    group alternative such as 'v̄' or 'ā') to a regex fragment.

    v̄ is the long-vowel wildcard.  It is two Unicode code points (v +
    COMBINING MACRON ABOVE, U+0304) so callers that iterate code-point by
    code-point would split it incorrectly; this helper keeps the pair together.
    """
    result = []
    i = 0
    while i < len(s):
        ch = s[i]
        # v followed by any combining character → long-vowel wildcard (v̄)
        if (ch == 'v'
                and i + 1 < len(s)
                and unicodedata.category(s[i + 1]) == 'Mn'):
            result.append(_L)
            i += 2
        else:
            result.append(_pattern_char_to_regex(ch))
            i += 1
    return ''.join(result)


def pattern_to_regex(pattern: str) -> re.Pattern:
    """
    Convert a PAI pattern string to a compiled regex.

    Wildcards : C=consonant  V=vowel (all)  v=short vowel  v̄=long vowel
                D=diphthong  G=guttural  E=emphatic
                B=bilabial (b ḅ m ṃ f)  L=liquid/nasal (l ḷ m ṃ r ṛ n)
                $=any characters (0 or more)
    Anchors   : ^ at start = word must begin here
                # at end   = word must end here
    Groups    : (x,y,z) = exactly one of the comma-separated alternatives
                e.g. (q,ʾ)tv matches qtv and ʾtv
                Each alternative can be a multi-character string or a wildcard.
                A trailing empty alternative (just leave it blank after the
                last comma) makes the whole group optional — the letter may
                be present OR absent entirely.
                e.g. (q,k,)tb matches qtb, ktb, AND tb (letter dropped).
    """
    pattern = unicodedata.normalize('NFC', pattern)
    anchor_start = pattern.startswith('^')
    anchor_end   = pattern.endswith('#')
    core = pattern
    if anchor_start: core = core[1:]
    if anchor_end:   core = core[:-1]

    parts = []
    i = 0
    while i < len(core):
        ch = core[i]
        if ch == '(':
            # Find the matching closing paren
            j = core.find(')', i)
            if j == -1:
                raise re.error("Unmatched '(' in pattern")
            inner = core[i + 1:j]
            # Split on commas and convert each alternative via _tok_to_regex so
            # that v̄ (two code points) inside a group is treated as one token.
            alternatives = [a.strip() for a in inner.split(',')]
            alt_regexes = [_tok_to_regex(alt) for alt in alternatives]
            parts.append('(?:' + '|'.join(alt_regexes) + ')')
            i = j + 1
        else:
            # Handle v̄ (v + combining macron) as the long-vowel wildcard.
            # It occupies two code points so consume both here.
            if (ch == 'v'
                    and i + 1 < len(core)
                    and unicodedata.category(core[i + 1]) == 'Mn'):
                parts.append(_L)
                i += 2
            else:
                parts.append(_pattern_char_to_regex(ch))
                i += 1

    rx_str = ''.join(parts)
    if anchor_start: rx_str = '^' + rx_str
    if anchor_end:   rx_str = rx_str + '$'
    return re.compile(rx_str, re.UNICODE)


def tokenize(text: str) -> list:
    return [w for w in WORD_DELIM.split(unicodedata.normalize('NFC', text)) if w.strip()]


def parse_sequence_pattern(pattern: str) -> list[re.Pattern]:
    """
    Split a search pattern on spaces and return one compiled regex per word-slot.
    A space means "word boundary" — e.g. "g# ^G" matches a word ending in 'g'
    immediately followed by a word starting with a guttural consonant.
    Single-word patterns (no space) return a one-element list.
    ^ and # anchors work per sub-pattern, not only at the very start/end of the
    whole string.
    """
    parts = pattern.strip().split()
    if not parts:
        raise re.error("Empty pattern")
    return [pattern_to_regex(p) for p in parts]


def root_to_pattern(root_input: str) -> str:
    """
    Convert a Semitic root string into a $-separated search pattern.
    Each letter (or alternatives group) is surrounded by $ wildcards so that
    the pattern matches any word containing the root letters in order with
    any characters between them.

    Examples
    --------
    'ktb'          → '$k$t$b$'
    '(q,ʾ,k)tv'   → '$(q,ʾ,k)$t$v$'
    'k t b'        → '$k$t$b$'   (spaces ignored)

    A group with a trailing empty alternative, e.g. '(q,k,)tb', makes that
    letter optional — matches words with q, k, OR neither letter at all
    (qtb, ktb, and tb all match).
    """
    root_input = unicodedata.normalize('NFC', root_input.strip())
    letters = []
    i = 0
    while i < len(root_input):
        ch = root_input[i]
        if ch in (' ', '\t'):
            i += 1
            continue
        if ch == '(':
            j = root_input.find(')', i)
            if j == -1:
                letters.append(ch)
                i += 1
            else:
                letters.append(root_input[i:j + 1])
                i = j + 1
        else:
            letters.append(ch)
            i += 1
    if not letters:
        return ''
    return '$' + '$'.join(letters) + '$'


def _subpattern_position(rx: re.Pattern, ui_position: str) -> str:
    """Position to use with match_word() for a sequence sub-pattern.
    Anchored sub-patterns (^ / $) handle positioning via the regex itself,
    so we pass 'anywhere'.  Un-anchored sub-patterns use the UI radio value.
    """
    anchor_s, anchor_e = _is_word_anchored(rx)
    return 'anywhere' if (anchor_s or anchor_e) else ui_position


def _match_sequence(words: list, sub_rxs: list, ui_position: str):
    """Check if len(words) consecutive words each match their sub-regex.
    Returns list of (word, hits) if the full sequence matches, else [].
    """
    result = []
    for word, rx in zip(words, sub_rxs):
        pos  = _subpattern_position(rx, ui_position)
        hits = match_word(word, rx, pos)
        if not hits:
            return []
        result.append((word, hits))
    return result


def match_word(word: str, rx: re.Pattern, position: str) -> list:
    out = []
    for m in rx.finditer(word):
        s, e, wl = m.start(), m.end(), len(word)
        if   position == 'anywhere':                       out.append(m)
        elif position == 'start'   and s == 0:             out.append(m)
        elif position == 'end'     and e == wl:            out.append(m)
        elif position == 'middle'  and 0 < s and e < wl:  out.append(m)
    return out


def highlight_word(word: str, matches: list) -> str:
    out = word
    for m in sorted(matches, key=lambda x: x.start(), reverse=True):
        out = out[:m.start()] + f'<mark>{out[m.start():m.end()]}</mark>' + out[m.end():]
    return out


def highlight_in_text(text: str, rx: re.Pattern) -> str:
    return rx.sub(lambda m: f'<mark>{m.group()}</mark>', text)


_MARK_STYLE = (
    'background:#b6f2c8;border-radius:3px;padding:0 2px;'
    'font-weight:700;color:#0d4a22'
)

_TURN_MARKER_HL = re.compile(r'^[-.][ \t\u00a0]')

def _is_transcription_para(para_html: str) -> bool:
    """Same structural test used by extract_transcription_text."""
    text = html_lib.unescape(re.sub(r'<[^>]+>', '', para_html)).strip()
    non_ascii = re.findall(r'[^\x00-\x7F]', text)
    # Require ≥8 % of characters to be non-ASCII: PAI transcription lines are
    # dense with ā/ī/ħ/ʿ/š/ġ… (~20–40 %), while English summaries that happen
    # to contain a single place-name like "Rīḥa" are only ~1–2 %.
    if not non_ascii or len(non_ascii) / len(text) < 0.08:
        return False
    return bool(_TURN_MARKER_HL.match(text) or text[:1].isdigit())

def _is_word_anchored(rx: re.Pattern) -> tuple[bool, bool]:
    """Return (anchor_start, anchor_end) based on the compiled regex pattern."""
    p = rx.pattern
    return p.startswith('^'), p.endswith('$')


def _highlight_text_nodes(fragment: str, rx: re.Pattern) -> str:
    """
    Highlight regex matches inside text nodes only (not inside HTML tags).
    Unescapes HTML entities and NFC-normalises each text node before matching,
    so characters like š / ī / ḥ are found regardless of how Google Docs
    encoded them in the export (entities, NFD decomposed, etc.).

    When the regex has ^ / $ word anchors, we tokenise the text node into
    whitespace-delimited words and run match_word() on each one — this
    matches the same semantics used in run_search() and correctly highlights
    patterns like ^di or kān# anywhere in the paragraph.
    """
    anchor_start, anchor_end = _is_word_anchored(rx)
    word_anchored = anchor_start or anchor_end

    parts = re.split(r'(<[^>]+>)', fragment)
    out = []
    for part in parts:
        if part.startswith('<'):
            out.append(part)
        elif not part:
            continue
        else:
            # Unescape HTML entities and normalise to NFC before regex search
            text = unicodedata.normalize('NFC', html_lib.unescape(part))

            if word_anchored:
                # ── Word-by-word matching (honours ^ / $ anchors) ──────────────
                # Determine position for match_word()
                if anchor_start and anchor_end:
                    pos = 'anywhere'   # whole-word match — match_word checks both ends implicitly
                elif anchor_start:
                    pos = 'start'
                else:
                    pos = 'end'

                # Tokenise preserving the inter-token separators so we can
                # reconstruct the original text with highlights.
                tokens  = WORD_DELIM.split(text)
                seps    = WORD_DELIM.findall(text)
                # Pad seps list so zip works cleanly
                while len(seps) < len(tokens):
                    seps.append('')

                result = []
                for tok, sep in zip(tokens, seps):
                    if not tok:
                        result.append(html_lib.escape(sep))
                        continue
                    hits = match_word(tok, rx, pos)
                    if hits:
                        result.append(
                            f'<mark style="{_MARK_STYLE}" data-word="{html_lib.escape(tok)}">'
                            f'{html_lib.escape(tok)}</mark>'
                        )
                    else:
                        result.append(html_lib.escape(tok))
                    result.append(html_lib.escape(sep))
                out.append(''.join(result))
            else:
                # ── Free match: run regex over the whole text node ─────────────
                result = []
                last = 0
                for m in rx.finditer(text):
                    result.append(html_lib.escape(text[last:m.start()]))
                    # Find the full whitespace-delimited word containing this match
                    w_start = m.start()
                    while w_start > 0 and not text[w_start - 1].isspace():
                        w_start -= 1
                    w_end = m.end()
                    while w_end < len(text) and not text[w_end].isspace():
                        w_end += 1
                    containing_word = html_lib.escape(text[w_start:w_end])
                    result.append(
                        f'<mark style="{_MARK_STYLE}" data-word="{containing_word}">'
                        f'{html_lib.escape(m.group())}</mark>'
                    )
                    last = m.end()
                result.append(html_lib.escape(text[last:]))
                out.append(''.join(result))
    return ''.join(out)

def _highlight_text_nodes_sequence(fragment: str, sub_rxs: list, ui_position: str) -> str:
    """
    Multi-word sequence highlighting for a single paragraph fragment.

    Unlike single-word highlighting, a multi-word pattern ("i# ^l") is only a
    real match when N *consecutive* words each satisfy their own sub-pattern
    in order. Highlighting each sub-pattern independently (the old behaviour)
    marked every word matching ANY sub-pattern anywhere in the paragraph —
    e.g. "i#" alone matched standalone "i" and every word ending in "i" such
    as "fi", even when no word starting with "l" followed it. This rebuilds
    the paragraph's word list (across formatting-tag boundaries) and only
    marks the words that are actually part of a valid adjacent sequence.
    """
    parts = re.split(r'(<[^>]+>)', fragment)
    n = len(sub_rxs)

    # Pass 1 — tokenize every text part, building a flat word list that spans
    # part boundaries (so a sequence can match across an inline tag).
    node_tokens: list[list[str]] = []
    node_seps:   list[list[str]] = []
    flat_words:  list[tuple[int, int, str]] = []   # (part_idx, token_idx, word)

    for idx, part in enumerate(parts):
        if not part or part.startswith('<'):
            node_tokens.append([])
            node_seps.append([])
            continue
        text   = unicodedata.normalize('NFC', html_lib.unescape(part))
        tokens = WORD_DELIM.split(text)
        seps   = WORD_DELIM.findall(text)
        while len(seps) < len(tokens):
            seps.append('')
        node_tokens.append(tokens)
        node_seps.append(seps)
        for t_idx, tok in enumerate(tokens):
            if tok:
                flat_words.append((idx, t_idx, tok))

    # Pass 2 — slide an N-word window across the flat list; only words inside
    # a window that satisfies the full sequence get marked for highlighting.
    highlight_map: dict[tuple[int, int], list] = {}
    for i in range(len(flat_words) - n + 1):
        window     = flat_words[i:i + n]
        words_only = [w for (_, _, w) in window]
        seq        = _match_sequence(words_only, sub_rxs, ui_position)
        if seq:
            for (p_idx, t_idx, _), (_, hits) in zip(window, seq):
                key = (p_idx, t_idx)
                existing = highlight_map.get(key, [])
                for h in hits:
                    if h not in existing:
                        existing.append(h)
                highlight_map[key] = existing

    # Pass 3 — re-render, marking only the highlighted occurrences.
    out = []
    for idx, part in enumerate(parts):
        if not part or part.startswith('<'):
            out.append(part)
            continue
        rendered = []
        for t_idx, (tok, sep) in enumerate(zip(node_tokens[idx], node_seps[idx])):
            if not tok:
                rendered.append(html_lib.escape(sep))
                continue
            hits = highlight_map.get((idx, t_idx))
            if hits:
                last = 0
                for hm in sorted(hits, key=lambda x: x.start()):
                    rendered.append(html_lib.escape(tok[last:hm.start()]))
                    rendered.append(
                        f'<mark style="{_MARK_STYLE}" data-word="{html_lib.escape(tok)}">'
                        f'{html_lib.escape(tok[hm.start():hm.end()])}</mark>'
                    )
                    last = hm.end()
                rendered.append(html_lib.escape(tok[last:]))
            else:
                rendered.append(html_lib.escape(tok))
            rendered.append(html_lib.escape(sep))
        out.append(''.join(rendered))
    return ''.join(out)


def highlight_in_exported_html(html_doc: str, rx_or_list, position: str = 'anywhere') -> str:
    """
    Apply highlighting only inside transcription paragraphs (those that start
    with a digit or turn marker and contain PAI characters).  Speaker bios,
    the FEATURES section, and the metadata header are left untouched.
    Accepts either a single re.Pattern (single-word search) or a list of
    patterns (multi-word sequence search) — sequence searches are highlighted
    adjacency-aware via _highlight_text_nodes_sequence so only words that are
    actually part of a matched sequence get marked, not every word that
    matches any individual sub-pattern in isolation.
    """
    rxs      = rx_or_list if isinstance(rx_or_list, list) else [rx_or_list]
    result   = []
    last_end = 0
    for m in re.finditer(r'(<p\b[^>]*>)(.*?)(</p>)', html_doc, re.DOTALL | re.IGNORECASE):
        result.append(html_doc[last_end:m.start()])
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        if _is_transcription_para(body):
            if len(rxs) > 1:
                highlighted = _highlight_text_nodes_sequence(body, rxs, position)
            else:
                highlighted = _highlight_text_nodes(body, rxs[0])
            result.append(open_tag + highlighted + close_tag)
        else:
            result.append(m.group(0))
        last_end = m.end()
    result.append(html_doc[last_end:])
    return ''.join(result)


_STRIP_MARK = re.compile(r'</?mark[^>]*>')


def inject_interaction_js(html_doc: str, doc_id: str, nav_words: list = None,
                          tagged_words: list = None, sheet_row: int = None) -> str:
    """
    Inject right-click context menu and edit-mode support into a Google Docs
    HTML export before it is rendered in the iframe.
    nav_words: plain-text list of matched words to show as clickable scroll chips.
    sheet_row: when given, values already tagged on that row are marked with a
               ✓ in the value submenu, so a user adding a second value can see
               what is already there instead of guessing.
    """
    # Serialize feature list for JavaScript
    features_js = json.dumps([
        {'name': fd[2], 'type': fd[3], 'opts': fd[4] or []}
        for fd in FEATURE_DEFS
    ])

    # Values already on this row, per feature name — drives the ✓ markers.
    # Best-effort only: a failure here must never stop the document rendering.
    _current_map: dict = {}
    if sheet_row:
        try:
            _row_vals = get_sheet_features(sheet_row)
            for fd in FEATURE_DEFS:
                if fd[3] == 'bool':
                    continue
                _vals = _split_feat_values(_row_vals.get(fd[1]), fd[4])
                if _vals:
                    _current_map[fd[2]] = _vals
        except Exception:
            _current_map = {}
    current_vals_js = json.dumps(_current_map, ensure_ascii=False)

    nav_words_js    = json.dumps(nav_words or [])
    tagged_words_js = json.dumps(list(dict.fromkeys(tagged_words or [])))  # deduplicated

    script = f"""
<style>
/* ── Match navigation chip strip ── */
#pai-chip-strip {{
  position:sticky; top:0; z-index:200;
  background:rgba(240,248,255,.97); padding:5px 10px;
  border-bottom:1px solid #b8deff;
  display:flex; flex-wrap:wrap; gap:5px; align-items:center;
  backdrop-filter:blur(4px);
}}
.pai-cs-label {{ font-size:11px; color:#60aee8; letter-spacing:.05em; }}
.pai-nav-chip {{
  background:#daeeff; border:1px solid #60aee8; border-radius:8px;
  padding:3px 11px; font-family:'IBM Plex Mono',monospace; font-size:13px;
  cursor:pointer; color:#0d3f75; transition:background .15s; user-select:none;
}}
.pai-nav-chip:hover {{ background:#b8deff; }}
.pai-nav-arrow {{
  background:#daeeff; border:1px solid #60aee8; border-radius:6px;
  padding:2px 8px; font-size:13px; line-height:1.3; cursor:pointer;
  color:#0d3f75; transition:background .15s, opacity .15s; user-select:none;
}}
.pai-nav-arrow:hover {{ background:#b8deff; }}
.pai-nav-arrow[disabled] {{ opacity:.35; cursor:default; }}
.pai-nav-arrow[disabled]:hover {{ background:#daeeff; }}
#pai-nav-group {{ display:flex; align-items:center; gap:5px; margin-left:auto; }}
#pai-mark-pos {{ font-size:11px; color:#999; min-width:34px; text-align:center; }}
mark {{ background:#b6f2c8; border-radius:2px; padding:0 1px; }}
mark.pai-hl {{ outline:2px solid #2075c7; border-radius:2px; background:#7ee8a2; }}
/* ── Auto-tagged word highlight ── */
.pai-tagged-word {{
  background: #ffd97d; border-radius:2px; padding:0 2px;
  outline: 1.5px solid #f5a623; cursor:default;
}}
/* ── Context menu ── */
#pai-ctx-menu {{
  position:fixed; z-index:999999; min-width:250px; max-width:310px;
  max-height:min(78vh, 500px);
  background:#1c1c1e; border-radius:12px;
  box-shadow:0 8px 40px rgba(0,0,0,.6);
  padding:0; display:none; flex-direction:column;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:13px; color:#f2f2f7; user-select:none;
  overflow:hidden;
}}
#pai-ctx-header {{
  padding:7px 14px 6px; font-size:11px; color:#aaa;
  letter-spacing:.08em; text-transform:uppercase;
  border-bottom:1px solid #333; background:#1c1c1e;
  flex-shrink:0;
}}
#pai-ctx-scroll {{
  flex:1; min-height:0;
  overflow-y:auto;
  overflow-x:hidden;
  padding:4px 0;
  scrollbar-width:thin;
  scrollbar-color:#444 transparent;
}}
#pai-ctx-scroll::-webkit-scrollbar {{ width:4px; }}
#pai-ctx-scroll::-webkit-scrollbar-thumb {{ background:#444; border-radius:2px; }}
.ctx-item {{
  padding:6px 16px; cursor:pointer; display:flex;
  align-items:center; gap:10px; position:relative;
}}
.ctx-item:hover {{ background:rgba(255,255,255,.09); }}
.ctx-icon {{ color:#60aee8; font-size:11px; min-width:14px; flex-shrink:0; }}
.ctx-label {{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ctx-badge {{
  font-size:10px; color:#666; background:#2c2c2e;
  border-radius:4px; padding:1px 5px; flex-shrink:0;
}}
.ctx-sub {{
  position:fixed; left:0; top:0;
  background:#1c1c1e; border-radius:12px;
  box-shadow:0 6px 28px rgba(0,0,0,.6);
  padding:5px 0; min-width:190px; display:none;
  font-size:13px; color:#f2f2f7; z-index:1000000;
  max-height:min(50vh,300px); overflow-y:auto;
  scrollbar-width:thin; scrollbar-color:#444 transparent;
}}
.ctx-sub-item {{ padding:7px 16px; cursor:pointer; white-space:nowrap; }}
.ctx-sub-item:hover {{ background:rgba(255,255,255,.09); }}
/* ── inline edit section ── */
#ctx-edit-section {{
  padding:8px 12px 10px; border-bottom:1px solid #333;
  background:#1c1c1e; flex-shrink:0;
}}
#ctx-edit-label {{
  font-size:10px; color:#aaa; letter-spacing:.07em;
  text-transform:uppercase; margin-bottom:6px;
}}
#ctx-edit-row {{
  display:flex; gap:6px; align-items:center;
}}
#ctx-edit-input {{
  flex:1; background:#2c2c2e; border:1px solid #444;
  border-radius:7px; color:#f2f2f7; font-size:13px;
  padding:5px 9px; outline:none; font-family:inherit;
  min-width:0;
}}
#ctx-edit-input:focus {{ border-color:#60aee8; }}
#ctx-edit-btn {{
  background:#2075c7; border:none; border-radius:7px;
  color:white; font-size:16px; padding:4px 10px;
  cursor:pointer; flex-shrink:0; line-height:1;
}}
#ctx-edit-btn:hover {{ background:#1a5fa8; }}
#ctx-edit-note {{
  font-size:10px; color:#666; margin-top:5px;
}}
/* ── edit-section PAI keyboard ── */
#ctx-kb-toggle {{
  background:none; border:1px solid #444; border-radius:5px;
  color:#aaa; font-size:11px; padding:2px 6px; cursor:pointer; margin-top:5px;
}}
#ctx-kb-toggle:hover {{ color:#f2f2f7; border-color:#666; }}
#ctx-kb-panel {{
  display:none; margin-top:6px; flex-wrap:wrap; gap:3px;
}}
#ctx-kb-panel.open {{ display:flex; }}
.ctx-kc {{
  background:#2c2c2e; border:1px solid #555; border-radius:5px;
  color:#f2f2f7; font-family:'IBM Plex Mono',monospace; font-size:12px;
  padding:3px 6px; cursor:pointer; min-width:24px; text-align:center;
}}
.ctx-kc:hover {{ background:#3a3a3c; }}
.ctx-kc.ctx-anchor {{ background:#1a3a5c; border-color:#60aee8; color:#90caf9; font-weight:700; }}
/* ── Free-text feature search ── */
#ctx-feat-search {{
  display:flex; gap:6px; align-items:center;
  padding:7px 12px; border-bottom:1px solid #333;
  background:#1c1c1e; flex-shrink:0;
}}
#ctx-feat-q {{
  flex:1; min-width:0; background:#2c2c2e; border:1px solid #444;
  border-radius:7px; color:#f2f2f7; font-size:12.5px;
  padding:5px 9px; outline:none; font-family:inherit;
}}
#ctx-feat-q:focus {{ border-color:#60aee8; }}
#ctx-feat-q::placeholder {{ color:#777; }}
#ctx-feat-clear {{
  background:none; border:none; color:#777; cursor:pointer;
  font-size:13px; padding:2px 4px; flex-shrink:0; display:none;
}}
#ctx-feat-clear:hover {{ color:#f2f2f7; }}
/* group tag shown next to a feature in flat search results */
.ctx-grp-tag {{
  font-size:9.5px; color:#60aee8; background:#123; border:1px solid #245;
  border-radius:4px; padding:1px 5px; flex-shrink:0; margin-right:7px;
  letter-spacing:.03em;
}}
.ctx-empty {{ padding:10px 16px; color:#777; font-size:12px; font-style:italic; }}
</style>
<div id="pai-ctx-menu">
  <div id="pai-ctx-header">TAG FEATURE</div>
  <!-- inline edit section -->
  <div id="ctx-edit-section">
    <div id="ctx-edit-label">✏️ Replace word</div>
    <div id="ctx-edit-row">
      <input id="ctx-edit-input" type="text" placeholder="replacement…" autocomplete="off" spellcheck="false"/>
      <button id="ctx-edit-btn" title="Apply">↵</button>
    </div>
    <div id="ctx-edit-note">Replaces only this occurrence</div>
    <button id="ctx-kb-toggle">⌨ PAI chars</button>
    <div id="ctx-kb-panel"></div>
  </div>
  <!-- Free-text feature search: finds a feature across ALL four groups,
       matching either its full name ("LEX. want") or its bare name ("want"). -->
  <div id="ctx-feat-search">
    <input id="ctx-feat-q" type="text" placeholder="🔎 search features…"
           autocomplete="off" spellcheck="false"/>
    <button id="ctx-feat-clear" title="Clear">✕</button>
  </div>
  <div id="pai-ctx-scroll"></div>
</div>
<div id="pai-ctx-sub"  class="ctx-sub"></div>
<div id="pai-ctx-sub2" class="ctx-sub"></div>
<script>
(function(){{
  const FEATURES   = {features_js};
  const CURRENT    = {current_vals_js};   // feature name -> values already tagged
  const DOC_ID     = {json.dumps(doc_id)};
  const menu       = document.getElementById('pai-ctx-menu');
  const header     = document.getElementById('pai-ctx-header');
  const scroll     = document.getElementById('pai-ctx-scroll');
  const subMenu    = document.getElementById('pai-ctx-sub');
  const subMenu2   = document.getElementById('pai-ctx-sub2');
  const editInput  = document.getElementById('ctx-edit-input');
  const editBtn    = document.getElementById('ctx-edit-btn');
  const editSect   = document.getElementById('ctx-edit-section');
  let   selText    = '';
  let   selRange   = null;
  let   activeItem = null;
  let   activeSub2Item = null;

  // ── Compute a 0-based occurrence index for `range` within the document's
  //    full text, so the backend can target the SAME occurrence the user
  //    actually selected (instead of replacing every match in the doc). ────
  function computeOccurrenceIndex(range, text) {{
    if (!range || !text) return 0;
    try {{
      var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
      var offset = 0;
      var targetOffset = -1;
      var node;
      while ((node = walker.nextNode())) {{
        if (node === range.startContainer) {{
          targetOffset = offset + range.startOffset;
          break;
        }}
        offset += node.nodeValue.length;
      }}
      if (targetOffset === -1) return 0;
      var fullText = document.body.textContent;
      var count = 0;
      var searchFrom = 0;
      while (true) {{
        var idx = fullText.indexOf(text, searchFrom);
        if (idx === -1 || idx >= targetOffset) break;
        count++;
        searchFrom = idx + 1;
      }}
      return count;
    }} catch(e) {{ return 0; }}
  }}

  // ── Edit section: stop clicks bubbling to the close-menu handler ────────
  editSect.addEventListener('click',   function(e) {{ e.stopPropagation(); }});
  editSect.addEventListener('mousedown', function(e) {{ e.stopPropagation(); }});

  // ── Context-menu PAI keyboard ─────────────────────────────────────────────
  var ctxKbToggle = document.getElementById('ctx-kb-toggle');
  var ctxKbPanel  = document.getElementById('ctx-kb-panel');
  var CTX_CHARS   = ['ʾ','ʿ','ḥ','ḍ','ṭ','ṯ','ġ','ğ','ž','č','š','ṣ',
                     'ā','ē','ī','ō','ū','ə','a','e','i','o','u'];
  CTX_CHARS.forEach(function(ch) {{
    var b = document.createElement('button');
    b.className = 'ctx-kc';
    b.textContent = ch;
    b.addEventListener('click', function(e) {{
      e.stopPropagation();
      var s = editInput.selectionStart, en = editInput.selectionEnd;
      editInput.value = editInput.value.slice(0,s) + ch + editInput.value.slice(en);
      editInput.selectionStart = editInput.selectionEnd = s + ch.length;
      editInput.focus();
    }});
    ctxKbPanel.appendChild(b);
  }});
  ctxKbToggle.addEventListener('click', function(e) {{
    e.stopPropagation();
    ctxKbPanel.classList.toggle('open');
  }});

  function applyEdit() {{
    const repl = editInput.value;
    if (!repl || repl === selText) return;
    const occIdx = computeOccurrenceIndex(selRange, selText);
    menu.style.display = 'none';
    hideSubMenu();
    try {{
      localStorage.setItem('pai_pending_tag', JSON.stringify({{
        type:            'edit',
        find:            selText,
        replace:         repl,
        occurrenceIndex: occIdx,
        docId:           DOC_ID,
        timestamp:       Date.now()
      }}));
    }} catch(e) {{}}
  }}
  editBtn.addEventListener('click', applyEdit);
  editInput.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') {{ e.preventDefault(); applyEdit(); }}
    e.stopPropagation();
  }});

  // ── Feature menu ──────────────────────────────────────────────────────
  // Two ways in:
  //   1. Browse by group  (PHON. → feature → value)   — default
  //   2. Free-text search (matches ANY feature across all four groups,
  //      by full name "LEX. want" OR bare name "want")
  const GROUP_ORDER = ['PHON.', 'MOR.', 'SYN.', 'LEX.'];
  const FEAT_GROUPS = {{}};
  GROUP_ORDER.forEach(function(p) {{ FEAT_GROUPS[p] = []; }});
  const UNGROUPED = [];
  FEATURES.forEach(function(fd) {{
    const grp = GROUP_ORDER.find(function(p) {{ return fd.name.startsWith(p); }});
    if (grp) FEAT_GROUPS[grp].push(fd); else UNGROUPED.push(fd);
  }});

  function stripPrefix(name) {{
    for (var i = 0; i < GROUP_ORDER.length; i++) {{
      if (name.indexOf(GROUP_ORDER[i]) === 0) {{
        return name.slice(GROUP_ORDER[i].length).trim();
      }}
    }}
    return name;
  }}
  function groupOf(name) {{
    const g = GROUP_ORDER.find(function(p) {{ return name.indexOf(p) === 0; }});
    return g ? g.replace('.', '') : '';
  }}
  // Match on the full name AND on the name with its prefix removed, so
  // typing "want" finds 'LEX. "want"' without knowing the category.
  function featMatches(fd, q) {{
    if (!q) return true;
    const full = fd.name.toLowerCase();
    const bare = stripPrefix(fd.name).toLowerCase();
    // also match the option values, so searching "bidd" finds its feature
    const opts = (fd.opts || []).join(' ').toLowerCase();
    return full.indexOf(q) >= 0 || bare.indexOf(q) >= 0 || opts.indexOf(q) >= 0;
  }}

  function hideSub2() {{
    subMenu2.style.display = 'none';
    subMenu2.innerHTML = '';
    activeSub2Item = null;
  }}
  function hideSubMenu() {{
    subMenu.style.display = 'none';
    subMenu.innerHTML = '';
    hideSub2();
    activeItem = null;
  }}

  // Position `target` beside `relEl`, vertically aligned with `anchorItem`.
  function positionSub(target, relEl, anchorItem) {{
    const rr = relEl.getBoundingClientRect();
    const ir = anchorItem.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;
    target.style.display = 'block';
    const tr = target.getBoundingClientRect();
    let sx = rr.right + 4;
    if (sx + tr.width > vw) sx = rr.left - tr.width - 4;
    let sy = ir.top;
    if (sy + tr.height > vh) sy = vh - tr.height - 8;
    target.style.left = sx + 'px';
    target.style.top  = sy + 'px';
  }}

  // Fill `target` with the value list for a select feature.
  function buildValueMenu(fd, anchorItem, target, relEl) {{
    const cur = CURRENT[fd.name] || [];
    target.innerHTML = '';
    (fd.opts || []).forEach(function(opt) {{
      const si2 = document.createElement('div');
      si2.className = 'ctx-sub-item';
      const isSet = cur.some(function(c) {{
        return String(c).trim().toLowerCase() === String(opt).trim().toLowerCase();
      }});
      si2.style.display = 'flex';
      si2.innerHTML =
        '<span style="flex:1">' + opt + '</span>' +
        (isSet ? '<span style="color:#7ee8a2;padding-left:10px">✓</span>' : '');
      si2.title = isSet
        ? 'Already tagged on this document'
        : (cur.length ? 'Will be added alongside: ' + cur.join(', ') : '');
      si2.addEventListener('click', function(e) {{
        e.stopPropagation();
        storeTag(fd.name, opt);
      }});
      target.appendChild(si2);
    }});
    positionSub(target, relEl, anchorItem);
  }}

  // One feature row. `showGroupTag` is used in flat search results, where the
  // category is no longer implied by which submenu you are in.
  // `valueTarget` / `valueRelEl` say where its value list should open.
  function makeFeatureItem(fd, valueTarget, valueRelEl, showGroupTag) {{
    const si = document.createElement('div');
    si.className = 'ctx-sub-item';
    si.style.display = 'flex';
    si.style.alignItems = 'center';
    const label = showGroupTag ? stripPrefix(fd.name) : fd.name;
    const tag   = showGroupTag && groupOf(fd.name)
      ? '<span class="ctx-grp-tag">' + groupOf(fd.name) + '</span>' : '';

    if (fd.type === 'bool') {{
      si.innerHTML = tag +
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis">' + label + '</span>';
      si.addEventListener('click', function(e) {{
        e.stopPropagation();
        storeTag(fd.name, true);
      }});
      si.addEventListener('mouseenter', function() {{
        if (valueTarget === subMenu) hideSub2(); else hideSub2();
      }});
    }} else {{
      // Select features are MULTI-VALUE: picking a second value adds to the
      // first rather than replacing it, so already-tagged values get a ✓.
      const cur   = CURRENT[fd.name] || [];
      const badge = cur.length
        ? '<span style="font-size:10px;color:#7ee8a2;flex-shrink:0;padding-left:6px">✓' +
          (cur.length > 1 ? cur.length : '') + '</span>'
        : '';
      si.innerHTML = tag +
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis">' + label + '</span>' +
        badge +
        '<span style="opacity:.5;flex-shrink:0;padding-left:6px">▸</span>';
      if (cur.length) si.title = 'Already tagged: ' + cur.join(', ');
      si.addEventListener('mouseenter', function() {{
        activeSub2Item = si;
        buildValueMenu(fd, si, valueTarget, valueRelEl);
      }});
    }}
    return si;
  }}

  // ── Mode 1: browse by group ───────────────────────────────────────────
  function renderGroups() {{
    scroll.innerHTML = '';
    hideSubMenu();
    const groups = GROUP_ORDER.concat(UNGROUPED.length ? ['__other__'] : []);
    groups.forEach(function(grp) {{
      const fds = grp === '__other__' ? UNGROUPED : FEAT_GROUPS[grp];
      if (!fds || !fds.length) return;
      const item = document.createElement('div');
      item.className = 'ctx-item';
      item.innerHTML = '<span class="ctx-icon">⊛</span>'
        + '<span class="ctx-label">' + (grp === '__other__' ? 'Other' : grp) + '</span>'
        + '<span class="ctx-badge">' + fds.length + ' ▸</span>';
      item.addEventListener('mouseenter', function() {{
        hideSub2();
        activeItem = item;
        subMenu.innerHTML = '';
        fds.forEach(function(fd) {{
          // inside a group submenu the values open one level further out
          subMenu.appendChild(makeFeatureItem(fd, subMenu2, subMenu, false));
        }});
        positionSub(subMenu, menu, item);
      }});
      scroll.appendChild(item);
    }});
  }}

  // ── Mode 2: flat search results ───────────────────────────────────────
  function renderSearch(q) {{
    scroll.innerHTML = '';
    hideSubMenu();
    const hits = FEATURES.filter(function(fd) {{ return featMatches(fd, q); }});
    if (!hits.length) {{
      const none = document.createElement('div');
      none.className = 'ctx-empty';
      none.textContent = 'No feature matches “' + q + '”';
      scroll.appendChild(none);
      return;
    }}
    hits.forEach(function(fd) {{
      // results live in the MAIN column, so their values open in subMenu
      scroll.appendChild(makeFeatureItem(fd, subMenu, menu, true));
    }});
  }}

  // ── Search box wiring ─────────────────────────────────────────────────
  const featQ     = document.getElementById('ctx-feat-q');
  const featClear = document.getElementById('ctx-feat-clear');

  // Header text to restore when the search box is emptied. The right-click
  // handler overwrites it with the selected word.
  let baseHeader = 'TAG FEATURE';

  function applyFeatureQuery() {{
    const q = featQ.value.trim().toLowerCase();
    featClear.style.display = q ? 'block' : 'none';
    header.textContent = q ? ('MATCHING \u201C' + q + '\u201D') : baseHeader;
    if (q) renderSearch(q); else renderGroups();
  }}

  featQ.addEventListener('input', applyFeatureQuery);
  // Keep clicks/keys inside the box from closing the menu or reaching the doc
  featQ.addEventListener('click',     function(e) {{ e.stopPropagation(); }});
  featQ.addEventListener('mousedown', function(e) {{ e.stopPropagation(); }});
  featQ.addEventListener('keydown',   function(e) {{
    e.stopPropagation();
    if (e.key === 'Escape') {{ featQ.value = ''; applyFeatureQuery(); }}
  }});
  featClear.addEventListener('click', function(e) {{
    e.stopPropagation();
    featQ.value = '';
    applyFeatureQuery();
    featQ.focus();
  }});
  document.getElementById('ctx-feat-search')
          .addEventListener('click', function(e) {{ e.stopPropagation(); }});

  renderGroups();

  // ── Right-click handler ─────────────────────────────────────────────────
  document.addEventListener('contextmenu', function(e) {{
    const sel = window.getSelection();
    selText = sel ? sel.toString().trim() : '';
    selRange = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0).cloneRange() : null;
    if (!selText) return;
    e.preventDefault();
    hideSubMenu();

    // Reset the feature search each time the menu opens, so a query typed for
    // a previous word doesn't silently hide most features on the next one.
    baseHeader = 'TAG: "' + selText.slice(0, 28) + (selText.length > 28 ? '…' : '') + '"';
    featQ.value = '';
    applyFeatureQuery();

    // First position at click, then adjust to keep fully inside viewport
    const vw = window.innerWidth, vh = window.innerHeight;
    menu.style.left = '0'; menu.style.top = '0';
    menu.style.display = 'flex';
    scroll.scrollTop = 0;
    const mr = menu.getBoundingClientRect();
    let x = e.clientX, y = e.clientY;
    if (x + mr.width  > vw) x = vw - mr.width  - 6;
    if (y + mr.height > vh) y = vh - mr.height - 6;
    if (x < 4) x = 4;
    if (y < 4) y = 4;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
  }});

  document.addEventListener('click', function(e) {{
    if (!menu.contains(e.target) && !subMenu.contains(e.target) && !subMenu2.contains(e.target)) {{
      menu.style.display = 'none';
      hideSubMenu();
    }}
  }});
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{ menu.style.display = 'none'; hideSubMenu(); }}
  }});

  // ── Highlight selected text as a tagged word (client-side, immediate) ───
  function highlightCurrentSelection() {{
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount || sel.isCollapsed) return;
    try {{
      var range = sel.getRangeAt(0);
      var span  = document.createElement('span');
      span.className = 'pai-tagged-word';
      range.surroundContents(span);
      sel.removeAllRanges();
    }} catch(e) {{
      // Selection may span multiple elements — just clear it
      sel.removeAllRanges();
    }}
  }}

  // ── Store tag in localStorage → bridge component picks it up ───────────
  function storeTag(featureName, value) {{
    highlightCurrentSelection();   // immediate visual feedback in document
    // Also flash the menu header green for 700ms
    header.textContent = '✓  ' + featureName;
    header.style.color = '#4ade80';
    hideSubMenu();
    setTimeout(function() {{ menu.style.display = 'none'; header.style.color = ''; }}, 700);
    try {{
      localStorage.setItem('pai_pending_tag', JSON.stringify({{
        feature:   featureName,
        value:     value,
        docId:     DOC_ID,
        selText:   selText,
        timestamp: Date.now()
      }}));
    }} catch(e) {{}}
  }}
}})();

// ── Preserve scroll position across Streamlit reruns ────────────────────────
// Every right-click tag (or untag) triggers a full Streamlit script rerun,
// which rebuilds this iframe's HTML from scratch and reloads it — losing
// whatever scroll position the user was reading at ("kicked out of the
// text" — reported when tagging, and even more noticeable after several
// tags accumulate). This iframe is same-origin with the parent page (an
// unsandboxed srcdoc iframe inherits the parent's origin — the same reason
// the right-click → localStorage bridge to _TAG_BRIDGE already works), so
// sessionStorage persists across these reloads and lets us save/restore
// scroll position per document.
(function() {{
  var DOC_ID = {json.dumps(doc_id)};
  var SCROLL_KEY = 'pai_scroll_' + DOC_ID;
  function restoreScroll() {{
    try {{
      var saved = sessionStorage.getItem(SCROLL_KEY);
      if (saved) window.scrollTo(0, parseInt(saved, 10) || 0);
    }} catch(e) {{}}
  }}
  var _saveTimer = null;
  function saveScrollSoon() {{
    if (_saveTimer) clearTimeout(_saveTimer);
    _saveTimer = setTimeout(function() {{
      try {{ sessionStorage.setItem(SCROLL_KEY, String(window.scrollY)); }} catch(e) {{}}
    }}, 150);
  }}
  window.addEventListener('scroll', saveScrollSoon, {{passive: true}});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restoreScroll);
  else restoreScroll();
  // Highlighting/layout above can still shift content height right after
  // DOMContentLoaded, so restore again once things settle.
  setTimeout(restoreScroll, 60);
  setTimeout(restoreScroll, 250);
}})();

// ── Word chip navigation ────────────────────────────────────────────────────
(function() {{
  var NAV_WORDS = {nav_words_js};
  if (!NAV_WORDS || NAV_WORDS.length === 0) return;

  // Build chip strip
  var strip = document.createElement('div');
  strip.id = 'pai-chip-strip';
  var html = '<span class="pai-cs-label">jump to match&nbsp;↓&nbsp;</span>';
  NAV_WORDS.forEach(function(w) {{
    html += '<button class="pai-nav-chip" data-navword="' + w.replace(/"/g,'&quot;') + '" onclick="paiNavWord(this)">' + w + '</button>';
  }});
  // Prev/next arrows to step between occurrences of whichever word is
  // currently active (set by clicking one of the chips above), so the user
  // isn't limited to repeatedly re-clicking the same chip to go forward only.
  html += '<span id="pai-nav-group">'
        +   '<button id="pai-nav-prev" class="pai-nav-arrow" onclick="paiNavStep(-1)" title="Previous occurrence" disabled>◀</button>'
        +   '<span id="pai-mark-pos"></span>'
        +   '<button id="pai-nav-next" class="pai-nav-arrow" onclick="paiNavStep(1)" title="Next occurrence" disabled>▶</button>'
        + '</span>';
  strip.innerHTML = html;

  function insertStrip() {{
    if (document.body) document.body.insertAdjacentElement('afterbegin', strip);
  }}
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', insertStrip);
  else insertStrip();
}})();

// ── Highlight already-pending tagged words on page load ────────────────────
(function() {{
  var TAGGED = {tagged_words_js};
  if (!TAGGED || !TAGGED.length) return;

  // Find the FEATURES: heading so we can exclude it and everything after
  var featuresStart = null;
  function findFeaturesSection() {{
    var all = document.body.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {{
      var el = all[i];
      if (el.children.length === 0 && el.textContent.trim() === 'FEATURES:') {{
        featuresStart = el;
        break;
      }}
    }}
  }}

  function isInOrAfterFeatures(node) {{
    if (!featuresStart) return false;
    if (featuresStart.contains(node)) return true;
    // DOCUMENT_POSITION_FOLLOWING means node comes after featuresStart
    return !!(featuresStart.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING);
  }}

  // Find every non-overlapping match of ANY word in `words` within `text`,
  // leftmost match wins ties (mirrors the previous per-word sequential
  // behavior closely enough for the rare overlapping-word edge case).
  function findNonOverlappingMatches(text, words) {{
    var matches = [];
    words.forEach(function(word) {{
      var idx = 0;
      while ((idx = text.indexOf(word, idx)) !== -1) {{
        matches.push({{start: idx, end: idx + word.length}});
        idx += word.length;
      }}
    }});
    matches.sort(function(a, b) {{ return a.start - b.start; }});
    var resolved = [];
    var lastEnd = -1;
    matches.forEach(function(m) {{
      if (m.start >= lastEnd) {{
        resolved.push(m);
        lastEnd = m.end;
      }}
    }});
    return resolved;
  }}

  // Wrap ALL tagged-word occurrences inside a single text node in one DOM
  // mutation, instead of one mutation per word — this is the key perf win:
  // previously, tagging N words caused N full document TreeWalker passes
  // PLUS N rounds of DOM mutation (each round operating on the just-mutated
  // tree from the previous word), which got slower the more words were
  // already tagged. Now it's exactly one pass, one mutation per node.
  function wrapAllWordsInNode(node, words) {{
    var text = node.nodeValue;
    var matches = findNonOverlappingMatches(text, words);
    if (!matches.length) return;
    var frag = document.createDocumentFragment();
    var pos = 0;
    matches.forEach(function(m) {{
      if (m.start > pos) frag.appendChild(document.createTextNode(text.slice(pos, m.start)));
      var span = document.createElement('span');
      span.className = 'pai-tagged-word';
      span.textContent = text.slice(m.start, m.end);
      frag.appendChild(span);
      pos = m.end;
    }});
    if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
    node.parentNode.replaceChild(frag, node);
  }}

  function highlightAllTagged(words) {{
    if (!words || !words.length) return;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {{
      acceptNode: function(n) {{
        // Skip script/style and already-highlighted spans
        var p = n.parentNode;
        if (!p) return NodeFilter.FILTER_REJECT;
        var tag = p.tagName && p.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return NodeFilter.FILTER_REJECT;
        if (p.classList && p.classList.contains('pai-tagged-word')) return NodeFilter.FILTER_REJECT;
        // Skip anything in or after the FEATURES section
        if (isInOrAfterFeatures(n)) return NodeFilter.FILTER_REJECT;
        for (var i = 0; i < words.length; i++) {{
          if (n.nodeValue.indexOf(words[i]) !== -1) return NodeFilter.FILTER_ACCEPT;
        }}
        return NodeFilter.FILTER_SKIP;
      }}
    }}, false);
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function(n) {{ wrapAllWordsInNode(n, words); }});
  }}

  function run() {{
    findFeaturesSection();
    highlightAllTagged(TAGGED);
  }}
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
}})();

// ── Match navigation: chip click (jump to a word) + prev/next arrows
//    (step through the currently-active word's occurrences in either
//    direction) share this single piece of state. ─────────────────────────
var _paiActiveWord  = null;   // raw (un-normalized) data-navword of the active chip
var _paiActiveMarks = [];     // all <mark> elements for the active word, in document order
var _paiActiveIdx   = -1;     // 0-based index into _paiActiveMarks of the current position
var _paiLastHL       = null;

function _paiCollectMarks(word) {{
  // Normalize both sides to NFC if available (guards against NFD mismatches)
  var normWord = (typeof word === 'string' && String.prototype.normalize)
                   ? word.normalize('NFC') : word;
  var allMarks = Array.from(document.querySelectorAll('mark[data-word]'));
  var wordMarks = allMarks.filter(function(m) {{
    var dw = m.getAttribute('data-word') || '';
    var ndw = String.prototype.normalize ? dw.normalize('NFC') : dw;
    return ndw === normWord;
  }});
  // Fallback 1: data-word contains the nav word (handles trailing punctuation)
  if (wordMarks.length === 0) {{
    wordMarks = allMarks.filter(function(m) {{
      var ndw = String.prototype.normalize
                  ? (m.getAttribute('data-word') || '').normalize('NFC') : (m.getAttribute('data-word') || '');
      return ndw.indexOf(normWord) >= 0;
    }});
  }}
  // Fallback 2: nav word contains the mark's text content (match portion)
  if (wordMarks.length === 0) {{
    wordMarks = allMarks.filter(function(m) {{
      var mc = String.prototype.normalize ? m.textContent.normalize('NFC') : m.textContent;
      return normWord.indexOf(mc) >= 0 || mc.indexOf(normWord) >= 0;
    }});
  }}
  // Fallback 3: use ALL marks so the jump still works
  if (wordMarks.length === 0) {{
    wordMarks = allMarks;
  }}
  return wordMarks;
}}

// Move the highlight + scroll position to `idx` (wrapped into range) within
// the currently-active word's occurrence list, and refresh the "n/total" +
// arrow enabled/disabled state.
function _paiGoTo(idx) {{
  var n = _paiActiveMarks.length;
  if (!n) return;
  idx = ((idx % n) + n) % n;   // proper modulo — handles negative `idx` for "prev"

  if (_paiLastHL) _paiLastHL.classList.remove('pai-hl');
  var m = _paiActiveMarks[idx];
  m.classList.add('pai-hl');
  m.scrollIntoView({{behavior:'smooth', block:'center'}});
  _paiLastHL = m;
  _paiActiveIdx = idx;

  var pos = document.getElementById('pai-mark-pos');
  if (pos) pos.textContent = (idx + 1) + '/' + n;
  var prevBtn = document.getElementById('pai-nav-prev');
  var nextBtn = document.getElementById('pai-nav-next');
  // With wraparound cycling, prev/next stay enabled whenever there's more
  // than one occurrence to move between.
  if (prevBtn) prevBtn.disabled = n <= 1;
  if (nextBtn) nextBtn.disabled = n <= 1;
}}

// Clicking a chip: jump to that word's FIRST occurrence the first time it's
// selected; clicking the SAME chip again cycles forward (kept for backward
// compatibility with the previous single-click-to-cycle behavior).
function paiNavWord(btn) {{
  var word = btn.getAttribute('data-navword');
  if (word !== _paiActiveWord) {{
    _paiActiveWord  = word;
    _paiActiveMarks = _paiCollectMarks(word);
    _paiActiveIdx   = -1;   // _paiGoTo(0) below lands on the first occurrence
  }}
  if (!_paiActiveMarks.length) return;
  _paiGoTo(_paiActiveIdx + 1);
}}

// Prev (-1) / next (+1) arrow buttons — step through occurrences of
// whichever word is currently active, in either direction, with wraparound.
function paiNavStep(delta) {{
  if (!_paiActiveWord || !_paiActiveMarks.length) return;
  _paiGoTo(_paiActiveIdx + delta);
}}
</script>
"""
    if '</body>' in html_doc:
        return html_doc.replace('</body>', script + '</body>')
    return html_doc + script


def extract_transcription_text(html_doc: str) -> str:
    """
    Extract the transcription-body search index from a Google Docs HTML export.

    Filters applied — derived from the structural rules of the PAI corpus:

      1. ≥1 non-ASCII (PAI) char       → skips plain-ASCII lines like
                                          FEATURES, VERB, PRONS, 1sg:, PERFECT …
      2. Starts with a digit OR a
         turn/continuation marker
         ("- " / ". ")                 → the ONLY reliable structural rule:
                                          every transcription turn is numbered
                                          ("1. rāħet …") or begins with a marker
                                          ("- w-šāfet …" / ". ʾana …").
                                          FEATURES examples and speaker bios
                                          NEVER start this way → no false matches.
      3. CSS italic ≥ 80 % of chars    → extra guard (only applied when Google
                                          Docs exports italic classes); falls back
                                          to rules 1+2 alone if it kills all lines.
    """
    # ── Parse italic CSS classes from Google Docs <style> block ──────────────
    italic_classes: set = set()
    style_m = re.search(r'<style[^>]*>(.*?)</style>', html_doc, re.DOTALL | re.IGNORECASE)
    if style_m:
        for rule_m in re.finditer(r'\.([\w-]+)\s*\{([^}]+)\}', style_m.group(1)):
            if re.search(r'font-style\s*:\s*italic', rule_m.group(2), re.IGNORECASE):
                italic_classes.add(rule_m.group(1))

    def _italic_ratio(para_html: str) -> float:
        total = italic = 0
        for attrs, content in re.findall(r'<span\b([^>]*)>(.*?)</span>', para_html, re.DOTALL):
            t = len(re.sub(r'<[^>]+>', '', content))
            total += t
            s = re.search(r'style="([^"]*)"', attrs)
            c = re.search(r'class="([^"]*)"', attrs)
            if (s and re.search(r'font-style\s*:\s*italic', s.group(1), re.IGNORECASE)) \
               or (c and set(c.group(1).split()) & italic_classes):
                italic += t
        return italic / total if total > 0 else 0.0

    paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', html_doc, re.DOTALL | re.IGNORECASE)

    # Continuation / turn markers: "- text" or ". text"
    TURN_MARKER = re.compile(r'^[-.][ \t\u00a0]')

    def _passes_base_filters(para_html: str, text: str) -> bool:
        """
        Structural filter: keeps only PAI transcription turns.
        Every such turn starts with a digit (numbered) or a turn marker (- / .).
        FEATURES examples, speaker bios, and header lines never start this way.
        Requires ≥8 % non-ASCII density to exclude English summaries that
        happen to contain a single PAI proper noun (e.g. "Rīḥa").
        """
        non_ascii = re.findall(r'[^\x00-\x7F]', text)
        if not non_ascii or len(non_ascii) / max(len(text), 1) < 0.08:
            return False
        if not (TURN_MARKER.match(text) or text[:1].isdigit()):
            return False
        return True

    # First pass: structural filter + CSS italic guard (if italic classes found)
    lines = []
    for para in paragraphs:
        text = html_lib.unescape(unicodedata.normalize('NFC', re.sub(r'<[^>]+>', '', para))).strip()
        if not _passes_base_filters(para, text):
            continue
        if italic_classes and _italic_ratio(para) < 0.8:
            continue
        lines.append(text)

    # Safety fallback: drop CSS italic requirement if it killed all results
    if not lines:
        for para in paragraphs:
            text = html_lib.unescape(unicodedata.normalize('NFC', re.sub(r'<[^>]+>', '', para))).strip()
            if _passes_base_filters(para, text):
                lines.append(text)

    return '\n'.join(lines)


# ════════════════════════════════════════════════════════════════════════════════
#  GOOGLE SERVICES
# ════════════════════════════════════════════════════════════════════════════════

SPREADSHEET_ID = "1Q9g4vlBDzNx3D872hKePtFy-VShD-ocI--kPs44lyJ4"

# Human-readable header names used to locate columns dynamically.
# If a column is renamed in the sheet, update the string here.
COL_NAMES = {
    'trans_link':     'קישורים לתעתיקים',
    'rec_link':       'קישורים להקלטות',
    'village':        'שם יישוב בתעתיק',
    'social_typology':'Social Typology',
    'geo_typology':   'Geographical Typology',
    'community':      'קהילה',
    'gender':         'מגדר דובר',
    'status':         'סטטוס',
}

# ── Status badge colours (mirrors Google Sheets conditional formatting) ────────
STATUS_COLORS: dict[str, tuple[str, str]] = {
    'אושר (אורי)':    ('#1b5e20', '#ffffff'),   # dark green
    'עבר הגהה':       ('#558b2f', '#ffffff'),   # olive green
    'עבר תעתיק':      ('#f57f17', '#ffffff'),   # amber
    'מאושר לתעתיק':   ('#0277bd', '#ffffff'),   # blue
    'בטיפול':         ('#b71c1c', '#ffffff'),   # red
}

# Emoji colour hint for the plain-text expander label
STATUS_EMOJI: dict[str, str] = {
    'אושר (אורי)':    '🟢',
    'עבר הגהה':       '🟡',
    'עבר תעתיק':      '🟠',
    'מאושר לתעתיק':   '🔵',
    'בטיפול':         '🔴',
}

def _status_badge(status: str) -> str:
    bg, fg = STATUS_COLORS.get(status, ('#78909c', '#ffffff'))
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 12px;'
        f'border-radius:999px;font-size:0.8rem;font-weight:700;'
        f'font-family:Heebo,Arial,sans-serif;direction:rtl;'
        f'display:inline-block;line-height:1.6">{status}</span>'
    )

# ── Feature column definitions, keyed by SPREADSHEET HEADER TEXT ────────────────
# (header_text, display_name, type, options)
# type: 'bool' = checkbox  |  'select' = fixed options  |  'text' = free text
# ──────────────────────────────────────────────────────────────────────────────
# IMPORTANT (2026-06-22 redesign): this list is no longer matched to the sheet
# by column LETTER/position. Every time the app loads, get_feature_defs()
# (defined below, near get_column_indices()) reads the live header row and
# looks up each entry here by its exact header_text, resolving the *current*
# column letter dynamically. This means the sheet's columns can be inserted,
# removed, reordered, or renamed-and-restored without silently corrupting
# reads/writes the way the old hardcoded-column-letter list did (see the
# 2026-06-22 "ق=q shows no results" incident this replaces).
# Display names are kept stable across header renames so existing "FEATURES:"
# lines already written into Google Docs (matched by display-name, not header
# text) don't get orphaned.
# To add a NEW feature column, just give it a PHON. / MOR. / SYN. / LEX.
# header in the spreadsheet — it is discovered automatically and its type and
# options are read from the column's data validation. Add an entry here only
# to pin a type/options combination in code. (The 'AppFeatureDefs' tab is still
# read by get_extra_feature_defs() for historical entries, but the sidebar UI
# that used to write to it was removed once prefix discovery made it redundant.)
# The four recognised category prefixes.  Any spreadsheet column whose
# header starts with one of these is automatically treated as a feature
# column (see get_feature_defs()).  FEATURE_HEADER_DEFS below is now used
# only as a type/options lookup, not as the authoritative column list.
FEAT_PREFIXES = ('PHON.', 'MOR.', 'SYN.', 'LEX.')

FEATURE_HEADER_DEFS: list[tuple] = [
    ('PHON. aCC > iCC',                       'aCC>iCC',                              'bool',   None),
    ('PHON. Diphthongs',                      'diphthongs',                           'bool',   None),
    ('MOR. Fem. Ending',                      'fem. ending',                          'select', ['-i', '-e', '-a', 'pausal']),
    ('PHON. Med. Imāla',                      'med. Imāla',                           'bool',   None),
    ('-a+n (Aram. sub.)',                     '-a+n (Aram. sub.)',                    'bool',   None),
    ('pausal -u>-o#, -i>-e#',                'pausal -u>-o#, -i>-e#',               'bool',   None),
    ('PHON. *ǧ',                              'ج',                                    'select', ['ž', 'ǧ', 'conditioned']),
    ('PHON. *q',                              'ق',                                    'select', ['q', 'ʾ', 'g', 'k', 'g/ǧ/k (conditioned)']),
    ('assimilation of gutturals to the left', 'assimilation of gutturals to the left','bool',   None),
    ('PHON. Vowel Epen.',                     'vowel epenthesis',                     'select', ['*CCC > CvCC', '*CCC > CCvC']),
    ('vocal harmonizing',                     'vocal harmonizing',                    'bool',   None),
    ('lowering of -uC>-oC/-iC>-eC',          'lowering of -uC>-oC/-iC>-eC',         'bool',   None),
    ('MOR. 1Pl Ind. Pron.',                   'independent pronoun 1.pl نحن',         'select', ['niḥna', 'iḥna']),
    ('3Pl Ind. Pron.',                        'independent pronoun 3.pl هم',          'select', ['hinne/hinne', 'hunne', 'hunni', 'humme/homme', 'hum/hom']),
    ('2.m.pl pron. كم-',                       '2.m.pl pron. كم-',                     'select', ['-ku/-ko', '-kum/-kom', '-čin']),
    ('3.m.pl (poss. pro) هم-',                 '3.m.pl (poss. pro) هم-',               'select', ['-h- > -∅- (e.g. -on)', '-hum/-hom', '-hin/-hen']),
    ('3.f.sg pron. ها-',                       '3.f.sg pron. ها-',                     'select', ['-a', '-a / -ya (after -i-)', '-ha',
                                                                                                   '-a; -ha only after -ū-',
                                                                                                   '-a; -ha only after -ū- / -i-', '-hä#/-he#']),
    ('impf. prefix 3.m.sg',                   'impf. prefix 3.m.sg',                  'select', ['bi-', 'byi-', 'yi-']),
    ('"want"',                                '"want"',                               'select', ['badd', 'bidd', 'widd']),
    ('LEX. "when?"',                          '"when?"',                              'select', ['ēmta', 'wēnta', 'wagtēš']),
    ('LEX."here"',                            '"here"',                               'select', ['hōn', 'hīn', 'hān', 'hina']),
    ('SYN. Past Con. Mod.',                   'past continuous modifier',             'select', ['kān', 'kān / čān', 'baka~biki / yibki~yibka',
                                                                                                  'baka/biki', 'baka~biki / yikbi~yikba', 'baʾa']),
    ('LEX. "He is saying"',                   '"he is saying"',                       'select', ['biʾūl']),
    ('LEX. "Rooster/Roosters"',               '"rooster/roosters"',                   'select', ['dīk / dyūk']),
    ('LEX. "Heavy"',                          '"heavy"',                              'select', ['tʾīl']),
    ('LEX. "now"',                            '"now"',                               'select', ['issa/hassāʿa', 'hallaʾ/halʾēt/halkēt/halgēt', 'alḥīn']),
    ('LEX. "Coffee"',                         '"coffee"',                             'select', ['ʾahwi']),
]

# Sentinel shown as a selectable value for every 'select'-type feature in
# Feature Browse mode, letting the user search for documents where that
# feature's spreadsheet column is empty (i.e. not yet tagged), rather than
# only being able to filter for one of the predefined tag values.
FEAT_NONE_OPTION = '— None (not tagged) —'


def _feat_val_norm(v) -> str:
    """
    Normalize a feature value for comparison: Unicode NFC-normalize, trim
    surrounding whitespace, and lowercase. Used so that a value typed into
    the spreadsheet that *looks* identical to one of the FEATURE_DEFS option
    strings (e.g. a precomposed vs. decomposed diacritic, stray spaces, or a
    capitalization difference) still matches the selected dropdown value.
    """
    return unicodedata.normalize('NFC', str(v or '')).strip().lower()


# ── Multi-value feature tags ──────────────────────────────────────────────────
# A 'select' feature cell may hold SEVERAL values at once, e.g.
#   MOR. Fem. Ending  ->  "-e; -a"
# because different researchers legitimately tag the same document with
# different reflexes. Tagging therefore MERGES rather than overwrites.
#
# Parsing is option-aware on purpose. Two real option values contain the
# separator themselves:
#     '-a; -ha only after -ū-'
#     '-a; -ha only after -ū- / -i-'
# A naive split(';') would shred those into two bogus tags, so the parser
# first tries to match whole known options (longest first) and only falls
# back to separator-splitting for text it doesn't recognise.
#
# WRITE format is ', ' because the feature columns are being migrated to
# Google Sheets' NATIVE multi-select dropdowns, which store their values
# comma-separated and render them as chips. Writing '; ' into such a column
# would produce one invalid value instead of two chips.
# READ accepts both ',' and ';' so columns not yet migrated keep working.
FEAT_VALUE_SEP = ', '


def _split_feat_values(raw, options=None) -> list[str]:
    """
    Parse a feature cell into its individual values.
    Returns [] for an empty/None/False cell. Order is preserved, duplicates
    (compared with _feat_val_norm) are dropped.
    """
    if raw is None or raw is False:
        return []
    s = unicodedata.normalize('NFC', str(raw)).strip()
    if not s:
        return []

    opts = [o for o in (options or []) if o and str(o).strip()]

    # Fast path: the whole cell is exactly one known option. This is what
    # protects the two options that contain ';' in their own text.
    for o in opts:
        if _feat_val_norm(o) == _feat_val_norm(s):
            return [o]

    out: list = []
    if opts:
        # Greedy longest-first scan, so '-a; -ha only after -ū-' wins over '-a'.
        by_len = sorted(opts, key=lambda o: len(str(o)), reverse=True)
        i, n = 0, len(s)
        while i < n:
            if s[i] in ';,' or s[i].isspace():
                i += 1
                continue
            matched = None
            for o in by_len:
                seg = s[i:i + len(str(o))]
                if _feat_val_norm(seg) == _feat_val_norm(o):
                    matched = str(o)
                    break
            if matched:
                out.append(matched)
                i += len(matched)
            else:
                j = i
                while j < n and s[j] not in ';,':
                    j += 1
                chunk = s[i:j].strip()
                if chunk:
                    out.append(chunk)
                i = j + 1
    else:
        # No known option list — plain separator split. Accepts ';' and ','
        # so cells written by Google Sheets' native multi-select still parse.
        out = [p.strip() for p in re.split(r'[;,]', s) if p.strip()]

    seen, uniq = set(), []
    for v in out:
        k = _feat_val_norm(v)
        if k and k not in seen:
            seen.add(k)
            uniq.append(v)
    return uniq


def _join_feat_values(values) -> str:
    """Render a list of feature values back into a single cell string."""
    return FEAT_VALUE_SEP.join(str(v) for v in values if str(v).strip())


def _merge_feat_values(existing_raw, new_val, options=None) -> tuple:
    """
    Merge new_val (a single value, or a list, or a '; '-joined string) into the
    values already in the cell.

    Returns (merged_cell_string, added_values, already_present_values).
    Nothing is ever removed — that is the whole point of multi-value tagging.
    """
    current = _split_feat_values(existing_raw, options)
    incoming = (new_val if isinstance(new_val, (list, tuple))
                else _split_feat_values(new_val, options))

    have = {_feat_val_norm(v) for v in current}
    added, dup = [], []
    merged = list(current)
    for v in incoming:
        k = _feat_val_norm(v)
        if not k:
            continue
        if k in have:
            dup.append(v)
        else:
            have.add(k)
            merged.append(v)
            added.append(v)
    return _join_feat_values(merged), added, dup


def _feat_value_matches(cell_raw, wanted, options=None) -> bool:
    """
    True if `wanted` is one of the values in a (possibly multi-value) cell.
    Used by Feature Browse so a document tagged '-e; -a' is found by a search
    for either '-e' or '-a'.
    """
    target = _feat_val_norm(wanted)
    return any(_feat_val_norm(v) == target
               for v in _split_feat_values(cell_raw, options))

# Features that appear in the doc FEATURES section but are NOT in the O-AO spreadsheet columns.
# '"was"' is intentionally included here (rather than in FEATURE_DEFS): the live
# sheet's reorganization on 2026-06-22 dropped its dedicated column (the new AJ
# column is a distinct "past continuous modifier" feature per Noam, not a renamed
# "was"). Listing it here means any existing "was  [...]" line already written
# into a Google Doc is preserved verbatim on rewrite, instead of being silently
# dropped — but it can no longer be read from, written to, or tagged via the
# spreadsheet, since there's nowhere left for it to live.
DOC_ONLY_FEATURES: list[str] = [
    '"was"',
    'long particles',
    'sandhi',
    '-a~-ä/-e#',
    'ḌLL+pron.',
    'Continuous modifier',
    'Anticipatory pronominal suffix',
]

# NOTE: FEATURE_DEFS itself and the _FEAT_BY_NAME lookup built from it are
# defined further below (right after get_column_indices()), once the helper
# functions that resolve header text against the live sheet are available —
# see get_feature_defs().


@st.cache_resource
def _get_service_account_info() -> dict:
    # Just the parsed JSON secret — a plain dict, safe to share read-only
    # across threads. The actual Credentials object (which holds the JWT
    # signer) is built fresh per-thread below, NOT cached/shared here.
    return json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])


def _build_credentials():
    return service_account.Credentials.from_service_account_info(
        _get_service_account_info(),
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/spreadsheets',
        ]
    )


# Each thread needs its OWN credentials + drive/docs/sheets service objects.
# Two separate thread-safety issues were stacked here:
#  1. googleapiclient.discovery.build() wraps an httplib2 HTTP transport that
#     is NOT thread-safe — sharing one service object across the
#     ThreadPoolExecutor workers used during search/preload caused native
#     segfaults (the http/SSL connection state got corrupted under
#     concurrent use, crashing the whole process with no Python traceback).
#  2. A single shared google.auth Credentials object signs JWTs (via the
#     `cryptography` library's RSA signer) on token refresh. If multiple
#     threads trigger a refresh/sign at the same moment on the SAME
#     Credentials instance, that can also corrupt native OpenSSL state and
#     segfault — even after (1) was fixed, since build() was still being
#     handed one shared `creds` object.
# Thread-local storage gives every worker thread its own credentials AND
# transport, while still avoiding a rebuild on every call.
_thread_local_services = threading.local()


def get_services():
    if not hasattr(_thread_local_services, 'services'):
        creds   = _build_credentials()
        drive   = build('drive',   'v3', credentials=creds, cache_discovery=False)
        docs    = build('docs',    'v1', credentials=creds, cache_discovery=False)
        sheets  = build('sheets',  'v4', credentials=creds, cache_discovery=False)
        _thread_local_services.services = (drive, docs, sheets)
    return _thread_local_services.services


def _extract_doc_id(url: str) -> str | None:
    """
    Extract a Google Doc/Drive file ID from any Google URL format.

    Handled patterns
    ─────────────────────────────────────────────────────────────────
    docs.google.com/document/d/ID/…          standard
    docs.google.com/document/u/0/d/ID/…      user-scoped (Google adds /u/N/)
    drive.google.com/file/d/ID/…             Drive file link
    drive.google.com/file/u/0/d/ID/…        Drive file link, user-scoped
    drive.google.com/open?id=ID              legacy "open" link
    drive.google.com/uc?id=ID&export=…      direct-download link
    Any URL with ?id=ID or &id=ID            generic id= parameter
    ─────────────────────────────────────────────────────────────────
    NOTE: published docs (/document/d/e/LONGID/pub) are intentionally
    excluded — they are not editable Docs API targets.
    """
    if not url:
        return None

    # /document/ and /file/ paths — both accept an optional /u/N/ user segment
    # The lookahead `(?![a-zA-Z0-9_-]{0,3}/)` prevents matching published-doc
    # stubs like /d/e/ where the "ID" would just be a single letter.
    m = re.search(r'/(?:document|file)/(?:u/\d+/)?d/([a-zA-Z0-9_-]{10,})', url)
    if m:
        return m.group(1)

    # id= query parameter (drive.google.com/open?id=… or /uc?id=…)
    m = re.search(r'[?&]id=([a-zA-Z0-9_-]{10,})', url)
    if m:
        return m.group(1)

    return None


def _col_letter(idx0: int) -> str:
    """
    Convert a 0-based column index to its A1 column letter(s), e.g.
    0 → 'A', 25 → 'Z', 26 → 'AA', 40 → 'AO'. There's no openpyxl import in
    this file (the spreadsheet is read purely via the Sheets API as plain
    values), so this small helper stands in for openpyxl's
    get_column_letter() wherever a 0-based index needs to become an A1 letter.
    """
    n = idx0 + 1
    letters = ''
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


@st.cache_data(ttl=120, show_spinner=False)
def _get_sheet_headers() -> list[str]:
    """
    Read just the header row (row 1) of the Recordings sheet. Shared by
    get_column_indices() and get_feature_defs() so both resolve column
    positions dynamically from the LIVE header text without each making its
    own duplicate Sheets API call.

    TTL=120s (2 min): row-1 is a tiny read; short TTL means newly-added or
    renamed feature columns appear automatically within ~2 minutes, without
    needing a manual 'Clear cache' in most cases.
    """
    _, _, sheets_svc = get_services()
    result = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='Recordings!1:1',
    ).execute()
    return (result.get('values') or [[]])[0]


@st.cache_data(ttl=3600, show_spinner=False)
def get_column_indices() -> dict:
    """
    Returns a dict mapping each COL_NAMES key to its 0-based column index in
    the live Recordings sheet. If a column header isn't found, its value is
    None. Cached for 1 hour.
    """
    headers = _get_sheet_headers()
    header_map = {h: i for i, h in enumerate(headers)}
    return {key: header_map.get(name) for key, name in COL_NAMES.items()}


# ════════════════════════════════════════════════════════════════════════════════
#  DYNAMIC FEATURE-COLUMN RESOLUTION
# ════════════════════════════════════════════════════════════════════════════════
# Every place in this app that needs a feature's spreadsheet column (tagging,
# searching, reading, writing, the Google-Doc FEATURES section, …) goes
# through the module-level FEATURE_DEFS list below, NOT through a hardcoded
# column letter. FEATURE_DEFS is rebuilt by get_feature_defs() — which is
# called once at module load (see the `FEATURE_DEFS = get_feature_defs()`
# assignment further down) and again on every Streamlit rerun once its cache
# TTL expires — by matching each known feature's *header text* against the
# live header row, via _get_sheet_headers(). This is the same "resolve by
# header text, not by position" pattern get_column_indices() already used for
# non-feature columns, now extended to cover features too.

APP_FEATURES_SHEET_NAME = "AppFeatureDefs"
_APP_FEATURES_HEADER = ['header_text', 'display_name', 'type', 'options']


@st.cache_data(ttl=600, show_spinner=False)
def get_extra_feature_defs() -> list[tuple]:
    """
    Read user-added feature definitions from the 'AppFeatureDefs' tab. Each row is
    (header_text, display_name, type, options) — options is None for 'bool'
    features or a list parsed from a '; '-separated string for 'select'
    features. Returns [] if the tab doesn't exist yet or has no data rows.
    Cached for 10 minutes so a freshly-added feature shows up quickly.
    """
    _, _, sheets_svc = get_services()
    try:
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{APP_FEATURES_SHEET_NAME}!A2:D",
        ).execute()
    except Exception:
        return []   # tab doesn't exist yet — nothing has been added
    rows = result.get('values') or []
    out = []
    for row in rows:
        row = row + [''] * (4 - len(row))
        header_text, display_name, ftype, options_raw = (c.strip() if isinstance(c, str) else c for c in row[:4])
        if not header_text:
            continue
        ftype = ftype or 'bool'
        options = [o.strip() for o in options_raw.split(';') if o.strip()] if ftype == 'select' else None
        out.append((header_text, display_name or header_text, ftype, options))
    return out


@st.cache_data(ttl=300, show_spinner=False)
def _infer_column_types(unknown_cols: tuple) -> dict:
    """
    Batch-read cell values for columns whose type is not in FEATURE_HEADER_DEFS
    or AppFeatureDefs, and infer bool vs. select from the actual data.

    unknown_cols is a tuple of (col_letter, header_text) pairs — it is the
    cache key, so this function re-fetches when the set of unknown column
    names changes (e.g. after adding a new column to the sheet).

    TTL=300s (5 min): also re-checks periodically so a column that was initially
    empty (inferred as bool) gets correctly re-classified once values are added.
    A manual 'Clear cache & reload' also triggers a re-fetch.

    Returns {header_text: (type, options)}.
    """
    if not unknown_cols:
        return {}
    _BOOL_VALS: frozenset = frozenset({
        '+', '-', 'true', 'false', 'yes', 'no', 'TRUE', 'FALSE', '1', '0',
    })
    result: dict = {}
    try:
        _, _, sheets_svc = get_services()

        # ── Step 1: read data-validation rules on row 2 of each unknown column.
        # Google Sheets dropdowns have ONE_OF_LIST validation — we can read the
        # options directly, even when the column is completely empty (no tagged rows).
        dv_options: dict = {}   # ht → list[str]
        try:
            dv_ranges = [f'Recordings!{col}2' for col, _ in unknown_cols]
            dv_resp = sheets_svc.spreadsheets().get(
                spreadsheetId=SPREADSHEET_ID,
                ranges=dv_ranges,
                includeGridData=True,
                fields='sheets.data.rowData.values.dataValidation',
            ).execute()
            sheet_data_list = (dv_resp.get('sheets') or [{}])[0].get('data', [])
            for i, (col, ht) in enumerate(unknown_cols):
                if i >= len(sheet_data_list):
                    break
                row_data = sheet_data_list[i].get('rowData') or []
                if not row_data:
                    continue
                cell_dv = (row_data[0].get('values') or [{}])[0].get('dataValidation', {})
                cond = cell_dv.get('condition', {})
                if cond.get('type') == 'ONE_OF_LIST':
                    opts = [v.get('userEnteredValue', '').strip()
                            for v in cond.get('values', [])]
                    dv_options[ht] = [o for o in opts if o]
        except Exception:
            pass  # DV read failed — fall through to value-based inference

        # ── Step 2: value-based inference for columns without DV rules.
        cols_no_dv = tuple((col, ht) for col, ht in unknown_cols if ht not in dv_options)
        if cols_no_dv:
            batch = sheets_svc.spreadsheets().values().batchGet(
                spreadsheetId=SPREADSHEET_ID,
                ranges=[f'Recordings!{col}2:{col}' for col, _ in cols_no_dv],
                majorDimension='COLUMNS',
            ).execute()
            for (col, ht), vr in zip(cols_no_dv, batch.get('valueRanges', [])):
                col_vals = (vr.get('values') or [[]])[0]
                # Cells may hold several values at once ("-e; -a"). Split them
                # so the inferred option list contains the individual values —
                # otherwise every combination a researcher happened to tag
                # would show up in the dropdown as its own bogus option.
                distinct: set = set()
                for v in col_vals:
                    if not str(v).strip():
                        continue
                    distinct.update(_split_feat_values(v))
                non_bool = sorted(v for v in distinct if v not in _BOOL_VALS)
                result[ht] = ('select', non_bool) if non_bool else ('bool', None)

        # ── Step 3: merge — DV-derived options take precedence over inference.
        for _, ht in unknown_cols:
            if ht in dv_options:
                result[ht] = ('select', sorted(dv_options[ht]))
            elif ht not in result:
                result[ht] = ('bool', None)

    except Exception:
        pass  # Fall back to bool for any column we couldn't read
    return result


def get_feature_defs() -> list[tuple]:
    """
    Dynamically discover feature columns by scanning the live Recordings
    header row for columns whose header starts with one of FEAT_PREFIXES
    ('PHON.', 'MOR.', 'SYN.', 'LEX.').

    • The header text itself is used as the display name (fd[2]).
    • Type/options come from FEATURE_HEADER_DEFS or AppFeatureDefs if known.
    • For unknown columns, _infer_column_types() reads their actual values.
    • NOT decorated with @st.cache_data — runs on every Streamlit rerun but
      cheaply, because _get_sheet_headers() and _infer_column_types() are
      themselves cached.  This ensures FEATURE_DEFS is always in sync with
      the header cache: as soon as _get_sheet_headers() refreshes (TTL or
      manual clear), the next rerun picks up new/removed columns immediately.

    Returns 5-tuples: (1-based-idx, col_letter, display_name, type, options).
    """
    headers = _get_sheet_headers()
    # Build type/options lookup from the static table + user-registered extras
    known_meta: dict = {
        ht.strip(): (dt, opts)
        for ht, _, dt, opts in FEATURE_HEADER_DEFS
    }
    for ht, _dn, dt, opts in get_extra_feature_defs():
        known_meta.setdefault(ht.strip(), (dt, opts))

    # Build a secondary lookup keyed by the name with its FEAT_PREFIX stripped.
    # This lets a new "LEX. want" column automatically inherit the type/options
    # from an old "want" entry in FEATURE_HEADER_DEFS or AppFeatureDefs, even
    # when the exact prefixed name isn't in known_meta yet.
    def _strip_prefix(s: str) -> str:
        for p in FEAT_PREFIXES:
            if s.startswith(p):
                return s[len(p):].strip()
        return s

    # Index EVERY known entry by its prefix-stripped name.  Bare entries (which
    # strip to themselves) are what make the rename case work: a sheet column
    # renamed from '"want"' to 'LEX. "want"' strips back to '"want"' and finds
    # the original definition.  Bare entries are inserted last so they win any
    # tie against an already-prefixed entry that strips to the same name.
    known_meta_stripped: dict = {}
    for k, v in known_meta.items():
        sk = _strip_prefix(k)
        if sk != k:                      # prefixed entry — index it first
            known_meta_stripped.setdefault(sk, v)
    for k, v in known_meta.items():
        if _strip_prefix(k) == k:        # bare entry — takes precedence
            known_meta_stripped[k] = v

    # Collect prefix-matching columns in sheet order
    prefix_cols: list = []   # [(idx, col_letter, ht), ...]
    for idx, header in enumerate(headers):
        ht = header.strip()
        if any(ht.startswith(p) for p in FEAT_PREFIXES):
            prefix_cols.append((idx, _col_letter(idx), ht))

    # Infer type for columns not resolvable from known_meta (exact or stripped)
    unknown = tuple(
        (col, ht) for _, col, ht in prefix_cols
        if ht not in known_meta and _strip_prefix(ht) not in known_meta_stripped
    )
    inferred_meta = _infer_column_types(unknown)

    resolved = []
    for idx, col_letter, ht in prefix_cols:
        dtype, options = (
            known_meta.get(ht)                          # 1. exact match (e.g. "LEX. want")
            or known_meta_stripped.get(_strip_prefix(ht))  # 2. prefix-stripped (e.g. "want")
            or inferred_meta.get(ht)                    # 3. inferred from data / DV rules
            or ('bool', None)                           # 4. fallback
        )
        resolved.append((idx + 1, col_letter, ht, dtype, options))
    return resolved


# Resolve the live feature list now (and again each cache window on every
# rerun) — this is THE list every consumer in this file reads from.
# Wrapped defensively: this now makes a live Sheets API call unconditionally
# at script load (unlike the old static literal, which couldn't fail). A
# transient API/network error here should degrade to "no features resolved
# this rerun" rather than crashing the entire app before it can render
# anything — st.cache_data will simply retry on the next rerun.
try:
    FEATURE_DEFS: list[tuple] = get_feature_defs()
except Exception as _feat_defs_err:
    FEATURE_DEFS = []
    _FEATURE_DEFS_LOAD_ERROR = str(_feat_defs_err)
else:
    _FEATURE_DEFS_LOAD_ERROR = None

# Map from feature display_name → FEATURE_DEFS entry (for fast lookup)
_FEAT_BY_NAME: dict = {fd[2]: fd for fd in FEATURE_DEFS}


@st.cache_data(ttl=600, show_spinner=False)
def load_corpus_index() -> list[dict]:
    """
    Reads the Recordings sheet and returns a list of dicts, one per transcribed doc.
    Column positions are discovered dynamically from the header row so the sheet
    columns can be reordered without breaking the app.
    """
    cols = get_column_indices()
    _, _, sheets_svc = get_services()
    result = sheets_svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        ranges=['Recordings'],
        includeGridData=True,
    ).execute()

    grid = result['sheets'][0]['data'][0]['rowData']
    corpus = []

    for grid_row_idx, row in enumerate(grid[1:], start=2):   # skip header; sheet row = grid_idx+1
        cells = row.get('values', [])

        def cell_val(idx, _cells=cells):
            if idx is None or idx >= len(_cells): return None
            return _cells[idx].get('formattedValue')

        def cell_link(idx, _cells=cells):
            if idx is None or idx >= len(_cells): return None
            cell = _cells[idx]
            # 1. Proper hyperlink (inserted via Insert > Link)
            if cell.get('hyperlink'):
                return cell['hyperlink']
            # 2. Plain-text URL pasted directly into the cell
            val = (
                (cell.get('userEnteredValue') or {}).get('stringValue')
                or cell.get('formattedValue')
                or ''
            )
            if 'docs.google.com' in val or val.startswith('https://'):
                return val.strip()
            return None

        trans_name = cell_val(cols['trans_link'])
        trans_url  = cell_link(cols['trans_link'])

        # Only include rows that have a recognisable Google link
        if not trans_url or not any(d in trans_url for d in (
            'docs.google.com/document', 'drive.google.com', 'docs.google.com/file'
        )):
            continue

        doc_id = _extract_doc_id(trans_url)
        if not doc_id:
            continue

        rec_name = cell_val(cols['rec_link']) or ''
        corpus.append({
            'name':            trans_name or rec_name or doc_id,
            'rec_name':        rec_name,
            'doc_id':          doc_id,
            'village':         cell_val(cols['village'])         or '',
            'social_typology': cell_val(cols['social_typology']) or '',
            'geo_typology':    cell_val(cols['geo_typology'])    or '',
            'community':       cell_val(cols['community'])       or '',
            'gender':          cell_val(cols['gender'])          or '',
            'status':          cell_val(cols['status'])          or '',
            'sheet_row':       grid_row_idx,
        })

    return corpus


@st.cache_data(ttl=3600, show_spinner=False, persist="disk")
def get_doc_content(doc_id: str, version: int = 0) -> dict:
    """
    Fetches a Google Doc via the Drive API HTML export.
      - display_html: full Google Docs HTML — rendered pixel-perfect in the viewer
      - italic_text:  italic body text (after ***) extracted from the HTML CSS classes
                      — used as the search index (reliable, no Docs API needed)
    """
    try:
        drive_svc, _, _ = get_services()

        export_req = drive_svc.files().export_media(fileId=doc_id, mimeType='text/html')
        buf = io.BytesIO()
        dl  = MediaIoBaseDownload(buf, export_req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        display_html = buf.getvalue().decode('utf-8')

    except Exception:
        return {'italic_text': '', 'display_html': ''}

    italic_text = extract_transcription_text(display_html)

    return {
        'italic_text':  italic_text,
        'display_html': display_html,
    }


def _split_feature_line(text: str, fd: tuple) -> tuple:
    """
    Parse ONE line of a document's FEATURES block into (example_words, value).

    Two formats exist across the corpus:
        new: "name  [word1; word2]   value"
        old: "name  [value]  word1, word2"
    The bracket content is read as the VALUE (old format) when it matches one of
    the feature's known options, or looks like an all-ASCII code rather than
    transcription; otherwise it is read as the example words (new format).

    Returns (None, None) when the line does not belong to `fd`.
    """
    if not text.startswith(fd[2] + '  ['):
        return (None, None)
    bo = text.find('[')
    bc = text.find(']', bo)
    if bo < 0 or bc < 0:
        return ('', '')
    inside = text[bo + 1:bc].strip()
    after  = text[bc + 1:].strip()
    known_vals = set(fd[4] or []) | {'+', '', 'TRUE', 'FALSE', 'True', 'False'}
    is_old = (inside in known_vals or
              (not any(ord(c) > 127 for c in inside) and inside == inside.upper()
               and not inside.replace(' ', '').isalpha()))
    return (after, inside) if is_old else (inside, after)


def _doc_html_to_lines(html_doc: str) -> list:
    """Flatten a Google Docs HTML export into plain per-paragraph text lines."""
    if not html_doc:
        return []
    txt = re.sub(r'</p>|</div>|<br[^>]*>|</h[1-6]>', '\n', html_doc, flags=re.I)
    txt = re.sub(r'<[^>]+>', '', txt)
    txt = html_lib.unescape(txt).replace('\xa0', ' ')
    return [ln.strip() for ln in txt.split('\n')]


@st.cache_data(ttl=3600, show_spinner=False)
def get_doc_feature_examples(doc_id: str, version: int = 0,
                             _col_set: tuple = ()) -> dict:
    """
    {feature_name: "word1; word2"} — the words a researcher tagged as the
    example for each feature in this document.

    These words live ONLY in the Google Doc's FEATURES block; the spreadsheet
    stores just the value. They are therefore read back out of the doc's HTML
    export — which get_doc_content() already cached while searching, so this
    costs no extra API call for any document that appeared in the results.

    _col_set is part of the cache key so a renamed feature column invalidates
    it, the same way _get_all_sheet_features() is keyed.
    Returns {} if the document cannot be read.
    """
    try:
        html_doc = (get_doc_content(doc_id, version) or {}).get('display_html', '')
    except Exception:
        return {}
    if not html_doc:
        return {}

    out: dict = {}
    in_feats = False
    for line in _doc_html_to_lines(html_doc):
        if line == 'FEATURES:':
            in_feats = True
            continue
        if not in_feats or not line or line in FEAT_PREFIXES:
            continue
        for fd in FEATURE_DEFS:
            ex, _val = _split_feature_line(line, fd)
            if ex is not None:          # line belongs to this feature
                if ex:
                    out[fd[2]] = ex
                break
    return out


def _csv_feature_header() -> list:
    """
    CSV column names for the feature block: every feature contributes TWO
    columns — its value, and immediately beside it the word that was tagged
    as the example for that value.
    """
    return [x for fd in FEATURE_DEFS for x in (fd[2], f'{fd[2]} — example')]


def _csv_feature_cells(sheet_row, doc_id: str = '') -> list:
    """
    Flat [value, example, value, example, ...] in FEATURE_DEFS order, matching
    _csv_feature_header().

    An untagged bool feature exports as an EMPTY cell, never 'FALSE'. Blank
    means "not assessed" while FALSE means "assessed and found absent"; writing
    FALSE for an untouched cell would silently invent negative data across the
    whole corpus.
    """
    vals: dict = {}
    if sheet_row:
        try:
            vals = get_sheet_features(sheet_row) or {}
        except Exception:
            vals = {}

    examples: dict = {}
    if doc_id:
        try:
            _ver = st.session_state.get('_doc_versions', {}).get(doc_id, 0)
            examples = get_doc_feature_examples(
                doc_id, _ver,
                _col_set=tuple((fd[1], fd[2]) for fd in FEATURE_DEFS),
            ) or {}
        except Exception:
            examples = {}

    out = []
    for fd in FEATURE_DEFS:
        v = vals.get(fd[1])
        if fd[3] == 'bool':
            cell = '' if v is None else ('TRUE' if v else 'FALSE')
        else:
            cell = v if v not in (None, '', False) else ''
        out.append(cell)
        out.append(examples.get(fd[2], ''))
    return out


# ════════════════════════════════════════════════════════════════════════════════
#  FEATURE READ / WRITE
# ════════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def _get_all_sheet_features(version: int = 0, _col_set: tuple = ()) -> dict:
    """
    Read every feature column (all rows) and return
    {sheet_row: {col_letter: value}}. Cached for 1 hour; pass a different
    version to bust the cache after a write.

    _col_set is a tuple of (col_letter, header_text) pairs derived from
    FEATURE_DEFS and passed as an explicit parameter so that it becomes part
    of the Streamlit cache key.  When a column is renamed or a new prefix-
    based column appears — causing FEATURE_DEFS to change — _col_set changes
    too, which immediately invalidates this cache and forces a fresh batchGet.
    Without this, a rename would silently serve 1-hour-stale feature data even
    though _get_sheet_headers() already picked up the change.

    Each feature is read via its OWN open-ended column range (e.g.
    'Recordings!V2:V'), all fetched together in a single batchGet call —
    rather than one contiguous range indexed by position, like the old
    implementation. This is deliberate: FEATURE_DEFS is now resolved
    dynamically by header text (see get_feature_defs()) and is no longer
    guaranteed to be a gapless, left-to-right-ordered block of columns —
    features can live anywhere in the sheet, including a brand-new column a
    user just added via the sidebar. Reading per-column by resolved letter
    keeps this correct regardless of layout.
    """
    _, _, sheets_svc = get_services()
    if not FEATURE_DEFS:
        return {}
    ranges = [f"Recordings!{fd[1]}2:{fd[1]}" for fd in FEATURE_DEFS]
    result = sheets_svc.spreadsheets().values().batchGet(
        spreadsheetId=SPREADSHEET_ID,
        ranges=ranges,
        valueRenderOption='UNFORMATTED_VALUE',
    ).execute()
    value_ranges = result.get('valueRanges', [])

    out: dict = {}
    for fd, vr in zip(FEATURE_DEFS, value_ranges):
        col_letter, ftype = fd[1], fd[3]
        rows = vr.get('values') or []
        for i, row_vals in enumerate(rows):
            sheet_row = i + 2   # spreadsheet row index (1-based, header = row 1)
            val = row_vals[0] if row_vals else None
            row_out = out.setdefault(sheet_row, {})
            if ftype == 'bool':
                row_out[col_letter] = bool(val) if val is not None else None
            else:
                row_out[col_letter] = str(val) if val else None
    return out


def get_sheet_features(sheet_row: int) -> dict:
    """
    Return feature values for a single sheet row.
    Uses the batch cache (_get_all_sheet_features) so no extra API call is made —
    all rows are loaded in one request and kept for 1 hour.
    """
    version  = st.session_state.get('_features_version', 0)
    col_set  = tuple((fd[1], fd[2]) for fd in FEATURE_DEFS)
    all_features = _get_all_sheet_features(version=version, _col_set=col_set)
    return all_features.get(sheet_row, {fd[1]: None for fd in FEATURE_DEFS})


def write_sheet_features(sheet_row: int, changes: dict[str, object]) -> list[str]:
    """
    Write feature changes to Google Sheets.
    changes: {col_letter: new_value}

    Select-type features are MULTI-VALUE: a new tag is merged into whatever is
    already in the cell rather than replacing it, so two researchers tagging
    different reflexes of the same feature both keep their tag. Nothing is ever
    silently dropped or blocked.

    Returns a list of human-readable notices describing what was merged
    (empty when every write went into an empty cell). Callers should DISPLAY
    these — unlike the old conflict list, a non-empty return no longer means
    the write was refused.
    """
    _, _, sheets_svc = get_services()
    current = get_sheet_features(sheet_row)
    notices: list = []

    data = []
    for col_letter, new_val in changes.items():
        fd = next((f for f in FEATURE_DEFS if f[1] == col_letter), None)
        if fd is None:
            continue
        cell_a1 = f"Recordings!{col_letter}{sheet_row}"

        if fd[3] == 'bool':
            data.append({'range': cell_a1, 'values': [[bool(new_val)]]})
            continue

        # ── select: merge instead of overwrite ────────────────────────────────
        cur_val = current.get(col_letter)
        merged, added, dup = _merge_feat_values(cur_val, new_val, fd[4])
        existing = _split_feat_values(cur_val, fd[4])

        if existing and added:
            notices.append(
                f"**{fd[2]}**: added `{'`, `'.join(added)}` — "
                f"this document is now tagged `{merged}`"
            )
        elif dup and not added:
            notices.append(
                f"**{fd[2]}**: `{'`, `'.join(dup)}` was already tagged — no change"
            )

        data.append({'range': cell_a1, 'values': [[merged]]})

    if data:
        sheets_svc.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'valueInputOption': 'RAW', 'data': data},
        ).execute()
        # Bust the batch-features cache so the next open reflects the write
        st.session_state['_features_version'] = st.session_state.get('_features_version', 0) + 1

    return notices


def delete_feature_tag(doc_id: str, sheet_rows: list[int], col_letter: str):
    """
    Delete a single feature tag:
      1. Clears the spreadsheet cell(s) for this doc's row(s).
      2. Rewrites the Google Doc FEATURES section with the cleared value.
    """
    _, _, sheets_svc = get_services()

    # 1. Clear the cell in every sheet row that belongs to this doc
    data = [
        {'range': f"Recordings!{col_letter}{row}", 'values': [['']]}
        for row in (sheet_rows or [])
    ]
    if data:
        sheets_svc.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'valueInputOption': 'RAW', 'data': data},
        ).execute()
        # Invalidate the sheet-features cache the same way write_sheet_features
        # does: bump the version so the next call to get_sheet_features fetches
        # fresh data. (get_sheet_features is a plain wrapper — calling .clear()
        # on it would raise AttributeError since it is not a cached function.)
        st.session_state['_features_version'] = st.session_state.get('_features_version', 0) + 1

    # 2. Rewrite Google Doc FEATURES section with updated (cleared) values
    if doc_id and sheet_rows:
        try:
            # Pass None for the deleted col → tells the function to remove that line
            update_gdoc_features_section(doc_id, {col_letter: None})
        except Exception:
            pass   # doc update failure is non-critical; spreadsheet already cleared


def _build_features_block(sheet_vals: dict, doc_only_vals: dict) -> str:
    """Build the FEATURES text block to write into the Google Doc."""
    lines = ['FEATURES:']
    # O-AO features (from spreadsheet)
    for fd in FEATURE_DEFS:
        col_l, name, ftype = fd[1], fd[2], fd[3]
        val = sheet_vals.get(col_l)
        if ftype == 'bool':
            lines.append(f'{name}  [{"+" if val else ""}]')
        else:
            lines.append(f'{name}  [{val or ""}]')
    # Doc-only features
    for name in DOC_ONLY_FEATURES:
        val = doc_only_vals.get(name)
        if isinstance(val, bool):
            lines.append(f'{name}  [{"+" if val else ""}]')
        elif val:
            lines.append(f'{name}  [{val}]')
        else:
            lines.append(f'{name}  []')
    return '\n'.join(lines)


def update_gdoc_features_section(
    doc_id: str,
    pending_vals: dict,       # {col_letter: value | None}  — newly tagged features
    example_words: dict | None = None,   # {col_letter: "word"} newly tagged words
):
    """
    Update the FEATURES section in the Google Doc — surgical update only.

    • Only modifies lines for features in pending_vals.
    • All other existing feature lines are preserved as-is.
    • If pending_vals[col] is None/empty → remove that feature's line.
    • If FEATURES section doesn't exist → create it with only the pending lines.
    """
    _, docs_svc, _ = get_services()
    doc = docs_svc.documents().get(documentId=doc_id).execute()
    body_content = doc.get('body', {}).get('content', [])
    example_words = example_words or {}

    all_known_names = {fd[2] for fd in FEATURE_DEFS} | set(DOC_ONLY_FEATURES)

    # ── Parse the doc: find FEATURES section + extract existing lines ──────────
    feat_start = feat_end = None
    existing_lines: dict[str, str] = {}   # feature_name → "full line text"
    existing_examples: dict[str, str] = {}  # col_letter → "word1, word2"

    para_texts: list[tuple[int, str]] = []
    for elem in body_content:
        if 'paragraph' not in elem:
            continue
        text = ''.join(
            e.get('textRun', {}).get('content', '')
            for e in elem['paragraph'].get('elements', [])
        ).strip()
        para_texts.append((elem['startIndex'], text))

    in_features = False
    for start_idx, text in para_texts:
        if text.strip() == 'FEATURES:':
            feat_start = start_idx
            in_features = True
            continue
        if in_features:
            # Bare group-header lines ('PHON.', 'MOR.', 'SYN.', 'LEX.') are
            # part of the block but carry no data — skip them; they'll be
            # regenerated on write.
            if text.strip() in FEAT_PREFIXES:
                continue
            # End condition: non-empty text that isn't a known feature line
            if text and not any(text.startswith(fn) for fn in all_known_names):
                feat_end = start_idx
                break
            # Parse each feature line.
            # Format written by this code (new): "name  [word1; word2]   val_str"
            # Format found in older docs (old):  "name  [val_str]  word1, word2"
            # Detection: content between [] is "words" if it contains non-ASCII
            # characters (Arabic transcription) or is absent from the feature's
            # known option list; otherwise it's treated as a value (old format).
            matched = False
            for fd in FEATURE_DEFS:
                if text.startswith(fd[2] + '  ['):
                    existing_lines[fd[2]] = text
                    matched = True
                    bo = text.find('[')
                    bc = text.find(']', bo)
                    if bo >= 0 and bc >= 0:
                        inside = text[bo + 1:bc].strip()
                        after  = text[bc + 1:].strip()
                        # Determine format: if inside looks like a feature value, old format
                        known_vals = set(fd[4] or []) | {'+', '', 'TRUE', 'FALSE', 'True', 'False'}
                        is_old = (inside in known_vals or
                                  (not any(ord(c) > 127 for c in inside) and inside == inside.upper()
                                   and not inside.replace(' ', '').isalpha()))
                        if is_old:
                            # Old format: words are after the bracket
                            existing_examples[fd[1]] = after
                        else:
                            # New format: words are inside the bracket
                            existing_examples[fd[1]] = inside
                    break
            if not matched:
                # Doc-only feature (no spreadsheet column, e.g. "was" since the
                # 2026-06-22 sheet reorg) — capture the line verbatim so it
                # survives the rewrite below unchanged; it's never present in
                # pending_vals (which is always keyed by col_letter), so it can
                # only ever be carried through, never edited here.
                for _don in DOC_ONLY_FEATURES:
                    if text.startswith(_don + '  ['):
                        existing_lines[_don] = text
                        break

    # ── Build updated set of lines ─────────────────────────────────────────────
    # Start with all existing lines, then apply pending changes
    updated_lines: dict[str, str] = dict(existing_lines)

    for col_l, new_val in pending_vals.items():
        fd = next((f for f in FEATURE_DEFS if f[1] == col_l), None)
        if not fd:
            continue
        name = fd[2]

        # Deletion: empty value removes the line
        if not new_val and new_val is not True:
            updated_lines.pop(name, None)
            continue

        val_str = '+' if fd[3] == 'bool' else str(new_val)

        # Merge example words: keep existing ones (from new-format lines),
        # append new word if not already present.  Separator is semicolon.
        ex_existing = existing_examples.get(col_l, '')
        _ex_raw = example_words.get(col_l) or ''
        # pending_words may be a list (accumulated from multiple tag actions) or a string
        if isinstance(_ex_raw, list):
            ex_new_items = [w.strip() for w in _ex_raw if w and w.strip()]
        else:
            ex_new_items = [_ex_raw.strip()] if _ex_raw.strip() else []
        if ex_new_items:
            words_list = [w.strip() for w in ex_existing.split(';') if w.strip()]
            for _wi in ex_new_items:
                if _wi and _wi not in words_list:
                    words_list.append(_wi)
            ex_merged = '; '.join(words_list)
        else:
            ex_merged = ex_existing

        # New format: name  [word1; word2]   val_str
        line = f'{name}  [{ex_merged}]'
        if val_str and val_str not in ('+', ''):
            line += f'   {val_str}'
        elif val_str == '+':
            line += '   +'
        updated_lines[name] = line

    # ── Reconstruct the FEATURES block with section headers ───────────────────
    # Features are emitted in spreadsheet column order (FEATURE_DEFS order).
    # A bare prefix header ('PHON.', 'MOR.', …) is inserted once before the
    # first feature of each group that has at least one line to write.
    lines = ['FEATURES:']
    emitted_prefixes: set = set()
    for fd in FEATURE_DEFS:
        if fd[2] not in updated_lines:
            continue
        prefix = next((p for p in FEAT_PREFIXES if fd[2].startswith(p)), None)
        if prefix and prefix not in emitted_prefixes:
            lines.append(prefix)
            emitted_prefixes.add(prefix)
        lines.append(updated_lines[fd[2]])
    # Preserve any doc-only feature lines (e.g. '"was"') that were already there
    fd_names = {fd[2] for fd in FEATURE_DEFS}
    for name, line in existing_lines.items():
        if name not in fd_names and name in updated_lines:
            lines.append(updated_lines[name])
    new_block = '\n'.join(lines) + '\n'

    # ── Write to Google Doc ────────────────────────────────────────────────────
    block_len = len(new_block)
    # "FEATURES:" is always the first line; its length (with newline) is used to
    # apply bold+non-italic style to just the heading, not the content lines.
    heading_len = len('FEATURES:\n')

    if feat_start is None:
        insert_at = body_content[-1]['endIndex'] - 1
        full_text  = '\n\n' + new_block
        heading_start = insert_at + 2   # skip the two leading newlines
        docs_svc.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': [
                {'insertText': {
                    'location': {'index': insert_at},
                    'text': full_text,
                }},
                # Clear inherited background on the whole block
                {'updateTextStyle': {
                    'range': {
                        'startIndex': insert_at,
                        'endIndex':   insert_at + len(full_text),
                    },
                    'textStyle': {'backgroundColor': {}},
                    'fields': 'backgroundColor',
                }},
                # Bold + non-italic for "FEATURES:" heading only
                {'updateTextStyle': {
                    'range': {
                        'startIndex': heading_start,
                        'endIndex':   heading_start + heading_len,
                    },
                    'textStyle': {'bold': True, 'italic': False},
                    'fields': 'bold,italic',
                }},
            ]},
        ).execute()
    else:
        end_idx = feat_end if feat_end else body_content[-1]['endIndex'] - 1
        docs_svc.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': [
                {'deleteContentRange': {'range': {
                    'startIndex': feat_start, 'endIndex': end_idx,
                }}},
                {'insertText': {
                    'location': {'index': feat_start},
                    'text': new_block,
                }},
                # Clear inherited background on the whole block
                {'updateTextStyle': {
                    'range': {
                        'startIndex': feat_start,
                        'endIndex':   feat_start + block_len,
                    },
                    'textStyle': {'backgroundColor': {}},
                    'fields': 'backgroundColor',
                }},
                # Bold + non-italic for "FEATURES:" heading only
                {'updateTextStyle': {
                    'range': {
                        'startIndex': feat_start,
                        'endIndex':   feat_start + heading_len,
                    },
                    'textStyle': {'bold': True, 'italic': False},
                    'fields': 'bold,italic',
                }},
            ]},
        ).execute()

    # NOTE: intentionally NOT clearing get_doc_content cache here.
    # The transcript text doesn't change when features are tagged (only the FEATURES
    # section at the end changes). Clearing the full cache causes intermittent failures
    # when the Drive API re-fetch is slow or rate-limited, making the doc disappear.
    # Users can click "Open in Google Docs" to see the freshly written FEATURES block.


def _get_gdoc_body_runs(doc_id: str) -> list[tuple]:
    """
    Return a flat list of (run_start_index, text) for every textRun in the
    Google Doc's body, in document order. run_start_index is the Docs API
    structural index where that run's text begins, so
    run_start_index + offset_within_run gives an absolute Docs API character
    index for any character inside that run. Used by
    replace_one_occurrence_in_gdoc() to locate a specific occurrence's exact
    [startIndex, endIndex) range for a targeted (not document-wide) edit.
    """
    _, docs_svc, _ = get_services()
    doc = docs_svc.documents().get(documentId=doc_id).execute()
    runs: list[tuple] = []

    def walk(elements):
        for el in elements:
            if 'paragraph' in el:
                for pe in el['paragraph'].get('elements', []):
                    tr = pe.get('textRun')
                    if tr is not None:
                        runs.append((pe['startIndex'], tr.get('content', '')))
            elif 'table' in el:
                for row in el['table'].get('tableRows', []):
                    for cell in row.get('tableCells', []):
                        walk(cell.get('content', []))
            elif 'tableOfContents' in el:
                walk(el['tableOfContents'].get('content', []))

    walk(doc.get('body', {}).get('content', []))
    return runs


def replace_one_occurrence_in_gdoc(doc_id: str, find_text: str, replace_text: str,
                                    occurrence_index: int = 0) -> bool:
    """
    Replace ONLY the occurrence_index-th (0-based) occurrence of find_text in
    the document body with replace_text.

    This replaces the old find_replace_in_gdoc(), which used the Docs API's
    replaceAllText and therefore replaced EVERY occurrence in the document —
    a bug, since the context menu is for editing the one word/phrase the
    user actually selected. occurrence_index is computed client-side (see
    computeOccurrenceIndex() in the context-menu JS) by counting how many
    matches of the selected text appear before the user's actual selection
    point, so it identifies exactly the occurrence they marked, regardless
    of how many other identical occurrences exist elsewhere in the doc.

    Returns True if the replacement was made; False if that occurrence
    couldn't be located (e.g. the doc changed since the page loaded, or the
    match's start/end fall in runs this can't safely resolve) — callers
    should show a clear "couldn't find it" message rather than silently
    falling back to a document-wide replace.
    """
    runs = _get_gdoc_body_runs(doc_id)
    full_text = ''.join(r[1] for r in runs)

    # Find the occurrence_index-th (0-based) match of find_text.
    search_from = 0
    match_start = -1
    for _ in range(occurrence_index + 1):
        match_start = full_text.find(find_text, search_from)
        if match_start == -1:
            return False
        search_from = match_start + 1
    match_end = match_start + len(find_text)

    # Map [match_start, match_end) in the concatenated text back to absolute
    # Docs API indices using each run's own startIndex — this stays correct
    # even though paragraph-break characters (not part of any textRun) are
    # absent from `full_text`, since each run supplies its own true offset.
    abs_start = abs_end = None
    pos = 0
    for run_start, text in runs:
        run_text_start, run_text_end = pos, pos + len(text)
        if abs_start is None and run_text_start <= match_start < run_text_end:
            abs_start = run_start + (match_start - run_text_start)
        if abs_end is None and run_text_start < match_end <= run_text_end:
            abs_end = run_start + (match_end - run_text_start)
        pos = run_text_end
        if abs_start is not None and abs_end is not None:
            break

    if abs_start is None or abs_end is None:
        return False   # couldn't safely resolve this occurrence's exact range

    _, docs_svc, _ = get_services()
    docs_svc.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': [
            {'deleteContentRange': {'range': {'startIndex': abs_start, 'endIndex': abs_end}}},
            {'insertText': {'location': {'index': abs_start}, 'text': replace_text}},
        ]},
    ).execute()

    # Bump the per-doc version so only this document's cache entry is invalidated,
    # not every other document in the search results.
    _dv = st.session_state.setdefault('_doc_versions', {})
    _dv[doc_id] = _dv.get(doc_id, 0) + 1
    return True


# ════════════════════════════════════════════════════════════════════════════════
#  SEARCH
# ════════════════════════════════════════════════════════════════════════════════

def _apply_filters(corpus: list[dict], active_filters: dict) -> list[dict]:
    """Filter corpus by the multiselect active_filters dict.
    Each key maps to a list of allowed values; empty list = no filter on that field."""
    for field, allowed in active_filters.items():
        if allowed:
            corpus = [d for d in corpus if d.get(field, '') in allowed]
    return corpus


def run_search(
    pattern: str,
    position: str,
    name_filter: str,
    corpus: list[dict],
    active_filters: dict | None = None,
) -> list[dict]:

    try:
        sub_rxs = parse_sequence_pattern(pattern)
    except re.error as e:
        st.error(f"Invalid pattern: {e}")
        return []

    # Apply filters
    if active_filters:
        corpus = _apply_filters(corpus, active_filters)

    if not corpus:
        st.info("No documents match the name filter.", icon="🔍")
        return []

    # Snapshot doc versions — safe to pass into threads
    _doc_versions = dict(st.session_state.get('_doc_versions', {}))

    bar = st.progress(0.0, text=f"Searching {len(corpus)} documents…")
    results      = []
    _load_errors = []

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    _n   = len(sub_rxs)  # number of words in the pattern sequence
    _ctx = get_script_run_ctx()

    def _fetch_and_search(doc):
        # See the matching comment in the background-preload block above —
        # propagate the ScriptRunContext into this worker thread before it
        # touches st.cache_data (get_doc_content).
        if _ctx is not None:
            add_script_run_ctx(threading.current_thread(), _ctx)
        ver     = _doc_versions.get(doc['doc_id'], 0)
        content = get_doc_content(doc['doc_id'], version=ver)
        search_text   = content['italic_text']
        word_list     = tokenize(search_text)
        match_count   = 0
        matched_words = []
        seen_words    = set()

        if _n == 1:
            # Single-word pattern — original per-word loop (fastest path)
            rx = sub_rxs[0]
            for word in word_list:
                hits = match_word(word, rx, _subpattern_position(rx, position))
                if hits:
                    match_count += len(hits)
                    if word not in seen_words:
                        seen_words.add(word)
                        matched_words.append(highlight_word(word, hits))
        else:
            # Multi-word sequence pattern — slide an N-gram window
            for i in range(len(word_list) - _n + 1):
                ngram = word_list[i:i + _n]
                seq   = _match_sequence(ngram, sub_rxs, position)
                if seq:
                    match_count += 1
                    for word, hits in seq:
                        if word not in seen_words:
                            seen_words.add(word)
                            matched_words.append(highlight_word(word, hits))

        if match_count > 0:
            display_html = highlight_in_exported_html(content['display_html'], sub_rxs, position)
            return {
                'name':          doc['name'],
                'doc_id':        doc['doc_id'],
                'sheet_row':     doc.get('sheet_row'),
                'village':       doc.get('village', ''),
                'community':     doc.get('community', ''),
                'gender':        doc.get('gender', ''),
                'status':        doc.get('status', ''),
                'match_count':   match_count,
                'word_count':    len(tokenize(search_text)),
                'matched_words': matched_words[:15],
                'display_html':  display_html,
            }
        return None

    try:
        total     = len(corpus)
        completed = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_and_search, doc): doc for doc in corpus}
            for future in as_completed(futures):
                completed += 1
                # Update progress bar at most every 5 % to avoid UI overhead
                if completed % max(1, total // 20) == 0 or completed == total:
                    bar.progress(completed / total,
                                 text=f"Searching… {completed}/{total}")
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as _doc_err:
                    _load_errors.append(f"{futures[future]['name']}: {_doc_err}")
    finally:
        bar.empty()

    if _load_errors:
        st.warning(f"⚠️  {len(_load_errors)} document(s) could not be loaded and were skipped.")

    results.sort(key=lambda r: r['match_count'], reverse=True)
    return results


def search_by_name(query: str, corpus: list[dict]) -> list[dict]:
    """
    Find documents whose name (or village / community) contains the query
    as a literal substring (case-insensitive).  Used for the 'Find document'
    mode so users can look up identifiers like Xḏ̣.2M.R1(t) directly.
    """
    q = query.strip().lower()
    matches = [
        doc for doc in corpus
        if q in doc['name'].lower()
        or q in doc.get('rec_name', '').lower()
        or q in doc.get('village', '').lower()
        or q in doc.get('community', '').lower()
    ]
    if not matches:
        return []

    results = []
    seen_doc_ids = set()   # same Google Doc can be listed under multiple sheet rows
    bar = st.progress(0.0, text="Loading document…")
    for i, doc in enumerate(matches):
        bar.progress((i + 1) / max(len(matches), 1), text=f"Loading · {doc['name']}")
        if doc['doc_id'] in seen_doc_ids:
            continue        # skip duplicate doc_ids — avoid a redundant fetch + a
                             # duplicate result card for what is really one document
        seen_doc_ids.add(doc['doc_id'])
        try:
            _doc_ver = st.session_state.get('_doc_versions', {}).get(doc['doc_id'], 0)
            content = get_doc_content(doc['doc_id'], version=_doc_ver)
        except Exception:
            continue
        results.append({
            'name':          doc['name'],
            'doc_id':        doc['doc_id'],
            'sheet_row':     doc.get('sheet_row'),
            'village':       doc['village'],
            'community':     doc['community'],
            'gender':        doc['gender'],
            'status':        doc.get('status', ''),
            'match_count':   1,
            'word_count':    len(tokenize(content['italic_text'])),
            'matched_words': [],
            'display_html':  content['display_html'],
        })
    bar.empty()
    return results


# ════════════════════════════════════════════════════════════════════════════════
#  FEATURE TAGGING PANEL
# ════════════════════════════════════════════════════════════════════════════════

def _render_submit_bar(doc_id: str, doc_name: str, sheet_rows: list):
    """
    Slim submit bar shown below the document viewer when the user has staged
    feature tags via right-click.  No checkbox grid — all tagging is via
    the right-click context menu in the document iframe.
    """
    sk = f"feat_{doc_id}"

    # Initialise session-state slots
    if f"{sk}_pending" not in st.session_state:
        st.session_state[f"{sk}_pending"] = {}
    if f"{sk}_doc_only" not in st.session_state:
        st.session_state[f"{sk}_doc_only"] = {}

    pending  = st.session_state[f"{sk}_pending"]
    doc_only = st.session_state[f"{sk}_doc_only"]

    has_changes = bool(pending)

    # ── Delete existing tags (always shown when there are tagged features) ──
    if sheet_rows:
        try:
            _existing = get_sheet_features(sheet_rows[0])
        except Exception:
            _existing = {}
        _tagged_feats = [
            (fd, _existing.get(fd[1]))
            for fd in FEATURE_DEFS
            if _existing.get(fd[1]) not in (None, False, '', 0)
        ]
        if _tagged_feats:
            with st.expander(f"🗑️  Remove existing tags  ({len(_tagged_feats)} tagged)"):
                _pending_del = st.session_state.get(f"{sk}_pending_delete")
                for _fd, _val in _tagged_feats:
                    _c1, _c2 = st.columns([5, 1])
                    _val_str = '✓' if _fd[3] == 'bool' else str(_val)
                    _c1.markdown(f"`{_fd[2]}` = **{_val_str}**")
                    if _c2.button("🗑️", key=f"del_{sk}_{_fd[1]}", help=f"Remove {_fd[2]}"):
                        st.session_state[f"{sk}_pending_delete"] = _fd[1]
                        st.rerun()

                # Confirmation step — shown after clicking 🗑️
                if _pending_del:
                    _del_fd = next((f for f in FEATURE_DEFS if f[1] == _pending_del), None)
                    if _del_fd:
                        _del_val = _existing.get(_pending_del)
                        _del_val_str = '✓' if _del_fd[3] == 'bool' else str(_del_val)
                        st.warning(
                            f"Delete **{_del_fd[2]}** = `{_del_val_str}`? "
                            f"This will clear the value from the spreadsheet and remove the line from the Google Doc."
                        )
                        _yes_col, _no_col = st.columns(2)
                        with _yes_col:
                            if st.button("✅ Yes, delete", key=f"{sk}_del_confirm", type="primary"):
                                with st.spinner(f"Deleting {_del_fd[2]}…"):
                                    try:
                                        delete_feature_tag(doc_id, sheet_rows, _pending_del)
                                        st.session_state.pop(f"{sk}_pending_delete", None)
                                        st.success(f"✅ Deleted **{_del_fd[2]}**")
                                        st.rerun()
                                    except Exception as _de:
                                        st.error(f"Delete failed: {_de}")
                        with _no_col:
                            if st.button("❌ Cancel", key=f"{sk}_del_cancel"):
                                st.session_state.pop(f"{sk}_pending_delete", None)
                                st.rerun()

    if not has_changes:
        st.caption("Right-click words in the transcript above to tag features.")
        return

    # ── Summary of staged tags ─────────────────────────────────────────────
    # Each feature (and each individual tagged word under it) can be discarded
    # on its own before submitting — no need to clear everything just to give
    # up on one mis-tagged word out of several.
    pending_words = st.session_state.get(f"{sk}_pending_words", {})
    n = len(pending)
    st.markdown(f"🏷️ **{n} feature(s) staged** — remove any you don't want, then submit the rest:")

    for col_l, val in list(pending.items()):
        fd = next((f for f in FEATURE_DEFS if f[1] == col_l), None)
        feat_label = fd[2] if fd else col_l
        words = pending_words.get(col_l, [])
        if isinstance(words, str):
            words = [words] if words else []

        _row1, _row2 = st.columns([5, 1])
        with _row1:
            st.markdown(f"`{feat_label}` = **{val}**")
        with _row2:
            if st.button("🗑️ Remove", key=f"{sk}_rmfeat_{col_l}",
                         help=f"Discard the {feat_label} tag entirely"):
                pending.pop(col_l, None)
                pending_words.pop(col_l, None)
                st.session_state[f"{sk}_pending"] = pending
                st.session_state[f"{sk}_pending_words"] = pending_words
                st.rerun()

        if words:
            _word_cols = st.columns(len(words))
            for i, w in enumerate(words):
                with _word_cols[i]:
                    if st.button(f"✕ {w}", key=f"{sk}_rmword_{col_l}_{i}",
                                 help=f"Remove just this example word from {feat_label} (keeps the feature tag)"):
                        new_words = [x for j, x in enumerate(words) if j != i]
                        if new_words:
                            pending_words[col_l] = new_words
                        else:
                            pending_words.pop(col_l, None)
                        st.session_state[f"{sk}_pending_words"] = pending_words
                        st.rerun()

    st.divider()

    btn_col, clr_col = st.columns([4, 1])
    with btn_col:
        if st.button(
            f"💾  Submit {n} feature(s)",
            key=f"{sk}_submit_bar", type="primary", use_container_width=True,
        ):
            st.session_state[f"{sk}_confirm"] = True
    with clr_col:
        if st.button("✕ Clear all", key=f"{sk}_clear_bar", use_container_width=True):
            st.session_state[f"{sk}_pending"] = {}
            st.session_state[f"{sk}_doc_only"] = {}
            st.session_state[f"{sk}_pending_words"] = {}
            st.rerun()

    if st.session_state.get(f"{sk}_confirm"):
        rows_label = (
            f"{len(sheet_rows)} spreadsheet rows"
            if len(sheet_rows) > 1 else "1 spreadsheet row"
        )
        st.warning(
            f"⚠️  Writing **{len(pending)}** feature(s) to **{rows_label}** "
            f"and updating the Google Doc for **{doc_name}**. Cannot be undone."
        )
        yes_col, no_col = st.columns(2)
        with yes_col:
            if st.button("✅  Yes, submit", key=f"{sk}_yes"):
                # Load current values for conflict check
                try:
                    current = get_sheet_features(sheet_rows[0])
                except Exception as e:
                    st.error(f"Could not read spreadsheet: {e}")
                    st.session_state[f"{sk}_confirm"] = False
                    return

                # Decide what actually needs writing.
                # Select features are multi-value: an existing different value
                # is NOT a conflict — the new tag is merged alongside it by
                # write_sheet_features(). We only skip the write when the value
                # is already present, and we collect a notice either way so the
                # user can see what the document ended up tagged with.
                merge_notes = []
                to_write    = {}
                for col_l, new_val in (pending or {}).items():
                    fd_tmp   = next((f for f in FEATURE_DEFS if f[1] == col_l), None)
                    name_tmp = fd_tmp[2] if fd_tmp else col_l
                    cur_val  = current.get(col_l)

                    if fd_tmp and fd_tmp[3] != 'bool':
                        _existing = _split_feat_values(cur_val, fd_tmp[4])
                        _merged, _added, _dup = _merge_feat_values(
                            cur_val, new_val, fd_tmp[4])
                        if _added:
                            to_write[col_l] = new_val      # merged inside the writer
                            if _existing:
                                merge_notes.append(
                                    f"**{name_tmp}**: added `{'`, `'.join(_added)}` "
                                    f"alongside `{_join_feat_values(_existing)}` → now `{_merged}`"
                                )
                        else:
                            merge_notes.append(
                                f"**{name_tmp}**: already tagged `{_join_feat_values(_existing)}` — no change"
                            )
                        continue

                    # bool features keep the old semantics
                    cell_empty = cur_val in (None, False, '', 0)
                    if cell_empty or cur_val != new_val:
                        to_write[col_l] = new_val

                # Write all values to spreadsheet (with retry on transient errors)
                if to_write:
                    for _attempt in range(2):
                        try:
                            write_sheet_features(sheet_rows[0], to_write)
                            break
                        except Exception as e:
                            if _attempt == 0 and 'pipe' in str(e).lower():
                                import time as _time; _time.sleep(1)
                                continue
                            st.error(f"Spreadsheet write failed: {e}")
                            st.session_state[f"{sk}_confirm"] = False
                            break  # don't continue to doc update
                    else:
                        pass  # wrote successfully on retry
                    # Write to remaining rows (split recordings)
                    for extra_row in sheet_rows[1:]:
                        try:
                            write_sheet_features(extra_row, to_write)
                        except Exception as e:
                            st.error(f"Row {extra_row} write failed: {e}")

                # Report what was merged (after successful write). This is
                # informational, not a warning — nothing was overwritten.
                if merge_notes:
                    st.info(
                        "🏷️  Existing tags were kept and yours added alongside:\n\n"
                        + "\n".join(f"- {c}" for c in merge_notes),
                        icon="🏷️",
                    )

                # Update Google Doc: only the pending features (NOT the full table)
                try:
                    pending_words = st.session_state.get(f"{sk}_pending_words", {})
                    update_gdoc_features_section(doc_id, pending, pending_words)
                except Exception as e:
                    st.error(f"Google Doc update failed: {e}")
                    st.session_state[f"{sk}_confirm"] = False
                    return

                # Persist tagged words into a doc-level store that survives submit,
                # so they stay highlighted in the transcript after the page reruns.
                saved_words = st.session_state.get(f"{sk}_saved_words", {})
                for col_l, words in pending_words.items():
                    # pending_words[col_l] is a LIST of example words (each can be
                    # removed individually before submit — see the per-word ✕
                    # buttons above). Flatten into saved_words as individual words,
                    # not as a nested list, or downstream code that does
                    # dict.fromkeys(...) over saved_words values breaks with
                    # "TypeError: unhashable type: 'list'".
                    word_list = words if isinstance(words, list) else ([words] if words else [])
                    if word_list:
                        saved_words.setdefault(col_l, [])
                        for w in word_list:
                            if w and w not in saved_words[col_l]:
                                saved_words[col_l].append(w)
                st.session_state[f"{sk}_saved_words"] = saved_words

                st.session_state[f"{sk}_pending"] = {}
                st.session_state[f"{sk}_doc_only"] = {}
                st.session_state[f"{sk}_pending_words"] = {}
                st.session_state[f"{sk}_confirm"] = False
                st.success(f"✅  Features saved for **{doc_name}**!")
                st.rerun()

        with no_col:
            if st.button("❌  Cancel", key=f"{sk}_no"):
                st.session_state[f"{sk}_confirm"] = False
                st.rerun()



# ════════════════════════════════════════════════════════════════════════════════
#  SIDEBAR – corpus stats & debug
# ════════════════════════════════════════════════════════════════════════════════

# ── Load corpus index (cached — fast after first load) ────────────────────────
with st.spinner("Loading corpus…"):
    try:
        corpus = load_corpus_index()
        st.session_state['_corpus_for_sidebar'] = corpus
    except Exception as e:
        st.error(f"Could not load corpus index: {e}")
        corpus = []

# ── Background preload: fetch all doc content into disk cache ─────────────────
# Runs once per session using a thread pool (8 workers = ~8× faster than sequential).
# get_doc_content uses persist="disk" so the cache survives app restarts/sleep.
if corpus and not st.session_state.get('_preload_started'):
    st.session_state['_preload_started'] = True
    import threading as _threading
    from concurrent.futures import ThreadPoolExecutor as _TPE
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    # Snapshot versions now — background thread can't read session_state safely
    _snap_versions = dict(st.session_state.get('_doc_versions', {}))
    _ctx = get_script_run_ctx()
    def _preload_one(doc, versions):
        # Attach the Streamlit ScriptRunContext to THIS pool worker thread —
        # called from inside the worker itself (the only reliable place to
        # do it, since ThreadPoolExecutor creates worker threads lazily and
        # there's no hook to tag them before they start running tasks).
        # These threads call into st.cache_data internals, and Streamlit's
        # documented guidance for background threads touching its APIs is to
        # propagate the context explicitly rather than leaving it unset.
        if _ctx is not None:
            add_script_run_ctx(_threading.current_thread(), _ctx)
        try:
            get_doc_content(doc['doc_id'], version=versions.get(doc['doc_id'], 0))
        except Exception:
            pass
    def _preload_all_docs(docs, versions):
        with _TPE(max_workers=8) as ex:
            list(ex.map(lambda d: _preload_one(d, versions), docs))
    _preload_thread = _threading.Thread(
        target=_preload_all_docs,
        args=(list(corpus), _snap_versions),
        daemon=True,
    )
    if _ctx is not None:
        add_script_run_ctx(_preload_thread, _ctx)
    _preload_thread.start()

with st.sidebar:
    st.markdown("### 📚 Corpus")
    if corpus:
        st.markdown(f"**{len(corpus)}** documents loaded")

    if st.button("🔄 Reload corpus cache", key="sidebar_reload"):
        get_column_indices.clear()
        load_corpus_index.clear()
        get_doc_content.clear()
        st.session_state.pop('_corpus_for_sidebar', None)
        st.rerun()

    # Moved here (2026-06-22) from the main search page, where it sat right
    # under the advanced filters and was getting clicked by mistake. This one
    # does a full st.cache_data.clear() (every cached function, not just the
    # corpus/column-index ones the button above targets).
    if st.button("↺ Clear cache & reload", key="sidebar_clear_cache",
                 help="Force a full reload of everything from Google Sheets/Docs"):
        st.cache_data.clear()
        st.rerun()

# ════════════════════════════════════════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="pai-header">
  <div class="title">PAI Corpus Search</div>
  <div class="subtitle">Palestinian Arabic — Pattern Search Interface</div>
</div>
""", unsafe_allow_html=True)

_, mid, _ = st.columns([1, 5, 1])
with mid:
    # ── Search mode toggle ────────────────────────────────────────────────────
    search_mode = st.radio(
        "search_mode",
        options=['transcription', 'root', 'document', 'feature'],
        format_func=lambda x: {
            'transcription': '🔍  Search transcriptions',
            'root':          '🔡  Root search',
            'document':      '📄  Find document by name / ID',
            'feature':       '🏷️  Browse by feature',
        }[x],
        horizontal=True,
        label_visibility="collapsed",
        key="search_mode",
    )

    if search_mode == 'transcription':
        st.markdown("""
        <div class="legend-row">
          <!-- Core set: the four wildcards that cover most searches. The rest
               live behind the <details> toggle below so the search bar isn't
               buried under a wall of pills on first load. <details> is native
               HTML, so opening it costs no Streamlit rerun. -->
          <span class="legend-pill"><b>C</b> = consonant</span>
          <span class="legend-pill"><b>V</b> = vowel (long or short)</span>
          <span class="legend-pill"><b>$</b> = any characters (0 or more)</span>
          <span class="legend-pill" style="background:#e3f2fd;border-color:#90caf9;color:#1565c0">
            <b>^</b> = start of word&nbsp;&nbsp;<b>#</b> = end of word
          </span>
          <span class="legend-pill" style="background:#fff8e0;border-color:#ffe082">
            e.g.&nbsp;<b>^aCC</b>&nbsp;·&nbsp;<b>f$m</b>&nbsp;·&nbsp;<b>VCC#</b>
          </span>

          <details class="legend-more">
            <summary>▸ more wildcards &amp; groups</summary>
            <div class="legend-more-body">
              <span class="legend-pill"><b>v</b> = short vowel (a e i o u ə)</span>
              <span class="legend-pill"><b>v̄</b> = long vowel (ā ē ī ō ū ā̈)</span>
              <span class="legend-pill"><b>D</b> = diphthong (aw/ay)</span>
              <span class="legend-pill"><b>G</b> = guttural (h x ḥ ʿ ġ q)</span>
              <span class="legend-pill"><b>E</b> = emphatic (ḍ ẓ ṣ ḏ̣)</span>
              <span class="legend-pill"><b>B</b> = Bilabial (b ḅ m ṃ f)</span>
              <span class="legend-pill"><b>L</b> = Laminal (l ḷ m ṃ r ṛ n)</span>
              <span class="legend-pill" style="background:#f3e5f5;border-color:#ce93d8;color:#6a1b9a">
                <b>(x,y,z)</b> = one of these alternatives &nbsp;e.g.&nbsp;<b>(q,ʾ)tv</b>
              </span>
              <span class="legend-pill" style="background:#f3e5f5;border-color:#ce93d8;color:#6a1b9a">
                <b>(x,y,)</b> = letter optional (may be absent) &nbsp;e.g.&nbsp;<b>(q,k,)tb</b> → qtb / ktb / tb
              </span>
              <span class="legend-pill" style="background:#fff8e0;border-color:#ffe082">
                space = word boundary &nbsp;e.g.&nbsp;<b>g# ^G</b>
              </span>
            </div>
          </details>
        </div>
        """, unsafe_allow_html=True)

        # ── Common correspondences info panel ─────────────────────────────────
        with st.expander("📖  Common letter correspondences (click to expand)"):
            st.markdown("""
<style>
.corr-table { border-collapse:collapse; width:100%; font-size:.93rem; }
.corr-table th { background:#e3f0ff; color:#1a2b3c; text-align:left;
                 padding:6px 14px; border-bottom:2px solid #90caf9; }
.corr-table td { padding:5px 14px; border-bottom:1px solid #dce8f5; vertical-align:top; }
.corr-table td:first-child { font-weight:700; font-size:1.05rem; color:#0d3f75; width:80px; }
.corr-table td:nth-child(2) { color:#555; }
.corr-table td:last-child  { font-family:monospace; color:#6a1b9a; }
</style>
<table class="corr-table">
  <tr><th>Letter</th><th>Corresponds to</th><th>Use in search</th></tr>
  <tr><td>ق &nbsp;q</td><td>q, ʾ, k, ḳ, g, ǧ</td><td><code>(q,ʾ,k,ḳ,g,ǧ)</code></td></tr>
  <tr><td>ج &nbsp;ǧ</td><td>ǧ, ž</td><td><code>(ǧ,ž)</code></td></tr>
  <tr><td>ذ &nbsp;ḏ</td><td>d, z</td><td><code>(ḏ,d,z)</code></td></tr>
  <tr><td>ث &nbsp;ṯ</td><td>t, s</td><td><code>(ṯ,t,s)</code></td></tr>
  <tr><td>ظ &nbsp;ḏ̣</td><td>ḍ, ẓ</td><td><code>(ḏ̣,ḍ,ẓ)</code></td></tr>
  <tr><td>ك &nbsp;k</td><td>k, č</td><td><code>(k,č)</code></td></tr>
</table>
            """, unsafe_allow_html=True)

    elif search_mode == 'root':
        st.markdown("""
        <div class="legend-row">
          <span class="legend-pill" style="background:#e8f5e9;border-color:#a5d6a7;color:#1b5e20">
            Enter 3+ root letters in order — the search finds any word containing
            those letters with anything between them.
          </span>
          <span class="legend-pill" style="background:#f3e5f5;border-color:#ce93d8;color:#6a1b9a">
            Use <b>(x,y,z)</b> for a letter with multiple reflexes — e.g.&nbsp;<b>(q,ʾ,k,ḳ,g,ǧ)</b>
          </span>
          <span class="legend-pill" style="background:#f3e5f5;border-color:#ce93d8;color:#6a1b9a">
            Add a trailing comma — <b>(x,y,)</b> — to make a letter optional &nbsp;e.g.&nbsp;<b>(q,k,)tb</b> → qtb / ktb / tb
          </span>
          <span class="legend-pill" style="background:#fff8e0;border-color:#ffe082">
            e.g.&nbsp;<b>k t b</b>&nbsp;·&nbsp;<b>(q,ʾ,k,ḳ,g,ǧ)tv</b>&nbsp;·&nbsp;<b>(ǧ,ž)ls</b>
          </span>
        </div>
        """, unsafe_allow_html=True)

    # ── Search bar component (handles typing + PAI keyboard) ─────────────────
    _sb_result = _SEARCH_BAR(
        key="searchbar",
        initial_value=st.session_state.get('_last_pattern', ''),
        disabled=st.session_state.get('_searching', False),
    )
    _sb_ts          = (_sb_result.get('timestamp', 0) if _sb_result else 0)
    # On first run of a new session, consume any stale component value so it
    # doesn't immediately trigger a search.
    if '_last_search_ts' not in st.session_state:
        st.session_state['_last_search_ts'] = _sb_ts
    _last_search_ts = st.session_state['_last_search_ts']
    # search_clicked whenever the user fires the Search button (new timestamp),
    # even with an empty query — allows "clear + filter-only" workflow.
    search_clicked  = (_sb_result is not None and _sb_ts != _last_search_ts and _sb_ts != 0)
    if search_clicked:
        st.session_state['_last_search_ts'] = _sb_ts
        # Use actual current query (may be empty if user cleared the bar)
        pattern_input = _sb_result.get('query', '').strip()
        st.session_state['_last_pattern'] = pattern_input
    else:
        # Between reruns (filter changes, doc opens, etc.) keep the last typed query
        pattern_input = st.session_state.get('_last_pattern', '')

    # ── Feature browser UI (shown only in feature mode) ──────────────────────
    if search_mode == 'feature':
        # Features are offered grouped by category — the same four groups the
        # right-click tagging popup uses — instead of one flat list, so the
        # two places you pick a feature look and behave alike.
        # Each group gets its own multiselect; the prefix is stripped from the
        # labels because the group heading already carries it.
        _FEAT_GROUP_LABELS = [
            ('PHON.', '🔊  Phonology'),
            ('MOR.',  '🧩  Morphology'),
            ('SYN.',  '🔗  Syntax'),
            ('LEX.',  '📖  Lexicon'),
        ]

        def _bare_feat(name: str) -> str:
            for _p in FEAT_PREFIXES:
                if name.startswith(_p):
                    return name[len(_p):].strip()
            return name

        _sel_feats = []
        _g1, _g2 = st.columns(2)
        for _gi, (_gprefix, _glabel) in enumerate(_FEAT_GROUP_LABELS):
            _g_feats = [fd[2] for fd in FEATURE_DEFS if fd[2].startswith(_gprefix)]
            if not _g_feats:
                continue
            with (_g1 if _gi % 2 == 0 else _g2):
                _sel_feats.extend(st.multiselect(
                    f"{_glabel}  ({len(_g_feats)})",
                    _g_feats,
                    key=f"feat_browse_grp_{_gprefix.rstrip('.')}",
                    placeholder="none",
                    format_func=_bare_feat,
                ))

        # Any feature that somehow carries no known prefix would otherwise be
        # unreachable from this screen — keep a catch-all so it stays findable.
        _ungrouped = [fd[2] for fd in FEATURE_DEFS
                      if not any(fd[2].startswith(p) for p in FEAT_PREFIXES)]
        if _ungrouped:
            _sel_feats.extend(st.multiselect(
                f"❓  Other  ({len(_ungrouped)})", _ungrouped,
                key="feat_browse_grp_other", placeholder="none",
            ))

        # Condition value is True for bool features, or a LIST of wanted values
        # for select features. A list is used (rather than one value) because
        # feature cells are multi-value in the sheet — mirroring the native
        # multi-select dropdown, several values can be searched at once and a
        # document matches if it carries ANY of them.
        _feat_conditions = []   # list of (feat_name, feat_def, value|list)
        if _sel_feats:
            for _sf in _sel_feats:
                _fd = next(fd for fd in FEATURE_DEFS if fd[2] == _sf)
                if _fd[3] == 'bool':
                    _feat_conditions.append((_sf, _fd, True))
                else:
                    # "— None (not tagged) —" lets the user search for documents
                    # where this feature column is empty, instead of only being
                    # able to pick one of the predefined tag values.
                    _vals = st.multiselect(
                        f"Value — {_sf}", [FEAT_NONE_OPTION] + (_fd[4] or []),
                        key=f"feat_browse_val_{_sf}",
                        label_visibility="visible",
                        placeholder="Any value…",
                        help="Pick one or more. A document matches if it is "
                             "tagged with any of them.",
                    )
                    if _vals:
                        _feat_conditions.append((_sf, _fd, list(_vals)))

            _logic = 'AND'
            if len(_feat_conditions) > 1:
                _logic = st.radio(
                    "Logic", ['AND', 'OR'],
                    horizontal=True, key="feat_browse_logic",
                    format_func=lambda x: (
                        '🔗 AND — must have all features'
                        if x == 'AND' else
                        '🔀 OR — must have at least one feature'
                    ),
                )

        _feat_search_btn = st.button(
            "🏷️  Find tagged documents", type="primary", key="feat_browse_btn",
            disabled=not _feat_conditions,
        )

        # If conditions/logic changed since last search, clear stale results so
        # the old result set is not shown and no automatic re-search is triggered.
        _stored_feat = st.session_state.get('_feat_search')
        if _stored_feat:
            _stored_conds, _stored_logic = _stored_feat
            _conds_changed = (
                [(n, v) for n, _, v in _feat_conditions] !=
                [(n, v) for n, _, v in _stored_conds]
            )
            if _conds_changed or _stored_logic != _logic:
                st.session_state.pop('_feat_search', None)
                st.session_state['_search_results'] = []

        # The main Search button (in the search-bar component) fires a feature
        # search too, so "Search" means the same thing in every mode. The
        # dedicated button above remains as the in-context primary action.
        if (_feat_search_btn or search_clicked) and _feat_conditions:
            st.session_state['_feat_search'] = (_feat_conditions, _logic)
            st.session_state['_search_results'] = []
        elif search_clicked and not _feat_conditions:
            st.info(
                "Choose at least one feature above, then press Search.",
                icon="🏷️",
            )

        search_clicked = False
        pattern_input  = ''
    elif search_mode == 'root':
        # ── Root search: expand letter sequence into $-wildcard pattern ───────
        st.session_state.pop('_feat_search', None)
        if search_clicked and pattern_input:
            _expanded = root_to_pattern(pattern_input)
            if _expanded:
                # Show what pattern was built so user understands the match
                st.caption(f"Pattern used: `{_expanded}`")
                pattern_input = _expanded
            else:
                st.info("Enter root letters to search (e.g. k t b).", icon="ℹ️")
                search_clicked = False
        elif not pattern_input:
            if search_clicked:
                st.info("Enter root letters to search (e.g. k t b).", icon="ℹ️")
                search_clicked = False
        # search_mode stays 'root' here; search execution block below converts it
    else:
        st.session_state.pop('_feat_search', None)

    def _corpus_vals(key):
        return sorted({d[key] for d in corpus if d.get(key)})

    # ── Active-filter indicator ───────────────────────────────────────────────
    # The expander's label is evaluated BEFORE the multiselects inside it run,
    # so the current selections are read from session_state (which holds the
    # values from the previous rerun — i.e. what is actually in effect right
    # now). Without this, filters set earlier stay silently active while the
    # panel is collapsed and quietly narrow every later search.
    _FILTER_KEYS = {
        'filt_village':   'village',
        'filt_geo':       'geography',
        'filt_social':    'social type',
        'filt_community': 'community',
        'filt_gender':    'gender',
        'filt_status':    'status',
    }
    _active_now = {
        _label: st.session_state.get(_k, [])
        for _k, _label in _FILTER_KEYS.items()
        if st.session_state.get(_k)
    }
    _n_active = len(_active_now)

    if _n_active:
        _summary = ', '.join(
            f"{_lbl} ({len(_vals)})" if len(_vals) > 1 else f"{_lbl}: {_vals[0]}"
            for _lbl, _vals in _active_now.items()
        )
        _exp_label = f"⚙️  Advanced options   ·   🔵 {_n_active} filter{'s' if _n_active != 1 else ''} active"
    else:
        _summary   = ''
        _exp_label = "⚙️  Advanced options"

    # Show the active filters OUTSIDE the expander too, so they stay visible
    # even when the panel is collapsed.
    if _n_active:
        _fb1, _fb2 = st.columns([5, 1])
        with _fb1:
            st.markdown(
                f'<div class="filter-banner">🔵 <b>Filters active:</b> {_summary}</div>',
                unsafe_allow_html=True,
            )
        with _fb2:
            if st.button("✕ Clear", key="clear_all_filters",
                         help="Remove all document filters"):
                for _k in _FILTER_KEYS:
                    st.session_state[_k] = []
                st.rerun()

    with st.expander(_exp_label):
        if search_mode == 'transcription':
            st.markdown("**Pattern position within word**")
            position = st.radio(
                "position",
                options=['anywhere', 'start', 'middle', 'end'],
                horizontal=True,
                label_visibility="collapsed",
                format_func=lambda x: {
                    'anywhere': '🔀  Anywhere',
                    'start':    '◀  Start of word',
                    'middle':   '◼  Middle of word',
                    'end':      '▶  End of word',
                }[x],
            )
        elif search_mode == 'root':
            st.info("Root search always matches letters in any position within the word ($ wildcards are added automatically).", icon="ℹ️")
            position = 'anywhere'
        else:
            st.info("In document search mode the query is matched literally (no regex) against document names and metadata.", icon="ℹ️")
            position = 'anywhere'

        st.markdown("**Filter documents**")
        _fc1, _fc2 = st.columns(2)
        with _fc1:
            filt_village = st.multiselect(
                "שם יישוב בתעתיק",
                options=_corpus_vals('village'),
                key="filt_village",
                placeholder="All villages…",
            )
            filt_geo = st.multiselect(
                "Geographical Typology",
                options=_corpus_vals('geo_typology'),
                key="filt_geo",
                placeholder="All geographies…",
            )
        with _fc2:
            filt_social = st.multiselect(
                "Social Typology",
                options=_corpus_vals('social_typology'),
                key="filt_social",
                placeholder="All social types…",
            )
            filt_community = st.multiselect(
                "קהילה",
                options=_corpus_vals('community'),
                key="filt_community",
                placeholder="All communities…",
            )

        _fc3, _fc4 = st.columns(2)
        with _fc3:
            filt_gender = st.multiselect(
                "מגדר דובר",
                options=_corpus_vals('gender'),
                key="filt_gender",
                placeholder="All genders…",
            )
        with _fc4:
            # Closed list: known statuses (in pipeline order) plus any extra
            # value that shows up in the sheet but isn't in STATUS_COLORS yet.
            _status_options = list(STATUS_COLORS.keys()) + [
                v for v in _corpus_vals('status') if v not in STATUS_COLORS
            ]
            filt_status = st.multiselect(
                "סטטוס",
                options=_status_options,
                key="filt_status",
                placeholder="All statuses…",
            )

        active_filters = {
            'village':         filt_village,
            'social_typology': filt_social,
            'geo_typology':    filt_geo,
            'community':       filt_community,
            'gender':          filt_gender,
            'status':          filt_status,
        }
        name_filter = ''  # removed; kept as empty string for backward compat

    # NOTE: the "Clear cache & reload" button used to live here. Users kept
    # clicking it by mistake while working with the filters above it, so
    # it's been moved into the sidebar (the "<<" panel).


# ── Bridge component: listens for right-click tags from document iframes ──────
_bridge_tag = _TAG_BRIDGE(key="tagbridge")
if _bridge_tag:
    _bt_ts = _bridge_tag.get('timestamp', 0)
    # Skip if we already processed this exact tag (same timestamp = same rerun replay)
    if _bt_ts and _bt_ts == st.session_state.get('_last_bridge_ts'):
        pass  # already handled
    else:
        _bt_type = _bridge_tag.get('type', '')
        doc_id   = _bridge_tag.get('docId', '')

        if _bt_type == 'edit':
            # ── Inline find-and-replace from context menu ──────────────────────
            # Replaces ONLY the specific occurrence the user selected (see
            # replace_one_occurrence_in_gdoc()) — not every occurrence of
            # find_text in the document.
            find_text = _bridge_tag.get('find', '').strip()
            repl_text = _bridge_tag.get('replace', '').strip()
            occ_idx   = _bridge_tag.get('occurrenceIndex', 0) or 0
            if find_text and repl_text and doc_id:
                try:
                    ok = replace_one_occurrence_in_gdoc(doc_id, find_text, repl_text, occ_idx)
                    st.session_state['_ctx_edit_result'] = (find_text, repl_text, ok, None)
                except Exception as e:
                    st.session_state['_ctx_edit_result'] = (find_text, repl_text, False, str(e))
            st.session_state['_last_bridge_ts'] = _bt_ts

        else:
            # ── Feature tag from context menu ──────────────────────────────────
            feat_name = _bridge_tag.get('feature', '')
            feat_val  = _bridge_tag.get('value')
            fd = _FEAT_BY_NAME.get(feat_name)
            if fd and doc_id:
                sk = f"feat_{doc_id}"
                if f"{sk}_pending" not in st.session_state:
                    st.session_state[f"{sk}_pending"] = {}
                if f"{sk}_pending_words" not in st.session_state:
                    st.session_state[f"{sk}_pending_words"] = {}
                # Select features are multi-value, so picking a SECOND value for
                # the same feature in one tagging session must add to the first,
                # not replace it (the same rule the spreadsheet write applies).
                if fd[3] != 'bool':
                    _prev = st.session_state[f"{sk}_pending"].get(fd[1])
                    _acc, _, _ = _merge_feat_values(_prev, feat_val, fd[4])
                    st.session_state[f"{sk}_pending"][fd[1]] = _acc
                else:
                    st.session_state[f"{sk}_pending"][fd[1]] = feat_val
                # Accumulate clicked words (selText) — keep a list per feature so
                # tagging a second word under the same feature doesn't erase the first.
                sel_text = _bridge_tag.get('selText', '').strip()
                if sel_text:
                    _existing_words = st.session_state[f"{sk}_pending_words"].get(fd[1], [])
                    if isinstance(_existing_words, str):
                        _existing_words = [_existing_words] if _existing_words else []
                    if sel_text not in _existing_words:
                        _existing_words = list(_existing_words) + [sel_text]
                    st.session_state[f"{sk}_pending_words"][fd[1]] = _existing_words
                st.session_state[f"{sk}_auto_expand"] = True
                st.session_state['_last_bridge_ts'] = _bt_ts

# ── Show result of context-menu find-replace (survives the rerun) ─────────────
if '_ctx_edit_result' in st.session_state:
    _find, _repl, _ok, _err = st.session_state.pop('_ctx_edit_result')
    if _err:
        st.error(f'Replace failed: {_err}')
    elif _ok:
        st.success(f'✅  Replaced "{_find}" → "{_repl}"')
    else:
        st.info(f'Couldn\'t find that exact occurrence of "{_find}" anymore — '
                f'the document may have changed since this page loaded. Try reloading.')

# ── Results ───────────────────────────────────────────────────────────────────
_filters_active = any(v for v in active_filters.values() if v)

# Detect filter changes: only clear filter-browse results (no query) when filters
# change without a Search click, so the user knows they need to click Search again.
# Text search results are NOT cleared by filter changes.
_active_filters_key = str(sorted((k, tuple(v)) for k, v in active_filters.items()))
if '_last_filters_key' not in st.session_state:
    # First run — initialise so we don't falsely detect a "change"
    st.session_state['_last_filters_key'] = _active_filters_key
_last_filters_key = st.session_state['_last_filters_key']

_is_filter_browse_result = (
    st.session_state.get('_search_pattern', '') == ''
    and bool(st.session_state.get('_search_results'))
)
if (not search_clicked
        and _active_filters_key != _last_filters_key
        and _is_filter_browse_result):
    # Filters changed after a filter-browse — clear stale list so user must re-search
    st.session_state['_search_results'] = []
    st.session_state['_last_filters_key'] = _active_filters_key

# Block new searches while one is already in progress (prevents crash from
# concurrent ThreadPoolExecutor runs triggered by rapid repeated clicks).
_is_searching = st.session_state.get('_searching', False)
_search_start_ts = st.session_state.get('_search_start_ts', 0)
if _is_searching and (time.time() - _search_start_ts) > 120:
    # Safety valve: clear stuck flag after 2 minutes
    st.session_state['_searching'] = False
    _is_searching = False
if search_clicked and _is_searching:
    st.info("⏳ A search is already running — please wait for it to finish.", icon="⏳")
    search_clicked = False

if search_clicked and pattern_input.strip() and corpus:
    # Root mode: pattern_input was ALREADY expanded to a $-wildcard pattern by
    # the root-mode UI block above (search_mode == 'root' branch around the
    # search bar) — that block ran earlier in this same script execution.
    # Do NOT call root_to_pattern() again here: doing so double-expanded an
    # already-expanded pattern (e.g. "$k$t$b$" -> "$$k$$t$$b$$"), producing a
    # much heavier, semantically-wrong regex (long chains of ".*?") that was
    # then matched unanchored across the entire corpus — the cause of root
    # search hanging/crashing the app.
    _effective_pattern = pattern_input.strip()
    if search_mode == 'root':
        search_mode = 'transcription'  # use transcription search internally
    st.session_state['_searching'] = True
    st.session_state['_search_start_ts'] = time.time()
    try:
        # Funnel counts for the empty-state diagnosis below: how many documents
        # existed, and how many survived the filters. Without this, a zero-result
        # search looks the same whether the pattern was wrong or the filters had
        # already excluded every document — the single most common confusion.
        _n_corpus_total = len({d['doc_id'] for d in corpus})
        _n_after_filter = len({d['doc_id'] for d in _apply_filters(corpus, active_filters)})

        def _explain_empty(what: str) -> None:
            """Show where the funnel collapsed, and the most likely fix."""
            st.info(f'No results found for {what}.', icon="🔍")
            _stages = (
                f"**{_n_corpus_total}** documents in corpus &nbsp;→&nbsp; "
                f"**{_n_after_filter}** after filters &nbsp;→&nbsp; "
                f"**0** matched the pattern"
            )
            st.markdown(
                f'<div class="filter-banner" style="background:#fff8e0;border-color:#ffe082;color:#7a5f00">'
                f'{_stages}</div>',
                unsafe_allow_html=True,
            )
            if _n_after_filter == 0 and _n_corpus_total > 0:
                st.caption(
                    "⚠️ Your filters excluded every document — the pattern was never tested. "
                    "Clear the filters and search again."
                )
            elif _n_after_filter < _n_corpus_total:
                st.caption(
                    f"ℹ️ Filters are limiting this search to {_n_after_filter} of "
                    f"{_n_corpus_total} documents. Widen or clear them to search the whole corpus."
                )
            else:
                st.caption(
                    "ℹ️ The whole corpus was searched, so this is the pattern, not the filters. "
                    "Try removing an anchor (^ or #), using $ between letters, or a broader "
                    "wildcard class."
                )

        if search_mode == 'document':
            results = search_by_name(_effective_pattern, _apply_filters(corpus, active_filters))
            if not results:
                _explain_empty(f'"{_effective_pattern}"')
        else:
            results = run_search(_effective_pattern, position, name_filter, corpus, active_filters)
            if not results:
                _explain_empty(f'**{_effective_pattern}**')
        st.session_state['_search_results']  = results
        st.session_state['_search_pattern']  = pattern_input.strip()
        st.session_state['_search_mode']     = search_mode
        st.session_state['_last_filters_key'] = _active_filters_key
    except Exception as e:
        st.error(f"Search failed: {e}")
        results = []
        st.session_state['_search_results'] = []
    finally:
        st.session_state['_searching'] = False
elif search_clicked and _filters_active and not pattern_input.strip() and corpus and search_mode != 'feature':
    # Search clicked with active filters but no text query — show filtered document list
    _filt_results = [
        {'name': d['name'], 'doc_id': d['doc_id'], 'match_count': 0,
         'village': d.get('village',''), 'community': d.get('community',''),
         'social_typology': d.get('social_typology',''), 'geo_typology': d.get('geo_typology','')}
        for d in _apply_filters(corpus, active_filters)
    ]
    if not _filt_results:
        st.info("No documents match the selected filters.", icon="🗂️")
    st.session_state['_search_results'] = _filt_results
    st.session_state['_search_pattern'] = ''
    st.session_state['_search_mode']    = 'document'
    st.session_state['_last_filters_key'] = _active_filters_key
elif search_clicked and not pattern_input.strip() and not _filters_active:
    st.info("Please enter a search pattern or select a filter.", icon="ℹ️")
elif not _filters_active and not search_clicked and not pattern_input.strip():
    # All filters cleared and no query, no search — wipe stale filter-browse results only
    # (don't wipe real search results which have a non-empty _search_pattern)
    if st.session_state.get('_search_pattern', '') == '' and st.session_state.get('_search_results'):
        st.session_state['_search_results'] = []

# Always display stored results (survive rerun after bridge tag)
results       = st.session_state.get('_search_results', [])
pattern_shown = st.session_state.get('_search_pattern', '')
mode_shown    = st.session_state.get('_search_mode', 'transcription')

if results:
    total = sum(r['match_count'] for r in results)
    if mode_shown == 'document':
        _label_left = f"📄 <b>{pattern_shown}</b>" if pattern_shown else "🗂️ <b>Filtered documents</b>"
        st.markdown(f"""
        <div class="stats-bar">
          <span>{_label_left}</span>
          <span>{len(results)} document{'s' if len(results) != 1 else ''} found</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="stats-bar">
          <span>🔍 <b>{pattern_shown}</b></span>
          <span>📄 {len(results)} document{'s' if len(results) != 1 else ''}</span>
          <span>◌ {total} total match{'es' if total != 1 else ''}</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Download search results as CSV ────────────────────────────────────────
    # Columns: Document · Link · Matches · Matched words · all corpus metadata
    # fields · one column per FEATURE_DEF (value or TRUE/FALSE for bool)
    import csv, io as _io
    _csv_buf  = _io.StringIO()
    _csv_w    = csv.writer(_csv_buf)

    # Metadata keys stored on every corpus entry — automatically includes any
    # new fields added in the future (just keep them in load_corpus_index).
    _META_KEYS = ['village', 'community', 'social_typology', 'geo_typology',
                  'gender', 'status']
    _META_LABELS = {
        'village':         'שם יישוב',
        'community':       'קהילה',
        'social_typology': 'Social Typology',
        'geo_typology':    'Geo Typology',
        'gender':          'מגדר דובר',
        'status':          'Status',
    }
    # Two columns per feature: the value, and beside it the tagged example word.
    _feat_names_dl = _csv_feature_header()

    _csv_w.writerow(
        ['#', 'Document', 'Link', 'Matches', 'Matched words']
        + [_META_LABELS.get(k, k) for k in _META_KEYS]
        + _feat_names_dl
    )

    # Explicit 1-based rank column — incremented in the exact same order (and
    # with the exact same de-dup skip logic) as the on-screen results list
    # below, so a row's "#" always matches its position in the search-results
    # panel even if a spreadsheet program re-sorts or the user wants to verify
    # the CSV matches what's shown on screen.
    _seen_dl = set()
    _dl_rank = 0
    for _r in results:
        if _r['doc_id'] in _seen_dl:
            continue
        _seen_dl.add(_r['doc_id'])
        _dl_rank += 1

        _words = ', '.join(list(dict.fromkeys(
            _STRIP_MARK.sub('', w) for w in _r.get('matched_words', [])
        )))
        _link = f"https://docs.google.com/document/d/{_r['doc_id']}/edit"

        # Look up corpus entry for this doc to get full metadata
        _corpus_entry = next((d for d in corpus if d['doc_id'] == _r['doc_id']), None)
        _meta_vals = [(_corpus_entry or _r).get(k, '') for k in _META_KEYS]

        # Feature values + their example words (both cached; no extra API call)
        _srow = (_corpus_entry or {}).get('sheet_row') or _r.get('sheet_row')
        _feat_vals = _csv_feature_cells(_srow, _r['doc_id'])

        _csv_w.writerow(
            [_dl_rank, _r['name'], _link, _r.get('match_count', ''), _words]
            + _meta_vals
            + _feat_vals
        )

    # ── Collect checked results from the previous render (session_state has the
    # checkbox values from the last Streamlit run, which is exactly what we want).
    _sel_ids: set = set()
    _seen_sel_tmp = set()
    for _r in results:
        if _r['doc_id'] in _seen_sel_tmp:
            continue
        _seen_sel_tmp.add(_r['doc_id'])
        if st.session_state.get(f"sel_{_r['doc_id']}", False):
            _sel_ids.add(_r['doc_id'])
    _n_sel = len(_sel_ids)

    # Build a second CSV that contains only the selected results + comments
    _sel_buf = _io.StringIO()
    if _n_sel > 0:
        _sel_w2 = csv.writer(_sel_buf)
        _sel_w2.writerow(
            ['#', 'Document', 'Link', 'Comment', 'Matches', 'Matched words']
            + [_META_LABELS.get(k, k) for k in _META_KEYS]
            + _feat_names_dl
        )
        _sel_rank2 = 0
        _seen_sel2 = set()
        for _r in results:
            if _r['doc_id'] in _seen_sel2:
                continue
            _seen_sel2.add(_r['doc_id'])
            _sel_rank2 += 1          # mirrors the rank shown on-screen
            if _r['doc_id'] not in _sel_ids:
                continue
            _comment2 = st.session_state.get(f"comment_{_r['doc_id']}", '') or ''
            _words2 = ', '.join(list(dict.fromkeys(
                _STRIP_MARK.sub('', w) for w in _r.get('matched_words', [])
            )))
            _link2 = f"https://docs.google.com/document/d/{_r['doc_id']}/edit"
            _ce2 = next((d for d in corpus if d['doc_id'] == _r['doc_id']), None)
            _mv2 = [(_ce2 or _r).get(k, '') for k in _META_KEYS]
            _srow2 = (_ce2 or {}).get('sheet_row') or _r.get('sheet_row')
            _fv2 = _csv_feature_cells(_srow2, _r['doc_id'])
            _sel_w2.writerow(
                [_sel_rank2, _r['name'], _link2, _comment2, _r.get('match_count', ''), _words2]
                + _mv2 + _fv2
            )

    _dl_col1, _dl_col2 = st.columns([3, 2])
    with _dl_col1:
        st.download_button(
            label="⬇ Download results (CSV)",
            data=_csv_buf.getvalue().encode('utf-8-sig'),
            file_name=f"pai_search_{pattern_shown or 'filtered'}.csv",
            mime='text/csv',
            key='dl_search_results',
        )
    with _dl_col2:
        if _n_sel > 0:
            st.download_button(
                label=f"⬇ Download selected ({_n_sel})",
                data=_sel_buf.getvalue().encode('utf-8-sig'),
                file_name=f"pai_selected_{pattern_shown or 'filtered'}.csv",
                mime='text/csv',
                key='dl_selected_results',
            )
        else:
            st.caption("☑ Check results below to download selected")

    # Map doc_id → all sheet rows (handles recordings split across multiple rows)
    doc_id_to_rows: dict = {}
    for doc in corpus:
        doc_id_to_rows.setdefault(doc['doc_id'], []).append(doc['sheet_row'])

    seen_doc_ids = set()
    _disp_rank = 0
    for r in results:
        if r['doc_id'] in seen_doc_ids:
            continue          # skip duplicate doc_ids (same Google Doc listed twice in sheet)
        seen_doc_ids.add(r['doc_id'])
        _disp_rank += 1       # matches the "#" column written to the CSV above

        meta  = ' · '.join(filter(None, [
            r.get('village', ''), r.get('community', ''), r.get('gender', '')
        ]))

        # Build preview words list (unique, strip mark tags)
        preview_words = list(dict.fromkeys(
            _STRIP_MARK.sub('', w) for w in r['matched_words']
        )) if r.get('matched_words') else []

        # Status: emoji hint + Hebrew text in the plain-text label
        status = r.get('status', '')
        status_str = f"  {STATUS_EMOJI.get(status, '⚪')} {status}" if status else ''

        # Word chips as plain text between pipes (up to 8, then "+N more")
        if preview_words:
            words_str = '   |  ' + '  ·  '.join(preview_words[:8])
            if len(preview_words) > 8:
                words_str += f'  +{len(preview_words)-8}'
            words_str += '  |'
        else:
            words_str = ''

        _has_content = bool(r.get('display_html'))
        # Show match count only for real text searches (transcription mode with actual matches)
        _is_text_search = _has_content and mode_shown == 'transcription' and r.get('match_count', 0) > 0
        if _is_text_search:
            label = (
                f"#{_disp_rank}  ·  📄  {r['name']}   ·   {r['match_count']} match{'es' if r['match_count'] != 1 else ''}"
                f"{status_str}{words_str}"
            )
        else:
            label = f"#{_disp_rank}  ·  📄  {r['name']}{status_str}"
            if meta:
                label += f"   ·   {meta}"

        _chk_col, _exp_col = st.columns([1, 20])
        with _chk_col:
            _is_sel = st.checkbox("", key=f"sel_{r['doc_id']}", label_visibility="collapsed",
                                  help="Select this result for CSV download")
        with _exp_col:
            with st.expander(label, key=f"res_exp_{r['doc_id']}"):
                if _has_content:
                    _meta_badges = f'<span style="color:#8899aa">{meta}</span>' if meta else ''
                    if _is_text_search:
                        _meta_badges = (
                            f'<span class="badge-green">✦ {r["match_count"]} matches</span>'
                            f'<span class="badge">{r.get("word_count", "?")} words</span>'
                            + _meta_badges
                        )
                    else:
                        _meta_badges = f'<span class="badge">{r.get("word_count", "?")} words</span>' + _meta_badges
                    st.markdown(f'<div class="doc-card-meta">{_meta_badges}</div>', unsafe_allow_html=True)
                    if r.get('word_count', None) == 0:
                        # A genuinely-empty transcription is possible, but far more often this
                        # means the cached copy of this document is stale (e.g. text was added
                        # in Google Docs after the result was cached). Point the user at the
                        # per-document "🔄 Reload" button below rather than leaving "0 words"
                        # unexplained.
                        st.caption("⚠️ Showing 0 words — if this document has text in Google Docs, "
                                   "try the 🔄 Reload button below to re-fetch it.")
                else:
                    st.markdown(f"""
                    <div class="doc-card-meta">
                      <span style="color:#8899aa">{meta}</span>
                    </div>
                    """, unsafe_allow_html=True)

                if _has_content:
                    # Word chips are now rendered as a sticky nav strip INSIDE the iframe.
                    nav_words = list(dict.fromkeys(
                        _STRIP_MARK.sub('', w) for w in r['matched_words']
                    )) if r.get('matched_words') else []

                    # Document viewer — with right-click context menu + chip nav injected
                    _sk = f"feat_{r['doc_id']}"
                    _pending_words = st.session_state.get(f"{_sk}_pending_words", {})
                    _saved_words   = st.session_state.get(f"{_sk}_saved_words", {})
                    _tagged = list(dict.fromkeys(
                        w for words in list(_pending_words.values()) + list(_saved_words.values())
                        for w in (words if isinstance(words, list) else [words])
                        if w
                    ))
                    interactive_html = inject_interaction_js(
                        r['display_html'], r['doc_id'], nav_words, _tagged,
                        sheet_row=(doc_id_to_rows.get(r['doc_id']) or [r.get('sheet_row')])[0],
                    )
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        components.html(interactive_html, height=580, scrolling=True)
                else:
                    # Filter-browse: no content loaded yet — show a load button
                    _load_key = f"_load_doc_{r['doc_id']}"
                    if st.session_state.get(_load_key):
                        with st.spinner("Loading document…"):
                            try:
                                _doc_ver = st.session_state.get('_doc_versions', {}).get(r['doc_id'], 0)
                                _content = get_doc_content(r['doc_id'], version=_doc_ver)
                                _sk = f"feat_{r['doc_id']}"
                                _pw = st.session_state.get(f"{_sk}_pending_words", {})
                                _sw = st.session_state.get(f"{_sk}_saved_words", {})
                                _tagged = list(dict.fromkeys(
                                    w for words in list(_pw.values()) + list(_sw.values())
                                    for w in (words if isinstance(words, list) else [words])
                                    if w
                                ))
                                _ihtml = inject_interaction_js(
                                    _content['display_html'], r['doc_id'], [], _tagged,
                                    sheet_row=(doc_id_to_rows.get(r['doc_id']) or [r.get('sheet_row')])[0],
                                )
                                import warnings
                                with warnings.catch_warnings():
                                    warnings.simplefilter("ignore")
                                    components.html(_ihtml, height=580, scrolling=True)
                            except Exception as e:
                                st.error(f"Could not load document: {e}")
                    else:
                        st.button("📖 Load document", key=f"btn_load_{r['doc_id']}",
                                  on_click=lambda k=_load_key: st.session_state.update({k: True}))

                # ── Submit bar (feature tags staged via right-click) ────────────
                all_rows = doc_id_to_rows.get(r['doc_id'], [r['sheet_row']] if r.get('sheet_row') else [])
                if all_rows:
                    _render_submit_bar(r['doc_id'], r['name'], all_rows)

                _link_col, _reload_col = st.columns([5, 1])
                with _link_col:
                    st.markdown(
                        f"[Open in Google Docs ↗](https://docs.google.com/document/d/{r['doc_id']}/edit)",
                        unsafe_allow_html=False,
                    )
                with _reload_col:
                    # Per-document cache-bust: the search results (incl. word count) are
                    # cached for up to an hour. If a document was just edited directly in
                    # Google Docs (text added/changed outside this app), the cached copy
                    # can look stale — e.g. showing "0 words" even though the live doc has
                    # content. This re-fetches just this one document, without forcing a
                    # full "Clear cache & reload" of the entire corpus.
                    if st.button("🔄 Reload", key=f"btn_reload_{r['doc_id']}",
                                 help="Re-fetch this document fresh from Google Docs "
                                      "(use this if the word count or text looks stale)"):
                        _dv = st.session_state.setdefault('_doc_versions', {})
                        _dv[r['doc_id']] = _dv.get(r['doc_id'], 0) + 1
                        st.rerun()
        if _is_sel:
            st.text_input("💬 Comment", key=f"comment_{r['doc_id']}",
                          placeholder="Add a comment for this transcription…",
                          label_visibility="collapsed")

# ── Feature browser results ───────────────────────────────────────────────────
if st.session_state.get('_feat_search') and corpus:
    _feat_conditions, _logic = st.session_state['_feat_search']

    # Build stats bar label
    _cond_labels = []
    for _fn, _fd, _fv in _feat_conditions:
        # _fv is True (bool feature) or a list of wanted values — render a
        # list as chips so it reads the same way the sheet displays them.
        if _fd[3] == 'bool':
            _cond_labels.append(f"<b>{_fn}</b> = ✓")
        else:
            _chips = ' '.join(
                f'<span class="val-chip">{v}</span>'
                for v in (_fv if isinstance(_fv, (list, tuple)) else [_fv])
            )
            _cond_labels.append(f"<b>{_fn}</b> = {_chips}")
    _logic_sep = f"&nbsp; <span style='color:#60aee8'>{_logic}</span> &nbsp;"
    st.markdown(f"""
    <div class="stats-bar">
      <span>🏷️ {_logic_sep.join(_cond_labels)}</span>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Reading feature values from spreadsheet…"):
        _feat_rows = []
        _seen_fids = set()
        # For each select-type condition, remember every distinct raw value
        # actually seen in that spreadsheet column across the filtered corpus —
        # used purely as a diagnostic if the search comes back empty, so the
        # user can see what's really in the sheet vs. what the dropdown expects.
        _seen_col_vals: dict = {_fn: set() for _fn, _fd, _fv in _feat_conditions if _fd[3] != 'bool'}
        _filtered_corpus = _apply_filters(corpus, active_filters)
        for _doc in _filtered_corpus:
            if _doc['doc_id'] in _seen_fids:
                continue
            _seen_fids.add(_doc['doc_id'])
            try:
                _fvals = get_sheet_features(_doc['sheet_row'])
            except Exception:
                continue

            # Evaluate each condition against this document
            _cond_results = []
            _matched_vals = {}
            for _fn, _fd, _fv in _feat_conditions:
                _cur = _fvals.get(_fd[1])
                # Diagnostic set: record each value INDIVIDUALLY, so a cell
                # holding "-e; -a" reports two distinct values rather than one
                # combined string the user would never recognise.
                if _fn in _seen_col_vals and str(_cur or '').strip():
                    for _one in _split_feat_values(_cur, _fd[4]):
                        _seen_col_vals[_fn].add(_one)
                if _fd[3] == 'bool':
                    _hit = bool(_cur) is True
                else:
                    # _fv is a list of wanted values. The cell itself may hold
                    # several values, so this is a set-intersection test:
                    # the document matches if ANY wanted value is present.
                    # _feat_value_matches normalises (NFC, case, whitespace) so
                    # composed vs. decomposed diacritics still compare equal.
                    _wanted = _fv if isinstance(_fv, (list, tuple)) else [_fv]
                    _is_empty = not str(_cur or '').strip()
                    _hit = any(
                        _is_empty if _w == FEAT_NONE_OPTION
                        else _feat_value_matches(_cur, _w, _fd[4])
                        for _w in _wanted
                    )
                _cond_results.append(_hit)
                _matched_vals[_fn] = _cur

            _include = all(_cond_results) if _logic == 'AND' else any(_cond_results)
            if _include:
                _feat_rows.append({
                    'name':        _doc['name'],
                    'doc_id':      _doc['doc_id'],
                    'sheet_row':   _doc['sheet_row'],
                    'village':     _doc.get('village', ''),
                    'community':   _doc.get('community', ''),
                    'values':      _matched_vals,
                })

    if not _feat_rows:
        def _fmt_cond(n, d, v):
            if d[3] == 'bool':
                return f"{n}=✓"
            vals = v if isinstance(v, (list, tuple)) else [v]
            return f"{n}={' / '.join(str(x) for x in vals)}"
        _desc = f" {_logic} ".join(_fmt_cond(n, d, v) for n, d, v in _feat_conditions)
        st.info(f"No documents found matching: {_desc}")

        # Same funnel diagnosis as transcription search: show whether the
        # filters or the feature conditions are what produced zero rows.
        _fb_total    = len({d['doc_id'] for d in corpus})
        _fb_filtered = len(_seen_fids)
        st.markdown(
            '<div class="filter-banner" '
            'style="background:#fff8e0;border-color:#ffe082;color:#7a5f00">'
            f'<b>{_fb_total}</b> documents in corpus &nbsp;→&nbsp; '
            f'<b>{_fb_filtered}</b> after filters &nbsp;→&nbsp; '
            '<b>0</b> matched the feature conditions'
            '</div>',
            unsafe_allow_html=True,
        )
        if _fb_filtered == 0 and _fb_total > 0:
            st.caption(
                "⚠️ Your filters excluded every document — the feature conditions were "
                "never tested. Clear the filters and search again."
            )
        elif _logic == 'AND' and len(_feat_conditions) > 1:
            st.caption(
                "ℹ️ Using **AND** — a document must have *all* the selected features. "
                "Switch to **OR** to find documents with at least one."
            )

        # Diagnostic: show what's actually in the spreadsheet for each
        # select-type column searched, so a value typed/stored differently
        # than the dropdown option (typo, extra spaces, different spelling)
        # is immediately visible instead of looking like a silent failure.
        for _fn, _vals_seen in _seen_col_vals.items():
            if _vals_seen:
                st.caption(
                    f"ℹ️ Values actually found in the **{_fn}** column for the "
                    f"documents searched: {', '.join(sorted(_vals_seen))}"
                )
            else:
                st.caption(
                    f"ℹ️ The **{_fn}** column is empty for every document searched — "
                    f"nothing has been tagged with this feature yet."
                )
    else:
        st.caption(f"{len(_feat_rows)} document(s) found")

        # ── Download feature results ──────────────────────────────────────────
        import csv as _csv_mod, io as _io2
        _fbuf = _io2.StringIO()
        _fw   = _csv_mod.writer(_fbuf)
        # All metadata fields + ALL feature columns (not just the searched ones)
        _fb_meta_keys   = ['village', 'community', 'social_typology', 'geo_typology',
                           'gender', 'status']
        _fb_meta_labels = ['שם יישוב', 'קהילה', 'Social Typology', 'Geo Typology',
                           'מגדר דובר', 'Status']
        # Two columns per feature: value + the tagged example word beside it
        _all_feat_names = _csv_feature_header()
        _fw.writerow(['#', 'Document', 'Link'] + _fb_meta_labels + _all_feat_names)
        # Same explicit rank column as the main search-results CSV, kept in
        # lock-step with the on-screen "#" prefix below.
        _fb_rank = 0
        for _fr in _feat_rows:
            _fb_rank += 1
            _fb_meta_vals = [_fr.get(k, '') for k in _fb_meta_keys]
            # Full feature row + example words (both cached)
            _fb_feat_vals = _csv_feature_cells(_fr.get('sheet_row'), _fr['doc_id'])
            _fw.writerow([
                _fb_rank,
                _fr['name'],
                f"https://docs.google.com/document/d/{_fr['doc_id']}/edit",
            ] + _fb_meta_vals + _fb_feat_vals)
        st.download_button(
            label="⬇ Download feature results (CSV)",
            data=_fbuf.getvalue().encode('utf-8-sig'),
            file_name="pai_feature_results.csv",
            mime='text/csv',
            key='dl_feat_results',
        )

        # Map doc_id → all sheet rows (handles recordings split across multiple rows)
        _feat_doc_id_to_rows: dict = {}
        for _cdoc in corpus:
            _feat_doc_id_to_rows.setdefault(_cdoc['doc_id'], []).append(_cdoc['sheet_row'])

        # ── Display each tagged document ──────────────────────────────────────
        _fb_disp_rank = 0
        for _fr in _feat_rows:
            _fb_disp_rank += 1   # matches the "#" column written to the CSV above
            _meta = ' · '.join(filter(None, [_fr['village'], _fr['community']]))
            # Split multi-value cells so the collapsed label reads
            # "MOR. Fem. Ending = -e / -a" instead of one run-together string.
            # (An expander label is plain text, so the real chips are rendered
            #  inside the expander below.)
            def _fb_vals(fn, v):
                if v is True:
                    return '✓'
                _fdx = _FEAT_BY_NAME.get(fn)
                _parts = _split_feat_values(v, _fdx[4] if _fdx else None)
                return ' / '.join(_parts) if _parts else str(v)

            _vals_str = '  ·  '.join(
                f"{fn} = {_fb_vals(fn, v)}"
                for fn, v in _fr['values'].items() if v
            )
            _fb_label_base = f"#{_fb_disp_rank}  ·  📄  {_fr['name']}   ·   {_meta}"
            with st.expander(f"{_fb_label_base}   |  {_vals_str}  |" if _vals_str else _fb_label_base,
                               key=f"feat_exp_{_fr['doc_id']}"):
                # Tagged values as chips — matches how the sheet displays a
                # native multi-select cell, and makes it obvious when a
                # document carries several values for one feature.
                _chip_rows = []
                for _cfn, _cv in _fr['values'].items():
                    if not _cv:
                        continue
                    if _cv is True:
                        _chip_rows.append(
                            f'<b>{_cfn}</b> <span class="val-chip">✓</span>')
                        continue
                    _cfd = _FEAT_BY_NAME.get(_cfn)
                    _cparts = _split_feat_values(_cv, _cfd[4] if _cfd else None)
                    _cchips = ' '.join(f'<span class="val-chip">{p}</span>'
                                       for p in _cparts) or \
                              '<span class="val-chip is-empty">not tagged</span>'
                    _chip_rows.append(f'<b>{_cfn}</b> {_cchips}')
                if _chip_rows:
                    st.markdown(
                        '<div style="margin:-4px 0 10px">'
                        + '<br>'.join(_chip_rows)
                        + '</div>',
                        unsafe_allow_html=True,
                    )
                # Document viewer — loaded on demand (same pattern as the main
                # search results), so the actual transcription text is shown
                # inline instead of only a "Open in Google Docs" link.
                _fb_load_key = f"_feat_load_doc_{_fr['doc_id']}"
                if st.session_state.get(_fb_load_key):
                    with st.spinner("Loading document…"):
                        try:
                            _fb_doc_ver = st.session_state.get('_doc_versions', {}).get(_fr['doc_id'], 0)
                            _fb_content = get_doc_content(_fr['doc_id'], version=_fb_doc_ver)
                            _fb_sk = f"feat_{_fr['doc_id']}"
                            _fb_pw = st.session_state.get(f"{_fb_sk}_pending_words", {})
                            _fb_sw = st.session_state.get(f"{_fb_sk}_saved_words", {})
                            _fb_tagged = list(dict.fromkeys(
                                w for words in list(_fb_pw.values()) + list(_fb_sw.values())
                                for w in (words if isinstance(words, list) else [words])
                                if w
                            ))
                            _fb_ihtml = inject_interaction_js(
                                _fb_content['display_html'], _fr['doc_id'], [], _fb_tagged,
                                sheet_row=(_feat_doc_id_to_rows.get(_fr['doc_id'])
                                           or [_fr.get('sheet_row')])[0],
                            )
                            import warnings
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                components.html(_fb_ihtml, height=580, scrolling=True)
                        except Exception as e:
                            st.error(f"Could not load document: {e}")
                else:
                    st.button(
                        "📖 Load document", key=f"feat_btn_load_{_fr['doc_id']}",
                        on_click=lambda k=_fb_load_key: st.session_state.update({k: True}),
                    )

                # ── Submit bar (feature tags staged via right-click) ────────────
                _fb_all_rows = _feat_doc_id_to_rows.get(
                    _fr['doc_id'], [_fr['sheet_row']] if _fr.get('sheet_row') else []
                )
                if _fb_all_rows:
                    _render_submit_bar(_fr['doc_id'], _fr['name'], _fb_all_rows)

                _fb_link_col, _fb_reload_col = st.columns([5, 1])
                with _fb_link_col:
                    st.markdown(
                        f"[Open in Google Docs ↗](https://docs.google.com/document/d/{_fr['doc_id']}/edit)"
                    )
                with _fb_reload_col:
                    # Same per-document cache-bust as the main search results — see
                    # the comment next to the equivalent button there.
                    if st.button("🔄 Reload", key=f"feat_btn_reload_{_fr['doc_id']}",
                                 help="Re-fetch this document fresh from Google Docs "
                                      "(use this if the word count or text looks stale)"):
                        _dv = st.session_state.setdefault('_doc_versions', {})
                        _dv[_fr['doc_id']] = _dv.get(_fr['doc_id'], 0) + 1
                        st.rerun()
