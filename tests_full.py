"""
Full regression test suite for pai-search/app.py
Pure-Python, no Streamlit runtime, no Google API credentials.
Run: python tests_full.py
Exit 0 = all passed, non-zero = failures.
"""
import sys, types, json, re, unicodedata
import unittest.mock as mock

# ════════════════════════════════════════════════════════════════════════════
# 1. Stub streamlit BEFORE importing app
# ════════════════════════════════════════════════════════════════════════════

st_stub = types.ModuleType('streamlit')

# cache_data / cache_resource — pass-through decorator with .clear() attribute
def _cache_dec(*_a, **_kw):
    def _dec(fn):
        fn.clear = lambda: None
        return fn
    if _a and callable(_a[0]):          # @st.cache_data without parens
        _dec(_a[0]); return _a[0]
    return _dec
_cache_dec.clear = lambda: None
st_stub.cache_data     = _cache_dec
st_stub.cache_resource = _cache_dec

# secrets as a dict-like object with valid service-account JSON
_FAKE_SA_JSON = json.dumps({
    "type": "service_account",
    "project_id": "fake-proj",
    "private_key_id": "a" * 40,
    "private_key": "",          # empty — Credentials mock won't actually use it
    "client_email": "fake@fake.iam.gserviceaccount.com",
    "client_id": "000",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/fake",
})

class _SecretsDict(dict):
    def __getitem__(self, k):
        return {"GOOGLE_SERVICE_ACCOUNT": _FAKE_SA_JSON,
                "SPREADSHEET_ID": "fake_sheet_id"}.get(k, '')
    def __contains__(self, k):
        return k in ("GOOGLE_SERVICE_ACCOUNT", "SPREADSHEET_ID")

st_stub.secrets       = _SecretsDict()
st_stub.session_state = {}

# st.columns([1, 5, 1]) → list of N MagicMocks  (the app unpacks them)
def _fake_columns(*args, **kwargs):
    spec = args[0] if args else 1
    n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
    return [mock.MagicMock() for _ in range(n)]

# Context managers (sidebar, expander, spinner) must return objects that work as `with`
def _ctx_mgr(*a, **kw):
    m = mock.MagicMock()
    m.__enter__ = lambda s: mock.MagicMock()
    m.__exit__  = lambda s, *a: False
    return m

for _a in ['error','warning','info','success','write','markdown',
           'button','checkbox','text_input','download_button',
           'multiselect','selectbox','radio','progress',
           'caption','rerun','set_page_config','title','stop']:
    setattr(st_stub, _a, mock.MagicMock())

st_stub.columns  = _fake_columns
st_stub.expander = _ctx_mgr
st_stub.spinner  = _ctx_mgr
st_stub.sidebar  = mock.MagicMock()
st_stub.sidebar.__enter__ = lambda s: mock.MagicMock()
st_stub.sidebar.__exit__  = lambda s, *a: False

sys.modules['streamlit'] = st_stub

# streamlit.components.v1
_comp_mod     = types.ModuleType('streamlit.components')
_comp_v1_mod  = types.ModuleType('streamlit.components.v1')
_comp_v1_mod.html               = mock.MagicMock()
_comp_v1_mod.declare_component  = mock.MagicMock(return_value=mock.MagicMock(return_value=None))
sys.modules['streamlit.components']    = _comp_mod
sys.modules['streamlit.components.v1'] = _comp_v1_mod

# ════════════════════════════════════════════════════════════════════════════
# 2. Stub Google libraries — MUST link parent to child properly
# ════════════════════════════════════════════════════════════════════════════

_mock_creds = mock.MagicMock()
_mock_creds.from_service_account_info = mock.MagicMock(return_value=mock.MagicMock())

_g_mod       = types.ModuleType('google')
_g_oauth2    = types.ModuleType('google.oauth2')
_g_sa        = types.ModuleType('google.oauth2.service_account')
_g_sa.Credentials = _mock_creds
_g_oauth2.service_account = _g_sa
_g_mod.oauth2 = _g_oauth2

