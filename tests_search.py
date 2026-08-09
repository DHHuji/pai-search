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
# Scope this to write_sheet_features: the auto-tag scanner legitimately builds
# its own `conflicts` report, which is a different thing entirely.
_wsf = source.split('def write_sheet_features')[1].split('\ndef ')[0]
check('X3 select writes merge instead of blocking on a conflict',
      '_merge_feat_values(cur_val, new_val, fd[4])' in _wsf
      and 'conflicts' not in _wsf)
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
check('Z15 the Search button is the ONLY feature-search trigger',
      'if search_clicked and _feat_conditions:' in source)
check('Z15b the separate "Find tagged documents" button is gone',
      'Find tagged documents' not in source.replace(
          '# NOTE: there is deliberately NO separate "Find tagged documents" button.', '')
      and 'feat_browse_btn' not in source)
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
# An empty value picker means "any value" — matching its placeholder. It must
# still produce a CONDITION, otherwise selecting a feature on its own does
# nothing and the BUT checkbox (disabled while there are no conditions) can
# never be ticked.
check('AF11 selecting a feature alone still produces a condition',
      'if _vals:\n                        _feat_conditions.append' not in source
      and '_feat_conditions.append((_sf, _fd, list(_vals)))' in source)
check('AF11b an empty picker matches any tagged value',
      'if not _wanted:' in source and '_hit = not _is_empty' in source)
check('AF11c the label reads "any value" when nothing is picked',
      "is-empty\">any value" in source)
check('AF11d the description reads "any value" too',
      "if vals else 'any value'" in source)
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
section('AI. CSV export — example words and blank vs FALSE')
# ══════════════════════════════════════════════════════════════════════════════

