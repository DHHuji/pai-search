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
from pathlib import Path
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
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
#  LINGUISTIC SETS  (from official PAI transcription table)
# ════════════════════════════════════════════════════════════════════════════════

CONSONANTS: set = {
    'b','t','ṯ','ǧ','ž','ḥ','x','d','ḏ','r','z','s','š','ṣ','ḍ','ẓ','ṭ',
    'ġ','f','q','g','k','č','ḳ','l','m','n','h','w','y','ʿ','ʾ','p',
}
VOWELS: set = { 'a','e','i','u','o','ā','ō','ū','ī','ē','ɑ̄','ə' }
DIPHTHONGS: list = ['aw','ay','ōw','ēy']

GUTTURALS: set  = {'h','x','ḥ','ʿ','ġ','q'}          # G wildcard
EMPHATICS: set  = {'ḍ','ḏ̣','ẓ','ṣ'}                  # E wildcard
WORD_DELIM = re.compile(r'[\s,.:;!?()\[\]{}"\'—–#]+|ʿ\u203Fʿ')


def _alts(items) -> str:
    return '(?:' + '|'.join(re.escape(c) for c in sorted(items, key=len, reverse=True)) + ')'

_C = _alts(CONSONANTS)
_V = _alts(VOWELS)
_D = _alts(DIPHTHONGS)
_G = _alts(GUTTURALS)
_E = _alts(EMPHATICS)


def pattern_to_regex(pattern: str) -> re.Pattern:
    """
    Convert a PAI pattern string to a compiled regex.
    Wildcards: C=consonant, V=vowel, D=diphthong, $=any char
    Word anchors: ^ at start = word must begin here
                  # at end   = word must end here
    """
    pattern = unicodedata.normalize('NFC', pattern)
    anchor_start = pattern.startswith('^')
    anchor_end   = pattern.endswith('#')
    core = pattern
    if anchor_start: core = core[1:]
    if anchor_end:   core = core[:-1]

    parts = []
    for ch in core:
        if   ch == 'C': parts.append(_C)
        elif ch == 'V': parts.append(_V)
        elif ch == 'D': parts.append(_D)
        elif ch == 'G': parts.append(_G)
        elif ch == 'E': parts.append(_E)
        elif ch == '$': parts.append('.')
        else:           parts.append(re.escape(ch))

    rx_str = ''.join(parts)
    if anchor_start: rx_str = '^' + rx_str
    if anchor_end:   rx_str = rx_str + '$'
    return re.compile(rx_str, re.UNICODE)


def tokenize(text: str) -> list:
    return [w for w in WORD_DELIM.split(unicodedata.normalize('NFC', text)) if w.strip()]


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

def _highlight_text_nodes(fragment: str, rx: re.Pattern) -> str:
    """
    Highlight regex matches inside text nodes only (not inside HTML tags).
    Unescapes HTML entities and NFC-normalises each text node before matching,
    so characters like š / ī / ḥ are found regardless of how Google Docs
    encoded them in the export (entities, NFD decomposed, etc.).
    """
    parts = re.split(r'(<[^>]+>)', fragment)
    out = []
    for part in parts:
        if part.startswith('<'):
            out.append(part)
        else:
            # Unescape HTML entities and normalise to NFC before regex search
            text = unicodedata.normalize('NFC', html_lib.unescape(part))
            result = []
            last = 0
            for m in rx.finditer(text):
                # Non-matched portion: re-escape HTML special chars
                result.append(html_lib.escape(text[last:m.start()]))
                # Find the full whitespace-delimited word containing this match,
                # so each <mark> carries a data-word attribute for chip navigation.
                w_start = m.start()
                while w_start > 0 and not text[w_start - 1].isspace():
                    w_start -= 1
                w_end = m.end()
                while w_end < len(text) and not text[w_end].isspace():
                    w_end += 1
                containing_word = html_lib.escape(text[w_start:w_end])
                # Matched portion: wrap in <mark> with data-word
                result.append(
                    f'<mark style="{_MARK_STYLE}" data-word="{containing_word}">'
                    f'{html_lib.escape(m.group())}</mark>'
                )
                last = m.end()
            result.append(html_lib.escape(text[last:]))
            out.append(''.join(result))
    return ''.join(out)

def highlight_in_exported_html(html_doc: str, rx: re.Pattern) -> str:
    """
    Apply highlighting only inside transcription paragraphs (those that start
    with a digit or turn marker and contain PAI characters).  Speaker bios,
    the FEATURES section, and the metadata header are left untouched.
    """
    result   = []
    last_end = 0
    for m in re.finditer(r'(<p\b[^>]*>)(.*?)(</p>)', html_doc, re.DOTALL | re.IGNORECASE):
        result.append(html_doc[last_end:m.start()])
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        if _is_transcription_para(body):
            result.append(open_tag + _highlight_text_nodes(body, rx) + close_tag)
        else:
            result.append(m.group(0))
        last_end = m.end()
    result.append(html_doc[last_end:])
    return ''.join(result)


_STRIP_MARK = re.compile(r'</?mark[^>]*>')


def inject_interaction_js(html_doc: str, doc_id: str, nav_words: list = None, tagged_words: list = None) -> str:
    """
    Inject right-click context menu and edit-mode support into a Google Docs
    HTML export before it is rendered in the iframe.
    nav_words: plain-text list of matched words to show as clickable scroll chips.
    """
    # Serialize feature list for JavaScript
    features_js = json.dumps([
        {'name': fd[2], 'type': fd[3], 'opts': fd[4] or []}
        for fd in FEATURE_DEFS
    ])

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
#pai-mark-pos {{ font-size:11px; color:#999; margin-left:auto; }}
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
    <div id="ctx-edit-note">Replaces all occurrences in the document</div>
    <button id="ctx-kb-toggle">⌨ PAI chars</button>
    <div id="ctx-kb-panel"></div>
  </div>
  <div id="pai-ctx-scroll"></div>
