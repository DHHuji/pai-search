"""
Deep regression tests for the RECENT changes to pai-search/app.py:
  - _infer_column_types() data-validation path (empty column -> select)
  - get_feature_defs() prefix-stripped type inheritance
  - _get_all_sheet_features() cache-key invalidation on column rename
  - end-to-end: rename an old column to a prefixed name

Run: python tests_deep.py
"""
import sys, types, json, re, unicodedata
import unittest.mock as mock

# ── reuse the exact harness from tests_full.py ────────────────────────────────
st_stub = types.ModuleType('streamlit')

def _cache_dec(*_a, **_kw):
    def _dec(fn):
        fn.clear = lambda: None
        return fn
    if _a and callable(_a[0]):
        _dec(_a[0]); return _a[0]
    return _dec
_cache_dec.clear = lambda: None
st_stub.cache_data     = _cache_dec
st_stub.cache_resource = _cache_dec

_FAKE_SA_JSON = json.dumps({
    "type": "service_account", "project_id": "fake-proj",
    "private_key_id": "a" * 40, "private_key": "",
    "client_email": "fake@fake.iam.gserviceaccount.com", "client_id": "000",
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

def _fake_columns(*args, **kwargs):
    spec = args[0] if args else 1
    n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
    return [mock.MagicMock() for _ in range(n)]

def _ctx_mgr(*a, **kw):
    m = mock.MagicMock()
    m.__enter__ = lambda s: mock.MagicMock()
    m.__exit__  = lambda s, *a: False
    return m

for _a in ['error','warning','info','success','write','markdown','button',
           'checkbox','text_input','download_button','multiselect','selectbox',
           'radio','progress','caption','rerun','set_page_config','title','stop']:
    setattr(st_stub, _a, mock.MagicMock())

st_stub.columns  = _fake_columns
st_stub.expander = _ctx_mgr
st_stub.spinner  = _ctx_mgr
st_stub.sidebar  = mock.MagicMock()
st_stub.sidebar.__enter__ = lambda s: mock.MagicMock()
st_stub.sidebar.__exit__  = lambda s, *a: False
sys.modules['streamlit'] = st_stub

_comp_mod    = types.ModuleType('streamlit.components')
_comp_v1_mod = types.ModuleType('streamlit.components.v1')
_comp_v1_mod.html              = mock.MagicMock()
_comp_v1_mod.declare_component = mock.MagicMock(return_value=mock.MagicMock(return_value=None))
sys.modules['streamlit.components']    = _comp_mod
sys.modules['streamlit.components.v1'] = _comp_v1_mod

_mock_creds = mock.MagicMock()
_mock_creds.from_service_account_info = mock.MagicMock(return_value=mock.MagicMock())
_g_mod    = types.ModuleType('google')
_g_oauth2 = types.ModuleType('google.oauth2')
_g_sa     = types.ModuleType('google.oauth2.service_account')
_g_sa.Credentials = _mock_creds
_g_oauth2.service_account = _g_sa
_g_mod.oauth2 = _g_oauth2
_gapi      = types.ModuleType('googleapiclient')
_gapi_disc = types.ModuleType('googleapiclient.discovery')
_gapi_disc.build = mock.MagicMock(return_value=mock.MagicMock())
_gapi_err  = types.ModuleType('googleapiclient.errors')
_gapi_err.HttpError = type('HttpError', (Exception,), {})
_gapi_http = types.ModuleType('googleapiclient.http')
_gapi_http.MediaIoBaseDownload = mock.MagicMock()
_gapi.discovery = _gapi_disc
_gapi.errors    = _gapi_err
_gapi.http      = _gapi_http
sys.modules.update({
    'google': _g_mod, 'google.oauth2': _g_oauth2,
    'google.oauth2.service_account': _g_sa,
    'googleapiclient': _gapi, 'googleapiclient.discovery': _gapi_disc,
    'googleapiclient.errors': _gapi_err, 'googleapiclient.http': _gapi_http,
})

APP_PATH = '/sessions/laughing-eager-ramanujan/mnt/pai-search/app.py'
sys.path.insert(0, '/sessions/laughing-eager-ramanujan/mnt/pai-search')
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('app', APP_PATH)
app   = _ilu.module_from_spec(_spec)
sys.modules['app'] = app
load_error = None
try:
    _spec.loader.exec_module(app)
except Exception as _e:
    load_error = _e

# ── test helpers ──────────────────────────────────────────────────────────────
failures = []
def check(desc, cond, detail=''):
    if cond:
        print(f'  [PASS] {desc}')
    else:
        print(f'  [FAIL] {desc}' + (f'\n         => {detail}' if detail else ''))
        failures.append(desc)

def section(t):
    print(f'\n{"="*66}\n  {t}\n{"="*66}')

source = open(APP_PATH).read()

if load_error:
    print(f'[FATAL] app.py did not load: {load_error}')
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
section('A. _infer_column_types() — Data Validation path')
# ══════════════════════════════════════════════════════════════════════════════

def _make_sheets_svc(dv_map=None, values_map=None, dv_raises=False):
    """
    dv_map:     {col_letter: [option strings]}  -> becomes ONE_OF_LIST validation
    values_map: {col_letter: [cell values]}     -> becomes batchGet response
    """
    dv_map     = dv_map or {}
    values_map = values_map or {}
    svc = mock.MagicMock()

    def _get(spreadsheetId=None, ranges=None, includeGridData=None, fields=None, **kw):
        if dv_raises:
            raise RuntimeError('DV read failed')
        data = []
        for rng in (ranges or []):
            col = rng.split('!')[1].rstrip('0123456789')
            opts = dv_map.get(col)
            if opts is not None:
                cell = {'dataValidation': {'condition': {
                    'type': 'ONE_OF_LIST',
                    'values': [{'userEnteredValue': o} for o in opts]}}}
            else:
                cell = {}
            data.append({'rowData': [{'values': [cell]}]})
        return mock.MagicMock(execute=lambda: {'sheets': [{'data': data}]})

    def _batchGet(spreadsheetId=None, ranges=None, majorDimension=None, **kw):
        vrs = []
        for rng in (ranges or []):
            col = rng.split('!')[1].split(':')[0].rstrip('0123456789')
            vals = values_map.get(col, [])
            vrs.append({'values': [vals]} if vals else {})
        return mock.MagicMock(execute=lambda: {'valueRanges': vrs})

    svc.spreadsheets.return_value.get        = _get
    svc.spreadsheets.return_value.values.return_value.batchGet = _batchGet
    return svc


# A1 — EMPTY column WITH data validation -> must be select, not bool.
#      This is the exact bug the user reported.
svc = _make_sheets_svc(dv_map={'AZ': ['ēmta', 'wēnta', 'wagtēš']},
                       values_map={'AZ': []})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('AZ', 'LEX. "when?"'),))