_gapi        = types.ModuleType('googleapiclient')
_gapi_disc   = types.ModuleType('googleapiclient.discovery')
_gapi_disc.build = mock.MagicMock(return_value=mock.MagicMock())
_gapi_err    = types.ModuleType('googleapiclient.errors')
_gapi_err.HttpError = type('HttpError', (Exception,), {})
_gapi_http   = types.ModuleType('googleapiclient.http')
_gapi_http.MediaIoBaseDownload = mock.MagicMock()
_gapi.discovery = _gapi_disc
_gapi.errors    = _gapi_err
_gapi.http      = _gapi_http

sys.modules.update({
    'google':                          _g_mod,
    'google.oauth2':                   _g_oauth2,
    'google.oauth2.service_account':   _g_sa,
    'googleapiclient':                 _gapi,
    'googleapiclient.discovery':       _gapi_disc,
    'googleapiclient.errors':          _gapi_err,
    'googleapiclient.http':            _gapi_http,
})

# ════════════════════════════════════════════════════════════════════════════
# 3. Load app.py
# ════════════════════════════════════════════════════════════════════════════

sys.path.insert(0, '/sessions/laughing-eager-ramanujan/mnt/pai-search')

import importlib.util as _ilu

_spec       = _ilu.spec_from_file_location(
                'app', '/sessions/laughing-eager-ramanujan/mnt/pai-search/app.py')
app_module  = _ilu.module_from_spec(_spec)
sys.modules['app'] = app_module

load_error = None
try:
    _spec.loader.exec_module(app_module)
except Exception as _e:
    load_error = _e

app = app_module

# ════════════════════════════════════════════════════════════════════════════
# Test helpers
# ════════════════════════════════════════════════════════════════════════════

PASS     = 'PASS'
FAIL     = 'FAIL'
failures = []

def check(desc, condition, detail=''):
    if condition:
        print(f'  [PASS] {desc}')
    else:
        msg = f'  [FAIL] {desc}'
        if detail:
            msg += f'\n         => {detail}'
        print(msg)
        failures.append(desc)

def section(title):
    print(f'\n{"=" * 60}')
    print(f'  {title}')
    print('=' * 60)

source = open('/sessions/laughing-eager-ramanujan/mnt/pai-search/app.py').read()

# ════════════════════════════════════════════════════════════════════════════
# 0. Sanity: did the module load?
# ════════════════════════════════════════════════════════════════════════════
section('0. Module import')
check('app.py loaded without crash',
      load_error is None,
      str(load_error) if load_error else '')
check('FEAT_PREFIXES attribute present',  hasattr(app, 'FEAT_PREFIXES'))
check('get_feature_defs callable',        hasattr(app, 'get_feature_defs'))
if load_error:
    print('\n[FAIL] Cannot continue — module did not load.')
    sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
# 1. FEAT_PREFIXES constant
# ════════════════════════════════════════════════════════════════════════════
section('1. FEAT_PREFIXES constant')

check('FEAT_PREFIXES has 4 entries',
      len(app.FEAT_PREFIXES) == 4, str(app.FEAT_PREFIXES))
check('Contains PHON.', 'PHON.' in app.FEAT_PREFIXES)
check('Contains MOR.',  'MOR.'  in app.FEAT_PREFIXES)
check('Contains SYN.',  'SYN.'  in app.FEAT_PREFIXES)
check('Contains LEX.',  'LEX.'  in app.FEAT_PREFIXES)


# ════════════════════════════════════════════════════════════════════════════
# 2. get_feature_defs() — prefix-based discovery logic
# ════════════════════════════════════════════════════════════════════════════
section('2. get_feature_defs() prefix-based discovery + type inference')

