# wf_name_matcher — The Name Matching Library

What `wf_name_matcher` is, how it works, and how NSS uses it. This is the
**single genuinely sophisticated matching component** in the whole NSS stack — every other
field comparator (date, address, identifier, gender, type) is simple arithmetic or set logic.
The "intelligence" people imagine the NSS model has, lives here.

> Cross-ref: `MODEL_INTEGRATION.md` (how the model wraps this) and `nss_model/field_matcher/name/
> name_matcher_entrypoint.py` (the NSS-side caller).

---

## 1. What it is (and is not)

- **External libraryversion **1.2.4shipped to the model repo as a wheel:
  Source is **not** in either NSS repo — unpack the wheel to read it.
- It is **NOT a trained ML model.** No weights, no training, no dataset fitting. It is a
  **hand-engineered ensemble** of string-similarity features + curated reference lists +
  a large amount of name-specific heuristic logic (nicknames, legal forms, acronyms, middle
  names, transliteration). Deterministic and explainable, like the rest of NSS — just far more
  elaborate.
- Dependencies (from wheel METADATA): `textdistance==4.6.0` (edit distance), `metaphone==0.6`
  (phonetic), `anyascii==0.3.2` (transliteration), `pydantic==1.10.13` (schemas). Also bundles a
  FastAPI app so it *can* run as a standalone service, but NSS calls it in-process.

---

## 2. The contract — input and output

NSS calls it via `UnifiedNameMatcher.predict(name_pair)`:

```python
from wf_name_matcher.matching.matcher import NameMatcher as UnifiedNameMatcher
from wf_name_matcher.matching.config import NameMatcherConfig
from wf_name_matcher.matching.schemas import NamePair, Name

matcher = UnifiedNameMatcher(NameMatcherConfig(match_if_token_overlap=..., ignore_middle_names=...))
out = matcher.predict(NamePair(
    name1=Name(value="John Smith",  type="person"),   # screened (input)
    name2=Name(value="Jon Smyth",   type="person"),   # WLE (watchlist hit)
))
out.similarity_score   # float, ~0.0–1.0  ← the ONLY field NSS reads
out.is_match           # bool (library's own verdict)  ← NSS IGNORES this
```

**`NameType`** (`schemas.py`): `organization`, `person`, `vessel`, `aircraft`, `location`,
`other` (DEFAULT). Unknown type strings coerce to `other`. Person names > 100 chars and other
names > 200 chars raise a validation error.

**Important — two threshold layers:** the library computes its own `is_match` using its internal
`match_threshold` (0.75). **NSS ignores `is_match`** and re-buckets the raw `similarity_score`
against the *customer-configured* `name_strong_match` / `name_strong_mismatch` thresholds to get
STRONG_MATCH / WEAK_MISMATCH / STRONG_MISMATCH (see `name_matcher_entrypoint.py:calculate_decision`).
So the library's own pass/fail line is effectively dead in the NSS path; only the continuous score
matters.

**Error handling (fail-safe):** `BaseNameMatcher.predict` wraps everything in try/except; on any
exception it returns `similarity_score = -1, is_match = True`. NSS maps score `-1` → `BAD_INFO`.
The bias on failure is toward *escalation*, never toward silently clearing.

---

## 3. Type routing — three sub-matchers

`NameMatcher` holds three engines and routes per pair (`matcher.py:_select_matcher`):

| Engine | Used when | Specializes in |
|---|---|---|
| `IndividualNameMatcher` | name type = `person` | nicknames, first/middle/last, phonetics, misspelling |
| `OrganizationNameMatcher` | name type = `organization` (also default fallback) | legal forms, acronyms, abbreviations, bank/securities terms |
| `LocationNameMatcher` | name type = `location` | country/city names, ISO codes |

Routing is decided by **the WLE name's type (`name2`) first**, falling back to the screened name's
type (`name1`), and finally to the **organization** engine by default. `vessel` / `aircraft` /
`other` therefore run through the org engine.

(Note: NSS only uses this library for the *default* path. For `entity_type == "securities"` NSS
bypasses it entirely and uses its own in-repo `CompanyNameMatcher` — see `MODEL_INTEGRATION.md`.)

---

## 4. Top-level flow — normalization candidates, take the max

`NameMatcher.predict` (`matcher.py:189`) does **not** score the pair once. It builds several
**normalization variants** of the pair, scores each through the type-specific engine, and returns
the variant with the **highest** similarity:

