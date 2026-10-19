
## What is it?

The NSS Classification Model (`nss-classification-model`) is a **per-hit binary classifier**.

For every sanctions watchlist hit on an alert, it answers one question:

> **Is this hit a True Positive (real match) or a False Positive (not a real match)?**

Output per hit:
- `decision = 0` → **True Positive** — escalate for human review
- `decision = 1` → **False Positive** — dismiss automatically

---

## Why a Classification Model? (And Why Not Something Else?)

This is the question most newcomers ask. The answer is rooted in the nature of the AML screening decision itself.

### The decision is binary by regulation

A sanctions screening outcome is not a score, a rank, or a generated explanation. A compliance officer must ultimately decide: **Yes, this is a real match** (block/review) or **No, this is not a match** (clear). There are only two outcomes. Binary classification is the natural fit.

### Why not regression?

Regression produces a continuous score (e.g. "0.73 similarity"). That is not what regulators or compliance workflows accept. You need a discrete decision: escalate or dismiss. You could threshold a regression score, but then you have just built a classifier the hard way, with an extra step and no gain.

### Why not ranking / similarity scoring only?

A pure similarity ranker would order hits by how likely they are to be real matches. Useful for search — not for automated clearing. NSS needs to **act**: dismiss the hit automatically if it is clearly a false positive. Ranking does not make decisions; classification does.

### Why not clustering / unsupervised?

Clustering groups unlabelled data. In sanctions screening you have explicit ground truth: every hit either truly matches the sanctioned entity or it does not. Supervision applies. Unsupervised methods provide no mechanism to incorporate that knowledge.

### Why not an LLM?

- **Latency**: LLMs take seconds per call. NSS processes thousands of hits per run. An LLM would make the pipeline orders of magnitude slower.
- **Determinism**: AML compliance requires reproducible, auditable decisions. LLMs are non-deterministic. The same input can produce different outputs across calls.
- **Auditability**: Every decision must cite a specific reason (name mismatch, date mismatch, etc.). The rule engine produces an exact `decision_rule` list. LLMs produce natural-language explanations that cannot be formally audited.
- **No training data required**: The model uses configured thresholds and rule logic — no labelled dataset needed to deploy.

### What the model actually is

Despite being called a "classification model", it is **not a statistical ML model** (no weights, no training, no gradient descent). It is a **deterministic rule engine** wrapped in the WorkFusion AutoML classification framework. Each field (name, date, address, gender, type, identifier) is scored independently, and a configured rule set decides the outcome.

This is intentional. Regulatory environments demand that decisions be fully explainable. A trained ML model (XGBoost, neural net) would be a black box that auditors cannot interrogate. A rule engine produces an exact trace: "hit cleared because name score 0.45 < strong_mismatch threshold 0.7".

---

## What the Model Compares

For each hit, the model compares the **screened entity** (the customer being checked) against the **watchlist entity** (the sanctions record). It does this across 6 fields, each independently scored:

| Field | Matcher | What it compares |
|-------|---------|-----------------|
| **Name** | `NameMatcher` — two impls (see below) | Full name, first/middle/last, aliases. Default: external `wf_name_matcher.UnifiedNameMatcher` (continuous score). Securities/companies: in-repo `AbstractNameMatcher` token-feature pipeline |
| **Address** | `AddressMatcher` | Country → State → City → Street (hierarchical); optional geo-distance in km |
| **Date** | `DateMatcher` | DOB/DOE — year/month/day proximity; handles partial dates |
| **Entity Type** | `EntityTypeMatcher` | PERSON vs ORGANIZATION |
| **Gender** | `GenderMatcher` | Normalized equality check |
| **Identifier** | `IdentifierMatcher` | Passport, tax ID, etc. — numeric normalization, match/mismatch lists |

Each field produces a match level:
- `STRONG_MATCH` — clearly the same
- `WEAK_MISMATCH` — probably not, but uncertain
- `STRONG_MISMATCH` — clearly different
- `BAD_INFO` — insufficient data to decide

---

## Decision Logic

The rule engine (`wfrules`) evaluates a configured rule set against the 6 field outcomes.