FAKE_HEADERS = [
    'Village',                      # metadata  -> excluded
    'PHON. aCC > iCC',              # in FEATURE_HEADER_DEFS -> bool
    'PHON. vocal harmonizing',      # NOT in FEATURE_HEADER_DEFS -> infer from values
    'MOR. Fem. Ending',             # in FEATURE_HEADER_DEFS -> select
    'MOR. brand new select',        # NOT in list -> infer: select (has non-bool values)
    'MOR. brand new bool',          # NOT in list -> infer: bool (only +/- values)
    'SYN. Past Con. Mod.',          # in list -> select
    'LEX. "now"',                   # in list -> select
    'vocal harmonizing',            # non-prefix -> excluded
]

# _infer_column_types is now a separate cached function.
# We patch it directly so the test controls the inferred types
# without needing a real Sheets API call.
_fake_inferred = {
    'PHON. vocal harmonizing': ('bool', None),           # only +/- in sheet
    'MOR. brand new select':   ('select', ['f', 'm', 'pl', 'sg']),  # real opts
    'MOR. brand new bool':     ('bool', None),           # only + in sheet
}

with (mock.patch.object(app, '_get_sheet_headers', return_value=FAKE_HEADERS),
      mock.patch.object(app, 'get_extra_feature_defs', return_value=[]),
      mock.patch.object(app, '_infer_column_types',
                        return_value=_fake_inferred)):
    result = app.get_feature_defs()

result_names = [fd[2] for fd in result]
result_types = {fd[2]: fd[3] for fd in result}
result_opts  = {fd[2]: fd[4] for fd in result}

check('Only prefix-matching columns returned (7)',
      len(result) == 7, f'got {len(result)}: {result_names}')
check('Non-prefix "vocal harmonizing" excluded',  'vocal harmonizing'  not in result_names)
check('"Village" excluded',                         'Village'           not in result_names)
check('PHON. aCC > iCC included',                   'PHON. aCC > iCC'  in result_names)
check('PHON. vocal harmonizing included',
      'PHON. vocal harmonizing' in result_names)
check('MOR. Fem. Ending type=select (from FEATURE_HEADER_DEFS)',
      result_types.get('MOR. Fem. Ending') == 'select', str(result_types))
check('PHON. aCC > iCC is bool (from FEATURE_HEADER_DEFS)',
      result_types.get('PHON. aCC > iCC') == 'bool', str(result_types))
check('LEX. "now" type=select (from FEATURE_HEADER_DEFS)',
      result_types.get('LEX. "now"') == 'select', str(result_types))

# Inference tests
check('PHON. vocal harmonizing inferred as bool (only +/- values in sheet)',
      result_types.get('PHON. vocal harmonizing') == 'bool',
      str(result_types))
check('MOR. brand new select inferred as select (real option values in sheet)',
      result_types.get('MOR. brand new select') == 'select',
      str(result_types))
check('MOR. brand new select options = [f, m, pl, sg]',
      result_opts.get('MOR. brand new select') == ['f', 'm', 'pl', 'sg'],
      str(result_opts.get('MOR. brand new select')))
check('MOR. brand new bool inferred as bool (only +/- values)',
      result_types.get('MOR. brand new bool') == 'bool',
      str(result_types))
check('Column order mirrors sheet order',
      result_names == ['PHON. aCC > iCC', 'PHON. vocal harmonizing',
                       'MOR. Fem. Ending', 'MOR. brand new select',
                       'MOR. brand new bool', 'SYN. Past Con. Mod.',
                       'LEX. "now"'],
      str(result_names))


# ════════════════════════════════════════════════════════════════════════════
# 3-4. Removed sidebar controls
# ════════════════════════════════════════════════════════════════════════════
section('3-4. Removed "Feature columns" sidebar controls')

# The sidebar "Feature columns" panel ("Add a feature column" + "Debug:
# inspect corpus row") was removed once prefix-based discovery made manual
# registration redundant. The functions behind it went with it. These checks
# assert the removal is complete, so no half-deleted UI can creep back.
for _gone in ['add_app_feature_def', 'remove_app_feature_def',
              '_ensure_app_features_sheet', 'get_unclaimed_headers',
              'get_unresolved_features', 'debug_corpus_load']:
    check(f'{_gone}() removed', not hasattr(app, _gone))

