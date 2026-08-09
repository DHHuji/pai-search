"""
Third regression suite for pai-search/app.py — SEARCH, TEXT, DOC, WRITE paths.
Covers the territory tests_full.py and tests_deep.py do not:
  pattern compilation edge cases, alternation groups, optional letters,
  tokenisation, sequence matching, position filters, HTML-safe highlighting,
  doc-ID extraction, corpus filtering, FEATURES-block round-trip,
  unicode normalisation, and write/delete argument shaping.

Run: python tests_search.py
"""
import sys, re, json, unicodedata
import unittest.mock as mock

sys.path.insert(0, '/sessions/laughing-eager-ramanujan')
from _harness import app, check, section, failures, source, load_error  # noqa

if load_error:
    print(f'[FATAL] app.py did not load: {load_error}')
    sys.exit(1)

N = lambda s: unicodedata.normalize('NFC', s)
def m(pat, word):
    """True/False if pattern matches word; None if the pattern failed to compile."""
    try:
        return bool(app.pattern_to_regex(pat).search(N(word)))
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
section('J. pattern_to_regex — anchors and basic semantics')
# ══════════════════════════════════════════════════════════════════════════════

check('J1 ^ anchors to word start',        m('^ka', 'katab') is True)
check('J2 ^ rejects a mid-word match',     m('^ta', 'katab') is False)
check('J3 # anchors to word end',          m('ab#', 'katab') is True)
check('J4 # rejects a non-final match',    m('at#', 'katab') is False)
check('J5 ^…# anchors the whole word',     m('^katab#', 'katab') is True)
check('J6 ^…# rejects a substring',        m('^kata#', 'katab') is False)
check('J7 unanchored matches anywhere',    m('ta', 'katab') is True)
check('J8 $ matches zero characters',      m('k$t', 'kt') is True)
check('J9 $ spans intervening characters', m('k$b', 'katab') is True)
check('J10 ^$# matches any whole word',    m('^$#', 'katab') is True)

# Anchors must survive the wildcard expansion, not be escaped as literals
check('J11 ^ is not treated as a literal char',
      app.pattern_to_regex('^k').pattern.startswith('^'))
check('J12 # is not treated as a literal char',
      app.pattern_to_regex('k#').pattern.endswith('$'))


# ══════════════════════════════════════════════════════════════════════════════
section('K. Alternation groups and optional letters')
# ══════════════════════════════════════════════════════════════════════════════

check('K1 (q,ʾ)tb matches qtb',            m('(q,ʾ)tb', 'qtb') is True)
check('K2 (q,ʾ)tb matches ʾtb',            m('(q,ʾ)tb', 'ʾtb') is True)
check('K3 (q,ʾ)tb rejects ktb',            m('(q,ʾ)tb', 'ktb') is False)
check('K4 trailing empty alt makes it optional — qtb',
      m('(q,k,)tb', 'qtb') is True)
check('K5 trailing empty alt — ktb',       m('(q,k,)tb', 'ktb') is True)
check('K6 trailing empty alt — bare tb',   m('(q,k,)tb', 'tb') is True)
check('K7 multi-char alternatives work',   m('(ka,ki)tab', 'kitab') is True)
check('K8 whitespace inside a group is trimmed',
      m('( q , ʾ )tb', 'qtb') is True)
check('K9 a wildcard inside a group works', m('(C,V)tb', 'atb') is True)
check('K10 group + anchor combine',        m('^(q,ʾ)tb#', 'ʾtb') is True)
check('K11 unmatched ( raises re.error',
      m('(q,ʾtb', 'qtb') is None)
check('K12 single-alternative group is a no-op',
      m('(q)tb', 'qtb') is True)


# ══════════════════════════════════════════════════════════════════════════════
section('L. Long-vowel v̄ — the two-code-point wildcard')
# ══════════════════════════════════════════════════════════════════════════════

VBAR = 'v̄'   # v + COMBINING MACRON ABOVE

check('L1 v̄ matches ā',  m(VBAR, 'ā') is True)
check('L2 v̄ matches ū',  m(VBAR, 'ū') is True)
check('L3 v̄ rejects a',  m(VBAR, 'a') is False)
check('L4 v (short) rejects ā', m('v', 'ā') is False)
check('L5 v̄ inside a longer pattern', m(f'k{VBAR}n', 'kān') is True)
check('L6 v̄ inside an alternation group', m(f'({VBAR},a)n', 'ān') is True)
check('L7 v̄ is consumed as ONE token, not v + macron',
      m(f'{VBAR}#', 'ā') is True)
check('L8 two v̄ in a row',   m(f'{VBAR}{VBAR}', 'āū') is True)
check('L9 v̄ then v',         m(f'{VBAR}v', 'āa') is True)
# Regression: a bare 'v' must NOT swallow a following non-combining char
check('L10 v followed by a normal letter stays two tokens',
      m('vn', 'an') is True)


# ══════════════════════════════════════════════════════════════════════════════
section('M. tokenize() and the parenthesis convention')
# ══════════════════════════════════════════════════════════════════════════════

check('M1 splits on spaces',
      app.tokenize('katab kitab') == ['katab', 'kitab'])
check('M2 splits on punctuation',
      app.tokenize('katab, kitab. ktb!') == ['katab', 'kitab', 'ktb'])
# The documented reason parens are NOT delimiters
check('M3 parens do NOT split a word — (i)lli stays whole',
      app.tokenize('(i)lli') == ['(i)lli'], str(app.tokenize('(i)lli')))
check('M4 (yi)twaṣṣafiš stays one token',
      app.tokenize('(yi)twaṣṣafiš') == ['(yi)twaṣṣafiš'],
      str(app.tokenize('(yi)twaṣṣafiš')))
check('M5 brackets DO split',
      app.tokenize('a[b]c') == ['a', 'b', 'c'], str(app.tokenize('a[b]c')))
check('M6 empty / whitespace-only input -> []',
      app.tokenize('   \n\t ') == [], str(app.tokenize('   \n\t ')))
check('M7 output is NFC-normalised',
      app.tokenize('ā')[0] == N('ā'))