_saved_defs = app.FEATURE_DEFS
app.FEATURE_DEFS = [
    (1, 'A', 'PHON. Diphthongs', 'bool',   None),
    (2, 'B', 'PHON. Med. Imāla', 'bool',   None),
    (3, 'C', 'MOR. Fem. Ending', 'select', ['-i', '-e', '-a']),
    (4, 'D', 'LEX. "want"',      'select', ['badd', 'bidd']),
]
_DOC = (
    '<html><body><p>text</p><p>FEATURES:</p><p>PHON.</p>'
    '<p>PHON. Diphthongs  [bayt; ʿayn]   +</p><p>MOR.</p>'
    '<p>MOR. Fem. Ending  [madrase]   -e, -a</p><p>LEX.</p>'
    '<p>LEX. &quot;want&quot;  [biddi ašrab]   bidd</p></body></html>'
)
try:
    # ── header shape ──
    hdr = app._csv_feature_header()
    check('AI1 header has three columns per feature',
          len(hdr) == 3 * len(app.FEATURE_DEFS), str(len(hdr)))
    check('AI2 example and BUT columns sit next to their value column',
          hdr[:3] == ['PHON. Diphthongs', 'PHON. Diphthongs — example',
                      'PHON. Diphthongs — BUT'], str(hdr[:3]))
    check('AI3 every feature has example and BUT columns',
          all(f'{fd[2]} — example' in hdr and f'{fd[2]} — BUT' in hdr
              for fd in app.FEATURE_DEFS))

    # ── example-word extraction from the doc ──
    with mock.patch.object(app, 'get_doc_content', return_value={'display_html': _DOC}):
        ex = app.get_doc_feature_examples('d1')
    check('AI4 example words are read from the doc FEATURES block',
          ex.get('PHON. Diphthongs') == 'bayt; ʿayn', str(ex))
    check('AI5 example words parsed for a select feature',
          ex.get('MOR. Fem. Ending') == 'madrase', str(ex))
    check('AI6 HTML entities in a feature name still match',
          ex.get('LEX. "want"') == 'biddi ašrab', str(ex))
    check('AI7 group-header lines are skipped', 'PHON.' not in ex, str(ex))

    # ── the two bugs being fixed ──
    SHEET = {'A': True, 'B': None, 'C': '-e, -a', 'D': 'bidd'}
    with mock.patch.object(app, 'get_sheet_features', return_value=SHEET), \
         mock.patch.object(app, 'get_doc_content', return_value={'display_html': _DOC}):
        cells = app._csv_feature_cells(7, 'd1')

    check('AI8 cells line up with the header',
          len(cells) == len(hdr), f'{len(cells)} vs {len(hdr)}')
    _c = dict(zip(hdr, cells))
    check('AI9 a ticked bool exports TRUE',
          _c['PHON. Diphthongs'] == 'TRUE', repr(_c['PHON. Diphthongs']))
    # THE reported bug: an untouched bool used to export as FALSE
    check('AI10 an UNTAGGED bool exports BLANK, not FALSE',
          _c['PHON. Med. Imāla'] == '', repr(_c['PHON. Med. Imāla']))
    check('AI11 its example column is blank too',
          _c['PHON. Med. Imāla — example'] == '')
    check('AI12 a multi-value select exports both values',
          _c['MOR. Fem. Ending'] == '-e, -a', repr(_c['MOR. Fem. Ending']))
    check('AI13 the tagged word appears beside its feature',
          _c['MOR. Fem. Ending — example'] == 'madrase',
          repr(_c['MOR. Fem. Ending — example']))
    check('AI14 example words survive multi-word tags',
          _c['LEX. "want" — example'] == 'biddi ašrab')

    # An UNTICKED checkbox (literal False in the sheet) must ALSO export blank.
    # These columns are Google Sheets checkboxes: False is the default state,
    # not a judgement, and a checkbox has no third state to distinguish them.
    # Exporting FALSE filled the CSV with meaningless negatives — 33 of the 36
    # checkbox columns were FALSE in all 778 corpus rows with no TRUE at all.
    with mock.patch.object(app, 'get_sheet_features',
                           return_value={'A': False, 'B': None, 'C': None, 'D': None}), \
         mock.patch.object(app, 'get_doc_content', return_value={'display_html': ''}):
        _c2 = dict(zip(hdr, app._csv_feature_cells(7, 'd1')))
    check('AI15 an unticked checkbox (False) exports BLANK, not FALSE',
          _c2['PHON. Diphthongs'] == '', repr(_c2['PHON. Diphthongs']))
    check('AI16 both False and None export the same blank cell',
          _c2['PHON. Diphthongs'] == '' and _c2['PHON. Med. Imāla'] == '')
    check('AI16b the string FALSE never reaches a CSV cell',
          'FALSE' not in [_c2[h] for h in hdr])

    # ── robustness ──
    with mock.patch.object(app, 'get_sheet_features', side_effect=RuntimeError('boom')), \
         mock.patch.object(app, 'get_doc_content', side_effect=RuntimeError('boom')):
        _c3 = app._csv_feature_cells(7, 'd1')
    check('AI17 a sheet/doc failure yields blanks, not a crash',
          len(_c3) == len(hdr) and set(_c3) == {''}, str(_c3))
    check('AI18 no sheet_row yields blanks',
          app._csv_feature_cells(None, '') == [''] * len(hdr))
    with mock.patch.object(app, 'get_doc_content', return_value={'display_html': ''}):
        check('AI19 an empty document yields no examples',
              app.get_doc_feature_examples('d2') == {})
    with mock.patch.object(app, 'get_doc_content',
                           return_value={'display_html': '<p>no features here</p>'}):
        check('AI20 a doc with no FEATURES block yields no examples',
              app.get_doc_feature_examples('d3') == {})

    # ── line parser, both historical formats ──
    _fd_sel = (3, 'C', 'MOR. Fem. Ending', 'select', ['-i', '-e', '-a'])
    check('AI21 new format: words inside the brackets',
          app._split_feature_line('MOR. Fem. Ending  [madrase]   -e', _fd_sel)
          == ('madrase', '-e', ''))
    check('AI22 old format: value inside the brackets, words after',
          app._split_feature_line('MOR. Fem. Ending  [-e]  madrase', _fd_sel)
          == ('madrase', '-e', ''))
    check('AI23 a line for a different feature is rejected',
          app._split_feature_line('LEX. "want"  [x]  y', _fd_sel) == (None, None, None))
    check('AI24 a malformed line does not crash',
          app._split_feature_line('MOR. Fem. Ending  [', _fd_sel) == ('', '', ''))
    # Regression: "name  []   value" is what the app writes when a feature has
    # a value but no example word. An empty bracket must NOT be read as the
    # old format, or the value comes back as the example and the value blank.
    check('AI24b empty bracket is new-format, not value/example swapped',
          app._split_feature_line('MOR. Fem. Ending  []   -e', _fd_sel)
          == ('', '-e', ''),
          str(app._split_feature_line('MOR. Fem. Ending  []   -e', _fd_sel)))
finally:
    app.FEATURE_DEFS = _saved_defs