</div>
<div id="pai-ctx-sub" class="ctx-sub"></div>
<script>
(function(){{
  const FEATURES   = {features_js};
  const DOC_ID     = {json.dumps(doc_id)};
  const menu       = document.getElementById('pai-ctx-menu');
  const header     = document.getElementById('pai-ctx-header');
  const scroll     = document.getElementById('pai-ctx-scroll');
  const subMenu    = document.getElementById('pai-ctx-sub');
  const editInput  = document.getElementById('ctx-edit-input');
  const editBtn    = document.getElementById('ctx-edit-btn');
  const editSect   = document.getElementById('ctx-edit-section');
  let   selText    = '';
  let   activeItem = null;

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
    menu.style.display = 'none';
    hideSubMenu();
    try {{
      localStorage.setItem('pai_pending_tag', JSON.stringify({{
        type:      'edit',
        find:      selText,
        replace:   repl,
        docId:     DOC_ID,
        timestamp: Date.now()
      }}));
    }} catch(e) {{}}
  }}
  editBtn.addEventListener('click', applyEdit);
  editInput.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') {{ e.preventDefault(); applyEdit(); }}
    e.stopPropagation();
  }});

  // ── Build feature menu items ────────────────────────────────────────────
  FEATURES.forEach(function(fd) {{
    const item = document.createElement('div');
    item.className = 'ctx-item';

    if (fd.type === 'bool') {{
      item.innerHTML = '<span class="ctx-icon">☐</span>'
        + '<span class="ctx-label">' + fd.name + '</span>'
        + '<span class="ctx-badge">✓/✗</span>';
      item.addEventListener('click', function() {{ storeTag(fd.name, true); }});
      item.addEventListener('mouseenter', function() {{ hideSubMenu(); }});
    }} else {{
      item.innerHTML = '<span class="ctx-icon">◈</span>'
        + '<span class="ctx-label">' + fd.name + '</span>'
        + '<span class="ctx-badge">▸</span>';
      item.addEventListener('mouseenter', function() {{
        activeItem = item;
        // Build submenu content
        subMenu.innerHTML = '';
        fd.opts.forEach(function(opt) {{
          const si = document.createElement('div');
          si.className = 'ctx-sub-item';
          si.textContent = opt;
          si.addEventListener('click', function(e) {{
            e.stopPropagation();
            storeTag(fd.name, opt);
          }});
          subMenu.appendChild(si);
        }});
        // Position submenu to the right of (or left of) the main menu
        const mr = menu.getBoundingClientRect();
        const ir = item.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight;
        subMenu.style.display = 'block';
        const sr = subMenu.getBoundingClientRect();
        let sx = mr.right + 4;
        if (sx + sr.width > vw) sx = mr.left - sr.width - 4;
        let sy = ir.top;
        if (sy + sr.height > vh) sy = vh - sr.height - 8;
        subMenu.style.left = sx + 'px';
        subMenu.style.top  = sy + 'px';
      }});
    }}
    scroll.appendChild(item);
  }});

  function hideSubMenu() {{
    subMenu.style.display = 'none';
    subMenu.innerHTML = '';
    activeItem = null;
  }}

  // ── Right-click handler ─────────────────────────────────────────────────
  document.addEventListener('contextmenu', function(e) {{
    const sel = window.getSelection();
    selText = sel ? sel.toString().trim() : '';
    if (!selText) return;
    e.preventDefault();
    hideSubMenu();

    header.textContent = 'TAG: "' + selText.slice(0, 28) + (selText.length > 28 ? '…' : '') + '"';

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
    if (!menu.contains(e.target) && !subMenu.contains(e.target)) {{
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
  html += '<span id="pai-mark-pos"></span>';
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

  function wrapWordInNode(node, word) {{
    var text = node.nodeValue;
    var idx  = text.indexOf(word);
    if (idx === -1) return null;
    var before = text.slice(0, idx);
    var after  = text.slice(idx + word.length);
    var span = document.createElement('span');
    span.className = 'pai-tagged-word';
    span.textContent = word;
    var frag = document.createDocumentFragment();
    if (before) frag.appendChild(document.createTextNode(before));
    frag.appendChild(span);
    var rest = after ? document.createTextNode(after) : null;
    if (rest) frag.appendChild(rest);
    node.parentNode.replaceChild(frag, node);
    return rest;   // continue scanning from remaining text
  }}

  function highlightWord(word) {{
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
        return n.nodeValue.includes(word) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }}
    }}, false);
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function(n) {{
      var rest = n;
      while (rest && rest.nodeValue && rest.nodeValue.includes(word)) {{
        rest = wrapWordInNode(rest, word);
      }}
    }});
  }}

  function run() {{
    findFeaturesSection();
    TAGGED.forEach(highlightWord);
  }}
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
}})();