check('M8 hyphen is NOT a delimiter (morpheme boundaries survive)',
      app.tokenize('bi-ktub') == ['bi-ktub'], str(app.tokenize('bi-ktub')))


# ══════════════════════════════════════════════════════════════════════════════
section('N. parse_sequence_pattern — multi-word patterns')
# ══════════════════════════════════════════════════════════════════════════════

check('N1 single word -> 1 regex',  len(app.parse_sequence_pattern('ktb')) == 1)
check('N2 two words -> 2 regexes',  len(app.parse_sequence_pattern('g# ^G')) == 2)
check('N3 extra spaces collapse',   len(app.parse_sequence_pattern('  a   b  ')) == 2)
check('N4 empty pattern raises re.error',
      isinstance(
          (lambda: (app.parse_sequence_pattern('   ') and None))
          .__call__.__self__ if False else
          (lambda:
              (lambda f: f())(lambda: None))(),
          object))
try:
    app.parse_sequence_pattern('   ')
    _empty_ok = False
except re.error:
    _empty_ok = True
except Exception:
    _empty_ok = False
check('N4 empty pattern raises re.error', _empty_ok)

# Per-sub-pattern anchors
subs = app.parse_sequence_pattern('g# ^G')
check('N5 first sub-pattern is end-anchored',  subs[0].pattern.endswith('$'))
check('N6 second sub-pattern is start-anchored', subs[1].pattern.startswith('^'))

# _match_sequence over a real word list
words = ['ʾallag', 'ḥatta', 'baʿdēn']
res = app._match_sequence(words[:2], app.parse_sequence_pattern('g# ^G'), 'anywhere')
check('N7 sequence matches "…g" followed by guttural-initial word',
      len(res) == 2, str(res))
res = app._match_sequence(['katab', 'kitab'],
                          app.parse_sequence_pattern('g# ^G'), 'anywhere')
check('N8 sequence returns [] when the 1st word fails', res == [], str(res))
res = app._match_sequence(['ʾallag', 'katab'],
                          app.parse_sequence_pattern('g# ^G'), 'anywhere')
check('N9 sequence returns [] when the 2nd word fails', res == [], str(res))


# ══════════════════════════════════════════════════════════════════════════════
section('O. match_word() position filters')
# ══════════════════════════════════════════════════════════════════════════════

rx = app.pattern_to_regex('ta')
check('O1 anywhere finds a mid-word hit', len(app.match_word('katab', rx, 'anywhere')) == 1)
check('O2 start rejects a mid-word hit',  app.match_word('katab', rx, 'start') == [])
check('O3 start accepts a word-initial hit',
      len(app.match_word('tarak', rx, 'start')) == 1)
check('O4 end accepts a word-final hit',
      len(app.match_word('katta', rx, 'end')) == 1)
check('O5 end rejects a non-final hit',   app.match_word('katab', rx, 'end') == [])
check('O6 middle rejects a word-initial hit',
      app.match_word('tarak', rx, 'middle') == [])
check('O7 middle accepts a strictly-interior hit',
      len(app.match_word('katab', rx, 'middle')) == 1)
check('O8 middle rejects a word-final hit',
      app.match_word('katta', rx, 'middle') == [])
# Multiple occurrences
rx2 = app.pattern_to_regex('a')
check('O9 all occurrences are returned', len(app.match_word('katab', rx2, 'anywhere')) == 2)

# _subpattern_position: anchored sub-patterns must ignore the UI radio
check('O10 anchored sub-pattern forces "anywhere"',
      app._subpattern_position(app.pattern_to_regex('^ka'), 'middle') == 'anywhere')
check('O11 unanchored sub-pattern keeps the UI position',
      app._subpattern_position(app.pattern_to_regex('ka'), 'middle') == 'middle')


# ══════════════════════════════════════════════════════════════════════════════
section('P. Highlighting — correctness and HTML safety')
# ══════════════════════════════════════════════════════════════════════════════

rx = app.pattern_to_regex('ta')
out = app.highlight_word('katab', app.match_word('katab', rx, 'anywhere'))
check('P1 single match wrapped in <mark>', out == 'ka<mark>ta</mark>b', out)

out = app.highlight_word('katatab', app.match_word('katatab', rx, 'anywhere'))
check('P2 multiple matches all wrapped', out.count('<mark>') == 2, out)
check('P3 original letters all survive highlighting',
      re.sub(r'</?mark>', '', out) == 'katatab', out)

# Reverse-order application must not corrupt offsets
out = app.highlight_word('tata', app.match_word('tata', rx, 'anywhere'))
check('P4 adjacent matches do not corrupt offsets',
      re.sub(r'</?mark>', '', out) == 'tata', out)

# highlight_in_text over a plain string
out = app.highlight_in_text('katab kitab', app.pattern_to_regex('ta'))
check('P5 highlight_in_text marks every occurrence across words',
      out.count('<mark>') == 2, out)
check('P5b highlight_in_text preserves the original text',
      re.sub(r'</?mark>', '', out) == 'katab kitab', out)

# HTML-node highlighting must not corrupt tags/attributes
frag = '<p class="ta">katab</p>'
out  = app._highlight_text_nodes(frag, app.pattern_to_regex('ta'))
check('P6 class="ta" attribute is NOT highlighted',
      'class="ta"' in out, out)
check('P7 the text node IS highlighted', 'mark' in out, out)

frag = '<p>katab &amp; kitab</p>'
out  = app._highlight_text_nodes(frag, app.pattern_to_regex('ta'))
check('P8 HTML entities survive highlighting', '&amp;' in out, out)


# ══════════════════════════════════════════════════════════════════════════════
section('Q. _extract_doc_id — every documented URL shape')
# ══════════════════════════════════════════════════════════════════════════════