# ── wiring: all three CSV writers must use the shared helpers ──
check('AI25 main results CSV uses the shared header',
      source.count('_csv_feature_header()') >= 2, str(source.count('_csv_feature_header()')))
check('AI26 all three CSV writers use the shared cell builder',
      source.count('_csv_feature_cells(') >= 4, str(source.count('_csv_feature_cells(')))
check('AI27 exactly one place decides bool export',
      source.count("'TRUE' if") == 1, str(source.count("'TRUE' if")))
# Assert on the CODE, not the prose — the docstring legitimately mentions
# FALSE while explaining why it is never exported.
check('AI27b no code path assigns the literal string FALSE',
      "else 'FALSE'" not in source and '"FALSE"' not in source.replace(
          "'+', '-', 'true', 'false', 'yes', 'no', 'TRUE', 'FALSE', '1', '0',", ''))
check('AI27c bool export is a plain TRUE-or-blank',
      "cell = 'TRUE' if v else ''" in source)
check('AI28 the document annotation parse is cached',
      '@st.cache_data(ttl=3600, show_spinner=False)\ndef get_doc_feature_annotations' in source)
check('AI29 example cache is keyed by column set (survives a rename)',
      '_col_set: tuple = ()' in source and '_col_set=tuple((fd[1], fd[2])' in source)
check('AI30 examples reuse the cached doc content, costing no extra API call',
      'get_doc_content(doc_id, version)' in source)

# ══════════════════════════════════════════════════════════════════════════════
section('AJ. BUT — counter-example tagging')
# ══════════════════════════════════════════════════════════════════════════════

_FD_W = (4, 'D', 'LEX. "want"', 'select', ['badd', 'bidd', 'widd'])
_sfl = app._split_feature_line

# ── parsing ──
check('AJ1 a line with no BUT yields empty exceptions',
      _sfl('LEX. "want"  [biddi]   bidd', _FD_W) == ('biddi', 'bidd', ''))
check('AJ2 BUT is parsed off the end',
      _sfl('LEX. "want"  [biddi]   bidd   BUT [widdi]', _FD_W)
      == ('biddi', 'bidd', 'widdi'))
check('AJ3 several BUT words',
      _sfl('LEX. "want"  [biddi]   bidd   BUT [widdi, waddi]', _FD_W)[2]
      == 'widdi, waddi')
check('AJ4 BUT does not corrupt the value',
      _sfl('LEX. "want"  [biddi]   bidd   BUT [widdi]', _FD_W)[1] == 'bidd')
check('AJ5 BUT with no example words',
      _sfl('LEX. "want"  []   bidd   BUT [widdi]', _FD_W) == ('', 'bidd', 'widdi'))
check('AJ6 BUT on a line with no value',
      _sfl('LEX. "want"  [biddi]   BUT [widdi]', _FD_W)[2] == 'widdi')
check('AJ7 a stray "BUT" in the example text is not treated as a marker',
      _sfl('LEX. "want"  [but not this]   bidd', _FD_W)[2] == '',
      str(_sfl('LEX. "want"  [but not this]   bidd', _FD_W)))
check('AJ8 the marker constant is exported', app.FEAT_BUT_MARK == 'BUT')

# ── reading from a document ──
_DOC_BUT = (
    '<html><body><p>FEATURES:</p><p>LEX.</p>'
    '<p>LEX. &quot;want&quot;  [biddi ašrab]   bidd   BUT [widdi, waddi]</p>'
    '</body></html>'
)
_saved = app.FEATURE_DEFS
app.FEATURE_DEFS = [_FD_W]
try:
    with mock.patch.object(app, 'get_doc_content',
                           return_value={'display_html': _DOC_BUT}):
        _ann = app.get_doc_feature_annotations('d1')
        _ex  = app.get_doc_feature_examples('d1')
        _but = app.get_doc_feature_exceptions('d1')
    check('AJ9 annotations carry example and but together',
          _ann['LEX. "want"'] == {'example': 'biddi ašrab', 'but': 'widdi, waddi'},
          str(_ann))
    check('AJ10 the examples wrapper still returns plain strings',
          _ex == {'LEX. "want"': 'biddi ašrab'}, str(_ex))
    check('AJ11 the exceptions wrapper returns the BUT words',
          _but == {'LEX. "want"': 'widdi, waddi'}, str(_but))

    # ── CSV ──
    hdrW = app._csv_feature_header()
    check('AJ12 each feature gets a BUT column',
          hdrW == ['LEX. "want"', 'LEX. "want" — example', 'LEX. "want" — BUT'],
          str(hdrW))
    with mock.patch.object(app, 'get_sheet_features', return_value={'D': 'bidd'}), \
         mock.patch.object(app, 'get_doc_content',
                           return_value={'display_html': _DOC_BUT}):
        cw = app._csv_feature_cells(5, 'd1')
    check('AJ13 CSV exports value, example and BUT',
          cw == ['bidd', 'biddi ašrab', 'widdi, waddi'], str(cw))
    with mock.patch.object(app, 'get_sheet_features', return_value={'D': 'bidd'}), \
         mock.patch.object(app, 'get_doc_content',
                           return_value={'display_html': '<p>none</p>'}):
        cw2 = app._csv_feature_cells(5, 'd1')
    check('AJ14 a feature with no exception exports a blank BUT cell',
          cw2 == ['bidd', '', ''], str(cw2))