check('the sidebar heading is gone',        'Feature columns' not in source)
check('the add-column expander is gone',    'Add a feature column' not in source)
check('the debug expander is gone',         'Debug: inspect corpus row' not in source)
check('no dangling references remain',
      not any(n in source for n in
              ['add_app_feature_def', 'get_unclaimed_headers',
               'get_unresolved_features', 'debug_corpus_load']))

# What must SURVIVE the removal:
check('get_extra_feature_defs() kept — still feeds type/options',
      hasattr(app, 'get_extra_feature_defs'))
check('AppFeatureDefs is still read by get_feature_defs',
      'get_extra_feature_defs()' in source)
check('FEATURE_DEFS is still built at module load',
      hasattr(app, 'FEATURE_DEFS'))
check('_FEAT_BY_NAME lookup still built',   hasattr(app, '_FEAT_BY_NAME'))
check('the load-error guard survived',      '_FEATURE_DEFS_LOAD_ERROR' in source)
check('"Clear cache & reload" survived',    'Clear cache & reload' in source)
check('"Reload corpus cache" survived',     'Reload corpus cache' in source)


# ════════════════════════════════════════════════════════════════════════════
# 5. inject_interaction_js() — grouped 3-level menu
# ════════════════════════════════════════════════════════════════════════════
section('5. inject_interaction_js() -- grouped 3-level JS menu')

fake_defs = [
    (1, 'B', 'PHON. aCC > iCC',        'bool',   None),
    (2, 'C', 'PHON. vocal harmonizing', 'bool',   None),
    (3, 'D', 'MOR. Fem. Ending',        'select', ['-i', '-e', '-a']),
    (4, 'E', 'LEX. now',                'select', ['hallaq', 'issa']),
]
with mock.patch.object(app, 'FEATURE_DEFS', fake_defs):
    html_out = app.inject_interaction_js('<html><body>hello</body></html>', 'DOC123')

check('#pai-ctx-sub2 div present',        'id="pai-ctx-sub2"' in html_out)
check('GROUP_ORDER array in JS',           'GROUP_ORDER' in html_out)
check('FEAT_GROUPS object in JS',          'FEAT_GROUPS' in html_out)
check('hideSub2() function present',       'hideSub2' in html_out)
check('subMenu2 variable/usage in JS',     'subMenu2' in html_out)
check('Feature name "PHON. aCC > iCC" in output',
      'PHON. aCC > iCC' in html_out)
check('storeTag(fd.name, true) for bool branch',
      'storeTag(fd.name, true)' in html_out)
check('storeTag(fd.name, opt) for select branch',
      'storeTag(fd.name, opt)' in html_out)
check('Old flat checkbox icon builder removed',
      '<span class="ctx-icon">&#9744;</span>' not in html_out
      and '<span class="ctx-icon">☐</span>' not in html_out)


# ════════════════════════════════════════════════════════════════════════════
# 6. FEATURES block reconstruction with group-section headers
# ════════════════════════════════════════════════════════════════════════════
section('6. FEATURES block reconstruction -- section headers')

def _sim_block(feature_defs, updated_lines):
    """Mirror the reconstruction logic from update_gdoc_features_section."""
    lines = ['FEATURES:']
    emitted = set()
    for fd in feature_defs:
        if fd[2] not in updated_lines:
            continue
        prefix = next((p for p in app.FEAT_PREFIXES if fd[2].startswith(p)), None)
        if prefix and prefix not in emitted:
            lines.append(prefix)
            emitted.add(prefix)
        lines.append(updated_lines[fd[2]])
    return '\n'.join(lines) + '\n'