1. the original pair
2. **camelCase** → lowercased ("JohnSmith" handling)
3. **bracket-stripped** ("Acme (Holdings) Ltd" → "Acme Ltd")
4. **quote-normalized** (`'` and `` ` `` → space)
5. **alias-split** — if a name contains an alias indicator (`t/as`, `trading as`, `aka`,
   `a.k.a.`, `also known as`), it splits into
   main + alias and scores **both halves** against the other name
6. **deduplicated tokens** (person only) — drops repeated tokens ("John John Smith" → "John Smith")

This "generate many cleanings, keep the best" pattern is the library's headline strategy. It trades
compute for recall: any reasonable normalization that makes the names line up will win.

---

## 5. The per-engine scoring (BaseNameMatcher)

Each engine's `predict` returns `max(predict_base_output, predict_main_flow)`:

### 5a. Base output — whole-name char similarity
`predict_base_output` (`base.py:540`) strips spaces and compares the names as single concatenated
strings via character similarity (scaled by `concatenated_coefficient` 0.9). If the two are
character-multiset-identical it short-circuits to 1.0. This catches token-boundary disagreements
("VanDerBerg" vs "Van Der Berg").

### 5b. Main flow — token-level optimal assignment
`predict_main_flow` (`base.py:567`) is the core. It:

1. **Preprocesses** both names (Processor — see §7), producing a cleaned, stopword-stripped form,
   plus a variant that *keeps* ambiguous stopwords, plus a "general-only" fallback when a name is
   stopwords-only.
2. For each variant, calls `calculate_similarity` (engine-specific).
3. Returns the best-scoring variant (ties broken toward the longer name). The ambiguous-kept variant
   is scaled ×0.99; the stopwords-only fallback ×0.98 — small nudges so cleaner matches win ties.

**Token similarity matrix + assignment** (`_generate_pairs_scores`,
`_calculate_sum_of_token_similarities`): every screened token is scored against every WLE token
(cross product) using the character features; then a **greedy-with-branching optimal assignment**
maps screened tokens → WLE tokens to maximize the summed similarity (it recurses to resolve ties).
Final score = `sum_of_matched_similarities / min(#screened_tokens, #wle_tokens)`.

### 5c. Token-pair features
`_compute_matching_score` = **max** over the active feature functions:

| Feature | Returns | What it catches |
|---|---|---|
| `damerau_levenshtein_sim` | normalized 0–1 | general typo/edit similarity |
| `is_short_prefix` | 0.95 / 0 | abbreviations ("Wm" → "William"; prefix ≤70% of full) |
| `is_misspelled` *(person)* | 0.98 / 0.95 / 0 | plural forms, same-sound subs ({c,k,q},{s,z},{v,w}), edit-distance-1 |
| `is_phonetically_identical` *(person)* | 0.95 / 0 | Double Metaphone phonetic match ("Smith"/"Smyth") |

### 5d. Penalties (what pushes scores *down*)
- **Strongly-mismatched token** present (score ≤ `strong_mismatch_threshold` 0.4) → ×`weak_mismatch_score` (0.7), unless there's a perfect/abbrev match on an *uncommon* token.
- **Unmatched tokens** (length differs) → decaying penalty (`_get_unmatched_penalty`).
- **Acronym mismatch** (one side has initials the other doesn't account for) → penalty.
- **Match on a single common word / stopword only** → penalty (so "International Bank" vs
  "International Holdings" doesn't score high just on "International").
- Frequency-aware: `freq_dist.json` distinguishes common vs rare tokens; a perfect match on a *rare*
  token is treated as strong evidence and can suppress the mismatch penalty.

---

## 6. IndividualNameMatcher — person-specific logic

The richest engine (`individual.py`). On top of the base flow:

- **First/last exact match with order inversion** (`_check_exact_first_last_match`): if first & last
  match (directly or swapped) → `identical_names_score` (0.99). Uses nickname expansion on the
  first name.
- **Middle-name handling** (`_handle_middle_name_matching`): missing middle on one side → still
  ~identical; middle initials matching full middle names; middle-name subset; repeated first name
  ("John John Smith"). Whether middle names matter is controlled by `ignore_middle_names` (NSS maps
  this from `name_unm_enable_middle_name_matching`).
- **Nicknames**: "Bob"↔"Robert", "Pepe"↔"Jose". A nickname
  hit scores `nicknames_coefficient` (0.98).
- **Short names** (`short_names.txt`): protects genuinely short names from being treated as acronyms.
- **Known-different pairs** (`different_name_pairs.txt`): curated list of name pairs that look
  similar but are known to be *distinct people-names*. Such a pair is force-scored **0.2**
  (`_compute_matching_score` override) and disables the base/concatenation shortcuts. This is the
  hand-maintained "do not let these fuzzy-match" override.

`OrganizationNameMatcher` and `LocationNameMatcher` follow the same skeleton with their own resource
lists (legal forms, acronyms, bank/securities/currency terms; country/city/ISO respectively).

---

## 7. Preprocessing

Before scoring, names are cleaned by `Processor`:

- **Transliteration** to ASCII (`anyascii`) — "Müller" → "Muller", Cyrillic → Latin.
- **Lowercase**, strip punctuation, normalize spelled-out numbers.
- **Strip legal forms** via `legal_form_mapping.json` (Inc, Ltd, GmbH, S.A., LLC, …) — and track
  whether the two names' legal forms are *different* (a bank "PLC" vs "GmbH" signal).
- **Strip stopwords**, with a careful ambiguous-vs-preserved distinction: a term removed from one
  name but kept (meaningful) in the other is excluded from removal so the comparison stays fair.
- **Geo-term removal** for org/company names (country/city names, ISO codes) — so "Acme USA" vs
  "Acme" still matches — but NOT for location-type names.

All driven by curated resource files under `wf_name_matcher/resources/`:
 (abbreviations, acronyms, words, ngrams, bank terms, securities, currencies, legal forms),
 (stopwords, nicknames, short names, different-name pairs),
 (country names, city names, ISO2/3 codes, forms of state),
 (freq_dist.json, stopwords, alias indicators).

---

## 8. Configuration (`NameMatcherConfig`)

Defaults that govern the scoring. NSS only overrides two of these (the rest are library defaults):

| Field | Default | Meaning |
|---|---|---|
| `match_if_token_overlap` | `none` | none / rare / screened / rare_and_screened — when token overlap alone counts as a match. **NSS sets this** from `name_unm_match_if_token_overlap` |
| `ignore_middle_names` | `False` | skip middle-name comparison. **NSS sets this** (inverted) from `name_unm_enable_middle_name_matching` |
| `match_threshold` | 0.75 | library's own is_match cutoff (**NSS ignores**) |
| `weak_match_threshold` | 0.95 | upper band |
| `strong_mismatch_threshold` | 0.4 | below this, a token is a strong mismatch → penalty |
| `weak_mismatch_score` | 0.7 | penalty multiplier |
| `nicknames_coefficient` | 0.98 | score for a nickname hit |
| `concatenated_coefficient` | 0.9 | scale for whole-name concatenated comparison |
| `identical_names_score` | 0.99 | score for first/last exact (incl. inversion) |
| `strong_name_match_score` | 0.95 | strong-match score |
| `match_base_for_penalties` | 0.9 | floor when applying length penalties |
| `max_acronym_lenght_person` / `_company` | 3 / 5 | token length treated as a potential acronym |
| `frequency_thresold_to_consider_common` | 10 | freq_dist cutoff for "common token" |
| `min_length_for_misspelled` | 3 | min length to apply misspelling features |

---

## 9. How it fits the NSS decision (recap)

```
NSS PrepareForMlProcessor → document JSON (input + hits + config)
        │
        ▼ (per input-name × hit-name, cross product — NSS side)
wf_name_matcher.UnifiedNameMatcher.predict(NamePair)
        │  returns similarity_score (continuous)
        ▼
NSS keeps the MAX score across all name pairs (name_matcher_entrypoint.py:45)
        │
        ▼ NSS calculate_decision() buckets the score:
   score < name_strong_mismatch          → STRONG_MISMATCH
   name_strong_mismatch ≤ s < name_strong_match → WEAK_MISMATCH
   score ≥ name_strong_match             → STRONG_MATCH
   score == -1 → BAD_INFO ;  -2 → NOT_COMPARED
        │
        ▼
NSS rule engine (wfrules) consumes the ordinal verdict, not the float.
```

So the library produces the **fuzzy float**; NSS owns the **thresholds** and the **decision**.
Re-tuning name behavior for a customer is done with the NSS `name_strong_*` thresholds, not by
touching this library — but the *quality ceiling* (what can match at all: transliteration,
nicknames, acronyms, phonetics, legal forms) is set entirely here, in `wf_name_matcher`.