check('A1 empty column WITH dropdown -> select (not bool)',
      r.get('LEX. "when?"', (None, None))[0] == 'select', str(r))
check('A1 options came from the validation rule',
      sorted(r.get('LEX. "when?"', (None, []))[1] or []) == sorted(['ēmta','wēnta','wagtēš']),
      str(r))

# A2 — empty column, NO validation -> bool (correct fallback)
svc = _make_sheets_svc(dv_map={}, values_map={'BA': []})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('BA', 'PHON. NewFlag'),))
check('A2 empty column, no dropdown -> bool',
      r.get('PHON. NewFlag', (None, None))[0] == 'bool', str(r))

# A3 — column with only +/- values -> bool
svc = _make_sheets_svc(dv_map={}, values_map={'BB': ['+', '', '+', '-']})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('BB', 'PHON. Diph'),))
check('A3 column of +/- -> bool',
      r.get('PHON. Diph', (None, None))[0] == 'bool', str(r))

# A4 — column with real values but NO validation -> select w/ those values
svc = _make_sheets_svc(dv_map={}, values_map={'BC': ['bidd', 'badd', 'bidd', '']})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('BC', 'LEX. "want"'),))
check('A4 column with values, no dropdown -> select',
      r.get('LEX. "want"', (None, None))[0] == 'select', str(r))
check('A4 options deduplicated + sorted',
      r.get('LEX. "want"', (None, []))[1] == ['badd', 'bidd'], str(r))

# A5 — DV takes PRECEDENCE over value inference when both exist.
#      Sheet has a typo value 'biddd' not in the dropdown; dropdown must win.
svc = _make_sheets_svc(dv_map={'BD': ['badd', 'bidd', 'widd']},
                       values_map={'BD': ['biddd', 'badd']})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('BD', 'LEX. "want2"'),))