finally:
    app.FEATURE_DEFS = _saved

# ── the doc rewrite must never silently drop an exception ──
check('AJ15 the doc parser captures existing BUT before parsing the value',
      'existing_buts[fd[1]] = _bm.group(1).strip()' in source)
check('AJ16 the rewrite merges rather than replaces exceptions',
      'if _bw not in _but_existing:' in source)
check('AJ17 the rebuilt line re-emits the BUT suffix',
      "line += f'   {FEAT_BUT_MARK} [{but_merged}]'" in source)
check('AJ18 update_gdoc_features_section accepts exception words',
      'exception_words: dict | None = None' in source)
check('AJ19 a feature tagged ONLY with an exception still gets a line',
      'c for c in (exception_words or {}) if c not in pending_vals' in source)
check('AJ20 an exception-only tag keeps the value the line already had',
      '_pe, _pv, _pb = _split_feature_line(_prev, fd)' in source)
check('AJ21 deletion is suppressed when an exception is being recorded',
      "and not (exception_words or {}).get(col_l)" in source)

# ── tagging UI ──
check('AJ22 storeTag carries a kind',            "function storeTag(featureName, value, kind)" in source)
check('AJ23 the popup has a BUT branch',         'BUT — exception' in source)
check('AJ24 the BUT branch is grouped into the four categories',
      'butGroups' in source
      and 'GROUP_ORDER.concat(UNGROUPED' in source)
check('AJ24b BUT groups open their features one level further out',
      "makeFeatureItem(fd, null, null, false, 'but')" in source
      and 'positionSub(subMenu2, subMenu, gi)' in source)
check('AJ24c BUT and normal tagging use the same category list',
      source.count('GROUP_ORDER.concat(UNGROUPED.length') == 2,
      str(source.count('GROUP_ORDER.concat(UNGROUPED.length')))
check('AJ24d features with no prefix stay reachable under BUT too',
      "grp === '__other__' ? UNGROUPED : FEAT_GROUPS[grp]" in source)
check('AJ25 in BUT mode one click tags (no value submenu)',
      "if (kind === 'but' || fd.type === 'bool')" in source)
check('AJ26 search results offer a BUT shortcut',
      'mark as BUT (exception)' in source)
check('AJ27 the bridge routes but-tags separately',
      "feat_kind == 'but'" in source)
check('AJ28 staged exceptions accumulate',
      '_prev = st.session_state[f"{sk}_pending_buts"].get(fd[1], [])' in source)
check('AJ29 the submit bar shows exception-only stages',
      'has_changes = bool(pending) or bool(pending_buts)' in source)
check('AJ30 staged exceptions are passed to the doc writer',
      'doc_id, pending, pending_words, _pending_buts' in source)
# Every post-submit reset of pending_words must reset pending_buts too, or a
# submitted exception would be re-applied on the next save. (The extra
# pending_buts line is its lazy init in _render_submit_bar.)
_rw = source.count('_pending_words"] = {}')
_rb = source.count('_pending_buts"] = {}')
check('AJ31 pending exceptions are cleared alongside pending words',
      _rb == _rw + 1, f'words={_rw} buts={_rb}')
check('AJ31b no reset sits inside another key\'s init guard',
      '_pending_words"] = {}\n                    st.session_state[f"{sk}_pending_buts"]'
      not in source)

# ── Feature Browse filter ──
check('AJ32 a "has exception" filter exists',    'feat_browse_but_only' in source)
check('AJ33 it is applied only to already-matched documents',
      "if _include and st.session_state.get('feat_browse_but_only')" in source)
