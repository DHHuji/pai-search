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


# ── shared test helpers ───────────────────────────────────────────────────────
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