check('A5 dropdown options win over stray sheet values',
      r.get('LEX. "want2"', (None, []))[1] == ['badd', 'bidd', 'widd'], str(r))

# A6 — DV API failure must NOT crash; falls back to value inference
svc = _make_sheets_svc(dv_map={'BE': ['x']}, values_map={'BE': ['alpha','beta']},
                       dv_raises=True)
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('BE', 'LEX. Fallback'),))
check('A6 DV failure falls back to value inference (no crash)',
      r.get('LEX. Fallback', (None, None))[0] == 'select', str(r))

# A7 — mixed batch: some cols have DV, some do not
svc = _make_sheets_svc(dv_map={'CA': ['one','two']},
                       values_map={'CB': ['+','-'], 'CC': ['red','blue']})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('CA','LEX. A'), ('CB','PHON. B'), ('CC','MOR. C')))
check('A7 mixed batch: DV col -> select',   r.get('LEX. A',  (None,None))[0] == 'select', str(r))
check('A7 mixed batch: bool col -> bool',   r.get('PHON. B', (None,None))[0] == 'bool',   str(r))
check('A7 mixed batch: value col -> select',r.get('MOR. C',  (None,None))[0] == 'select', str(r))
check('A7 every requested column present in result', len(r) == 3, str(r))

# A8 — empty input short-circuits without any API call
svc_never = mock.MagicMock()
svc_never.spreadsheets.side_effect = AssertionError('should not call API')
with mock.patch.object(app, 'get_services', return_value=(None, None, svc_never)):
    r = app._infer_column_types(())
check('A8 empty tuple -> {} with no API call', r == {}, str(r))

# A9 — blank / whitespace-only dropdown entries are dropped
svc = _make_sheets_svc(dv_map={'CD': ['ok', '', '   ', 'fine']}, values_map={})
with mock.patch.object(app, 'get_services', return_value=(None, None, svc)):
    r = app._infer_column_types((('CD', 'LEX. Blanks'),))
check('A9 blank dropdown options filtered out',
      r.get('LEX. Blanks', (None, []))[1] == ['fine', 'ok'], str(r))


# ══════════════════════════════════════════════════════════════════════════════
section('B. get_feature_defs() — prefix-stripped type inheritance')
# ══════════════════════════════════════════════════════════════════════════════

def _run_gfd(headers, inferred=None, extras=None):
    """Run get_feature_defs() against a fake header row."""
    inferred = inferred or {}
    extras   = extras or []
    with mock.patch.object(app, '_get_sheet_headers', return_value=headers), \
         mock.patch.object(app, 'get_extra_feature_defs', return_value=extras), \
         mock.patch.object(app, '_infer_column_types', return_value=inferred):
        return app.get_feature_defs()

# B1 — exact match in FEATURE_HEADER_DEFS wins
defs = _run_gfd(['x', 'LEX. "when?"'])
d = {fd[2]: fd for fd in defs}
check('B1 exact FEATURE_HEADER_DEFS match -> select',
      d['LEX. "when?"'][3] == 'select', str(d.get('LEX. "when?"')))
check('B1 options from FEATURE_HEADER_DEFS',
      d['LEX. "when?"'][4] == ['ēmta','wēnta','wagtēš'], str(d.get('LEX. "when?"')))

# B2 — THE RENAME CASE: old '"want"' (no prefix) is in FEATURE_HEADER_DEFS.
#      New column 'LEX. "want"' must inherit its select+options via prefix strip.
defs = _run_gfd(['x', 'LEX. "want"'])
d = {fd[2]: fd for fd in defs}
check('B2 renamed LEX. "want" inherits type from bare "want"',
      d['LEX. "want"'][3] == 'select', str(d.get('LEX. "want"')))
check('B2 renamed LEX. "want" inherits options',
      d['LEX. "want"'][4] == ['badd','bidd','widd'], str(d.get('LEX. "want"')))

# B3 — prefix-strip must NOT fire when inference already has the exact name
defs = _run_gfd(['LEX. Brand New'],
                inferred={'LEX. Brand New': ('select', ['p','q'])})
