# PAI Search App — Handoff Document

## מה האפליקציה

כלי חיפוש ל-PAI Corpus (Palestinian Arabic Institute). כתוב ב-Streamlit (Python), מאוחסן ב-GitHub, ומופעל אוטומטית ב-Streamlit Cloud.

- **GitHub**: https://github.com/DHHuji/pai-search.git (branch: main)
- **Streamlit Cloud**: מחובר אוטומטית — כל push ל-main מפעיל redeploy תוך ~2 דקות
- **⚠️ חשוב**: ה-sandbox לא יכול לעשות `git push`. נעם חייב לרוץ `git push` מ-MacBook שלו. הקבצים ב-`/mnt/pai-search/` הם הקבצים האמיתיים על המחשב שלו, ולכן כל שינוי שנעשה ב-sandbox מגיע ישירות אליו.

---

## מבנה קבצים

```
pai-search/
├── app.py                  # כל הלוגיקה — ~4100 שורות
├── searchbar/index.html    # Web component של שורת חיפוש + מקלדת PAI
├── tagbridge/index.html    # Web component לתיוג דרך right-click
├── requirements.txt        # streamlit, google-auth, google-api-python-client
├── runtime.txt             # python-3.11
└── HANDOFF.md              # מסמך זה
```

---

## Google APIs שבשימוש

- **Google Sheets API** — קורפוס הנתונים בגיליון `Recordings`, הגדרות feature columns ב-`AppFeatureDefs`
- **Google Docs API** — קריאה וכתיבה של תמליל ב-Google Docs
- **Google Drive API** — (שימוש עקיף)

אותנטיקציה: Service Account, המפתח נמצא ב-`st.secrets["gcp_service_account"]` (מוגדר ב-Streamlit Cloud secrets).

**SPREADSHEET_ID** = `"1Q9g4vlBDzNx3D872hKePtFy-VShD-ocI--kPs44lyJ4"`

---

## ה-Schema של גיליון Recordings

עמודות קבועות (מזוהות לפי **כותרת**, לא לפי מיקום):

| מפתח ב-COL_NAMES | כותרת בגיליון |
|---|---|
| `trans_link` | `קישורים לתעתיקים` |
| `rec_link` | `קישורים להקלטות` |
| `village` | `שם יישוב בתעתיק` |
| `social_typology` | `Social Typology` |
| `geo_typology` | `Geographical Typology` |
| `community` | `קהילה` |
| `gender` | `מגדר דובר` |
| `status` | `סטטוס` |

**Feature columns** — עמודות שכותרתן מתחילה ב-`PHON.` / `MOR.` / `SYN.` / `LEX.` מגולות אוטומטית. אין צורך לרשום אותן ידנית.

---

## Feature Columns — ארכיטקטורה

### `FEAT_PREFIXES` (app.py ~שורה 1532)
```python
FEAT_PREFIXES = ('PHON.', 'MOR.', 'SYN.', 'LEX.')
```
כל עמודה שכותרתה מתחילה באחד מה-prefixes האלה מגולת אוטומטית כ-feature column.

### `FEATURE_HEADER_DEFS` (app.py ~שורה 1534)
רשימה סטטית של feature columns **ידועים מראש**, לצורך הגדרת type ו-options בלבד (לא לגילוי עמודות). פורמט:
```python
('PHON. aCC > iCC', 'display_name', 'bool', None)
('LEX. "when?"',    '"when?"',      'select', ['ēmta', 'wēnta'])
```

**כדי להוסיף feature column חדש** — פשוט תן לעמודה בגיליון כותרת שמתחילה ב-PHON. / MOR. / SYN. / LEX. והגדר לה dropdown. היא תתגלה אוטומטית תוך ~2 דקות. הוסף שורה כאן רק כדי לקבע type/options בקוד.

### `AppFeatureDefs` tab בגיליון
מבנה: `header_text | display_name | type | options (;-separated)`.

⚠️ **הממשק שכתב לטאב הזה הוסר** (הפאנל "🧬 Feature columns" בסרגל הצד) — גילוי לפי prefix הפך אותו למיותר. הטאב עדיין **נקרא** ע"י `get_extra_feature_defs()`, כך שרשומות היסטוריות ממשיכות לספק type/options. אם צריך לערוך אותו — עורכים ידנית בגיליון.

### פונקציות מרכזיות לניהול features

```
_get_sheet_headers()       TTL=120s  — שורה 1 של הגיליון (כותרות)
_infer_column_types()      TTL=300s  — קורא data validation מ-Sheets API לזיהוי dropdown vs bool
get_feature_defs()         ללא cache — רץ בכל rerun, זול כי מסתמך על שתי הפונקציות הנ"ל
get_extra_feature_defs()   TTL=600s  — קורא AppFeatureDefs tab
_get_all_sheet_features()  TTL=3600s — קורא את כל ערכי ה-features מכל השורות (batchGet)
                           ⚠️ cache key כולל _col_set — מתבטל אוטומטית אם FEATURE_DEFS השתנה
```

### כיצד עמודה חדשה מגולה

