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

**כדי להוסיף feature column עם type/options ידועים**, הוסף שורה כאן.  
**כדי להוסיף feature column זמני** (ללא שינוי קוד), השתמש ב-"➕ Add a feature column" בסרגל הצד.

### `AppFeatureDefs` tab בגיליון
feature columns שנוספו דרך הממשק נשמרים כאן. מבנה: `header_text | display_name | type | options (;-separated)`.

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
get_unresolved_features()     ttl=600s
get_unclaimed_headers()       ttl=600s
load_corpus_index()           ttl=600s   — list of all recordings with metadata
get_doc_content()             ttl=3600s, persist="disk"  — Google Doc HTML
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
python tests_full.py     # 85 טסטים — רגרסיה כללית
python tests_deep.py     # 85 טסטים — feature-columns, cache, wildcards
python tests_search.py   # 247 טסטים — חיפוש, טקסט, מסמכים, UX, multi-value, chips
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