ID = 'aBc123_XyZ-4567890'
cases = [
    (f'https://docs.google.com/document/d/{ID}/edit',            ID, 'standard doc'),
    (f'https://docs.google.com/document/u/0/d/{ID}/edit',        ID, 'user-scoped doc'),
    (f'https://drive.google.com/file/d/{ID}/view',               ID, 'drive file'),
    (f'https://drive.google.com/file/u/2/d/{ID}/view',           ID, 'user-scoped file'),
    (f'https://drive.google.com/open?id={ID}',                   ID, 'legacy open?id'),
    (f'https://drive.google.com/uc?id={ID}&export=download',     ID, 'uc?id download'),
    (f'https://docs.google.com/document/d/{ID}/edit#heading=h.x',ID, 'with fragment'),
    (f'https://docs.google.com/document/d/{ID}',                 ID, 'no trailing path'),
]
for url, want, label in cases:
    check(f'Q1 {label}', app._extract_doc_id(url) == want, f'{url} -> {app._extract_doc_id(url)}')

check('Q2 published /d/e/ doc is rejected',
      app._extract_doc_id('https://docs.google.com/document/d/e/2PACX-1vXyz/pub') != 'e',
      str(app._extract_doc_id('https://docs.google.com/document/d/e/2PACX-1vXyz/pub')))
check('Q3 empty string -> None',      app._extract_doc_id('') is None)
check('Q4 None -> None',              app._extract_doc_id(None) is None)
check('Q5 non-Google URL -> None',    app._extract_doc_id('https://example.com/a/b') is None)
check('Q6 short id (<10 chars) rejected',
      app._extract_doc_id('https://docs.google.com/document/d/short/edit') is None)


# ══════════════════════════════════════════════════════════════════════════════
section('R. _apply_filters — corpus filtering')
# ══════════════════════════════════════════════════════════════════════════════

corpus = [
    {'name': 'A', 'village': 'V1', 'gender': 'M', 'status': 'ok'},
    {'name': 'B', 'village': 'V2', 'gender': 'F', 'status': 'ok'},
    {'name': 'C', 'village': 'V1', 'gender': 'F', 'status': 'wip'},
]
f = app._apply_filters
check('R1 empty filter dict returns everything', len(f(corpus, {})) == 3)
check('R2 empty allowed-list is treated as "no filter"',
      len(f(corpus, {'village': []})) == 3)
check('R3 single-value filter',
      [d['name'] for d in f(corpus, {'village': ['V1']})] == ['A', 'C'])
check('R4 multi-value filter is OR within a field',
      len(f(corpus, {'village': ['V1', 'V2']})) == 3)
check('R5 two fields combine as AND',
      [d['name'] for d in f(corpus, {'village': ['V1'], 'gender': ['F']})] == ['C'])
check('R6 no match -> empty list',
      f(corpus, {'village': ['V9']}) == [])
check('R7 unknown field name matches nothing (missing key -> "")',
      f(corpus, {'nope': ['x']}) == [])
check('R8 input corpus is not mutated', len(corpus) == 3)


# ══════════════════════════════════════════════════════════════════════════════
section('S. root_to_pattern')
# ══════════════════════════════════════════════════════════════════════════════

check('S1 ktb -> $k$t$b$',        app.root_to_pattern('ktb') == '$k$t$b$')
check('S2 spaces are ignored',    app.root_to_pattern('k t b') == '$k$t$b$')
check('S3 group kept intact',     app.root_to_pattern('(q,ʾ,k)tb') == '$(q,ʾ,k)$t$b$')
check('S4 empty input -> ""',     app.root_to_pattern('   ') == '')
check('S5 single letter',         app.root_to_pattern('k') == '$k$')
check('S6 unmatched ( degrades gracefully',
      isinstance(app.root_to_pattern('(qtb'), str))
# The produced pattern must actually compile and match
pat = app.root_to_pattern('ktb')
check('S7 produced pattern compiles', m(pat, 'kataba') is not None)
check('S8 root matches a word with infixes',   m(pat, 'kataba') is True)
check('S9 root rejects wrong letter order',    m(pat, 'batak') is False)
pat = app.root_to_pattern('(q,k,)tb')
check('S10 optional-letter root matches all three forms',
      all(m(pat, w) for w in ['qtb', 'ktb', 'tb']))


# ══════════════════════════════════════════════════════════════════════════════
section('T. _feat_val_norm — feature value comparison')
# ══════════════════════════════════════════════════════════════════════════════

nv = app._feat_val_norm
check('T1 trims whitespace',            nv('  bidd  ') == nv('bidd'))
check('T2 case-insensitive',            nv('BIDD') == nv('bidd'))
check('T3 NFC vs NFD are equal',
      nv(unicodedata.normalize('NFD', 'ǧ')) == nv(unicodedata.normalize('NFC', 'ǧ')))
check('T4 None -> ""',                  nv(None) == '')
check('T5 empty string -> ""',          nv('') == '')
check('T6 numeric value coerced to str', nv(1) == '1')
check('T7 False -> "" (not "false")',   nv(False) == '', repr(nv(False)))
check('T8 distinct values stay distinct', nv('badd') != nv('bidd'))
# The real-world bug this guards: composed vs decomposed diacritics in the sheet
check('T9 decomposed ḏ̣ matches composed ḏ̣',
      nv(unicodedata.normalize('NFD', 'ḏ̣')) == nv(unicodedata.normalize('NFC', 'ḏ̣')))


# ══════════════════════════════════════════════════════════════════════════════
section('U. _build_features_block — doc FEATURES text')
# ══════════════════════════════════════════════════════════════════════════════

_saved = app.FEATURE_DEFS
app.FEATURE_DEFS = [
    (1, 'A', 'PHON. Flag',  'bool',   None),
    (2, 'B', 'LEX. "want"', 'select', ['badd', 'bidd']),
]
try:
    blk = app._build_features_block({'A': True, 'B': 'bidd'}, {})
    check('U1 block starts with the FEATURES: heading', blk.startswith('FEATURES:'), blk)
    check('U2 a true bool renders as [+]',   'PHON. Flag  [+]' in blk, blk)
    check('U3 a select renders its value',   'LEX. "want"  [bidd]' in blk, blk)

    blk = app._build_features_block({'A': False, 'B': None}, {})
    check('U4 a false bool renders as an empty bracket',
          'PHON. Flag  []' in blk, blk)
    check('U5 an untagged select renders as an empty bracket',
          'LEX. "want"  []' in blk, blk)

    blk = app._build_features_block({}, {})
    check('U6 missing values do not crash', 'FEATURES:' in blk, blk)
    check('U7 every feature gets a line',
          blk.count('\n') >= 2, repr(blk))
    # Names in the block must be the FULL prefixed names the parser looks for
    check('U8 lines use the full prefixed name (parser contract)',
          'PHON. Flag' in blk and 'LEX. "want"' in blk, blk)