fake_fd2 = [
    (1,'B','PHON. aCC > iCC',       'bool',  None),
    (2,'C','PHON. vocal harmonizing','bool',  None),
    (3,'D','MOR. Fem. Ending',       'select',['-i']),
    (4,'E','MOR. 3.f.sg pron.',      'bool',  None),
    (5,'F','LEX. now',               'select',['hallaq']),
]
updated2 = {
    'PHON. aCC > iCC':    'PHON. aCC > iCC  [baddi]   +',
    'MOR. Fem. Ending':   'MOR. Fem. Ending  [baddi]   -i',
    'MOR. 3.f.sg pron.':  'MOR. 3.f.sg pron.  [baddi]   +',
}

lines2 = _sim_block(fake_fd2, updated2).strip().split('\n')
check('Block starts with FEATURES:',               lines2[0] == 'FEATURES:', lines2[0])
check('PHON. header emitted before first feature',  lines2[1] == 'PHON.',    lines2[1])
check('First PHON. feature on line[2]',
      lines2[2] == 'PHON. aCC > iCC  [baddi]   +', lines2[2])
check('PHON. header emitted only once',             lines2.count('PHON.') == 1, str(lines2))
check('MOR. header before first MOR. feature',      lines2[3] == 'MOR.',     lines2[3])
check('MOR. header emitted only once',              lines2.count('MOR.') == 1,  str(lines2))
check('LEX. header NOT emitted (no LEX. content)',
      'LEX.' not in lines2, str(lines2))
check('Total 6 lines',
      len(lines2) == 6, f'{len(lines2)}: {lines2}')


# ════════════════════════════════════════════════════════════════════════════
# 7. FEATURES parser skips bare prefix lines (source check)
# ════════════════════════════════════════════════════════════════════════════
section('7. FEATURES parser skips bare prefix lines')

_guard_pos = source.find('if text.strip() in FEAT_PREFIXES:')
check('"if text.strip() in FEAT_PREFIXES:" guard present in source',
      _guard_pos != -1)
if _guard_pos != -1:
    snippet = source[_guard_pos: _guard_pos + 120]
    check('"continue" follows the guard within 120 chars',
          'continue' in snippet, snippet)


# ════════════════════════════════════════════════════════════════════════════
# 8. Selective CSV export
# ════════════════════════════════════════════════════════════════════════════
section('8. Selective CSV export -- checkboxes + comment + download button')

check('Checkbox key sel_{doc_id} in results loop',
      "key=f\"sel_{r['doc_id']}\"" in source)
check('Comment text_input key comment_{doc_id}',
      "key=f\"comment_{r['doc_id']}\"" in source)
check('_sel_ids set built from session_state',
      '_sel_ids' in source and "sel_{" in source)
check('Download-selected label contains _n_sel count',
      'Download selected ({_n_sel})' in source)
check('Selected CSV has Comment column',
      "'Comment'" in source or '"Comment"' in source)
check('st.columns([1, 20]) for checkbox+expander layout',
      'st.columns([1, 20])' in source)
check('if _is_sel: shows comment text_input',
      'if _is_sel:' in source)


# ════════════════════════════════════════════════════════════════════════════
# 9. Wildcard v / v-bar
# ════════════════════════════════════════════════════════════════════════════
section('9. Wildcard symbols: vowels + B (bilabial) + L (lamnr)')

check("ch == 'v' maps to _S in _pattern_char_to_regex",
      "ch == 'v'" in source)
check('v-bar uses unicodedata.category for peek-ahead',
      'unicodedata.category' in source and '_L' in source)
check('Legend pill shows <b>v</b>',   '<b>v</b>' in source)
check('Legend mentions long vowel',   'long vowel' in source)
check('BILABIALS set defined in source', 'BILABIALS' in source)
check('LAMNR set defined in source',    'LAMNR' in source)
check("'B' case in _pattern_char_to_regex",
      "ch == 'B'" in source)
check("'L' case in _pattern_char_to_regex",
      "ch == 'L'" in source)