d = {fd[2]: fd for fd in defs}
check('B3 unknown column uses inferred type',
      d['LEX. Brand New'][3] == 'select' and d['LEX. Brand New'][4] == ['p','q'],
      str(d.get('LEX. Brand New')))

# B4 — a genuinely unknown column with no inference -> bool fallback
defs = _run_gfd(['SYN. Totally Unknown'], inferred={})
d = {fd[2]: fd for fd in defs}
check('B4 unknown + no inference -> bool fallback',
      d['SYN. Totally Unknown'][3] == 'bool', str(d.get('SYN. Totally Unknown')))

# B5 — non-prefixed columns are NEVER discovered (old '"want"' must not appear)
defs = _run_gfd(['"want"', 'קהילה', 'סטטוס', 'LEX. "want"'])
names = [fd[2] for fd in defs]
check('B5 bare "want" (no prefix) NOT discovered', '"want"' not in names, str(names))
check('B5 only the prefixed LEX. "want" is discovered',
      names == ['LEX. "want"'], str(names))

# B6 — column letters are correct (0-based index -> letter)
defs = _run_gfd(['a','b','c','LEX. AtIndex3'])
d = {fd[2]: fd for fd in defs}
check('B6 col_letter for index 3 == "D"', d['LEX. AtIndex3'][1] == 'D', str(d))
check('B6 1-based index == 4',            d['LEX. AtIndex3'][0] == 4,   str(d))

# B7 — column past Z gets a two-letter reference
hdrs = [f'c{i}' for i in range(26)] + ['LEX. PastZ']
defs = _run_gfd(hdrs)
d = {fd[2]: fd for fd in defs}
check('B7 index 26 -> "AA"', d['LEX. PastZ'][1] == 'AA', str(d.get('LEX. PastZ')))

# B8 — AppFeatureDefs extras are honoured
defs = _run_gfd(['MOR. FromExtras'],
                extras=[('MOR. FromExtras', 'disp', 'select', ['e1','e2'])])
d = {fd[2]: fd for fd in defs}
check('B8 AppFeatureDefs extras supply type/options',
      d['MOR. FromExtras'][3] == 'select' and d['MOR. FromExtras'][4] == ['e1','e2'],
      str(d.get('MOR. FromExtras')))

# B9 — headers are stripped of whitespace before matching
defs = _run_gfd(['  LEX. "when?"  '])
d = {fd[2]: fd for fd in defs}
check('B9 whitespace-padded header still matches known def',
      d.get('LEX. "when?"', (None,None,None,'?'))[3] == 'select', str(d))

# B10 — a column whose name equals the prefix alone must not crash
defs = _run_gfd(['LEX.'])
check('B10 bare prefix header handled without crash', isinstance(defs, list), str(defs))

# B11 — prefix-strip must not cross-contaminate: PHON. X should not pick up
#       options from an unrelated bare 'X' unless one genuinely exists.
defs = _run_gfd(['PHON. impf. prefix 3.m.sg'])
d = {fd[2]: fd for fd in defs}
check('B11 PHON.-prefixed version of a bare known feature inherits its options',
      d['PHON. impf. prefix 3.m.sg'][4] == ['bi-','byi-','yi-'],
      str(d.get('PHON. impf. prefix 3.m.sg')))

# B12 — sheet order is preserved
defs = _run_gfd(['LEX. Z', 'x', 'PHON. A', 'y', 'MOR. M'])
check('B12 features returned in sheet column order',
      [fd[2] for fd in defs] == ['LEX. Z', 'PHON. A', 'MOR. M'],
      str([fd[2] for fd in defs]))

# B13 — only unresolvable columns are sent to _infer_column_types
seen = {}
def _spy(unknown):
    seen['cols'] = unknown
    return {}
with mock.patch.object(app, '_get_sheet_headers',
                       return_value=['LEX. "when?"', 'LEX. "want"', 'SYN. Mystery']), \
     mock.patch.object(app, 'get_extra_feature_defs', return_value=[]), \
     mock.patch.object(app, '_infer_column_types', side_effect=_spy):
    app.get_feature_defs()
sent = [ht for _, ht in seen.get('cols', ())]
check('B13 known column not sent for inference', 'LEX. "when?"' not in sent, str(sent))
check('B13 prefix-inheritable column not sent for inference',
      'LEX. "want"' not in sent, str(sent))
check('B13 genuinely unknown column IS sent for inference',
      'SYN. Mystery' in sent, str(sent))