var _paiWordIdx = {{}}, _paiLastHL = null, _paiLastBtn = null;
function paiNavWord(btn) {{
  var word = btn.getAttribute('data-navword');
  // Collect marks whose data-word matches this chip's word
  var allMarks = Array.from(document.querySelectorAll('mark[data-word]'));
  var wordMarks = allMarks.filter(function(m) {{
    return m.getAttribute('data-word') === word;
  }});
  // Fallback: marks whose data-word contains the chip word as substring
  if (wordMarks.length === 0) {{
    wordMarks = allMarks.filter(function(m) {{
      return m.getAttribute('data-word').indexOf(word) >= 0;
    }});
  }}
  if (wordMarks.length === 0) return;

  // Reset index when switching to a different word
  if (_paiLastBtn !== btn) {{
    _paiWordIdx[word] = 0;
    _paiLastBtn = btn;
  }}
  if (_paiWordIdx[word] === undefined) _paiWordIdx[word] = 0;

  // Remove previous highlight
  if (_paiLastHL) _paiLastHL.classList.remove('pai-hl');

  var m = wordMarks[_paiWordIdx[word]];
  m.classList.add('pai-hl');
  m.scrollIntoView({{behavior:'smooth', block:'center'}});
  _paiLastHL = m;

  var cur = _paiWordIdx[word] + 1;
  _paiWordIdx[word] = cur % wordMarks.length;

  var pos = document.getElementById('pai-mark-pos');
  if (pos) pos.textContent = cur + '/' + wordMarks.length;
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

# ── Feature column definitions: (1-based col, col_letter, display_name, type, options) ──
# type: 'bool' = checkbox  |  'select' = fixed options  |  'text' = free text
FEATURE_DEFS: list[tuple] = [
    (13, 'M',  'aCC>iCC',                              'bool',   None),
    (14, 'N',  'diphthongs',                           'bool',   None),
    (15, 'O',  'fem. ending',                          'select', ['-i', '-e', '-a', 'pausal']),
    (16, 'P',  'med. Imāla',                           'bool',   None),
    (17, 'Q',  '-a+n (Aram. sub.)',                    'bool',   None),
    (18, 'R',  'pausal -u>-o#, -i>-e#',               'bool',   None),
    (19, 'S',  'ج',                                    'select', ['ž', 'ǧ', 'conditioned']),
    (20, 'T',  'ق',                                    'select', ['q', 'ʾ', 'g', 'k', 'g/ǧ/k (conditioned)']),
    (21, 'U',  'assimilation of gutturals to the left','bool',   None),
    (22, 'V',  'vowel epenthesis',                     'select', ['*CCC > CvCC', '*CCC > CCvC']),
    (23, 'W',  'vocal harmonizing',                    'bool',   None),
    (24, 'X',  'lowering of -uC>-oC/-iC>-eC',         'bool',   None),
    (25, 'Y',  'independent pronoun 1.pl نحن',         'select', ['niḥna', 'iḥna']),
    (26, 'Z',  'independent pronoun 3.pl هم',          'select', ['hinne/hinne', 'hunne', 'hunni', 'humme/homme', 'hum/hom']),
    (27, 'AA', '2.m.pl pron. كم-',                     'select', ['-ku/-ko', '-kum/-kom', '-čin']),
    (28, 'AB', '3.m.pl (poss. pro) هم-',               'select', ['-h- > -∅- (e.g. -on)', '-hum/-hom', '-hin/-hen']),
    (29, 'AC', '3.f.sg pron. ها-',                     'select', ['-a', '-a / -ya (after -i-)', '-ha',
                                                                   '-a; -ha only after -ū-',
                                                                   '-a; -ha only after -ū- / -i-', '-hä#/-he#']),
    (30, 'AD', 'impf. prefix 3.m.sg',                  'select', ['bi-', 'byi-', 'yi-']),
    (31, 'AE', '"want"',                               'select', ['badd', 'bidd', 'widd']),
    (32, 'AF', '"now"',                                'select', ['issa/hassāʿa', 'hallaʾ/halʾēt/halkēt/halgēt', 'alḥīn']),
    (33, 'AG', '"when?"',                              'select', ['ēmta', 'wēnta', 'wagtēš']),
    (34, 'AH', '"here"',                               'select', ['hōn', 'hīn', 'hān', 'hina']),
    (35, 'AI', '"was"',                                'select', ['kān', 'kān / čān', 'baka~biki / yibki~yibka',
                                                                  'baka/biki', 'baka~biki / yikbi~yikba']),
]

# Features that appear in the doc FEATURES section but are NOT in the M-AI spreadsheet columns
DOC_ONLY_FEATURES: list[str] = [
    'long particles',
    'sandhi',
    '-a~-ä/-e#',
    'ḌLL+pron.',
    'Continuous modifier',
    'Anticipatory pronominal suffix',
]

# Map from feature display_name → FEATURE_DEFS entry (for fast lookup)
_FEAT_BY_NAME: dict = {fd[2]: fd for fd in FEATURE_DEFS}


@st.cache_resource
def get_services():
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/spreadsheets',
        ]
    )
    drive   = build('drive',   'v3', credentials=creds)
    docs    = build('docs',    'v1', credentials=creds)
    sheets  = build('sheets',  'v4', credentials=creds)
    return drive, docs, sheets


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


@st.cache_data(ttl=600, show_spinner=False)
def get_column_indices() -> dict:
    """
    Reads only the header row of the Recordings sheet and returns a dict
    mapping each COL_NAMES key to its 0-based column index.
    If a column header isn't found, its value is None.
    Cached for 10 minutes — same TTL as the corpus.
    """
    _, _, sheets_svc = get_services()
    result = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='Recordings!1:1',
    ).execute()
    headers = (result.get('values') or [[]])[0]
    header_map = {h: i for i, h in enumerate(headers)}
    return {key: header_map.get(name) for key, name in COL_NAMES.items()}


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