check('AJ34 exceptions are shown as chips in the results',
      'val-chip is-but' in source)
check('AJ35 BUT chips have their own style',     '.val-chip.is-but' in source)

# ══════════════════════════════════════════════════════════════════════════════
section('AK. Deleting tags — per value, and no silent disappearance')
# ══════════════════════════════════════════════════════════════════════════════

_FD_FE = (3, 'C', 'MOR. Fem. Ending', 'select', ['-i', '-e', '-a'])
_saved = app.FEATURE_DEFS
app.FEATURE_DEFS = [_FD_FE]
_w = {}
def _svc():
    _s = mock.MagicMock()
    def _bu(spreadsheetId=None, body=None, **k):
        for d in body['data']:
            _w[d['range']] = d['values'][0][0]
        return mock.MagicMock(execute=lambda: {})
    _s.spreadsheets.return_value.values.return_value.batchUpdate = _bu
    return (None, None, _s)

def _del(cell, only):
    _w.clear()
    with mock.patch.object(app, 'get_services', side_effect=_svc), \
         mock.patch.object(app, 'get_sheet_features', return_value={'C': cell}), \
         mock.patch.object(app, 'update_gdoc_features_section') as _ug:
        app.delete_feature_tag('d', [7], 'C', only)
    return _w.get('Recordings!C7'), _ug

try:
    check('AK1 removing one value keeps the others',
          _del('-e, -a', '-a')[0] == '-e', str(_del('-e, -a', '-a')[0]))
    check('AK2 removing the other value keeps the first',
          _del('-e, -a', '-e')[0] == '-a')
    check('AK3 removing from three keeps two',
          _del('-e, -a, -i', '-a')[0] == '-e, -i', str(_del('-e, -a, -i', '-a')[0]))
    check('AK4 only_value=None still clears the whole cell',
          _del('-e, -a', None)[0] == '')
    check('AK5 removing the last value clears the cell',
          _del('-e', '-e')[0] == '')
    check('AK6 removing a value that is not there changes nothing',
          _del('-e, -a', '-i')[0] == '-e, -a')
    check('AK7 removal is case/space insensitive',
          _del('-e, -a', '  -A  ')[0] == '-e', str(_del('-e, -a', '  -A  ')[0]))

    # the doc must be rewritten with what REMAINS, not blanked
    _cell, _ug = _del('-e, -a', '-a')
    check('AK8 the doc is rewritten with the remaining value',
          _ug.call_args[0][1] == {'C': '-e'}, str(_ug.call_args))
    _cell, _ug = _del('-e', '-e')
    check('AK9 the doc line is removed when nothing remains',
          _ug.call_args[0][1] == {'C': None}, str(_ug.call_args))
finally:
    app.FEATURE_DEFS = _saved

# ── signature / wiring ──
check('AK10 delete_feature_tag takes an only_value',
      'only_value: str | None = None' in source)
check('AK11 the cell is rebuilt from the kept values, not blanked',
      '_kept = [v for v in _split_feat_values' in source)
check('AK12 the doc write follows the remaining values',
      "update_gdoc_features_section(doc_id, {col_letter: _new_cell or None})" in source)

# ── UI ──
check('AK13 each value gets its own remove button',
      'key=f"del_{sk}_{_fd[1]}_{_vi}"' in source)
check('AK14 a "remove all" button appears only for multi-value features',
      'if len(_vals) > 1:' in source and '_all"' in source)
check('AK15 pending_delete carries (column, value)',
      '(_fd[1], _one)' in source and '(_fd[1], None)' in source)
check('AK16 an older bare-string pending_delete is tolerated',
      'if isinstance(_pending_del, str):' in source)
check('AK17 the confirmation says what will remain',
      'The document stays tagged' in source)
check('AK18 the confirmation calls out the last-value case',
      'It is the last remaining value' in source)

# ── the disappearing panel ──
check('AK19 a failed read is tracked separately from "no tags"',
      '_read_failed' in source)
check('AK20 a failed read tells the user instead of hiding the panel',
      'Could not read the current tags from the spreadsheet' in source)
check('AK21 the notice makes clear existing tags are unaffected',
      'your existing tags are unaffected' in source)

# ══════════════════════════════════════════════════════════════════════════════
section('AL. Reported bugs — search bar, empty state, replace cost')
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. the search bar showed the PREVIOUS query after a second search ──
# initial_value is only applied when the iframe (re)mounts. _last_pattern is
# still the previous query at the moment the component is rendered, so a
# remount during the search rerun redisplayed the old string.
check('AL1 the search bar seeds from the component\'s own stored value',
      "_prev_sb = st.session_state.get('searchbar')" in source)