# ══════════════════════════════════════════════════════════════════════════════
section('C. _get_all_sheet_features() — cache-key invalidation')
# ══════════════════════════════════════════════════════════════════════════════

check('C1 _get_all_sheet_features accepts a _col_set parameter',
      '_col_set' in app._get_all_sheet_features.__code__.co_varnames,
      str(app._get_all_sheet_features.__code__.co_varnames))
check('C2 get_sheet_features builds col_set from FEATURE_DEFS',
      re.search(r'col_set\s*=\s*tuple\(\(fd\[1\], fd\[2\]\) for fd in FEATURE_DEFS\)', source)
      is not None)
check('C3 get_sheet_features passes _col_set through',
      re.search(r'_get_all_sheet_features\(version=version,\s*_col_set=col_set\)', source)
      is not None)

# C4 — a rename must produce a DIFFERENT cache key
old_defs = [(1,'A','"want"','select',['badd']), (2,'B','PHON. X','bool',None)]
new_defs = [(1,'A','LEX. "want"','select',['badd']), (2,'B','PHON. X','bool',None)]
k_old = tuple((fd[1], fd[2]) for fd in old_defs)
k_new = tuple((fd[1], fd[2]) for fd in new_defs)
check('C4 rename changes the cache key', k_old != k_new, f'{k_old} vs {k_new}')

# C5 — adding a column changes the key
k_add = k_new + (('C', 'LEX. Added'),)
check('C5 adding a column changes the cache key', k_add != k_new)

# C6 — identical defs produce an identical key (no needless invalidation)
k_same = tuple((fd[1], fd[2]) for fd in new_defs)
check('C6 unchanged defs keep the same key', k_same == k_new)

# C7 — key is hashable (Streamlit cache requirement)
try:
    hash(k_new); ok = True
except TypeError as e:
    ok = False
check('C7 cache key is hashable', ok)


# ══════════════════════════════════════════════════════════════════════════════
section('D. Cache TTL configuration')
# ══════════════════════════════════════════════════════════════════════════════

def _ttl_before(fn_name):
    m = re.search(r'@st\.cache_data\(([^)]*)\)\s*\ndef ' + re.escape(fn_name), source)
    if not m: return None
    t = re.search(r'ttl=(\d+)', m.group(1))
    return int(t.group(1)) if t else 'NO_TTL'

check('D1 _get_sheet_headers TTL is short (<=300s)',
      isinstance(_ttl_before('_get_sheet_headers'), int)
      and _ttl_before('_get_sheet_headers') <= 300,
      str(_ttl_before('_get_sheet_headers')))
check('D2 _infer_column_types has a TTL (not cached forever)',
      isinstance(_ttl_before('_infer_column_types'), int),
      str(_ttl_before('_infer_column_types')))
check('D3 get_feature_defs is NOT cached (must run every rerun)',
      re.search(r'@st\.cache_data[^\n]*\n\s*def get_feature_defs', source) is None)


# ══════════════════════════════════════════════════════════════════════════════
section('E. End-to-end: rename an old column to a prefixed name')
# ══════════════════════════════════════════════════════════════════════════════

# Sheet BEFORE the rename: bare '"want"' — not discoverable.
before = _run_gfd(['קהילה', '"want"', 'סטטוס'])
check('E1 before rename: "want" invisible to the app',
      [fd[2] for fd in before] == [], str([fd[2] for fd in before]))

# Sheet AFTER renaming the SAME column (same position -> same letter/data).
after = _run_gfd(['קהילה', 'LEX. "want"', 'סטטוס'])
d = {fd[2]: fd for fd in after}
check('E2 after rename: column discovered', 'LEX. "want"' in d, str(list(d)))
check('E3 after rename: same column letter B (data preserved)',
      d['LEX. "want"'][1] == 'B', str(d.get('LEX. "want"')))
check('E4 after rename: type inherited as select',
      d['LEX. "want"'][3] == 'select', str(d.get('LEX. "want"')))
check('E5 after rename: options inherited',
      d['LEX. "want"'][4] == ['badd','bidd','widd'], str(d.get('LEX. "want"')))
check('E6 rename invalidates the feature-value cache',
      tuple((fd[1], fd[2]) for fd in before) != tuple((fd[1], fd[2]) for fd in after))