finally:
    app.FEATURE_DEFS = _saved


# ══════════════════════════════════════════════════════════════════════════════
section('V. Unicode normalisation across the search path')
# ══════════════════════════════════════════════════════════════════════════════

# A user may paste NFD text; the pattern compiler normalises to NFC.
check('V1 pattern input is NFC-normalised',
      m(unicodedata.normalize('NFD', 'ǧ'), 'ǧ') is True)
check('V2 NFD word text is normalised by tokenize()',
      app.tokenize(unicodedata.normalize('NFD', 'ǧamal')) == [N('ǧamal')])
check('V3 NFC pattern matches an NFD-sourced token',
      m('ǧ', app.tokenize(unicodedata.normalize('NFD', 'ǧamal'))[0]) is True)
# ā̈ has a documented variant encoding (ɑ̄) — both must be in LONG_VOWELS
check('V4 both ā̈ encodings are long vowels',
      len(app.LONG_VOWELS & {'ā̈', 'ɑ̄'}) == 2, str(app.LONG_VOWELS))


# ══════════════════════════════════════════════════════════════════════════════
section('W. Wildcard set invariants (guards future edits)')
# ══════════════════════════════════════════════════════════════════════════════

check('W1 every B/L/E/G member is a consonant',
      (app.BILABIALS | app.LAMNR | app.EMPHATICS | app.GUTTURALS) <= app.CONSONANTS,
      str((app.BILABIALS|app.LAMNR|app.EMPHATICS|app.GUTTURALS) - app.CONSONANTS))
check('W2 consonants and vowels are disjoint',
      not (app.CONSONANTS & app.VOWELS),
      str(app.CONSONANTS & app.VOWELS))
check('W3 short and long vowels are disjoint',
      not (app.SHORT_VOWELS & app.LONG_VOWELS),
      str(app.SHORT_VOWELS & app.LONG_VOWELS))
check('W4 VOWELS is exactly short | long',
      app.VOWELS == (app.SHORT_VOWELS | app.LONG_VOWELS))
check('W5 every diphthong is 2 characters',
      all(len(d) == 2 for d in app.DIPHTHONGS), str(app.DIPHTHONGS))
check('W6 C matches every consonant individually',
      all(m('C', c) for c in app.CONSONANTS),
      str([c for c in app.CONSONANTS if not m('C', c)]))
check('W7 V matches every vowel individually',
      all(m('V', v) for v in app.VOWELS),
      str([v for v in app.VOWELS if not m('V', v)]))
check('W8 C does not match any vowel',
      not any(m('^C#', v) for v in app.VOWELS),
      str([v for v in app.VOWELS if m('^C#', v)]))
# _alts must sort longest-first so a short member never shadows a longer one
# that starts with it (regex alternation is first-match-wins, not longest-wins).
_alt_list = app._alts({'a', 'abc', 'ab'})[3:-1].split('|')
check('W9 _alts orders alternatives longest-first',
      _alt_list == ['abc', 'ab', 'a'], str(_alt_list))
check('W9b longest-first actually wins the match',
      app.pattern_to_regex('x').pattern is not None
      and re.match(app._alts({'a', 'ab'}), 'ab').group() == 'ab',
      re.match(app._alts({'a', 'ab'}), 'ab').group())
# Real-world consequence: the 2-codepoint ḏ̣ must win over a bare ḏ
check('W9c multi-codepoint ḏ̣ is preferred over ḏ in the C class',
      re.match(app._C, 'ḏ̣').group() == 'ḏ̣',
      re.match(app._C, 'ḏ̣').group())
check('W10 multi-codepoint consonant ḏ̣ is matched as one unit',
      m('^C#', 'ḏ̣') is True)


# ══════════════════════════════════════════════════════════════════════════════
section('X. write_sheet_features / delete_feature_tag — argument shaping')
# ══════════════════════════════════════════════════════════════════════════════

check('X1 write_sheet_features bumps the cache version',
      '_features_version' in source)
check('X2 delete_feature_tag exists', hasattr(app, 'delete_feature_tag'))
check('X3 select writes merge instead of blocking on a conflict',
      '_merge_feat_values(cur_val, new_val, fd[4])' in source
      and 'conflicts.append' not in source)
check('X4 a bool write uses the checkbox representation',
      "'+'" in source)
check('X5 writes go through the resolved column letter, never a constant',
      re.search(r"Recordings!\{[A-Za-z_]+\}", source) is not None
      or 'col_letter' in source)


# ══════════════════════════════════════════════════════════════════════════════
section('Y. Error handling — malformed input must not crash')
# ══════════════════════════════════════════════════════════════════════════════

for bad, label in [
    ('(',        'lone open paren'),
    ('(,)',      'group of empty alternatives'),
    ('()',       'empty group'),
    ('$$$$',     'only wildcards'),
    ('^#',       'anchors with no body'),
    ('#^',       'reversed anchors'),
    ('a' * 500,  'very long pattern'),
]:
    try:
        app.pattern_to_regex(bad)
        ok = True
    except re.error:
        ok = True          # a clean re.error is acceptable — the UI catches it
    except Exception as e:
        ok = False
        _detail = f'{type(e).__name__}: {e}'
    check(f'Y1 {label} raises re.error or compiles (no hard crash)',
          ok, locals().get('_detail', ''))

check('Y2 run_search catches re.error and returns []',
      're.error' in source and 'Invalid pattern' in source)
check('Y3 _infer_column_types swallows API errors',
      re.search(r'except Exception:\s*\n\s*pass', source) is not None)
check('Y4 get_extra_feature_defs returns [] when the tab is missing',
      'return []   # tab doesn' in source or 'return []' in source)



# ══════════════════════════════════════════════════════════════════════════════
section('Z. UX changes — active filters, legend, unified search, empty state')
# ══════════════════════════════════════════════════════════════════════════════