1. משתמש מוסיף עמודה `LEX. something` בגיליון
2. תוך 2 דקות (TTL של `_get_sheet_headers`): `get_feature_defs()` מוצא אותה
3. `_infer_column_types()` קורא את Data Validation של Sheets → אם יש `ONE_OF_LIST`, סוג `select` עם אפשרויות
4. אם אין data validation, בודק ערכים קיימים (אם בוליאניים → bool, אחרת → select)
5. `_get_all_sheet_features()` מתבטל מיידית (col_set השתנה) → קורא נתונים מ-C_new

### בעיית שמות כפולים (עמודה ישנה vs. חדשה)
אם עמודה ישנה ללא prefix (`"want"`) מוחלפת בעמודה חדשה עם prefix (`LEX. "want"`):
- הקוד מגלה רק את החדשה (יש prefix)
- type/options: הקוד מנסה גם את השם המקוצר (`"want"`) ב-FEATURE_HEADER_DEFS אם הטקסט המלא לא נמצא
- הנתונים חייבים להיות בעמודה החדשה. הדרך הפשוטה ביותר: **שינוי שם הכותרת הישנה** (לא יצירת עמודה חדשה)

---

## מערכת ה-Wildcard לחיפוש

### קבצים רלוונטיים
- `app.py` ~שורות 235–290: הגדרות ה-sets ופונקציות regex
- `searchbar/index.html`: מקלדת עם כפתורי wildcard

### Wildcards זמינים

| תו | שם | סט |
|---|---|---|
| `C` | any consonant | כל העיצורים |
| `V` | any vowel | `SHORT_VOWELS ∪ LONG_VOWELS` |
| `v` | short vowel | `{a, e, i, u, o, ə}` |
| `v̄` | long vowel | `{ā, ē, ī, ō, ū, ā̈}` |
| `D` | diphthong | `{aw, ay, ōw, ēy}` |
| `G` | guttural | `{h, x, ḥ, ʿ, ġ, q}` |
| `E` | emphatic | `{ḍ, ḏ̣, ẓ, ṣ}` |
| `B` | bilabial | `{b, ḅ, m, ṃ, f}` |
| `L` | laminal/lamnr | `{l, ḷ, m, ṃ, r, ṛ, n}` |
| `$` | any chars (0+) | `.*?` |
| `^` | start of word | anchor |
| `#` | end of word | anchor |

**כדי להוסיף wildcard חדש:**
1. הוסף set לאוסף ב-app.py (~שורה 244)
2. הוסף `_X = _alts(SET)` (~שורה 266)
3. הוסף `elif ch == 'X': return _X` ב-`_pattern_char_to_regex()` (~שורה 270)
4. הוסף כפתור ב-`WILDCARDS` array ב-`searchbar/index.html` (~שורה 107)
5. הוסף legend pill ב-app.py (~שורה 3314)

---

## Cache Architecture — חשוב להבין

כל הפונקציות הנ"ל מוגנות ב-`@st.cache_data`. מפות ה-cache:

```
_get_service_account_info()   @st.cache_resource  — GCP credentials (across users)
_get_sheet_headers()          ttl=120s   — row 1 of Recordings sheet
get_column_indices()          ttl=3600s  — COL_NAMES → column index
get_extra_feature_defs()      ttl=600s   — AppFeatureDefs tab
_infer_column_types()         ttl=300s   — Data Validation lookup + value inference
                              key: tuple of (col_letter, header_text)
load_corpus_index()           ttl=600s   — list of all recordings with metadata
get_doc_content()             ttl=3600s, persist="disk"  — Google Doc HTML
get_doc_feature_examples()    ttl=3600s  — מילות הדוגמה מבלוק FEATURES שבמסמך
                              key: (doc_id, version, _col_set)
_get_all_sheet_features()     ttl=3600s  — {sheet_row: {col_letter: value}}
                              key: (version, _col_set)  — מתבטל אם column set השתנה
```

**Clear cache**: כפתור "🗑️ Clear cache & reload" בסרגל הצד — מתנקה כל הcaches.  
**Cache busting after write**: `st.session_state['_features_version']` עולה ב-1 אחרי כל tag, מה שמבטל את `_get_all_sheet_features`.

---

## שלושה מצבי חיפוש

1. **Pattern search** — Regex על תמליל, תמיכה ב-wildcards ורצפי מילים (space = word boundary)
2. **Root search** — הזנת אותיות שורש, הופך אוטומטית לpattern עם `$` בין האותיות
3. **Feature Browse** — בחירת feature + ערך, מחזיר מסמכים שתוייגו

---

## מרכיבים חיצוניים (Streamlit Components)

### `searchbar/index.html`
Web component לשורת חיפוש. מכיל:
- Input field
- מקלדת PAI (תווים מיוחדים + wildcards)
- שולח `{query: "...", timestamp: N}` ל-Streamlit דרך `postMessage`

### `tagbridge/index.html`
Web component לתיוג (לא ל-UI — רק "גשר" לשמירת נתונים דרך localStorage כשה-iframe מגביל).

---

## FEATURES Block במסמך

כל מסמך קורפוס מכיל בסוף section:
```
FEATURES:
PHON.
PHON. aCC > iCC  [+]
PHON. *q  [q]
LEX.
LEX. "want"  [bidd]
```
- שורות `PHON.` / `LEX.` וכו' הן headers בלבד (בלי ערך)
- כל שאר השורות: `feature_name  [value]` — שם מדויק כמו ב-`fd[2]` (כולל prefix)
- הפונקציה `update_gdoc_features_section()` כותבת/מעדכנת את הblock
- הפונקציה בודקת `text.startswith(fd[2] + '  [')` לזיהוי שורות