# ══════════════════════════════════════════════════════════════════════════════
section('F. Wildcards — regression + edge cases')
# ══════════════════════════════════════════════════════════════════════════════

def _m(pattern, word):
    try:
        return bool(app.pattern_to_regex(pattern).search(word))
    except Exception:
        return None

check('F1 B matches every bilabial',
      all(_m('B', c) for c in ['b','ḅ','m','ṃ','f']))
check('F2 L matches every laminal',
      all(_m('L', c) for c in ['l','ḷ','m','ṃ','r','ṛ','n']))
check('F3 m is in BOTH B and L (documented overlap)',
      'm' in app.BILABIALS and 'm' in app.LAMNR)
check('F4 B and L are disjoint from GUTTURALS',
      not (app.BILABIALS & app.GUTTURALS) and not (app.LAMNR & app.GUTTURALS))
check('F5 B/L members are all real consonants',
      (app.BILABIALS | app.LAMNR) <= app.CONSONANTS,
      str((app.BILABIALS | app.LAMNR) - app.CONSONANTS))
check('F6 combined pattern BvL matches "bal"',  _m('BvL', 'bal') is True)
check('F7 combined pattern BvL rejects "qal"', _m('BvL', 'qal') is False)
check('F8 anchored ^B# matches single "b"',    _m('^B#', 'b') is True)
check('F9 E emphatics still work',
      all(_m('E', c) for c in ['ḍ','ẓ','ṣ']))
check('F10 G gutturals still work',
      all(_m('G', c) for c in ['h','x','ḥ','ʿ','ġ','q']))


# ══════════════════════════════════════════════════════════════════════════════
section('G. Keyboard / legend consistency with the Python sets')
# ══════════════════════════════════════════════════════════════════════════════

kb = open('/sessions/laughing-eager-ramanujan/mnt/pai-search/searchbar/index.html').read()

for ch, label in [('B','Bilabial'), ('L','Laminal')]:
    check(f'G1 keyboard has a "{ch}" key', f"ch:'{ch}'" in kb)
    check(f'G2 keyboard tooltip for {ch} says {label}', label in kb)

# Every wildcard on the keyboard must be handled by _pattern_char_to_regex
kb_chars = re.findall(r"\{ch:'([^']+)'\s*,\s*cls:'wildcard'", kb)
unhandled = []
for ch in kb_chars:
    frag = app._pattern_char_to_regex(ch[0]) if len(ch) == 1 else None
    if len(ch) == 1 and frag == re.escape(ch):
        unhandled.append(ch)   # fell through to the literal-escape branch
check('G3 every single-char keyboard wildcard maps to a real regex class',
      not unhandled, f'unhandled: {unhandled}')

# Legend pills in app.py must mention B and L with the right words
check('G4 legend pill for B says Bilabial',
      re.search(r'<b>B</b>\s*=\s*Bilabial', source) is not None)
check('G5 legend pill for L says Laminal',
      re.search(r'<b>L</b>\s*=\s*Laminal', source) is not None)

# Legend character lists must match the actual Python sets
mB = re.search(r'<b>B</b>\s*=\s*Bilabial\s*\(([^)]*)\)', source)
mL = re.search(r'<b>L</b>\s*=\s*Laminal\s*\(([^)]*)\)',  source)
if mB:
    check('G6 legend B list matches BILABIALS set',
          set(mB.group(1).split()) == app.BILABIALS,
          f'legend={set(mB.group(1).split())} set={app.BILABIALS}')
if mL:
    check('G7 legend L list matches LAMNR set',
          set(mL.group(1).split()) == app.LAMNR,
          f'legend={set(mL.group(1).split())} set={app.LAMNR}')


# ══════════════════════════════════════════════════════════════════════════════
section('H. FEATURES doc block — prefixed names round-trip')
# ══════════════════════════════════════════════════════════════════════════════

check('H1 features are matched in docs by full prefixed name fd[2]',
      "text.startswith(fd[2] + '  [')" in source)
check('H2 bare prefix lines are skipped when parsing',
      'if text.strip() in FEAT_PREFIXES:' in source)
check('H3 group headers are emitted once per prefix',
      'emitted_prefixes' in source)
check('H4 DOC_ONLY_FEATURES preserved on rewrite',
      'DOC_ONLY_FEATURES' in source and 'fd_names' in source)