Example `rules_config.json`:
```json
{
  "rules": [
    {"name": "strong_mismatch"},
    {"date": "strong_mismatch"},
    {"name": "weak_mismatch", "location": "weak_mismatch"}
  ],
  "thresholds": {
    "name_strong_match": 0.8,
    "name_strong_mismatch": 0.7,
    "date_strong_match": 30,
    "date_strong_mismatch": 365
  }
}
```

Rules are OR-combined. Each rule entry is AND-combined across its fields.

```
if ANY rule fires → decision = 0 (True Positive, escalate)
if NO rule fires  → decision = 1 (False Positive, dismiss)
```

Wait — that seems backwards. It is not. The rules encode **grounds for clearance** (false positive conditions). If a rule fires it means a dismissal condition was met. The naming in the source inverts the sense:

```python
decision = 1 - int(bool(rules_result.first_matched_output))
# no rule matched → decision = 1 (True Positive, needs review)
```

---

## Model Internals (verified from `nss-classification-model` source)

Model repo version: `model.yml` → **5.2.2-dev** (the artifact NSS pins in its own `worker.yml`
may lag — verify per branch). Entry point `nss_model.app`; subclasses
`automl.sdk...ClassificationPipeline`.

### `_fit` is NOT training

`pipeline.py:_fit` loads labelled JSON docs (gold label under key `y` / `gold_value`), runs the
**same** `make_decision` over them, and writes evaluation/regression metrics. No weights are
learned. There is no trained state anywhere in the model. "Fit" = a regression/eval harness.

### Config-as-model — rebuilt per request

`ModelConfig` is constructed from `document["data"]["configuration"]` on **every** predict call.
`Model` is only rebuilt when the config actually changes, gated by a custom `ModelConfig.__eq__`
(`pipeline.py:50`, `model_config.py:59`) comparing thresholds, proximity, fields, rules, stopwords,
and the two `name_unm_*` flags. Same artifact → completely different behavior per tenant. The
"model version" is far less meaningful than the per-request config.

`ModelConfig` raises if `rules` is empty after cleaning (`model_config.py:31`) — empty/blank rule
entries are stripped first. `fields` keeps only entries whose value is a real `bool`.

### The ordinal verdict contract (`matching_decision.py`)

Every matcher, regardless of internals, emits one `MatchingDecision` IntEnum value:

```
NOT_COMPARED   = -2   # field disabled in config.fields
BAD_INFO       = -1   # insufficient data to judge
STRONG_MISMATCH=  0
WEAK_MISMATCH  =  1
STRONG_MATCH   =  2
```

This enum is the contract between the "perception" layer (6 matchers) and the "decision" layer
(rule engine). `model.py:apply_rules` lowercases each enabled field's verdict name into the dict
passed to `wfrules.predict_by_rule`.

### Per-matcher design (exact behavior)

| Matcher | Cross-product reduction | Verdict logic |
|---|---|---|
| **Name** | all input names × all hit names (incl. aliases), keep **max** score | continuous score bucketed: `< name_strong_mismatch` → STRONG_MISMATCH; `[mismatch, match)` → WEAK_MISMATCH; `≥ name_strong_match` → STRONG_MATCH. score `-1`→BAD_INFO, `-2`→NOT_COMPARED |
| **Date** | all input × all hit dates, keep **min proximity** (closest in days) | type-aware (DOB≠DOE → STRONG_MISMATCH if `enable_date_type`); year-only uses `incomplete_date_match_threshold`; else `abs(days)` bucketed by `date_strong_match` / `date_strong_mismatch` |
| **Identifier** | dict comparison; same value under different key still counts as match | counts-based: mismatch & no match → STRONG_MISMATCH; match & no mismatch → STRONG_MATCH; both → WEAK_MISMATCH. **TIN** uses edit-distance ≤ 1 (`areStringsAtMostOneDistanceApart`) |
| **Address** | hierarchical Country→State→City→Street; optional geo-proximity (km) | reference data from `country_dataset.csv` |
| **Gender / Type** | normalized equality | `individual`→`person`; entity type parsed in `Entity.parse_record_type` |