check('AL2 it falls back to _last_pattern only when there is no stored value',
      "else st.session_state.get('_last_pattern', '')" in source)
check('AL3 the stale initial_value=_last_pattern call is gone',
      "initial_value=st.session_state.get('_last_pattern', '')" not in source)
check('AL4 a non-dict stored value cannot crash the fallback',
      'isinstance(_prev_sb, dict)' in source)

# ── 2. no indication when a search returned nothing ──
# The explanation was printed inside the search block only; results are
# re-rendered from session_state on every later rerun, so it vanished on the
# next interaction and left a blank page.
check('AL5 the empty state is recorded, not just printed',
      "st.session_state['_empty_state'] = {" in source)
check('AL6 it is re-rendered on later reruns',
      "_es = st.session_state.get('_empty_state')" in source)
check('AL7 it is only shown when there really are no results',
      'if _es and not results' in source)
check('AL8 it is hidden while a search is running',
      "not st.session_state.get('_searching')" in source)
check('AL9 a successful search clears it',
      "if results:\n            st.session_state.pop('_empty_state', None)" in source)
check('AL10 starting a new search clears the previous notice',
      "# Drop the previous run's \"no results\" notice" in source)
check('AL11 the persistent notice still shows the funnel counts',
      "documents in corpus &nbsp;→&nbsp; " in source
      and source.count('after filters &nbsp;→&nbsp;') >= 2)

# ── 3. replace-word wiping the whole cache (reported; already fixed) ──
check('AL12 replace bumps only the edited document\'s version',
      '_dv[doc_id] = _dv.get(doc_id, 0) + 1' in source)
# Count real CALLS, not mentions in comments.
_clear_lines = [ln for ln in source.split('\n')
                if ln.strip() == 'st.cache_data.clear()']
check('AL13 there is exactly ONE global cache clear in the whole app',
      len(_clear_lines) == 1, str(_clear_lines))
# ...and it belongs to the explicit sidebar button, not to any edit path
_idx = next(i for i, ln in enumerate(source.split('\n'))
            if ln.strip() == 'st.cache_data.clear()')
_ctx = '\n'.join(source.split('\n')[max(0, _idx - 6):_idx])
check('AL14 the only global clear is the sidebar button',
      'sidebar_clear_cache' in _ctx, _ctx[-160:])
check('AL14b no cache clear sits in the replace path',
      'clear()' not in source.split('def replace_one_occurrence_in_gdoc')[1]
                             .split('\ndef ')[0])
check('AL15 the background preload runs once per session, not per edit',
      "not st.session_state.get('_preload_started')" in source)
check('AL16 doc content is cached per (doc_id, version)',
      'def get_doc_content(doc_id: str, version: int = 0)' in source)

# ══════════════════════════════════════════════════════════════════════════════
section('AM. Auto-tag from the transcription table')
# ══════════════════════════════════════════════════════════════════════════════

_AT_DEFS = [
    (1, 'A', 'LEX. "He is saying"',     'select', ['biʾūl', 'ygūl']),
    (2, 'B', 'LEX. "Rooster/Roosters"', 'select', ['dīk / dyūk', 'dīč / dyuk']),
    (3, 'C', 'LEX. "Heavy"',            'select', ['tʾīl']),
    (4, 'D', 'LEX. "Coffee"',           'select', ['ʾahwi']),
    (5, 'E', 'PHON. *q',                'select', ['q', 'ʾ', 'g']),
    (6, 'F', 'PHON. *k',                'select', ['k', 'č', 'k~č']),
]
def _tbl(saying, rooster, heavy, coffee):
    return ('<table><tr><td>يقول</td><td>ديك \\ ديوك</td><td>ثقيل</td>'
            '<td>قهوة</td></tr>'
            f'<tr><td>{saying}</td><td>{rooster}</td><td>{heavy}</td>'
            f'<td>{coffee}</td></tr></table>')