check('Legend pill shows <b>B</b>',   '<b>B</b>' in source)
check('Legend pill shows <b>L</b>',   '<b>L</b>' in source)

try:
    rx_v  = app._pattern_char_to_regex('v')
    vbar  = 'v̄'
    rx_vl = app._tok_to_regex(vbar)
    check('_pattern_char_to_regex("v") returns _S (short vowel)',
          rx_v == app._S, f'got {rx_v!r}')
    check('_tok_to_regex("v+macron") returns _L (long vowel)',
          rx_vl == app._L, f'got {rx_vl!r}')

    rx_b = app._pattern_char_to_regex('B')
    rx_l = app._pattern_char_to_regex('L')
    check('_pattern_char_to_regex("B") returns _B',
          rx_b == app._B, f'got {rx_b!r}')
    check('_pattern_char_to_regex("L") returns _LAMNR',
          rx_l == app._LAMNR, f'got {rx_l!r}')

    # Functional: B matches bilabials
    import re as _re
    for ch_b in ('b', 'f', 'm'):
        check(f'B wildcard matches "{ch_b}"',
              bool(_re.fullmatch(rx_b, ch_b)), f'_B={rx_b!r}')
    # Functional: L matches lamnr members
    for ch_l in ('l', 'r', 'n', 'm'):
        check(f'L wildcard matches "{ch_l}"',
              bool(_re.fullmatch(rx_l, ch_l)), f'_LAMNR={rx_l!r}')
    # Negative: B should NOT match purely guttural consonants
    check('B wildcard does not match "q"',
          not bool(_re.fullmatch(rx_b, 'q')))
    check('L wildcard does not match "q"',
          not bool(_re.fullmatch(rx_l, 'q')))

except Exception as exc:
    check('Wildcard regex functions callable', False, str(exc))


# ════════════════════════════════════════════════════════════════════════════
# 10. Previous bugfixes still intact
# ════════════════════════════════════════════════════════════════════════════
section('10. Previous bugfixes still intact')

check('Stable expander key= present',
      "key=f\"res_exp_{r['doc_id']}\"" in source)
check('_features_version bump for cache-busting present',
      '_features_version' in source)
check('seen_doc_ids deduplication in search_by_name',
      'seen_doc_ids' in source)


# ════════════════════════════════════════════════════════════════════════════
# 11. searchbar/index.html — wildcard key labels
# ════════════════════════════════════════════════════════════════════════════
section('11. searchbar/index.html wildcard labels')

try:
    kb_src = open('/sessions/laughing-eager-ramanujan/mnt/pai-search/searchbar/index.html').read()
    check("Keyboard: 'v' wildcard key present",
          "ch:'v'" in kb_src or "ch:\"v\"" in kb_src)
    check("Keyboard: v-bar (long vowel) wildcard key present",
          'v̄' in kb_src)
    check("Keyboard: old 'S' key gone",
          "ch:'S'" not in kb_src and "ch:\"S\"" not in kb_src)
    check("Keyboard: 'B' bilabial wildcard key present",
          "ch:'B'" in kb_src or "ch:\"B\"" in kb_src)
    check("Keyboard: 'L' lamnr wildcard key present",
          "ch:'L'" in kb_src or "ch:\"L\"" in kb_src)
    check("Keyboard: 'L' key title says Laminal",
          'Laminal' in kb_src or 'laminal' in kb_src)
    check("Keyboard: 'B' key title says Bilabial",
          'Bilabial' in kb_src or 'bilabial' in kb_src)
except FileNotFoundError:
    check('searchbar/index.html found', False, 'file not found')


# ════════════════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════════════════
print(f'\n{"=" * 60}')
if failures:
    print(f'RESULT: {len(failures)} test(s) FAILED:')
    for f in failures:
        print(f'  [FAIL] {f}')
    sys.exit(1)
else:
    print('RESULT: ALL TESTS PASSED')
    sys.exit(0)