**Two name implementations** (`name_matcher_entrypoint.py`):
- **Default** → `wf_name_matcher.UnifiedNameMatcher` (external library; the only genuinely
  fuzzy/sophisticated component — NOT in this repo). Wraps name+type into a `NamePair`, returns
  `similarity_score`. Errors → score `-1`, BAD_INFO, source `'error'`. **Full writeup:
  [NAME_MATCHER.md](NAME_MATCHER.md).**
- **Securities only** (`entity_type == "securities"`) → in-repo `CompanyNameMatcher` /
  `AbstractNameMatcher`: tokenize → token cross-product → per-pair string-similarity features →
  greedy **top-3 non-overlapping** token pairs → **position-weighted mean** (1st pair ×4, 2nd ×2,
  3rd ×1, scaled by token length). Entirely hand-engineered, zero trained coefficients.

### Known correctness gaps in the matching core

`identifier_matcher.py:126` carries a developer `TODO: Potential bug?` — the zero-normalization
(`normalise_identifiers`) terminates after stripping leading **or** trailing zeros and mishandles
interior zeros (`000aaa00112200` → `aaa001122`, not `aaa1122`). This is in the path that decides
whether two tax IDs / passports match.

### Hardcoded rule override for location hits

`pipeline.py:57` — if `hit_entity.entity_type == "location"`, the configured rule set is ignored and
replaced with `[{'location': 'weak_mismatch'}]` for that hit. Baked into the engine, not configurable.

### Decision posture

Rules encode **grounds for clearance**, so the default (no rule fires) is **escalate to a human**
(`decision = 1`). The engine only auto-clears (`decision = 0`) when a configured discrepancy is
positively. Correct safety bias for AML: silence routes to a human, never to dismissal.
`decision_rule` (the keys of the matched rule) is the audit trace of *why* a hit was cleared.

---

### The two processors that wrap the model call

```
PrepareForMlProcessor      — builds the JSON document sent to the model
        |
        | DOCUMENT (JSON), MODEL_ID
        v
   Execute AutoML : Bridge  — WorkFusion JNW step that calls the Python model via IPC
        |
        | MODEL_RESULT (ClassificationModelResult)
        v
SaveModelResultsProcessor  — reads model output, builds AlertDecision + WleDecision per hit
```

### PrepareForMlProcessor (`prepare-for-ml-task`)

Reads `SCREENED_DATA` and `WLE_LIST` from the row, builds a `ModelDocument` JSON, and outputs it as `DOCUMENT` along with `MODEL_ID`.

Also enforces the **data pairs limit**. For each `(input, wle)` pair, data pairs = sum of cross-products across all enabled fields:

```
pairs_per_wle = (input_names × wle_names)
              + (input_dates × wle_dates)
              + (input_locations × wle_locations)
              + (input_identifiers × wle_identifiers)
              + (input_gender × wle_gender)      # 0 or 1 each
              + (input_type × wle_type)          # 0 or 1 each

total = sum across all WLEs
```

`input_names` counts the screened entity's main name + aliases that have at least one non-blank name field. Same logic applies to wle. If `total > MAX_MDP_PAIRS`, the model call is skipped entirely and the alert is routed to `save-model-results` with `DATA_PAIRS_LIMIT_EXCEEDED=true`. Those alerts get `NEED_REVIEW` with explanation "Please review manually. Alert is too big for automated processing."

### Execute AutoML: Bridge

WorkFusion platform step. Sends `DOCUMENT` to the running Python model worker (IPC). The Python side:

1. — starts `NssPipeline` as a bridge IPC server on worker startup
2. `NssPipeline._predict` — runs field matchers → rule engine → returns per-hit decisions
3. Result returned as `ClassificationModelResult` to Java

The model processes each WLE **independently**, one at a time (`pipeline.py`):

```python
result = []
for hit_entity in hit_entities:
    result_series = self.model.make_decision(input_entity, hit_entity)
    result.append(result_series.to_dict())
```

One `make_decision` call per WLE. The model never sees all WLEs together — each is an independent `(input, wle)` comparison.

Model artifact referenced in `worker.yml`: `nss-classification-model-v4.6.0`

---

## Model Document Format

`PrepareForMlProcessor` serializes `SCREENED_DATA` and `WLE_LIST` into a single JSON document. Structure (from `conftest.py` `document` fixture):