**⚠️ חשוב**: אם שם עמודה השתנה, שורות ישנות במסמכים לא ייקראו עוד (כי הname לא match). נתונים ישנים במסמכים נשמרים רק בgsheet.

---

## DOC_ONLY_FEATURES (app.py ~שורה 1592)

Features שמופיעים בdoc FEATURES section אבל **אין להם עמודה בגיליון** (לא ניתן לתייג, רק נשמרים כטקסט). דוגמה: `'"was"'` שהוסר מהגיליון ב-2026-06-22 אבל עדיין קיים במסמכים ישנים.

---

## הוספה/שינוי של דברים נפוצים

### הוספת feature column חדש עם type/options קבועים
הוסף שורה ל-`FEATURE_HEADER_DEFS` בapp.py:
```python
('LEX. "new_word"', '"new_word"', 'select', ['opt1', 'opt2', 'opt3']),
```
כותרת בגיליון חייבת להתחיל ב-PHON./MOR./SYN./LEX. — אחרת לא תגלה.

### הוספת עמודה לגיליון (ללא שינוי קוד)
1. ב-Google Sheets, הוסף עמודה עם כותרת `LEX. something` (עם prefix)
2. הוסף Data Validation dropdown לעמודה → הapp יזהה `ONE_OF_LIST` ויציג כ-select
3. תוך 2 דקות הeapp יגלה אותה אוטומטית

### שינוי אפשרויות של feature קיים
ערוך את `FEATURE_HEADER_DEFS` בapp.py, או אם הוגדר ב-Data Validation בגיליון — ערוך שם.

### הוספת metadata column למסך הסינון
1. הוסף לCOL_NAMES:
   ```python
   COL_NAMES = { ..., 'new_col': 'Column Header In Sheet' }
   ```
2. ב-`load_corpus_index()` (~שורה 2112), הוסף:
   ```python
   'new_col': cell_val(cols['new_col']) or '',
   ```
3. בsidebar (~שורה 3610), הוסף multiselect/filter

---

## טיפים לניפוי שגיאות

- **שינויים לא מופיעים**: לחץ "🗑️ Clear cache & reload" בסרגל הצד
- **Feature column ריק/שגוי type**: ודא שהכותרת מתחילה ב-FEAT_PREFIX ושיש Data Validation בגיליון
- **0 תוצאות ב-Feature Browse**: בדוק שהנתונים בעמודה החדשה (לא ישנה). אם שינית שם כותרת, col_set השתנה והcache מתאפס — אמור לעבוד אחרי ~2 דקות
- **עמודה ישנה vs. חדשה**: אל תיצור עמודה חדשה ריקה. עדיף **שינוי שם הכותרת הישנה** כדי לשמור נתונים
- **git push נכשל**: רץ `git push` מהterminal על ה-MacBook, לא מתוך הsession

---

## Test Suite

שלושה קבצים, כולם בתיקיית הפרויקט. הרץ את שלושתם אחרי כל שינוי:

```bash
python tests_full.py     # 98 טסטים — רגרסיה כללית
python tests_deep.py     # 85 טסטים — feature-columns, cache, wildcards
python tests_search.py   # 419 טסטים — חיפוש, טקסט, מסמכים, UX, multi-value, chips, קיבוץ, CSV
```

`_harness.py` מכיל את ה-stubs המשותפים (Streamlit + Google APIs). `tests_search.py` מייבא ממנו; שני האחרים מכילים עותק משלהם.

שניהם משתמשים ב-`importlib.util.spec_from_file_location` לטעינת app.py עם stubs מלאים ל-Streamlit ול-Google APIs — אין צורך בcredentials או ברשת.

`tests_deep.py` מחולק לסקשנים:

| סקשן | מה נבדק |
|---|---|
| A | `_infer_column_types()` — נתיב ה-Data Validation, כולל עמודה ריקה עם dropdown |
| B | `get_feature_defs()` — ירושת type דרך prefix-strip, סדר עמודות, col_letter |
| C | `_get_all_sheet_features()` — ביטול cache בשינוי שם עמודה |
| D | TTL של כל ה-caches |
| E | End-to-end: שינוי שם עמודה ישנה לשם עם prefix |
| F | Wildcards — כולל בדיקה שכל חברי B/L/E נמצאים ב-CONSONANTS |
| G | עקביות בין המקלדת, ה-legend, וה-sets ב-Python |
| H | FEATURES block במסמכים |
| I | Invariants על FEATURE_HEADER_DEFS (כפילויות, התנגשויות, type/options תקינים) |

`tests_search.py`:

| סקשן | מה נבדק |
|---|---|
| J–L | `pattern_to_regex` — עוגנים, קבוצות אלטרנטיבה, אות אופציונלית, ה-wildcard הדו-תווי `v̄` |
| M–N | `tokenize()` וקונבנציית הסוגריים, חיפוש רצף מילים |
| O–P | פילטרי מיקום (start/middle/end), הדגשה בטוחה ב-HTML |
| Q–S | `_extract_doc_id`, `_apply_filters`, `root_to_pattern` |
| T–V | נרמול ערכי feature, בניית בלוק FEATURES, NFC/NFD |
| W | Invariants על ה-sets של ה-wildcards |
| X–Y | נתיבי כתיבה, טיפול בקלט שגוי |
| Z | ארבעת שינויי ה-UX (ראה למטה) |
| AA–AD | תיוג מרובה-ערכים: פרסור, מיזוג, התאמה בחיפוש, חיווט בקוד |
| AE–AF | פורמט multi-select נייטיב (chips) ותצוגת chips בממשק |
| AG–AH | חיפוש פיצ'רים בפופ-אפ (כולל תקינות ה-JS המרונדר) וקיבוץ לקטגוריות |
| AI | ייצוא CSV: מילות דוגמה, והבחנה בין ריק ל-FALSE |
| AJ | תיוג BUT: פרסור, שימור בשכתוב מסמך, ממשק, CSV, סינון |
| AK | מחיקת ערך בודד + הפאנל שנעלם |
| AL | באגים שדווחו: שורת חיפוש, מצב ריק, עלות replace |
| AM | תיוג אוטומטי מטבלת התעתיק |

---

## באגים שתוקנו (2026-08-08)

### 1. ה-wildcard `C` פספס עיצורים מודגשים — באג חיפוש שקט
`ḅ ṃ ḷ ṛ ḏ̣` היו חברים ב-`BILABIALS`/`LAMNR`/`EMPHATICS` אבל **לא** ב-`CONSONANTS`. התוצאה: חיפוש `CvC` החזיר **0 תוצאות** למילים כמו `ḅal`, `ṃan`, `ḷaw`, `ṛas` — בלי שום הודעת שגיאה. תוקן ע"י הוספתם ל-`CONSONANTS`.

**Invariant לשמירה**: כל חבר ב-B/L/E/G חייב להיות גם ב-`CONSONANTS`. טסט F5 אוכף את זה — אם מוסיפים wildcard חדש, ודא שהתווים שלו נמצאים ב-`CONSONANTS`.

### 2. ירושת type דרך prefix-strip הייתה מאונדקסת הפוך
`known_meta_stripped` נבנה רק מרשומות שכבר היה להן prefix, ולכן חיפוש `LEX. "want"` → `"want"` מעולם לא מצא את הרשומה הבסיסית `"want"`, והעמודה נפלה ל-fallback של `bool`. תוקן — עכשיו כל רשומה מאונדקסת לפי שמה המקוצר, ורשומות בסיסיות (ללא prefix) מקבלות עדיפות.

---

## שינויי UX (2026-08-08)

ארבעה שינויים, כולם ננעלו בבדיקות בסקשן Z של `tests_search.py`.

### 1. אינדיקציה לפילטרים פעילים
**הבעיה**: `active_filters` נבנה בתוך expander סגור. פילטר שהוגדר פעם אחת נשאר פעיל בשקט וצמצם כל חיפוש עתידי, בלי שום סימן.

**הפתרון**: כותרת ה-expander כוללת ספירה (`⚙️ Advanced options · 🔵 2 filters active`), ומעליו באנר שמפרט אילו פילטרים פעילים + כפתור `✕ Clear`.

**נקודה טכנית חשובה**: Streamlit מעריך את כותרת ה-expander **לפני** שהווידג'טים בתוכו רצים. לכן הערכים נקראים מ-`st.session_state` (שמחזיק את ערכי ה-rerun הקודם — כלומר מה שבאמת בתוקף עכשיו). המילון `_FILTER_KEYS` ממפה מפתח widget → תווית; אם מוסיפים פילטר חדש, **חובה** להוסיף אותו שם (טסט Z9 אוכף שכל מפתח מתאים ל-widget אמיתי).

### 2. legend מתקפל
רק `C`, `V`, `$` והעוגנים גלויים; השאר בתוך `<details class="legend-more">`. זהו HTML טהור — פתיחה לא גורמת ל-rerun של Streamlit (בניגוד ל-`st.toggle`). ה-CSS ב-`details.legend-more`.

טסטים Z12/Z13 אוכפים שה-wildcards הנפוצים נשארים בחוץ והנדירים בפנים; Z14 אוכף שכל wildcard עדיין מתועד איפשהו.

### 3. כפתור Search אחיד
בעבר Feature Browse דרש כפתור נפרד, והאפליקציה הציגה הודעה שמסבירה זאת. עכשיו `(_feat_search_btn or search_clicked)` — כפתור החיפוש הראשי עובד בכל ארבעת המצבים. הכפתור הייעודי נשאר כפעולה ראשית בהקשר.

### 4. אבחון למצב "אין תוצאות"
במקום "נסה תבנית רחבה יותר", מוצג המשפך:

```
312 documents in corpus → 47 after filters → 0 matched the pattern
```

ואז הסבר ממוקד לפי המצב:

- `_n_after_filter == 0` → "הפילטרים סיננו הכל, התבנית מעולם לא נבדקה"
- `_n_after_filter < total` → "הפילטרים מגבילים ל-N מתוך M"
- אחרת → "כל הקורפוס נסרק, אז זו התבנית ולא הפילטרים" + הצעות קונקרטיות