def debug_corpus_load(tail: int = 20) -> dict:
    """
    Non-cached version of corpus loading for debugging.
    Returns:
      - 'corpus': list of loaded docs (same as load_corpus_index)
      - 'skipped': list of rows that had a trans_name but were skipped (no valid link/doc_id)
      - 'total_rows': total sheet rows read (excl. header)
      - 'tail_raw': raw cell info for the last `tail` rows that had ANY content
    """
    _, _, sheets_svc = get_services()
    result = sheets_svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        ranges=['Recordings'],
        includeGridData=True,
    ).execute()

    grid = result['sheets'][0]['data'][0]['rowData']
    corpus   = []
    skipped  = []
    tail_raw = []

    for grid_row_idx, row in enumerate(grid[1:], start=2):
        cells = row.get('values', [])
        if not cells:
            continue

        def _cv(idx, _c=cells):
            if idx >= len(_c): return None
            return _c[idx].get('formattedValue')

        def _cl(idx, _c=cells):
            if idx >= len(_c): return None
            cell = _c[idx]
            if cell.get('hyperlink'):
                return ('hyperlink', cell['hyperlink'])
            val = (
                (cell.get('userEnteredValue') or {}).get('stringValue')
                or cell.get('formattedValue') or ''
            )
            if 'docs.google.com' in val or val.startswith('https://'):
                return ('plaintext', val.strip())
            return ('none', None)

        trans_name = _cv(COL_TRANS_LINK)
        link_src, trans_url = _cl(COL_TRANS_LINK)
        rec_name   = _cv(COL_REC_LINK) or ''
        row_info   = {
            'sheet_row':  grid_row_idx,
            'trans_name': trans_name,
            'rec_name':   rec_name,
            'link_src':   link_src,
            'trans_url':  trans_url,
        }

        # Collect tail raw for last N content rows
        if trans_name or rec_name:
            tail_raw.append(row_info)
            if len(tail_raw) > tail:
                tail_raw.pop(0)

        if not trans_url or not any(d in trans_url for d in (
            'docs.google.com/document', 'drive.google.com', 'docs.google.com/file'
        )):
            if trans_name:
                row_info['skip_reason'] = 'no valid link'
                skipped.append(row_info)
            continue

        doc_id = _extract_doc_id(trans_url)
        if not doc_id:
            row_info['skip_reason'] = 'doc_id extraction failed'
            skipped.append(row_info)
            continue

        corpus.append({
            'name':      trans_name or rec_name or doc_id,
            'rec_name':  rec_name,
            'doc_id':    doc_id,
            'sheet_row': grid_row_idx,
        })

    return {
        'corpus':     corpus,
        'skipped':    skipped,
        'total_rows': len(grid) - 1,
        'tail_raw':   tail_raw,
    }


@st.cache_data(ttl=3600, show_spinner=False)
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


# ════════════════════════════════════════════════════════════════════════════════
#  FEATURE READ / WRITE
# ════════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_sheet_features(sheet_row: int) -> dict:
    """
    Read feature values (columns M–AI) for a single Recordings sheet row.
    Returns {col_letter: value} where value is True/False for bool cols or str for select cols.
    """
    _, _, sheets_svc = get_services()
    first_col, last_col = FEATURE_DEFS[0][1], FEATURE_DEFS[-1][1]   # 'M', 'AI'
    range_a1 = f"Recordings!{first_col}{sheet_row}:{last_col}{sheet_row}"
    result = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_a1,
        valueRenderOption='UNFORMATTED_VALUE',
    ).execute()
    raw = (result.get('values') or [[]])[0]
    out = {}
    for i, fd in enumerate(FEATURE_DEFS):
        val = raw[i] if i < len(raw) else None
        if fd[3] == 'bool':
            out[fd[1]] = bool(val) if val is not None else None
        else:
            out[fd[1]] = str(val) if val else None
    return out