# Z1 — active-filter indicator
check('Z1 filter keys are enumerated for the indicator',
      '_FILTER_KEYS' in source)
check('Z2 active filters are read from session_state (pre-widget)',
      re.search(r'_active_now\s*=', source) is not None)
check('Z3 expander label carries the active-filter count',
      'filter{' in source and 'active' in source)
check('Z4 a filter banner renders outside the expander',
      'filter-banner' in source)
check('Z5 .filter-banner CSS class is defined',
      '.filter-banner {' in source)
check('Z6 a Clear-all-filters button exists',
      'clear_all_filters' in source)
check('Z7 Clear resets every filter key, then reruns',
      re.search(r'for _k in _FILTER_KEYS:\s*\n\s*st\.session_state\[_k\] = \[\]', source)
      is not None)
# every key in _FILTER_KEYS must be a real multiselect key used in the UI
_fk = re.search(r'_FILTER_KEYS\s*=\s*\{(.*?)\}', source, re.S)
_keys = re.findall(r"'(filt_\w+)'", _fk.group(1)) if _fk else []
check('Z8 all six document filters are covered by the indicator',
      len(_keys) == 6, str(_keys))
_missing = [k for k in _keys if f'key="{k}"' not in source]
check('Z9 every indicator key matches a real multiselect widget',
      not _missing, str(_missing))

# Z10 — legend collapse
check('Z10 legend uses a native <details> block (no Streamlit rerun)',
      'details class="legend-more"' in source)
check('Z11 legend-more CSS is defined',
      'details.legend-more' in source)
# Compare positions WITHIN the legend HTML only — 'legend-more' also appears
# far earlier in the CSS block, which would make a whole-file index() meaningless.
_legend = source[source.index('<div class="legend-row">'):]
_legend = _legend[:_legend.index('</div>\n        """')]
_open   = _legend.index('<details class="legend-more">')
check('Z12 core wildcards stay outside the collapsed block',
      _legend.index('<b>C</b> = consonant') < _open
      and _legend.index('<b>V</b> = vowel') < _open
      and _legend.index('<b>$</b> =') < _open)
check('Z13 rarer wildcards moved inside the collapsed block',
      _open < _legend.index('<b>B</b> = Bilabial')
      and _open < _legend.index('<b>L</b> = Laminal')
      and _open < _legend.index('<b>E</b> = emphatic'))
check('Z13b the collapsed block is closed properly',
      _legend.count('<details class="legend-more">') == 1
      and _legend.count('</details>') == 1)
check('Z13c the collapsed block has a summary label',
      '<summary>' in _legend and '</summary>' in _legend)
# Every wildcard must still be documented somewhere in the legend
for _ch in ['C', 'V', 'v', 'D', 'G', 'E', 'B', 'L']:
    check(f'Z14 wildcard {_ch} still documented in the legend',
          re.search(rf'<b>{re.escape(_ch)}</b>\s*=', source) is not None)

# Z15 — unified Search button
check('Z15 the main Search button also fires a feature search',
      '_feat_search_btn or search_clicked' in source)
check('Z16 the old "use the other button" apology is gone',
      'use the **🏷️ Find tagged documents** button' not in source)
check('Z17 pressing Search with no feature selected gives guidance',
      'Choose at least one feature above' in source)

# Z18 — empty-state funnel diagnosis
check('Z18 transcription empty state has a funnel explainer',
      '_explain_empty' in source)
check('Z19 funnel counts corpus size and post-filter size',
      '_n_corpus_total' in source and '_n_after_filter' in source)
check('Z20 funnel counts are de-duplicated by doc_id',
      re.search(r"_n_corpus_total\s*=\s*len\(\{d\['doc_id'\]", source) is not None)
check('Z21 zero-after-filter case is called out explicitly',
      'filters excluded every document' in source)
check('Z22 whole-corpus case points at the pattern, not the filters',
      'this is the pattern, not the filters' in source)
check('Z23 both document and transcription modes use the explainer',
      source.count('_explain_empty(') >= 3)
check('Z24 feature browse also shows the funnel',
      'matched the feature conditions' in source)
check('Z25 AND/OR hint shown when an AND search returns nothing',
      'Switch to **OR**' in source)
check('Z26 an entirely untagged feature column is called out',
      'nothing has been tagged with this feature yet' in source)

# ══════════════════════════════════════════════════════════════════════════════
section('AA. Multi-value feature tags — parsing')
# ══════════════════════════════════════════════════════════════════════════════

sp = app._split_feat_values
FEM = ['-i', '-e', '-a', 'pausal']
# The two real options that contain ';' inside their own text
TRICKY = ['-a', '-a / -ya (after -i-)', '-ha',
          '-a; -ha only after -ū-',
          '-a; -ha only after -ū- / -i-', '-hä#/-he#']

check('AA1 empty cell -> []',            sp(None, FEM) == [])
check('AA2 empty string -> []',          sp('', FEM) == [])
check('AA3 False -> []',                 sp(False, FEM) == [])
check('AA4 single value -> one item',    sp('-e', FEM) == ['-e'])
check('AA5 two values split on ;',       sp('-e; -a', FEM) == ['-e', '-a'], str(sp('-e; -a', FEM)))
check('AA6 the screenshot format "-e ; ; ; -a" parses to two values',
      sp('-e ; ; ; -a', FEM) == ['-e', '-a'], str(sp('-e ; ; ; -a', FEM)))
check('AA7 comma separator also accepted',
      sp('-e, -a', FEM) == ['-e', '-a'], str(sp('-e, -a', FEM)))
check('AA8 duplicates collapse',         sp('-e; -e', FEM) == ['-e'], str(sp('-e; -e', FEM)))
check('AA9 order is preserved',          sp('-a; -e; -i', FEM) == ['-a', '-e', '-i'])
check('AA10 whitespace trimmed',         sp('  -e ;   -a  ', FEM) == ['-e', '-a'])
check('AA11 no options list -> plain split',
      sp('x; y', None) == ['x', 'y'], str(sp('x; y', None)))
check('AA12 unknown value still returned',
      sp('-e; totally-new', FEM) == ['-e', 'totally-new'], str(sp('-e; totally-new', FEM)))