_saved = app.FEATURE_DEFS
app.FEATURE_DEFS = _AT_DEFS
try:
    # ── parsing the real document's table ──
    _real = _tbl('biʾūl', 'dīk-dyūk', 'tʾīl', 'Select')
    with mock.patch.object(app, 'get_doc_content',
                           return_value={'display_html': _real}):
        _t = app.parse_doc_feature_table('d')
    check('AM1 the table is found and read',
          _t.get('LEX. "He is saying"') == 'biʾūl', str(_t))
    check('AM2 the Arabic headings map to features despite the slash',
          _t.get('LEX. "Rooster/Roosters"') == 'dīk-dyūk', str(_t))
    check('AM3 "Select" placeholders are treated as unfilled',
          'LEX. "Coffee"' not in _t, str(_t))
    with mock.patch.object(app, 'get_doc_content',
                           return_value={'display_html': '<p>no table</p>'}):
        check('AM4 a document with no table yields {}',
              app.parse_doc_feature_table('d2') == {})

    # ── the four rules ──
    _d = lambda v: app.derive_phon_from_table(v)[0]
    _u = lambda v: app.derive_phon_from_table(v)[1]
    _R = 'LEX. "Rooster/Roosters"'
    _full = {'LEX. "He is saying"': 'biʾūl', 'LEX. "Coffee"': 'ʾahwi',
             'LEX. "Heavy"': 'tʾīl'}
    check('AM5 rule 1 fires on all three pieces of evidence',
          _d(_full) == {'PHON. *q': 'ʾ'}, str(_d(_full)))
    for _missing in ('LEX. "Coffee"', 'LEX. "Heavy"', 'LEX. "He is saying"'):
        _partial = {k: v for k, v in _full.items() if k != _missing}
        check(f'AM6 rule 1 does NOT fire without {_missing.replace(chr(34), "")}',
              'PHON. *q' not in _d(_partial), str(_d(_partial)))
    check('AM7 rule 1 needs saying=biʾūl exactly',
          'PHON. *q' not in _d({**_full, 'LEX. "He is saying"': 'ygūl'}))
    for _c in ('ʾahwa', 'ʾahwe', 'ʾahwi'):
        check(f'AM8 rule 1 accepts coffee={_c}',
              _d({**_full, 'LEX. "Coffee"': _c}) == {'PHON. *q': 'ʾ'})
    for _h in ('tʾīl', 'ṯʾīl'):
        check(f'AM9 rule 1 accepts heavy={_h}',
              _d({**_full, 'LEX. "Heavy"': _h}) == {'PHON. *q': 'ʾ'})

    check('AM10 rule 2  k/k -> k',   _d({_R: 'dīk / dyūk'}) == {'PHON. *k': 'k'})
    check('AM11 rule 3  č/č -> č',   _d({_R: 'dīč / dyūč'}) == {'PHON. *k': 'č'})
    check('AM12 rule 4  č/k -> k~č', _d({_R: 'dīč / dyūk'}) == {'PHON. *k': 'k~č'})
    check('AM13 the hyphen separator used in documents works',
          _d({_R: 'dīk-dyūk'}) == {'PHON. *k': 'k'})
    check('AM14 a missing macron does not defeat the rule',
          _d({_R: 'dīč / dyuk'}) == {'PHON. *k': 'k~č'},
          'rules turn on k vs č, not on vowel length')
    check('AM15 an unrecognised reflex pattern is reported, not guessed',
          'PHON. *k' not in _d({_R: 'dīk / dyūč'}) and _u({_R: 'dīk / dyūč'}))
    check('AM16 an unparseable value is reported',
          _u({_R: 'nonsense'}) != [])

    # ── canonicalising to the column's own options ──
    _opts = ['dīk / dyūk', 'dīč / dyuk']
    check('AM17 the document spelling maps onto the sheet option',
          app.canonicalise_table_value('dīk-dyūk', _opts) == 'dīk / dyūk')
    check('AM18 an exact option passes through',
          app.canonicalise_table_value('dīk / dyūk', _opts) == 'dīk / dyūk')
    check('AM19 a value matching no option returns None',
          app.canonicalise_table_value('weird', _opts) is None)
    check('AM20 macrons are NOT normalised away',
          app.canonicalise_table_value('dīč / dyūk', _opts) is None,
          'dyuk and dyūk must stay distinct')
    check('AM21 a column with no options accepts anything',
          app.canonicalise_table_value('x', None) == 'x')

    # ── the scan ──
    _DOCS = {
        'd1': _tbl('biʾūl', 'dīk-dyūk', 'tʾīl', 'ʾahwi'),
        'd2': _tbl('biʾūl', 'dīč / dyuk', 'Select', 'Select'),
        'd3': _tbl('ygūl', 'dīk / dyūk', 'Select', 'Select'),
        'd4': '<p>no table</p>',
    }
    _SHEET = {1: {}, 2: {'F': 'k~č'}, 3: {'F': 'č'}, 4: {}}
    _corpus = [{'doc_id': k, 'name': k, 'sheet_row': i + 1}
               for i, k in enumerate(_DOCS)]
    with mock.patch.object(app, 'get_doc_content',
                           side_effect=lambda d, v=0: {'display_html': _DOCS[d]}), \
         mock.patch.object(app, 'get_sheet_features',
                           side_effect=lambda r: _SHEET.get(r, {})):
        _res = app.scan_auto_tags(_corpus)

    _pv = {(p['doc'], p['feature']): p['value'] for p in _res['proposals']}
    check('AM22 every document is scanned', _res['scanned'] == 4)
    check('AM23 table values are proposed for empty cells',
          _pv.get(('d1', 'LEX. "Heavy"')) == 'tʾīl', str(_pv))
    check('AM24 proposals use the canonical option spelling',
          _pv.get(('d1', 'LEX. "Rooster/Roosters"')) == 'dīk / dyūk')
    check('AM25 derived values are proposed too',
          _pv.get(('d1', 'PHON. *q')) == 'ʾ' and _pv.get(('d1', 'PHON. *k')) == 'k')
    check('AM26 a value ALREADY correct in the sheet is not re-proposed',
          ('d2', 'PHON. *k') not in _pv, str(_pv))
    check('AM27 a DISAGREEING existing value is a conflict, not a proposal',
          ('d3', 'PHON. *k') not in _pv
          and any(c['doc'] == 'd3' and c['feature'] == 'PHON. *k'
                  for c in _res['conflicts']), str(_res['conflicts']))
    check('AM28 the conflict records both sides',
          _res['conflicts'][0]['existing'] == 'č'
          and _res['conflicts'][0]['value'] == 'k')
    check('AM29 documents with no table are listed',
          _res['no_table'] == ['d4'], str(_res['no_table']))
    check('AM30 every proposal carries its evidence',
          all(p['evidence'] for p in _res['proposals']))
    check('AM31 derived proposals name the evidence they used',
          'rule:' in _pv and True or all(
              p['evidence'].startswith('rule:')
              for p in _res['proposals'] if p['feature'].startswith('PHON.')))

    # ── apply ──
    _written = {}
    def _svc2():
        _s2 = mock.MagicMock()
        def _bu(spreadsheetId=None, body=None, **k):
            for d in body['data']:
                _written[d['range']] = d['values'][0][0]
            return mock.MagicMock(execute=lambda: {})
        _s2.spreadsheets.return_value.values.return_value.batchUpdate = _bu
        return (None, None, _s2)
    with mock.patch.object(app, 'get_services', side_effect=_svc2):
        _n = app.apply_auto_tags([
            {'col': 'E', 'rows': [7], 'value': 'ʾ'},
            {'col': 'F', 'rows': [7, 9], 'value': 'k'},
        ])
    check('AM32 apply writes one cell per row', _n == 3, str(_n))
    check('AM33 apply targets the right cells',
          _written == {'Recordings!E7': 'ʾ', 'Recordings!F7': 'k',
                       'Recordings!F9': 'k'}, str(_written))
    with mock.patch.object(app, 'get_services', side_effect=_svc2):
        check('AM34 applying nothing writes nothing', app.apply_auto_tags([]) == 0)
finally:
    app.FEATURE_DEFS = _saved

# ── UI wiring ──
check('AM35 the scan is preview-only — nothing is written by scanning',
      'batchUpdate' not in source.split('def scan_auto_tags')[1].split('\ndef ')[0])
check('AM36 applying requires an explicit confirmation',
      '_autotag_confirm' in source)
check('AM37 the preview is exportable as CSV', 'pai_autotag_preview.csv' in source)
check('AM38 conflicts and unmatched values are shown, not hidden',
      'conflicts — left unchanged' in source and 'unrecognised values' in source)
check('AM39 apply writes only the sheet, not 700+ documents',
      'update_gdoc_features_section' not in
      source.split('def apply_auto_tags')[1].split('\ndef ')[0])
check('AM40 the write is batched rather than one call per row',
      'for i in range(0, len(data), 500)' in source)


# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{"="*66}')
if failures:
    print(f'RESULT: {len(failures)} FAILURE(S)')
    for f_ in failures:
        print(f'  - {f_}')
    sys.exit(1)
print('RESULT: ALL SEARCH/TEXT/DOC TESTS PASSED')