אותו משפך קיים גם ב-Feature Browse, עם רמז נוסף על AND/OR ועל עמודות שמעולם לא תוייגו.

---

## תיוג מרובה-ערכים (multi-value tags)

**כל פיצ'ר מסוג `select` יכול להחזיק כמה ערכים בו-זמנית.** זה נדרש כי חוקרים שונים מתייגים לגיטימית את אותו מסמך ברפלקסים שונים של אותו פיצ'ר — למשל `MOR. Fem. Ending` = `-e; -a`.

**הכלל**: תיוג חדש **מתמזג** עם הקיים. שום דבר לא נדרס ולא נחסם.

### פונקציות עזר (app.py, ליד `_feat_val_norm`)

```python
FEAT_VALUE_SEP = ', '   # כתיבה: פורמט multi-select נייטיב של Sheets

_split_feat_values(raw, options)   # תא → רשימת ערכים
_join_feat_values(values)          # רשימה → מחרוזת תא
_merge_feat_values(existing, new, options)  # → (merged, added, duplicates)
_feat_value_matches(cell, wanted, options)  # חברות, לא שוויון
```

### ⚠️ הפרסור חייב להיות option-aware

שני ערכי אופציה **מכילים נקודה-פסיק בתוכם**:

```
-a; -ha only after -ū-
-a; -ha only after -ū- / -i-
```