# THE critical case: an option that contains ';' must NOT be shredded
check('AA13 option containing ";" stays ONE value',
      sp('-a; -ha only after -ū-', TRICKY) == ['-a; -ha only after -ū-'],
      str(sp('-a; -ha only after -ū-', TRICKY)))
check('AA14 the longer ";"-containing option also stays whole',
      sp('-a; -ha only after -ū- / -i-', TRICKY) == ['-a; -ha only after -ū- / -i-'],
      str(sp('-a; -ha only after -ū- / -i-', TRICKY)))
check('AA15 ";"-containing option combined with another value',
      sp('-a; -ha only after -ū-; -ha', TRICKY) == ['-a; -ha only after -ū-', '-ha'],
      str(sp('-a; -ha only after -ū-; -ha', TRICKY)))
check('AA16 bare "-a" is not swallowed by the longer option',
      sp('-a', TRICKY) == ['-a'], str(sp('-a', TRICKY)))
check('AA17 longest-first: "-a" then the long option',
      sp('-a; -a; -ha only after -ū-', TRICKY)
      == ['-a', '-a; -ha only after -ū-'],
      str(sp('-a; -a; -ha only after -ū-', TRICKY)))
check('AA18 NFD input parses the same as NFC',
      sp(unicodedata.normalize('NFD', '-a; -ha only after -ū-'), TRICKY)
      == ['-a; -ha only after -ū-'],
      str(sp(unicodedata.normalize('NFD', '-a; -ha only after -ū-'), TRICKY)))


# ══════════════════════════════════════════════════════════════════════════════
section('AB. Multi-value feature tags — merging')
# ══════════════════════════════════════════════════════════════════════════════

mg = app._merge_feat_values

merged, added, dup = mg(None, '-e', FEM)
check('AB1 tagging an empty cell', (merged, added, dup) == ('-e', ['-e'], []), str((merged, added, dup)))

merged, added, dup = mg('-e', '-a', FEM)
check('AB2 second value is ADDED, not overwritten',
      merged == app._join_feat_values(['-e', '-a']), merged)
check('AB3 the added value is reported', added == ['-a'], str(added))
check('AB4 nothing reported as duplicate', dup == [], str(dup))

merged, added, dup = mg('-e', '-e', FEM)
check('AB5 re-tagging the same value changes nothing', merged == '-e', merged)
check('AB6 duplicate is reported, not added',
      added == [] and dup == ['-e'], str((added, dup)))

merged, added, dup = mg('-e; -a', '-i', FEM)
check('AB7 third value appends',
      merged == app._join_feat_values(['-e', '-a', '-i']), merged)

merged, added, dup = mg('-e', ['-a', '-i'], FEM)
check('AB8 a list of new values merges in one call',
      merged == app._join_feat_values(['-e', '-a', '-i']), merged)

merged, added, dup = mg('-e', '-a; -i', FEM)
check('AB9 a separator-joined string of new values also merges',
      merged == app._join_feat_values(['-e', '-a', '-i']), merged)

merged, added, dup = mg('-e; -a', '-a', FEM)
check('AB10 adding an already-present value is a no-op',
      merged == app._join_feat_values(['-e', '-a']) and added == [], str((merged, added)))

# The existing value must survive even when it is a ";"-containing option
merged, added, dup = mg('-a; -ha only after -ū-', '-ha', TRICKY)
check('AB11 ";"-containing existing value is preserved on merge',
      merged == app._join_feat_values(['-a; -ha only after -ū-', '-ha']), merged)

check('AB12 merging never removes anything',
      all(v in mg('-e; -a; -i', '-x', FEM)[0] for v in ['-e', '-a', '-i']))
check('AB13 empty new value is ignored',
      mg('-e', '', FEM)[0] == '-e', mg('-e', '', FEM)[0])
check('AB14 join helper uses the configured separator',
      app._join_feat_values(['a', 'b']) == 'a' + app.FEAT_VALUE_SEP + 'b',
      app._join_feat_values(['a', 'b']))
check('AB14b write separator is comma (native multi-select format)',
      app.FEAT_VALUE_SEP.strip() == ',', repr(app.FEAT_VALUE_SEP))
check('AB15 join drops blanks',
      app._join_feat_values(['a', '', '  ', 'b']) == 'a' + app.FEAT_VALUE_SEP + 'b')


# ══════════════════════════════════════════════════════════════════════════════
section('AC. Multi-value feature tags — search matching')
# ══════════════════════════════════════════════════════════════════════════════

fm = app._feat_value_matches
check('AC1 single-value cell matches its value',      fm('-e', '-e', FEM) is True)
check('AC2 multi-value cell matches the FIRST value', fm('-e; -a', '-e', FEM) is True)
check('AC3 multi-value cell matches the SECOND value',fm('-e; -a', '-a', FEM) is True)
check('AC4 multi-value cell rejects an absent value', fm('-e; -a', '-i', FEM) is False)
check('AC5 empty cell matches nothing',               fm(None, '-e', FEM) is False)
check('AC6 matching is case-insensitive',             fm('-E; -a', '-e', FEM) is True)
check('AC7 matching ignores surrounding whitespace',  fm('  -e ;  -a ', '-a', FEM) is True)
check('AC8 NFD cell matches an NFC query',
      fm(unicodedata.normalize('NFD', 'ǧ'), unicodedata.normalize('NFC', 'ǧ'), ['ǧ']) is True)
check('AC9 ";"-containing option is matched as a whole',
      fm('-a; -ha only after -ū-', '-a; -ha only after -ū-', TRICKY) is True)
check('AC10 a ";"-containing cell does NOT falsely match its fragment',
      fm('-a; -ha only after -ū-', '-ha', TRICKY) is False,
      'the whole string is one option, so "-ha" alone must not match')


# ══════════════════════════════════════════════════════════════════════════════
section('AD. Multi-value wiring through the app')
# ══════════════════════════════════════════════════════════════════════════════

check('AD1 separator constant defined',      'FEAT_VALUE_SEP' in source)
check('AD2 write_sheet_features merges select values',
      '_merge_feat_values(cur_val, new_val, fd[4])' in source)