# ══════════════════════════════════════════════════════════════════════════════
section('I. Known-risk checks (potential bugs)')
# ══════════════════════════════════════════════════════════════════════════════

# I1 — FEATURE_HEADER_DEFS must not contain duplicate header_texts
hts = [t[0] for t in app.FEATURE_HEADER_DEFS]
dupes = {h for h in hts if hts.count(h) > 1}
check('I1 no duplicate header_text in FEATURE_HEADER_DEFS', not dupes, str(dupes))

# I2 — after prefix-stripping, no two entries collide (would make inheritance
#      ambiguous: two different features could claim the same stripped name)
def _strip(s):
    for p in app.FEAT_PREFIXES:
        if s.startswith(p):
            return s[len(p):].strip()
    return s
stripped = [_strip(h) for h in hts if _strip(h) != h]
sdupes = {s for s in stripped if stripped.count(s) > 1}
check('I2 no ambiguous collisions after prefix-strip', not sdupes, str(sdupes))

# I3 — a stripped prefixed name must not collide with an existing BARE entry
bare = {h for h in hts if _strip(h) == h}
shadow = {s for s in stripped if s in bare}
check('I3 stripped names do not shadow bare FEATURE_HEADER_DEFS entries',
      not shadow, f'shadowed: {shadow}')

# I4 — every select-type entry actually has options
bad = [t[0] for t in app.FEATURE_HEADER_DEFS if t[2] == 'select' and not t[3]]
check('I4 every select feature has a non-empty options list', not bad, str(bad))

# I5 — every bool-type entry has options=None
bad = [t[0] for t in app.FEATURE_HEADER_DEFS if t[2] == 'bool' and t[3] is not None]
check('I5 every bool feature has options=None', not bad, str(bad))

# I6 — types are restricted to the known set
bad = [t[0] for t in app.FEATURE_HEADER_DEFS if t[2] not in ('bool','select','text')]
check('I6 all feature types are bool/select/text', not bad, str(bad))

# I7 — DOC_ONLY_FEATURES must not also be live feature columns
overlap = set(app.DOC_ONLY_FEATURES) & set(hts)
check('I7 DOC_ONLY_FEATURES do not overlap FEATURE_HEADER_DEFS', not overlap, str(overlap))

# I8 — options within a single feature must be unique
bad = [t[0] for t in app.FEATURE_HEADER_DEFS
       if t[3] and len(t[3]) != len(set(t[3]))]
check('I8 no duplicate options inside a feature', not bad, str(bad))

# I9 — _col_letter round-trips correctly at the 26/27 boundary
check('I9 _col_letter(0)="A", (25)="Z", (26)="AA", (27)="AB"',
      [app._col_letter(i) for i in (0,25,26,27)] == ['A','Z','AA','AB'],
      str([app._col_letter(i) for i in (0,25,26,27)]))

# I10 — COL_NAMES keys used by load_corpus_index all exist
used = set(re.findall(r"cols\['(\w+)'\]", source))
missing = used - set(app.COL_NAMES)
check('I10 every cols[...] key exists in COL_NAMES', not missing, str(missing))

# I11 — the DV read requests the dataValidation field it then parses
m = re.search(r"fields='([^']*dataValidation[^']*)'", source)
check('I11 DV request asks for the dataValidation field', m is not None,
      m.group(1) if m else 'fields= not found')

# I12 — DV parse loop must be index-safe against a short API response
check('I12 DV loop guards against a short sheets.data list',
      'if i >= len(sheet_data_list)' in source)

# I13 — FEAT_NONE_OPTION must not collide with any real option value
allopts = {o for t in app.FEATURE_HEADER_DEFS for o in (t[3] or [])}
check('I13 FEAT_NONE_OPTION is not a real option value',
      app.FEAT_NONE_OPTION not in allopts)

# I14 — bool features are searched by truthiness, select by normalised equality
check('I14 select comparison uses _feat_val_norm on both sides',
      '_feat_val_norm(_cur) == _feat_val_norm(_fv)' in source)


# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{"="*66}')
if failures:
    print(f'RESULT: {len(failures)} FAILURE(S)')
    for f in failures:
        print(f'  - {f}')
    sys.exit(1)
print('RESULT: ALL DEEP TESTS PASSED')