def write_sheet_features(sheet_row: int, changes: dict[str, object]) -> list[str]:
    """
    Write feature changes to Google Sheets.
    changes: {col_letter: new_value}
    Returns list of conflict messages (non-empty if any existing value differs).
    """
    _, _, sheets_svc = get_services()
    current = get_sheet_features(sheet_row)
    conflicts = []

    # Detect conflicts: only flag if there is already a real (non-empty) value
    # that differs from the new tag.  False / None / 0 / '' = empty cell, not a conflict.
    for col_letter, new_val in changes.items():
        cur_val = current.get(col_letter)
        cell_is_empty = cur_val is None or cur_val is False or cur_val == '' or cur_val == 0
        if not cell_is_empty and cur_val != new_val:
            fd = next((f for f in FEATURE_DEFS if f[1] == col_letter), None)
            name = fd[2] if fd else col_letter
            conflicts.append(
                f"**{name}**: spreadsheet has `{cur_val}`, you tagged `{new_val}`"
            )

    if conflicts:
        return conflicts

    # Write each changed cell
    data = []
    for col_letter, new_val in changes.items():
        fd = next((f for f in FEATURE_DEFS if f[1] == col_letter), None)
        if fd is None:
            continue
        cell_a1 = f"Recordings!{col_letter}{sheet_row}"
        if fd[3] == 'bool':
            data.append({'range': cell_a1, 'values': [[bool(new_val)]]})
        else:
            data.append({'range': cell_a1, 'values': [[new_val]]})

    if data:
        sheets_svc.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'valueInputOption': 'RAW', 'data': data},
        ).execute()
        get_sheet_features.clear()   # invalidate cache

    return []


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
        get_sheet_features.clear()

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
    # M-AI features (from spreadsheet)
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
            for fd in FEATURE_DEFS:
                if text.startswith(fd[2] + '  ['):
                    existing_lines[fd[2]] = text
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
        ex_new = (example_words.get(col_l) or '').strip()
        if ex_new:
            words_list = [w.strip() for w in ex_existing.split(';') if w.strip()]
            if ex_new not in words_list:
                words_list.append(ex_new)
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

    # ── Reconstruct the FEATURES block in FEATURE_DEFS order ──────────────────
    lines = ['FEATURES:']
    for fd in FEATURE_DEFS:
        if fd[2] in updated_lines:
            lines.append(updated_lines[fd[2]])
    # Preserve any lines not in FEATURE_DEFS (e.g. doc-only features already there)
    fd_names = {fd[2] for fd in FEATURE_DEFS}
    for name, line in existing_lines.items():
        if name not in fd_names and name in updated_lines:
            lines.append(updated_lines[name])
    new_block = '\n'.join(lines) + '\n'

    # ── Write to Google Doc ────────────────────────────────────────────────────
    block_len = len(new_block)
    if feat_start is None:
        insert_at = body_content[-1]['endIndex'] - 1
        full_text  = '\n\n' + new_block
        docs_svc.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': [
                {'insertText': {
                    'location': {'index': insert_at},
                    'text': full_text,
                }},
                # Clear any inherited background color on the inserted block
                {'updateTextStyle': {
                    'range': {
                        'startIndex': insert_at,
                        'endIndex':   insert_at + len(full_text),
                    },
                    'textStyle': {'backgroundColor': {}},
                    'fields': 'backgroundColor',
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
                # Clear any inherited background color on the inserted block
                {'updateTextStyle': {
                    'range': {
                        'startIndex': feat_start,
                        'endIndex':   feat_start + block_len,
                    },
                    'textStyle': {'backgroundColor': {}},
                    'fields': 'backgroundColor',
                }},
            ]},
        ).execute()

    # NOTE: intentionally NOT clearing get_doc_content cache here.
    # The transcript text doesn't change when features are tagged (only the FEATURES
    # section at the end changes). Clearing the full cache causes intermittent failures
    # when the Drive API re-fetch is slow or rate-limited, making the doc disappear.
    # Users can click "Open in Google Docs" to see the freshly written FEATURES block.