(בפיצ'ר `3.f.sg pron. ها-`). `split(';')` תמים היה קורע אותם לשני תגים מזויפים.

**הפתרון**: הפרסר מנסה קודם להתאים אופציות **שלמות ידועות, הארוכה ביותר קודם**, ורק לטקסט שהוא לא מזהה נופל לפיצול על מפריד. לכן `_split_feat_values` מקבל את רשימת האופציות — **תמיד העבר את `fd[4]`**. בלי זה, אופציות שמכילות `;` יישברו.

בקריאה מתקבלים גם `,` וגם `;`. **בכתיבה תמיד `', '`** — כי עמודות הפיצ'רים עוברות ל-**multi-select נייטיב של Google Sheets**, שמאחסן ערכים מופרדים בפסיק ומציג אותם כ-chips. כתיבת `'; '` לעמודה כזו הייתה יוצרת ערך אחד לא-תקין במקום שני chips.

עמודות שעדיין לא הומרו ממשיכות לעבוד — הקריאה סובלנית לשני המפרידים, ולכן אין צורך ב-backfill.

⚠️ **אף ערך אופציה לא מכיל פסיק כרגע** — זה מה שהופך פיצול על פסיק לבטוח. טסט AE8 נכשל אם מישהו יוסיף ערך עם פסיק, לפני שזה יספיק לשבור פרסור.

### מה השתנה בקוד

| מקום | לפני | אחרי |
|---|---|---|
| `write_sheet_features` | conflict → מסרב לכתוב | ממזג, מחזיר notices |
| דיאלוג ה-submit | אזהרה "overwritten" | info "tags were kept and yours added" |
| Feature Browse | selectbox (ערך אחד) | multiselect + chips, מתאים אם יש **אחד מהם** |
| תצוגת ערכים | טקסט רץ | chips (`.val-chip`) כמו בגיליון |
| tagging session | בחירה שנייה דורסת ראשונה | מצטברת |
| תפריט ימני | ללא אינדיקציה | ✓ ליד ערכים שכבר מתויגים |
| `_infer_column_types` | `-e; -a` נחשב אופציה אחת | מפוצל לערכים בודדים |

### נקודות זהירות לפיתוח עתידי

- פיצ'רים מסוג `bool` **לא** השתנו — נשארו חד-ערכיים.
- `write_sheet_features` מחזיר עכשיו **notices, לא conflicts**. ערך חוזר לא-ריק **כבר לא אומר שהכתיבה נכשלה** — הוא רק תיאור של מה שמוזג. אל תתייחס אליו כשגיאה.
- `_get_all_sheet_features` ממשיך להחזיר את התא כמחרוזת גולמית. הפיצול קורה בנקודות השימוש.
- `inject_interaction_js` מקבל `sheet_row` אופציונלי כדי לסמן ✓. הקריאה עטופה ב-try/except — כישלון בקריאת הערכים לעולם לא יעצור רינדור של מסמך.

---

## חיפוש פיצ'רים וקיבוץ לקטגוריות

### תפריט ימני (popup) — חיפוש חופשי

מעל רשימת הקטגוריות יש שדה חיפוש (`#ctx-feat-q`). הקלדה מסננת את **כל** הפיצ'רים בבת אחת, ומתאימה לפי:

1. השם המלא — `LEX. "want"`
2. **השם ללא הקידומת** — `want`
3. ערכי האופציות — `bidd` ימצא את הפיצ'ר שמכיל אותו

התוצאות מוצגות שטוח, כל אחת עם תג קטן של הקטגוריה שלה. השדה מתאפס בכל לחיצה ימנית — אחרת שאילתה שהוקלדה עבור מילה אחת הייתה מסתירה בשקט את רוב הפיצ'רים במילה הבאה.

**מבנה ה-JS** (בתוך `inject_interaction_js`):

```
stripPrefix(name)    — מסיר PHON./MOR./SYN./LEX.
groupOf(name)        — מחזיר את הקטגוריה לתג
featMatches(fd, q)   — התאמה לפי שם מלא / שם חשוף / ערכי אופציות
positionSub(t,rel,a) — מיקום תפריט משנה
buildValueMenu(...)  — רשימת הערכים של פיצ'ר select
makeFeatureItem(...) — שורת פיצ'ר אחת (משותפת לשני המצבים)
renderGroups()       — מצב עיון בקטגוריות (ברירת מחדל)
renderSearch(q)      — מצב תוצאות חיפוש שטוח
```

⚠️ **`makeFeatureItem` משותף לשני המצבים בכוונה.** בעבר הקוד היה משוכפל, ולכן סימוני ה-✓ של ריבוי-ערכים היו יכולים להתפצל בין המצבים. אם מוסיפים התנהגות לשורת פיצ'ר — להוסיף שם, לא בשני מקומות.

⚠️ **ה-JS יושב בתוך f-string של Python** — כל סוגר מסולסל ליטרלי חייב להיות כפול (`{{` / `}}`). שגיאה כאן **לא מייצרת חריגה ב-Python** אלא שוברת את התפריט בשקט בדפדפן. טסטים AG18–AG22 בודקים איזון סוגריים ב-JS המרונדר ואת היעדר `{{` שלא עברו רינדור.

### מסך "Browse by feature" — קיבוץ לקטגוריות

במקום multiselect שטוח אחד, יש עכשיו multiselect לכל קטגוריה, בשתי עמודות, בדיוק כמו החלוקה בפופ-אפ. הקידומת מוסרת מהתוויות (`format_func=_bare_feat`) כי הכותרת כבר נושאת אותה, וכל כותרת מציגה מונה.

מפתחות ה-session state: `feat_browse_grp_PHON` וכו' (הישן `feat_browse_names` הוסר).

⚠️ טסט AH11 אוכף ש-`_FEAT_GROUP_LABELS` מכיל **בדיוק** את `FEAT_PREFIXES`. אם מוסיפים קידומת חדשה ל-`FEAT_PREFIXES` ושוכחים כאן — קטגוריה שלמה תיעלם מהמסך הזה בשקט.

---

## ייצוא CSV

כל פיצ'ר תורם **שתי עמודות**:

| עמודה | תוכן |
|---|---|
| `MOR. Fem. Ending` | הערך/ים מהגיליון |
| `MOR. Fem. Ending — example` | **המילה שתויגה** כדוגמה |

### מאיפה מגיעות מילות הדוגמה

מילות הדוגמה קיימות **רק בבלוק FEATURES שב-Google Doc** — הגיליון מחזיק רק את הערך. `get_doc_feature_examples()` קורא אותן מה-HTML של המסמך, שכבר נשמר ב-cache ע"י `get_doc_content()` בזמן החיפוש — ולכן **אין קריאת API נוספת** למסמכים שהופיעו בתוצאות.

`_split_feature_line(text, fd)` מפרסר שורת FEATURES ומחזיר `(example_words, value)`. הוא מטפל בשני פורמטים היסטוריים:

```
חדש:  "name  [word1; word2]   value"
ישן:   "name  [value]  word1, word2"
```

### ⚠️ עמודות bool = צ'קבוקסים → רק TRUE או ריק

| ערך בגיליון | ב-CSV |
|---|---|
| `TRUE` (מסומן) | `TRUE` |
| `FALSE` (לא מסומן) | **ריק** |
| תא ריק | **ריק** |

**למה גם `FALSE` יוצא ריק:** עמודות ה-bool בגיליון הן **צ'קבוקסים של Google Sheets**. צ'קבוקס לא מסומן מאחסן `FALSE` ליטרלי בתא — זו ברירת המחדל של העמודה, לא שיפוט של חוקר.

הנתונים בקורפוס (9.8.2026, 778 שורות, 36 עמודות צ'קבוקס) מוכיחים את זה:

- **33 עמודות**: `FALSE` בכל 778 השורות, בלי אף `TRUE`
- **3 עמודות**: `TRUE` אחד בדיוק בכל אחת
- **אף תא ריק** בשום מקום

לצ'קבוקס אין מצב שלישי, ולכן "נבדק ולא נמצא" פשוט לא ניתן לביטוי בעמודות האלה — רק סימון נושא מידע. ייצוא `FALSE` מילא כל CSV ב-~3,600 שליליים חסרי משמעות שנקראים כממצאים אמיתיים.

⚠️ **אם אי פעם צריך פיצ'ר תלת-מצבי אמיתי** — להגדיר לו עמודת `select` עם אופציה מפורשת "no", **לא** צ'קבוקס.

### פונקציות משותפות

```python
_csv_feature_header()              # שמות העמודות (ערך + example לכל פיצ'ר)
_csv_feature_cells(sheet_row, doc_id)   # התאים בסדר תואם
```

⚠️ **שלושת כותבי ה-CSV** (תוצאות חיפוש, תוצאות מסומנות, feature browse) שיכפלו בעבר את הלוגיקה inline — ולכן התיקון היה צריך להיעשות בשלושה מקומות. כולם עוברים עכשיו דרך שתי הפונקציות האלה. **אל תשכפל שוב.** טסט AI27 נכשל אם מופיע `'TRUE' if` יותר מפעם אחת בקובץ.

---

## מה הוסר (2026-08-08)

הפאנל **"🧬 Feature columns"** בסרגל הצד הוסר יחד עם הקוד שמאחוריו:

- `➕ Add a feature column` — מיותר מאז גילוי לפי prefix
- `🔧 Debug: inspect corpus row`
- `add_app_feature_def` / `remove_app_feature_def` / `_ensure_app_features_sheet`
- `get_unclaimed_headers` / `get_unresolved_features` / `debug_corpus_load`

`app.py` ירד מ-5109 ל-4748 שורות. הכל שחזיר מ-git history במידת הצורך.

**נשמר בכוונה:**

- `get_extra_feature_defs()` — הטאב עדיין נקרא
- `↺ Clear cache & reload` ו-`🔄 Reload corpus cache` — יושבים באותו סרגל אבל לא קשורים

⚠️ **לקח מהמחיקה הזו**: הבלוק ברמת המודול `FEATURE_DEFS = get_feature_defs()` ישב מיד אחרי `get_unclaimed_headers`, ומחיקה אוטומטית של הפונקציה בלעה גם אותו. הבדיקות תפסו את זה מיד. אם מוחקים פונקציה — **לוודא שלא נבלע איתה קוד ברמת המודול שיושב אחריה**. סקשן 3-4 ב-`tests_full.py` אוכף עכשיו גם שהמחיקה הושלמה וגם שהחלקים שהיו חייבים לשרוד אותה עדיין קיימים.

---

## תיוג BUT — דוגמאות נגד

פיצ'ר יכול להיות קיים בטקסט, ובכל זאת מילים מסוימות מראות שהוא **לא חל** עליהן. זה טיעון שונה מ"הפיצ'ר לא קיים", ולכן יש לו מנגנון נפרד.

### פורמט בשורת ה-FEATURES

```
LEX. "want"  [biddi ašrab]   bidd   BUT [widdi, waddi]
```

`FEAT_BUT_MARK = 'BUT'`, והביטוי `_BUT_RE` תופס את הסיומת.

### איפה זה נשמר

**במסמך בלבד** — כמו מילות הדוגמה. אין שינוי בגיליון ואין מיגרציה. הקריאה דרך `get_doc_feature_annotations()` (cached), עם שני wrappers:

```python
get_doc_feature_examples(doc_id)    # {name: "w1; w2"}
get_doc_feature_exceptions(doc_id)  # {name: "w1, w2"}
```

### ⚠️ הנקודה המסוכנת: שכתוב המסמך

`update_gdoc_features_section()` בונה מחדש את בלוק ה-FEATURES. אם היא לא מכירה את `BUT`, כל תיוג עתידי של אותו פיצ'ר **ימחק את החריגים בשקט**.

לכן הפרסר:

1. **מקלף את `BUT [...]` לפני** קריאת הערך — אחרת `bidd   BUT [widdi]` נקרא כערך
2. שומר אותו ב-`existing_buts[col_letter]`
3. **ממזג** חריגים חדשים לקיימים (לעולם לא מחליף)
4. פולט אותו מחדש בסוף השורה

טסטים AJ15–AJ21 אוכפים את כל ארבעת השלבים. אם נוגעים בבניית השורה — לוודא שהם עדיין עוברים.

### ממשק התיוג

ענף נפרד בתפריט הימני: **`⚠ BUT — exception`**, שמשקף את אותו עץ קטגוריות. נבחר במכוון ענף נפרד ולא פריט בתוך כל פיצ'ר ולא "מצב" (mode):

- הנתיב הרגיל של התיוג נשאר ללא שינוי — אפס סיכון רגרסיה במסלול שבשימוש תמידי
- אין state נסתר ששוכחים שהשאירו דלוק

הענף מחולק **לאותן ארבע קטגוריות** כמו התיוג הרגיל, כך ששני המסלולים מנווטים באותה צורה: `BUT → קטגוריה → פיצ'ר`. אין רמת ערכים — ב-BUT המילה **היא** התג, ולכן קליק אחד מספיק, גם לפיצ'רים מסוג select. תוצאות חיפוש מקבלות קיצור `⚠ mark as BUT` בשורה נפרדת.

⚠️ רשימת הקטגוריות נבנית מ-`GROUP_ORDER` + `UNGROUPED` **בשני המקומות**. טסט AJ24c אוכף שהיא מופיעה פעמיים — אם מוסיפים קטגוריה ומעדכנים רק את הענף הרגיל, היא תיעלם מ-BUT בשקט.

זרימת הנתונים: `storeTag(name, value, kind)` → `kind:'but'` → הגשר מנתב ל-`{sk}_pending_buts` (מצטבר) → `_render_submit_bar` מציג chips → `update_gdoc_features_section(..., exception_words)`.

⚠️ כל איפוס של `_pending_words` חייב לאפס גם `_pending_buts`, אחרת חריג שכבר נשלח ייכתב שוב בשמירה הבאה. טסט AJ31 אוכף שהספירות תואמות.

### CSV

עמודה שלישית לכל פיצ'ר: `<feature> — BUT`.

### סינון ב-Browse by feature

צ'קבוקס "only documents that have a BUT". זהו **post-filter על מסמכים שכבר התאימו** לחיפוש הפיצ'רים, לא שאילתה עצמאית — החריגים במסמכים ולא בגיליון, ולכן בדיקתם דורשת קריאת מסמכים. הגבלה לתוצאות (בד"כ כמה עשרות, בדרך כלל כבר ב-cache) שומרת על מהירות; סריקה של כל 778 המסמכים מראש לא הייתה.

---

## תיוג אוטומטי מטבלת התעתיק

בראש כל מסמך תעתיק יש טבלה:

```
يقول   | ديك \ ديوك | ثقيل | قهوة   | الآن
biʾūl  | dīk-dyūk   | tʾīl | Select | Select
```

`Select` = תא שלא מולא. הנתונים האלה קיימים במאות מסמכים אבל **כמעט לא הועברו לגיליון** (במצב שנסרק: `He is saying` ב-9 מתוך 778, `Coffee` ב-7, `Heavy` ב-**אפס**). לכן הטבלאות, לא הגיליון, הן מקור האמת.

### מיפוי וחוקים

`DOC_TABLE_FEATURE_MAP` ממפה כותרת ערבית → שם פיצ'ר. `derive_phon_from_table()` מיישם:

| חוק | תנאי | תוצאה |
|---|---|---|
| 1 | saying=`biʾūl` **וגם** coffee∈{ʾahwa,ʾahwe,ʾahwi} **וגם** heavy∈{tʾīl,ṯʾīl} | `PHON. *q` = `ʾ` |
| 2 | rooster = `dīk / dyūk` | `PHON. *k` = `k` |
| 3 | rooster = `dīč / dyūč` | `PHON. *k` = `č` |
| 4 | rooster = `dīč / dyūk` | `PHON. *k` = `k~č` |

⚠️ **חוקים 2–4 מוכרעים לפי איזה מבין k / č מופיע בכל חצי, לא לפי איות מדויק.** הקורפוס לא עקבי לא במפריד (מסמכים כותבים `dīk-dyūk`, הגיליון `dīk / dyūk`) ולא במקרון (קיימים גם `dyūk` וגם `dyuk`). ההבחנה שהחוק באמת נשען עליה היא העיצור.

אימות: ה-`PHON. *k` היחיד שתויג ידנית בקורפוס — `dīč / dyuk` → `k~č` — משוחזר בדיוק ע"י חוק 4.

### ⚠️ קנוניזציה מול אופציות העמודה

`canonicalise_table_value()` ממפה ערך מהטבלה לאופציה המתאימה ב-dropdown של העמודה, כדי שהתא יעמוד ב-data validation. ההשוואה **מתעלמת ממפרידים ורווחים אבל לא מאותיות** — `dyuk` ו-`dyūk` נשארים נפרדים, כי המקרון הוא הבחנה פונולוגית אמיתית וניחוש עליה היה ממציא נתונים.

ערך שלא תואם לאף אופציה **מדווח ולא נכתב**.

### זרימת העבודה

`🤖 Auto-tag from document tables` בסרגל הצד:

1. **Scan** — `scan_auto_tags()` קורא את כל המסמכים (מה-cache של `get_doc_content`, בלי קריאות API נוספות). **לא כותב כלום.** מחזיר: הצעות (עם הראיה לכל אחת), התנגשויות, ערכים לא מזוהים, ומסמכים בלי טבלה.
2. **Preview** — טבלה + הורדת CSV
3. **Apply** — דורש אישור שני; `apply_auto_tags()` כותב לגיליון ב-batchUpdate מקובץ (500 תאים לבקשה)

**התנגשות** = תא שכבר מכיל ערך אחר → מדולג ומדווח. תיוג אנושי מעיד על שיפוט שהחוקים אולי לא לוכדים.

**המסמכים עצמם לא נכתבים מחדש** — הראיה כבר נמצאת בטבלה שלהם, ושכתוב 700+ מסמכי Google היה מוסיף סיכון וזמן ריצה בלי להוסיף מידע.

---

## רעיונות UX שלא מומשו

לפי סדר עדיפות מוצע:

1. **הצגת היקף החיפוש לפני הרצה** — כיתוב `Will search 47 of 312 documents` מעל כפתור החיפוש. מונע הפתעות אחרי חיפוש ארוך.
2. **תצוגה מקדימה של תבנית** — שורה חיה מתחת לשדה: `^aCC matches: aktab, aḍrab…` מתוך מסמך אחד ב-cache. מאפשר אימות תבנית בשנייה במקום בדקה.
3. **היסטוריית חיפושים** — dropdown עם 10 התבניות האחרונות מ-session state. זול ליישום.
4. **חיפושים שמורים** — צרור מנוי של תבנית + פילטרים + מיקום, נשמר ל-tab בגיליון (כמו `AppFeatureDefs`).
5. **אחידות שפה בתוויות** — כרגע מצבי החיפוש באנגלית והפילטרים בעברית (`שם יישוב בתעתיק`). תוויות דו-לשוניות (`Village / יישוב`) הן פשרה סבירה.

---

## Session Context

- המשתמש: נעם קשי (`noam.kashi@mail.huji.ac.il`)
- המחקר: ניב ערבי פלסטיני
- הקורפוס: תמלילים ב-Google Docs, metadata בGoogle Sheets
- סביבת עבודה: macOS, repo מונטה ב-`/mnt/pai-search/`