```json
{
  "data": {
    "input": {
      "id": "...",
      "uuid": "...",
      "type": "PERSON|ORGANIZATION",
      "gender": "MALE|FEMALE",
      "name": "...",
      "first_name": "...",
      "middle_name": "...",
      "last_name": "...",
      "aliases": ["..."],
      "addresses": [
        { "type": "citizenship|residence", "country": "...", "state": "...", "city": "...", "street": "..." }
      ],
      "dates": [
        { "type": "DOB", "year": "YYYY", "month": "MM", "day": "DD" }
      ],
      "identifiers": { "passport": "...", "tax_id": "..." }
    },
    "hits": [
      { /* same structure as input — one object per WLE */ }
    ],
    "configuration": {
      "thresholds": { "name_strong_match": 0.8, "name_strong_mismatch": 0.7, "date_strong_match": 30, "date_strong_mismatch": 365 },
      "rules": [ {"name": "strong_mismatch"}, {"date": "strong_mismatch"} ],
      "fields": { "name": true, "date": true, "location": true, "identifiers": true, "gender": true, "type": true },
      "stopwords": { "geographical": [...], "financial": [...] }
    }
  }
}
```

All WLEs are sent in the `hits` array in one document. The Python model then iterates them one by one.

---

### SaveModelResultsProcessor (`save-model-results-task`)

Reads `MODEL_RESULT`. For each hit in the response:
- Maps `decision` → `WleResolution` (FALSE_POSITIVE or MORE_INFORMATION_NEEDED)
- Maps field-level match results → `NameDecision`, `LocationDecision`, `DateDecision`, `GenderDecision`, `EntityTypeDecision`, `IdentifierDecision`
- Generates a human-readable `explanation` via `ModelExplanationProvider`
- Calculates a composite `score` via `MultiFactorScoringService`
- Assembles `AlertDecision` (overall resolution + list of `WleDecision`)

**Alert-level resolution** (`AlertResolution`) is derived from the WLE decisions:
- All hits `FALSE_POSITIVE` → `ALL_FP` → Firco gets `fpStatus`, alert cleared
- Any hit `MORE_INFORMATION_NEEDED` → `NEED_REVIEW` → Firco gets `nmiStatus`, escalated

---

## Full Pipeline Position

```
FircoMessageDetailsProcessor
        |
        | SCREENED_DATA (customer), WLE_LIST (hits)
        v
PrepareForMlProcessor       — data pairs check, build DOCUMENT JSON
        |
        v
Execute AutoML : Bridge     — Python NssPipeline, IPC call
        |
        v
SaveModelResultsProcessor   — parse per-hit decisions, build AlertDecision
        |
        | ALERT_DECISION
        v
ScreeningSystemReportProcessor — write decision back to Firco Trust via SOAP
```

---

## Configuration Fields Relevant to the Model

| Config path | What it controls |
|-------------|-----------------|
| `configuration.ml.model_id` | Override model artifact version |
| `configuration.ml.max_data_pairs` | Pairs limit; 0 = unlimited |
| `configuration.rules.fields.name` | Enable name comparison |
| `configuration.rules.fields.location` | Enable location comparison |
| `configuration.rules.fields.date` | Enable date comparison |
| `configuration.rules.fields.identifiers` | Enable identifier comparison |
| `configuration.rules.fields.gender` | Enable gender comparison |
| `configuration.rules.fields.type` | Enable entity type comparison |
| `configuration.reports.explanation_narratives` | Include all field narratives in explanation |
| `configuration.reports.explanation_missing_data` | Include missing-data notes in explanation |

---

## Key Source Locations

| File | What it does |
|------|-------------|
| | `NssPipeline._predict` — top-level model entry point |
| | Applies rule engine to field match results |
| `nss-classification-model/nss_model/field_matcher/name/` | Name scoring (`wf_name_matcher` + textdistance/metaphone) |
| `nss-classification-model/nss_model/field_matcher/address/` | Address hierarchical + proximity matching |
| `nss-classification-model/nss_model/field_matcher/date/` | Date proximity matching |
| | IPC bridge server startup |
| | Builds document, enforces data pairs limit |
| | Parses model result, builds AlertDecision |
| | Generates human-readable explanation text |
| | Composite alert score calculation |