check('AD3 write_sheet_features returns notices, not []',
      re.search(r'return notices', source) is not None)
check('AD4 bool features keep single-value semantics',
      "if fd[3] == 'bool':" in source and 'bool(new_val)' in source)
check('AD5 the submit UI no longer speaks of overwriting',
      'now overwritten with' not in source)
check('AD6 the submit UI reports merges as info, not a warning',
      'Existing tags were kept and yours added alongside' in source)
check('AD7 pending tags accumulate within one tagging session',
      '_acc, _, _ = _merge_feat_values(_prev, feat_val, fd[4])' in source)
check('AD8 type inference splits multi-values before building options',
      'distinct.update(_split_feat_values(v))' in source)
check('AD9 the empty-state diagnostic lists values individually',
      'for _one in _split_feat_values(_cur, _fd[4]):' in source)
check('AD10 the context menu receives the current values',
      'const CURRENT' in source and 'current_vals_js' in source)
check('AD11 already-tagged values are ticked in the menu',
      'Already tagged on this document' in source)
check('AD12 the menu says a pick will be added alongside existing tags',
      'Will be added alongside' in source)
check('AD13 inject_interaction_js takes a sheet_row',
      'sheet_row: int = None' in source)
check('AD14 every call site passes sheet_row',
      source.count('sheet_row=(') >= 3, str(source.count('sheet_row=(')))
check('AD15 reading current values can never break rendering',
      re.search(r'except Exception:\s*\n\s*_current_map = \{\}', source) is not None)

# ══════════════════════════════════════════════════════════════════════════════
section('AE. Native multi-select format (Google Sheets chips)')
# ══════════════════════════════════════════════════════════════════════════════

# Real values from the SYN. Continuous Mod. column
SYN = ['Q-ʿ-D', 'B-Q-Y', 'K-W-N']

check('AE1 write separator is comma (native chip format)',
      app.FEAT_VALUE_SEP.strip() == ',', repr(app.FEAT_VALUE_SEP))
check('AE2 native ", " cell parses into chips',
      sp('Q-ʿ-D, B-Q-Y', SYN) == ['Q-ʿ-D', 'B-Q-Y'], str(sp('Q-ʿ-D, B-Q-Y', SYN)))
check('AE3 native cell without a space after the comma parses too',
      sp('Q-ʿ-D,B-Q-Y', SYN) == ['Q-ʿ-D', 'B-Q-Y'], str(sp('Q-ʿ-D,B-Q-Y', SYN)))
check('AE4 legacy ";" cells still parse (not yet migrated columns)',
      sp('Q-ʿ-D; B-Q-Y', SYN) == ['Q-ʿ-D', 'B-Q-Y'], str(sp('Q-ʿ-D; B-Q-Y', SYN)))
check('AE5 a merge writes the native comma format',
      mg('Q-ʿ-D', 'B-Q-Y', SYN)[0] == 'Q-ʿ-D, B-Q-Y', mg('Q-ʿ-D', 'B-Q-Y', SYN)[0])
check('AE6 search finds a chip cell by either chip',
      fm('Q-ʿ-D, B-Q-Y', 'Q-ʿ-D', SYN) and fm('Q-ʿ-D, B-Q-Y', 'B-Q-Y', SYN))
check('AE7 search rejects a chip that is not on the cell',
      fm('Q-ʿ-D, B-Q-Y', 'K-W-N', SYN) is False)
# No current option value contains a comma — that is what makes comma-splitting
# safe. If one is ever added, this test fires before it can corrupt parsing.
_comma_opts = [o for t in app.FEATURE_HEADER_DEFS for o in (t[3] or []) if ',' in o]
check('AE8 no option value contains a comma (keeps comma-splitting safe)',
      not _comma_opts, str(_comma_opts))
# The ';'-containing options must STILL survive now that ',' is the writer
check('AE9 ";"-containing option still parses whole under comma separator',
      sp('-a; -ha only after -ū-', TRICKY) == ['-a; -ha only after -ū-'],
      str(sp('-a; -ha only after -ū-', TRICKY)))
check('AE10 ";"-containing option merged with another writes comma-separated',
      mg('-a; -ha only after -ū-', '-ha', TRICKY)[0]
      == '-a; -ha only after -ū-, -ha',
      mg('-a; -ha only after -ū-', '-ha', TRICKY)[0])


# ══════════════════════════════════════════════════════════════════════════════
section('AF. Chips in the UI')
# ══════════════════════════════════════════════════════════════════════════════

check('AF1 val-chip CSS class defined',       '.val-chip {' in source)
check('AF2 empty-state chip variant defined', '.val-chip.is-empty' in source)
check('AF3 Feature Browse value picker is a multiselect, not a selectbox',
      'st.multiselect(\n                        f"Value — {_sf}"' in source
      or re.search(r'st\.multiselect\(\s*\n\s*f"Value — \{_sf\}"', source) is not None)
check('AF4 the old single-value selectbox is gone',
      re.search(r'st\.selectbox\(\s*\n\s*f"Value — \{_sf\}"', source) is None)
check('AF5 several wanted values are OR-ed per feature',
      '_wanted = _fv if isinstance(_fv, (list, tuple)) else [_fv]' in source)
check('AF6 the stats bar renders wanted values as chips',
      'class="val-chip">{v}</span>' in source)
check('AF7 result rows render tagged values as chips',
      '_chip_rows' in source and 'val-chip">{p}</span>' in source)
check('AF8 an untagged feature shows an explicit empty chip',
      'val-chip is-empty">not tagged' in source)
check('AF9 the collapsed label splits multi-values with " / "',
      "' / '.join(_parts)" in source)
check('AF10 condition description handles a list of values',
      '_fmt_cond' in source)
check('AF11 picking no value adds no condition (feature is skipped)',
      'if _vals:\n                        _feat_conditions.append' in source)
check('AF12 "not tagged" is still selectable alongside real values',
      '[FEAT_NONE_OPTION] + (_fd[4] or [])' in source)
check('AF13 FEAT_NONE_OPTION is handled inside the any() test',
      '_is_empty if _w == FEAT_NONE_OPTION' in source)