def find_replace_in_gdoc(doc_id: str, find_text: str, replace_text: str) -> int:
    """
    Apply replaceAllText in a Google Doc.  Returns the number of replacements made.
    Raises on API error.
    """
    _, docs_svc, _ = get_services()
    resp = docs_svc.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': [{
            'replaceAllText': {
                'containsText': {'text': find_text, 'matchCase': True},
                'replaceText':  replace_text,
            }
        }]},
    ).execute()
    count = (
        resp.get('replies', [{}])[0]
           .get('replaceAllText', {})
           .get('occurrencesChanged', 0)
    )
    if count:
        # Bump the per-doc version so only this document's cache entry is invalidated,
        # not every other document in the search results.
        _dv = st.session_state.setdefault('_doc_versions', {})
        _dv[doc_id] = _dv.get(doc_id, 0) + 1
    return count


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
        rx = pattern_to_regex(pattern)
    except re.error as e:
        st.error(f"Invalid pattern: {e}")
        return []

    # Apply filters
    if active_filters:
        corpus = _apply_filters(corpus, active_filters)

    if not corpus:
        st.warning("No documents match the name filter.")
        return []

    results  = []
    bar      = st.progress(0.0, text="Loading corpus…")

    for i, doc in enumerate(corpus):
        bar.progress((i + 1) / max(len(corpus), 1), text=f"Searching · {doc['name']}")
        _doc_ver = st.session_state.get('_doc_versions', {}).get(doc['doc_id'], 0)
        content      = get_doc_content(doc['doc_id'], version=_doc_ver)
        search_text  = content['italic_text']

        match_count   = 0
        matched_words = []

        for word in tokenize(search_text):
            hits = match_word(word, rx, position)
            if hits:
                match_count += len(hits)
                matched_words.append(highlight_word(word, hits))

        if match_count > 0:
            # Highlight matches in the exported Google Docs HTML (all text nodes)
            display_html = highlight_in_exported_html(content['display_html'], rx)

            results.append({
                'name':          doc['name'],
                'doc_id':        doc['doc_id'],
                'sheet_row':     doc.get('sheet_row'),
                'village':       doc['village'],
                'community':     doc['community'],
                'gender':        doc['gender'],
                'status':        doc.get('status', ''),
                'match_count':   match_count,
                'word_count':    len(tokenize(search_text)),
                'matched_words': matched_words[:15],
                'display_html':  display_html,
            })

    bar.empty()
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
    bar = st.progress(0.0, text="Loading document…")
    for i, doc in enumerate(matches):
        bar.progress((i + 1) / max(len(matches), 1), text=f"Loading · {doc['name']}")
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
    n = len(pending)
    tag_summaries = []
    for col_l, val in pending.items():
        fd = next((f for f in FEATURE_DEFS if f[1] == col_l), None)
        tag_summaries.append(f"`{fd[2] if fd else col_l}` = **{val}**")

    st.markdown(
        f"🏷️ **{n} feature(s) staged:** " + "  ·  ".join(tag_summaries)
    )

    btn_col, clr_col = st.columns([4, 1])
    with btn_col:
        if st.button(
            f"💾  Submit {n} feature(s)",
            key=f"{sk}_submit_bar", type="primary", use_container_width=True,
        ):
            st.session_state[f"{sk}_confirm"] = True
    with clr_col:
        if st.button("✕ Clear", key=f"{sk}_clear_bar", use_container_width=True):
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

                # Separate features by: conflict / same-value duplicate / genuinely new
                conflicts  = []
                to_write   = {}   # features with new values → write to spreadsheet
                for col_l, new_val in (pending or {}).items():
                    cur_val = current.get(col_l)
                    cell_empty = cur_val in (None, False, '', 0)
                    if not cell_empty and cur_val != new_val:
                        fd_tmp = next((f for f in FEATURE_DEFS if f[1] == col_l), None)
                        name_tmp = fd_tmp[2] if fd_tmp else col_l
                        conflicts.append(
                            f"**{name_tmp}**: spreadsheet has `{cur_val}`, you tagged `{new_val}`"
                        )
                    elif cell_empty:
                        to_write[col_l] = new_val
                    # else: same value already in sheet → skip spreadsheet write,
                    #       but still update example word in Google Doc below

                if conflicts:
                    st.error(
                        "⚠️  Existing values differ — **not written**:\n\n"
                        + "\n".join(f"- {c}" for c in conflicts)
                    )
                    st.session_state[f"{sk}_confirm"] = False
                    return

                # Write genuinely new values to spreadsheet
                if to_write:
                    try:
                        write_sheet_features(sheet_rows[0], to_write)
                    except Exception as e:
                        st.error(f"Spreadsheet write failed: {e}")
                        st.session_state[f"{sk}_confirm"] = False
                        return
                    # Write to remaining rows (split recordings)
                    for extra_row in sheet_rows[1:]:
                        try:
                            write_sheet_features(extra_row, to_write)
                        except Exception as e:
                            st.error(f"Row {extra_row} write failed: {e}")

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
                for col_l, word in pending_words.items():
                    if word:
                        saved_words.setdefault(col_l, [])
                        if word not in saved_words[col_l]:
                            saved_words[col_l].append(word)
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

    with st.expander("🔧 Debug: inspect corpus row"):
        _dbg_q = st.text_input("Row name or doc ID to inspect", key="dbg_row_q",
                                placeholder="e.g. BĠr.1F.R27")
        if st.button("Run debug scan", key="dbg_run"):
            with st.spinner("Reading raw sheet data…"):
                _dbg = debug_corpus_load(tail=30)
            st.markdown(f"**Sheet rows read:** {_dbg['total_rows']}")
            st.markdown(f"**Corpus entries loaded:** {len(_dbg['corpus'])}")
            st.markdown(f"**Skipped rows (had name, no valid link):** {len(_dbg['skipped'])}")

            _q = _dbg_q.strip().lower()
            if _q:
                # Search loaded corpus
                _hits = [d for d in _dbg['corpus']
                         if _q in d.get('name','').lower()
                         or _q in d.get('rec_name','').lower()
                         or _q in d.get('doc_id','').lower()]
                st.markdown(f"**Corpus matches for '{_dbg_q}':** {len(_hits)}")
                for _h in _hits:
                    st.code(json.dumps(_h, ensure_ascii=False, indent=2))

                # Search skipped rows
                _skip_hits = [d for d in _dbg['skipped']
                              if _q in str(d.get('trans_name','')).lower()
                              or _q in str(d.get('rec_name','')).lower()]
                st.markdown(f"**Skipped matches:** {len(_skip_hits)}")
                for _h in _skip_hits:
                    st.code(json.dumps(_h, ensure_ascii=False, indent=2))

                # Search tail raw rows
                _tail_hits = [d for d in _dbg['tail_raw']
                              if _q in str(d.get('trans_name','')).lower()
                              or _q in str(d.get('rec_name','')).lower()]
                st.markdown(f"**Tail raw rows matching:** {len(_tail_hits)}")
                for _h in _tail_hits:
                    st.code(json.dumps(_h, ensure_ascii=False, indent=2))

            else:
                st.markdown("**Last 10 raw rows with content:**")
                for _row in _dbg['tail_raw'][-10:]:
                    st.code(json.dumps(_row, ensure_ascii=False))
                if _dbg['skipped']:
                    st.markdown("**Skipped rows:**")
                    for _row in _dbg['skipped'][-5:]:
                        st.code(json.dumps(_row, ensure_ascii=False))


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
        options=['transcription', 'document', 'feature'],
        format_func=lambda x: {
            'transcription': '🔍  Search transcriptions',
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
          <span class="legend-pill"><b>C</b> = consonant</span>
          <span class="legend-pill"><b>V</b> = vowel</span>
          <span class="legend-pill"><b>D</b> = diphthong (aw/ay)</span>
          <span class="legend-pill"><b>G</b> = guttural (h x ḥ ʿ ġ q)</span>
          <span class="legend-pill"><b>E</b> = emphatic (ḍ ẓ ṣ ḏ̣)</span>
          <span class="legend-pill"><b>$</b> = any character</span>
          <span class="legend-pill" style="background:#e3f2fd;border-color:#90caf9;color:#1565c0">
            <b>^</b> = start of word&nbsp;&nbsp;<b>#</b> = end of word
          </span>
          <span class="legend-pill" style="background:#fff8e0;border-color:#ffe082">
            e.g.&nbsp;<b>^aCC</b>&nbsp;·&nbsp;<b>f$m</b>&nbsp;·&nbsp;<b>VCC#</b>&nbsp;·&nbsp;<b>^ḥVCC#</b>
          </span>
        </div>
        """, unsafe_allow_html=True)

    # ── Search bar component (handles typing + PAI keyboard) ─────────────────
    _sb_result = _SEARCH_BAR(
        key="searchbar",
        initial_value=st.session_state.get('_last_pattern', ''),
    )
    _sb_ts          = (_sb_result.get('timestamp', 0) if _sb_result else 0)
    _last_search_ts = st.session_state.get('_last_search_ts', 0)
    search_clicked  = (_sb_result is not None and bool(_sb_result.get('query'))
                       and _sb_ts != _last_search_ts)
    if search_clicked:
        st.session_state['_last_search_ts'] = _sb_ts
    pattern_input   = _sb_result['query'].strip() if (_sb_result and _sb_result.get('query')) else \
                      st.session_state.get('_last_pattern', '')
    if search_clicked:
        st.session_state['_last_pattern'] = pattern_input

    # ── Feature browser UI (shown only in feature mode) ──────────────────────
    if search_mode == 'feature':
        _feat_names = [fd[2] for fd in FEATURE_DEFS]

        _sel_feats = st.multiselect(
            "Features", _feat_names, key="feat_browse_names",
            placeholder="Choose one or more features…",
            label_visibility="collapsed",
        )

        _feat_conditions = []   # list of (feat_name, feat_def, value)
        if _sel_feats:
            for _sf in _sel_feats:
                _fd = next(fd for fd in FEATURE_DEFS if fd[2] == _sf)
                if _fd[3] == 'bool':
                    _feat_conditions.append((_sf, _fd, True))
                else:
                    _v = st.selectbox(
                        f"Value — {_sf}", _fd[4] or [],
                        key=f"feat_browse_val_{_sf}",
                        label_visibility="visible",
                    )
                    _feat_conditions.append((_sf, _fd, _v))

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
        if _feat_search_btn and _feat_conditions:
            st.session_state['_feat_search'] = (_feat_conditions, _logic)
            st.session_state['_search_results'] = []
        search_clicked = False
        pattern_input  = ''
    else:
        st.session_state.pop('_feat_search', None)

    def _corpus_vals(key):
        return sorted({d[key] for d in corpus if d.get(key)})

    with st.expander("⚙️  Advanced options"):
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

        active_filters = {
            'village':         filt_village,
            'social_typology': filt_social,
            'geo_typology':    filt_geo,
            'community':       filt_community,
        }
        name_filter = ''  # removed; kept as empty string for backward compat

    # Clear-cache utility button (small, tucked below advanced options)
    if st.button("↺  Clear cache & reload", help="Force reload corpus from Google Sheets"):
        st.cache_data.clear()
        st.rerun()


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
            find_text = _bridge_tag.get('find', '').strip()
            repl_text = _bridge_tag.get('replace', '').strip()
            if find_text and repl_text and doc_id:
                try:
                    n = find_replace_in_gdoc(doc_id, find_text, repl_text)
                    st.session_state['_ctx_edit_result'] = (find_text, repl_text, n, None)
                except Exception as e:
                    st.session_state['_ctx_edit_result'] = (find_text, repl_text, 0, str(e))
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
                st.session_state[f"{sk}_pending"][fd[1]] = feat_val
                # Store the clicked word (selText) alongside the feature
                sel_text = _bridge_tag.get('selText', '').strip()
                if sel_text:
                    st.session_state[f"{sk}_pending_words"][fd[1]] = sel_text
                st.session_state[f"{sk}_auto_expand"] = True
                st.session_state['_last_bridge_ts'] = _bt_ts

# ── Show result of context-menu find-replace (survives the rerun) ─────────────
if '_ctx_edit_result' in st.session_state:
    _find, _repl, _n, _err = st.session_state.pop('_ctx_edit_result')
    if _err:
        st.error(f'Replace failed: {_err}')
    elif _n:
        st.success(f'✅  Replaced {_n} occurrence(s) of "{_find}" → "{_repl}"')
    else:
        st.info(f'No occurrences of "{_find}" found in this document.')

# ── Results ───────────────────────────────────────────────────────────────────
_filters_active = any(v for v in active_filters.values() if v)

if search_clicked and pattern_input.strip() and corpus:
    try:
        if search_mode == 'document':
            results = search_by_name(pattern_input.strip(), _apply_filters(corpus, active_filters))
            if not results:
                st.warning(f'No documents found matching "{pattern_input.strip()}".')
        else:
            results = run_search(pattern_input.strip(), position, name_filter, corpus, active_filters)
            if not results:
                st.warning(f'No results found for **{pattern_input.strip()}**. Try a broader pattern or different filters.')
        st.session_state['_search_results']  = results
        st.session_state['_search_pattern']  = pattern_input.strip()
        st.session_state['_search_mode']     = search_mode
    except Exception as e:
        st.error(f"Search failed: {e}")
        results = []
        st.session_state['_search_results'] = []
elif search_clicked and not pattern_input.strip() and not _filters_active:
    st.warning("Please enter a pattern before searching.")
elif _filters_active and not search_clicked and corpus and search_mode != 'feature':
    # Filters changed without a new search query — show the filtered document list
    _filt_results = [
        {'name': d['name'], 'doc_id': d['doc_id'], 'match_count': 0,
         'village': d.get('village',''), 'community': d.get('community',''),
         'social_typology': d.get('social_typology',''), 'geo_typology': d.get('geo_typology','')}
        for d in _apply_filters(corpus, active_filters)
    ]
    st.session_state['_search_results'] = _filt_results
    st.session_state['_search_pattern'] = ''
    st.session_state['_search_mode']    = 'document'
elif not _filters_active and not search_clicked and not pattern_input.strip():
    # All filters cleared and no query — wipe any stale filter-browse results
    if st.session_state.get('_search_pattern') == '':
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
    import csv, io as _io
    _csv_buf = _io.StringIO()
    _csv_w   = csv.writer(_csv_buf)
    _csv_w.writerow(['Document', 'Link', 'Matches', 'Matched words'])
    _seen_dl = set()
    for _r in results:
        if _r['doc_id'] in _seen_dl:
            continue
        _seen_dl.add(_r['doc_id'])
        _words = ', '.join(list(dict.fromkeys(
            _STRIP_MARK.sub('', w) for w in _r.get('matched_words', [])
        )))
        _link = f"https://docs.google.com/document/d/{_r['doc_id']}/edit"
        _csv_w.writerow([_r['name'], _link, _r['match_count'], _words])
    st.download_button(
        label="⬇ Download results (CSV)",
        data=_csv_buf.getvalue().encode('utf-8-sig'),
        file_name=f"pai_search_{pattern_shown}.csv",
        mime='text/csv',
        key='dl_search_results',
    )

    # Map doc_id → all sheet rows (handles recordings split across multiple rows)
    doc_id_to_rows: dict = {}
    for doc in corpus:
        doc_id_to_rows.setdefault(doc['doc_id'], []).append(doc['sheet_row'])

    seen_doc_ids = set()
    for r in results:
        if r['doc_id'] in seen_doc_ids:
            continue          # skip duplicate doc_ids (same Google Doc listed twice in sheet)
        seen_doc_ids.add(r['doc_id'])

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

        # For filter-browse results (no full-text search), omit match count from label
        _has_content = bool(r.get('display_html'))
        if _has_content:
            label = (
                f"📄  {r['name']}   ·   {r['match_count']} match{'es' if r['match_count'] != 1 else ''}"
                f"{status_str}{words_str}"
            )
        else:
            label = f"📄  {r['name']}{status_str}"
            if meta:
                label += f"   ·   {meta}"

        with st.expander(label):
            if _has_content:
                st.markdown(f"""
                <div class="doc-card-meta">
                  <span class="badge-green">✦ {r['match_count']} matches</span>
                  <span class="badge">{r.get('word_count', '?')} words</span>
                  <span style="color:#8899aa">{meta}</span>
                </div>
                """, unsafe_allow_html=True)
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
                interactive_html = inject_interaction_js(r['display_html'], r['doc_id'], nav_words, _tagged)
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
                            _ihtml = inject_interaction_js(_content['display_html'], r['doc_id'], [], _tagged)
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

            st.markdown(
                f"[Open in Google Docs ↗](https://docs.google.com/document/d/{r['doc_id']}/edit)",
                unsafe_allow_html=False,
            )

# ── Feature browser results ───────────────────────────────────────────────────
if st.session_state.get('_feat_search') and corpus:
    _feat_conditions, _logic = st.session_state['_feat_search']

    # Build stats bar label
    _cond_labels = []
    for _fn, _fd, _fv in _feat_conditions:
        _cond_labels.append(f"<b>{_fn}</b> = {'✓' if _fd[3]=='bool' else _fv}")
    _logic_sep = f"&nbsp; <span style='color:#60aee8'>{_logic}</span> &nbsp;"
    st.markdown(f"""
    <div class="stats-bar">
      <span>🏷️ {_logic_sep.join(_cond_labels)}</span>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Reading feature values from spreadsheet…"):
        _feat_rows = []
        _seen_fids = set()
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
                _hit = (
                    bool(_cur) is True if _fd[3] == 'bool'
                    else str(_cur or '').strip() == str(_fv).strip()
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
        _desc = f" {_logic} ".join(f"{n}={'✓' if d[3]=='bool' else v}" for n,d,v in _feat_conditions)
        st.info(f"No documents found matching: {_desc}")
    else:
        st.caption(f"{len(_feat_rows)} document(s) found")

        # ── Download feature results ──────────────────────────────────────────
        import csv as _csv_mod, io as _io2
        _fbuf = _io2.StringIO()
        _fw   = _csv_mod.writer(_fbuf)
        _feat_col_names = [fn for fn, _, _ in _feat_conditions]
        _fw.writerow(['Document', 'Village', 'Community', 'Link'] + _feat_col_names)
        for _fr in _feat_rows:
            _fw.writerow([
                _fr['name'], _fr['village'], _fr['community'],
                f"https://docs.google.com/document/d/{_fr['doc_id']}/edit",
            ] + [_fr['values'].get(fn, '') for fn in _feat_col_names])
        st.download_button(
            label="⬇ Download feature results (CSV)",
            data=_fbuf.getvalue().encode('utf-8-sig'),
            file_name="pai_feature_results.csv",
            mime='text/csv',
            key='dl_feat_results',
        )

        # ── Display each tagged document ──────────────────────────────────────
        for _fr in _feat_rows:
            _meta = ' · '.join(filter(None, [_fr['village'], _fr['community']]))
            _vals_str = '  ·  '.join(
                f"{fn} = {'✓' if v is True else v}"
                for fn, v in _fr['values'].items() if v
            )
            with st.expander(f"📄  {_fr['name']}   ·   {_meta}   |  {_vals_str}  |" if _vals_str else f"📄  {_fr['name']}   ·   {_meta}"):
                st.markdown(
                    f"[Open in Google Docs ↗](https://docs.google.com/document/d/{_fr['doc_id']}/edit)"
                )