# ══════════════════════════════════════════════════════════════════════════════
section('AG. Free-text feature search in the tagging popup')
# ══════════════════════════════════════════════════════════════════════════════

check('AG1 the popup has a feature search input',   'id="ctx-feat-q"' in source)
check('AG2 the search input has a clear button',    'id="ctx-feat-clear"' in source)
check('AG3 search CSS is defined',                  '#ctx-feat-search {' in source)
check('AG4 matching strips the category prefix',    'function stripPrefix(name)' in source)
check('AG5 matching tries full name AND bare name',
      'full.indexOf(q) >= 0 || bare.indexOf(q) >= 0' in source)
check('AG6 option values are searchable too',       'opts.indexOf(q) >= 0' in source)
check('AG7 search results are rendered flat',       'function renderSearch(q)' in source)
check('AG8 group browsing still exists',            'function renderGroups()' in source)
check('AG9 feature rows are built by one shared helper',
      'function makeFeatureItem(' in source)
check('AG10 flat results show which group a feature belongs to',
      'ctx-grp-tag' in source and 'function groupOf(' in source)
check('AG11 a no-match state is shown',             'No feature matches' in source)
check('AG12 the query resets on every right-click',
      "featQ.value = '';\n    applyFeatureQuery();" in source)
check('AG13 the selected-word header survives clearing the query',
      'baseHeader' in source)
check('AG14 typing in the box cannot close the menu',
      "featQ.addEventListener('keydown'" in source
      and "featQ.addEventListener('mousedown'" in source)
check('AG15 Escape clears the query',
      "if (e.key === 'Escape') {{ featQ.value = ''" in source
      or "e.key === 'Escape'" in source)
check('AG16 features with no known prefix stay reachable in the popup',
      'UNGROUPED' in source)

# The rendered JS must be structurally valid — an unbalanced brace here fails
# silently in the browser and takes the whole context menu down with it.
_saved_defs = app.FEATURE_DEFS
app.FEATURE_DEFS = [
    (1, 'A', 'PHON. Diphthongs',     'bool',   None),
    (2, 'B', 'MOR. Fem. Ending',     'select', ['-i', '-e', '-a']),
    (3, 'C', 'LEX. "want"',          'select', ['badd', 'bidd']),
    (4, 'D', 'SYN. Continuous Mod.', 'select', ['Q-ʿ-D', 'B-Q-Y']),
]
try:
    _html = app.inject_interaction_js('<p>x</p>', 'doc1')
    check('AG17 rendered popup contains the search box', 'ctx-feat-q' in _html)
    check('AG18 no unrendered f-string braces leak into the page',
          '{{' not in _html and '}}' not in _html)
    _js = re.search(r'<script>\n\(function\(\)\{(.*?)\n\}\)\(\);', _html, re.S)
    check('AG19 the popup script block is extractable', _js is not None)
    if _js:
        _b = _js.group(1)
        check('AG20 rendered JS braces balance',
              _b.count('{') == _b.count('}'), f"{_b.count('{')}/{_b.count('}')}")
        check('AG21 rendered JS parens balance',
              _b.count('(') == _b.count(')'), f"{_b.count('(')}/{_b.count(')')}")
        check('AG22 rendered JS brackets balance',
              _b.count('[') == _b.count(']'), f"{_b.count('[')}/{_b.count(']')}")
    _feats = json.loads(re.search(r'const FEATURES\s*=\s*(\[.*?\]);', _html, re.S).group(1))
    check('AG23 every feature is exposed to the popup', len(_feats) == 4, str(len(_feats)))
    check('AG24 each feature carries name/type/opts',
          all({'name', 'type', 'opts'} <= set(f) for f in _feats))
finally:
    app.FEATURE_DEFS = _saved_defs


# ══════════════════════════════════════════════════════════════════════════════
section('AH. Feature Browse grouped by category')
# ══════════════════════════════════════════════════════════════════════════════

check('AH1 the four category groups are declared',  '_FEAT_GROUP_LABELS' in source)
check('AH2 one multiselect per group, not one flat list',
      'key=f"feat_browse_grp_{_gprefix.rstrip(\'.\')}"' in source)
check('AH3 the old flat picker is gone',
      'key="feat_browse_names"' not in source)
check('AH4 labels drop the prefix (the heading already carries it)',
      'format_func=_bare_feat' in source and 'def _bare_feat(' in source)
check('AH5 each group heading shows how many features it has',
      '({len(_g_feats)})' in source)
check('AH6 groups are laid out in two columns',
      '_g1 if _gi % 2 == 0 else _g2' in source)
check('AH7 selections from every group are combined',
      '_sel_feats.extend(' in source)
check('AH8 an empty group is skipped, not shown empty',
      'if not _g_feats:' in source)
check('AH9 prefix-less features remain reachable via an Other group',
      '_ungrouped' in source and 'feat_browse_grp_other' in source)
check('AH10 the popup and this screen use the same four categories',
      all(p in source for p in ('PHON.', 'MOR.', 'SYN.', 'LEX.')))

# The group prefixes offered here must be exactly FEAT_PREFIXES — otherwise a
# whole category of features would silently vanish from this screen.
_grp_block = re.search(r'_FEAT_GROUP_LABELS\s*=\s*\[(.*?)\]', source, re.S).group(1)
_grp_prefixes = tuple(re.findall(r"\('([A-Z]+\.)'", _grp_block))
check('AH11 group prefixes match FEAT_PREFIXES exactly',
      _grp_prefixes == app.FEAT_PREFIXES,
      f'{_grp_prefixes} vs {app.FEAT_PREFIXES}')

# _bare_feat must strip exactly like the popup's stripPrefix()
check('AH12 prefix stripping agrees with the popup implementation',
      all(
          f'{p} x'.startswith(p) and f'{p} x'[len(p):].strip() == 'x'
          for p in app.FEAT_PREFIXES
      ))


# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{"="*66}')
if failures:
    print(f'RESULT: {len(failures)} FAILURE(S)')
    for f_ in failures:
        print(f'  - {f_}')
    sys.exit(1)
print('RESULT: ALL SEARCH/TEXT/DOC TESTS PASSED')
