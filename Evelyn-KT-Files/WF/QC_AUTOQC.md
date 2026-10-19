# QC and AutoQC — Names Screening

How Quality Control (QC) and Automatic Quality Control (AutoQC) work end-to-end in NSS.

Checked against the code (`AutoQcService`, `QcReportProcessor`, `QcReportContextBuilder`, `FircoTrustService`, `WorldCheckOneProvider`, `SelectForManualReviewProcessor`).

---

### QC Report
A CSV file written to S3 containing every screened alert (one row per watchlist hit) with full field-level detail: screened entity data, watchlist entity data, model scores, and per-hit decisions. Used by compliance teams and auditors to review NSS's automated decisions.

### AutoQC
A **sampling mechanism** that marks a subset of `ALL_FP` alerts for mandatory manual review, even though the ML pipeline classified them as false positives. The purpose is statistical quality assurance: ensure the model is not silently under-performing by spot-checking its FP decisions.

The two features are related: every alert that goes through the pipeline gets its `auto_qc` flag saved to the database, and that flag appears as a column in the QC Report CSV.

---

## 2. The AutoQC Flag — Lifecycle

```
SaveModelResultsProcessor
    └── Sets AlertDecision (resolution, WLE decisions with scores)
            │
            ▼
AlertReportProcessor           ← determines AUTO_QC here
    └── AutoQcService.isSelectedForAutoQC()
    └── Outputs AUTO_QC (boolean) in row map
            │
            ▼
ScreeningSystemReportProcessor ← reads AUTO_QC, changes Firco/WC1 decision routing
            │
            ▼
SelectForManualReviewProcessor ← reads AUTO_QC, can override routing to MT
            │
            ▼
HtmlReportProcessor, QcReportProcessor (if automatic)
            │
            ▼
FinishTransactionProcessor     ← persists AUTO_QC into QcReportData DB table
            │
            ▼
SendResultsBackToCallerProcessor ← includes isAutoQc in REST response
```

`AUTO_QC` is a boolean carried in the JNW row map under key `"auto_qc"` (defined in `ProcessingAttributes.AUTO_QC`).

---

## 3. AutoQcService — Selection Algorithm

**File:**

### Hard guard: only ALL_FP alerts qualify

```java
if (ALL_FP.equals(alertDecision.getResolution()) && autoQcEnabled) {
    // ... selection logic
}
return false;  // ALL other resolutions → never selected
```

If the alert resolution is `NEED_REVIEW`, `NO_HITS`, or `ALL_FP` with `autoQcEnabled=false`, AutoQC returns false immediately. Only fully-cleared false positive alerts are candidates.

### Mode 1 — Simple rate (DISCRETE_AUTO_QC = false)

```java
double autoQcProportion = config.getProperty(AUTO_QC_RATE, Double.class).orElse(0.0) / 100;
return isSendOnQcReview(autoQcProportion);
```

`AUTO_QC_RATE` is entered as a percentage (e.g. `5` = 5%). Divided by 100 before use.

`isSendOnQcReview`:
```java
if (autoQcProportion > 0.0) {
    return secureRandom.nextDouble() <= autoQcProportion;
}
return false;
```

Uses `SecureRandom` — not `Math.random`. A rate of 0 always returns false.

### Mode 2 — Discrete risk matrix (DISCRETE_AUTO_QC = true)

Only activates when `inputCategory` from `ScreenedData` is non-empty.

**Step 1 — Score the alert's mismatch level**

```java
double maxScore = alertDecision.getWleDecisions().stream()
    .mapToDouble(WleDecision::getScore)
    .min()          // ← min, not max (lowest score = worst match = highest mismatch)
    .orElse(0.0);
maxScore = maxScore == 0.0 ? 0.0 : 1.0 - maxScore;
```

`WleDecision.score` is a similarity score (higher = better match). The code takes the **minimum** similarity across all WLE decisions, then inverts it to get a mismatch score. A 0.0 similarity is kept as 0.0 (special case, avoids 1.0 - 0.0 = 1.0 for a no-data hit).

**Step 2 — Classify the mismatch score into a Score tier**

```java
double strongMismatchThreshold = config.getRequiredProperty(NAME_STRONG_MISMATCH_THRESHOLD, Double.class);
double highScore  = config.getProperty(HIGH_RISK_SCORE,   Double.class).orElse(0.0) / 100;
double mediumScore = config.getProperty(MEDIUM_RISK_SCORE, Double.class).orElse(0.0) / 100;
double lowScore   = config.getProperty(LOW_RISK_SCORE,    Double.class).orElse(0.0) / 100;

if (alertMaxScore >= strongMismatchThreshold - highScore)   → Score.HIGH_SCORE
else if (alertMaxScore >= strongMismatchThreshold - mediumScore) → Score.MEDIUM_SCORE
else if (alertMaxScore >= strongMismatchThreshold - lowScore)    → Score.LOW_SCORE
else → Score.DEFAULT_SCORE
```

`NAME_STRONG_MISMATCH_THRESHOLD` is a model threshold (from `ThresholdConfiguration` — typically ~0.7). The risk score offsets define a band below the threshold:
- `HIGH_RISK_SCORE=10` → band width 0.10 below threshold
- Wider band = more alerts classified as HIGH_SCORE

**Step 3 — Classify the input category**

```java
if (highRiskCategories.contains(inputCategory))   → Category.HIGH_CATEGORY
else if (mediumRiskCategories.contains(inputCategory)) → Category.MEDIUM_CATEGORY
else if (lowRiskCategories.contains(inputCategory))    → Category.LOW_CATEGORY
else → Category.DEFAULT_CATEGORY
```

`HIGH_RISK_CATEGORIES` is a `List<String>` from config. The match is case-sensitive (uses `Set.contains`).

**Step 4 — Look up the grid rate**

```java
String key = riskScore.name() + "_" + riskCategory.name() + "_RATE";
// e.g. "HIGH_SCORE_HIGH_CATEGORY_RATE"
NssConfiguration nssConfiguration = NssConfiguration.fromKey(key);
Optional<Double> rate = configuration.getProperty(nssConfiguration.getPath(), Double.class);
```

The key maps to a `NssConfiguration` enum entry, which maps to a path like `configuration.auto_qc.auto_qc_grid.high_score_high_category`. If the grid entry is absent, the default `AUTO_QC_RATE` is used as fallback.

**Full 3×3 grid (plus DEFAULT):**

| | HIGH_CATEGORY | MEDIUM_CATEGORY | LOW_CATEGORY | DEFAULT_CATEGORY |
|---|---|---|---|---|
| **HIGH_SCORE** | `high_score_high_category` | `high_score_medium_category` | `high_score_low_category` | ← uses AUTO_QC_RATE |
| **MEDIUM_SCORE** | `medium_score_high_category` | `medium_score_medium_category` | `medium_score_low_category` | ← uses AUTO_QC_RATE |
| **LOW_SCORE** | `low_score_high_category` | `low_score_medium_category` | `low_score_low_category` | ← uses AUTO_QC_RATE |
| **DEFAULT_SCORE** | ← uses AUTO_QC_RATE | ← uses AUTO_QC_RATE | ← uses AUTO_QC_RATE | ← uses AUTO_QC_RATE |

---

## 3.5 Per-Alert Decision, Per-Hit Rows — the `auto_qc` analysis trap

**The decision is made ONCE per alert, but the QC report has one row per hit.** The single alert-level flag is copied onto every hit row. This mismatch is the #1 source of "AutoQC is over-selecting in the low bracket" false alarms (e.g. EXPERT-38002).

The chain:

1. `AlertReportProcessor` calls `AutoQcService.isSelectedForAutoQC(...)` **once per alert**. The alert's score bracket comes from its **worst** hit — `1 - min(WleDecision.score)` — so a multi-hit alert is classified by its single most-borderline hit.
2. That boolean is persisted as **one** `autoQcIndicator` per transaction (`QcReportData.autoQcIndicator` → `ReportRawData.autoQcIndicator`, one per alert).
3. `QcReportService` emits **one row per hit** (`for (WleData wle : wles)`, `QcReportService`), calling `ReportRowAssembler.buildRowData(...)` per hit.
4. `ReportRowAssembler` stamps that same alert-level flag onto every hit row (`isSelectedForQC = reportRowData.autoQcIndicator` → `auto_qc = "Y"/"N"`, `ReportRowAssembler.java:91,135-136`). Every hit of a selected alert shows `Y`; every hit of a non-selected alert shows `N`.

**Why per-hit rate analysis looks wrong.** Each hit row also carries its own per-hit `decision_score` (= that hit's `WleDecision.score`, `ReportRowAssembler.java:173`). If you bucket hit rows by their own Real Score (`1 - decision_score`) and compute the `Y` rate per bucket, the rates will **not** match the configured grid, because:

- An alert selected on its worst hit (say HIGH bracket, 100%) contributes its *other*, lower-score hits as `Y` rows in the LOW/DEFAULT buckets.
- Most real multi-hit alerts span more than one bracket, so low-score buckets inherit `Y`s "earned" in higher buckets → the low bracket looks inflated (a configured 30% can measure as ~40%+). The sub-threshold **DEFAULT bucket, configured at 0%, still shows non-zero `Y` per hit** — a dead giveaway that this is the measurement artifact, not a selection bug.

**To verify configured rates, deduplicate to one row per alert first:** group by `transaction_uuid` (`auto_qc` is constant within an alert), classify each alert by its **max** Real Score (`= 1 - min(decision_score)` across its hits), then compute the `Y` rate per bracket. Per alert, the rates match the grid.

---

## 4. AlertReportProcessor — Where AUTO_QC Is Set

**File:**
**Task ID:** `alert-report-task`

```java
AlertDecision alertDecision = Optional.ofNullable(input.getValueAsType(ALERT_DECISION, AlertDecision.class))
    .orElse(new AlertDecision().setId(screenedData.getId()));

// Only set resolution/explanation if SaveModelResultsProcessor didn't (MDP exceeded case)
if (alertDecision.getResolution() == null) {
    alertDecision.setResolution(alertDecisionService.getAlertResolution(wleData.size(), needMoreInfoCount, isFilteredTransaction));
}
if (alertDecision.getExplanation() == null || alertDecision.getExplanation().isBlank()) {
    alertDecision.setExplanation(alertDecisionService.getAlertExplanation(...));
}

var selectedForAutoQC = autoQcService.isSelectedForAutoQC(configuration, alertDecision, screenedData);
analyticsService.updateAlertDecision(transactionUuid, alertDecision.getResolution().name(), alertDecision.getExplanation(), selectedForAutoQC);
```

Key points:
- Resolution is set here only if `SaveModelResultsProcessor` did not set it (normal path). When `DATA_PAIRS_LIMIT_EXCEEDED=true`, the resolution was already set in `SaveModelResultsProcessor` and is preserved.
- `analyticsService.updateAlertDecision` records AutoQC in the analytics table at this step.
- Outputs: `ALERT_DECISION` (updated), `AUTO_QC` (boolean), `TRANSACTION_ID`.

---

### 5.1 Firco Trust write-back (ScreeningSystemReportProcessor → FircoTrustService)

**File:**

**Status routing** (`getStatusToUpdate`):

| Resolution | selectedForAutoQc | Status sent to Firco |
|---|---|---|
| `ALL_FP` | `false` | `fpStatus` (alert closed as false positive) |
| `ALL_FP` | `true` | `nmiStatus` (pushed back for human review) |
| `NEED_REVIEW` / any | either | `nmiStatus` |

An AutoQC-selected alert is deliberately routed to NMI so a human reviewer sees it in Firco, even though NSS classified it as ALL_FP.

**Comment messaging** (`getMessageComment`) — AutoQC is the **first** branch, so it wins over parallel production:

```java
if (selectedForAutoQc) {
    return new CommentAndUpdateStatus(INPUT_EXPLANATION_SELECTED_FOR_AUTO_QC, false);
}
if (!updateEnabled) {
    return new CommentAndUpdateStatus(INPUT_EXPLANATION_PROCESSING_FOR_PARALLEL_PRODUCTION, false);
}
// otherwise: readable resolution + explanation, updateEnabled stays true
```

The constant text is `"This alert was selected for auto QC, please review alert."`. Returning `updateEnabled=false` does two things: `getStatusToUpdate` then sends `nmiStatus` (it only sends `fpStatus` when resolution is `ALL_FP` **and** `updateEnabled` is still true), and the per-hit CSV attachment is skipped.

**Attachment (per-hit hits report CSV)**:
- Only attached if `updateEnabled=true` AND `!selectedForAutoQc`
- AutoQC-selected alerts never get the CSV attachment

### 5.2 World-Check One write-back

`WorldCheckOneProvider.buildResultsResolutionAction` treats AutoQC the same as parallel production, not as Firco's NMI status:

| | status | risk | remark |
|---|---|---|---|
| `parallelProd` or `autoQc` | `UNSPECIFIED` | `UNKNOWN` | parallel-production text, or the AutoQC text when it is AutoQC |
| `ALL_FP` (normal) | configured `fpStatus` | configured `fpRisk` | alert explanation |
| `NEED_REVIEW` (normal) | configured `nmiStatus` | configured `nmiRisk` | alert explanation |

WC1 update only runs when `WORLD_CHECK_ONE_UPDATE_ENABLE=true` and `resolution != NO_HITS`.

### 5.3 Manual Task routing (SelectForManualReviewProcessor)

**File:**

```java
boolean mtEnableAutoQc = configuration.getProperty(MT_AUTO_QC.getPath(), Boolean.class).orElse(false);
boolean selectedForAutoQc = taskInputData.getValueAsType(AUTO_QC, Boolean.class);
if (mtEnableAutoQc && selectedForAutoQc) {
    return true;
}
```

Config path: `manualTask.enable_auto_qc`.

This check sits **after** the category lists and **before** the decision criteria, and only on the default criteria path:

1. `manualTask.criteria = DISABLE_ALL` — AutoQC is ignored. Only a request-level `mt_force=true` sends the alert to MT.
2. `ENABLE_ALL` — every alert goes to MT, AutoQC or not.
3. Default path: an **enabled** category returns true first. A **disabled** category returns false **before** the AutoQC check, so a disabled category blocks the WorkFusion MT even when the alert was sampled. AutoQC then forces MT only for alerts that are in neither list. Decision criteria (`ENABLE_FP` / `ENABLE_NMI`) are the last fallback.

Firco NMI write-back is independent of this flag. `manualTask.enable_auto_qc` only controls the WorkFusion manual-task UI.

### 5.4 REST response (SendResultsBackToCallerProcessor)

**File:**

External REST response includes `isAutoQc` field:

```java
AlertResponse alertResponse = new AlertResponse()
    ...
    .setIsAutoQc(isAutoQc);
```

Internal BP-to-BP pass-through preserves `AUTO_QC` in the row map unchanged.

Optional: if `INCLUDE_QC_REPORT_IN_REST_RESPONSE=true` (`configuration.include_qc_report_in_rest`), the processor downloads the QC report CSV from S3 and injects it as `qcReportBody` (JSON array of row objects) directly in the REST response.

---

## 6. Database Persistence — QcReportData

**File:**
**Table:** `ds_uc_B_AML_PEP_qc_report_data_v3_0`

```java
@Entity
@Table(name = "ds_uc_B_AML_PEP_qc_report_data_v3_0")
public class QcReportData {

    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    @Column(length = 36, nullable = false, unique = true)
    private UUID uuid;             // Jakarta entity — no @Type("uuid-char")

    @Column(name = "client_id", nullable = false)
    private String clientId;

    @Column(length = 36, nullable = false)
    private UUID bpRunId;

    @Column(length = 36, nullable = false, unique = true)
    private UUID transactionId;    // unique — one row per transaction

    @Lob @Column
    private String screenedDataJson;  // Gson JSON of ScreenedData

    @Lob @Column
    private String wleList;           // Gson JSON array of WleData[]

    @Lob @Column
    private String alertDecision;     // Gson JSON of AlertDecision

    @Column(columnDefinition = "BOOLEAN")
    private Boolean autoQcIndicator;  // null or true/false
}
```

**Populated :** `FinishTransactionProcessor.populateQcReportDataTable`

```java
qcReportDataRepository.save(new QcReportData()
    .setClientId(screenedData.getClientId())
    .setTransactionId(transactionUuid)
    .setBpRunId(executionUtils.getBPRunId())
    .setScreenedDataJson(gson.toJson(screenedData))
    .setWleList(gson.toJson(wleDataList))
    .setAlertDecision(gson.toJson(alertDecision))
    .setAutoQcIndicator(autoQcIndicator));  // false if AUTO_QC was null
```

Guarded by `DataIntegrityViolationException` catch — if the same transaction is already in the table (retry scenario), logs a warning instead of failing.

### QcReportDataRepository

```java
List<QcReportData> findByBpRunId(UUID bpRunId);
QcReportData findByTransactionId(UUID transactionId);  // returns null if not found — known issue
```

**Known issue:** `findByTransactionId` should return `Optional<QcReportData>` to be null-safe. Currently returns bare reference.

---

### 7.1 Triggers

Two config flags both have to be true before the main BP even calls this processor. `WaitForCompletionProcessor` sets `automatic_report = configuration.reports.csv.enable && configuration.reports.csv.automatic_generation`. The "Automatic report?" gateway skips the QC sub-process when that flag is false. The step runs only on the **master** transaction, after `wait-for-completion`. See MAIN_BP_FLOW.md.

| Trigger | How `ReadContext` is built |
|---|---|
| **Main BP** | `wait-for-completion` puts `bp_uuid` = current BP run id on the row. That short-circuits `readAndNormalize`: `isAutomatic=true`, `isRest=false`, no time window, `hasAnyOtherParam=false`. |
| **Standalone QC Report BP** | No `bp_uuid`. Caller passes `business_process_ids` / `variations` / a time range (or those come from configuration). `isAutomatic=false`. |
| **REST** | Body is a `RestRequest`. Same shape as the standalone path, plus `isRest=true`. `isAutomatic=false`. |

`isAutomatic` is **only** the `bp_uuid` path. It is what decides whether analytics gets the S3 link (`updateCsvReportLink`) and which token is used in the file name (below). The standalone BP is not automatic.

### 7.2 QcReportProcessor

**File:**
**Task ID:** `qc-report`
**Annotations:** `@SendResultToCaller(true)` — the result goes back to the caller (a BP or a REST client), but only when that caller is synchronous. In the main BP, this is how `qc_reports` returns from the QC Report BP: the main BP calls it through the synchronous "Qc Report Sub-process" (`qc-signal-id`). See MAIN_BP_FLOW.md "How results reach a caller".

```java
ReadContext ctx = qcReportContextBuilder.readAndNormalize(taskInputData, bpConfiguration);
Optional<String> validationError = qcReportContextBuilder.validate(ctx);
if (validationError.isPresent()) {
    return buildErrorResponse(validationError.get());  // 200 status, error body
}

QCReport qcReportDetails = qcReportGenerator.generateCsvReport(bpConfiguration, ctx, masterTransaction);

if (ctx.isAutomatic()) {
    analyticsService.updateCsvReportLink(qcReportDetails.getReportLinks(), transactionDataProvider.getTransactionIds(ctx));
}
```

`extRecordId` is not a generator argument. `QcReportContextBuilder` reads `request_id`, unwraps quotes, and stores it on `ReadContext.exRecordId`. The master transaction UUID is used only as the report timestamp (`TransactionService.findMasterTransactionDate`), not as a row filter.

**What `validate` actually returns as a 200 body:** variations are set, no BP UUIDs, and no time window. The `bp_uuid` path (`hasAnyOtherParam=false`) skips this check. BP UUIDs alone, with or without a time range, are valid.

**What throws inside `readAndNormalize` instead** (`IllegalArgumentException`, not the 200 body): more than one non-zero `last_x_*`, `start_time` without `end_time`, `start_time` not strictly before `end_time`, or a negative `last_x_*`. A value of `0` does **not** count toward the "only one" check, and hours are applied before days before months. So `last_x_hours=0` together with `last_x_days=5` silently uses the current-hour window and ignores the days.

**Output:**
- REST mode: `RestResponse(gson.toJson(qcReports), 200, headers)`
- Non-REST: `QC_REPORTS` (QCReport object with S3 links)

### 7.3 ReadContext — Input resolution priority

**File:**

Priority order in `readAndNormalize`:
1. `bp_uuid` in input row → single-BP automatic mode (no time window)
2. REST request body (`RestRequest.REQUEST_FIELD_NAME`) present → parse REST body
3. `business_process_ids` or `variations` in input data → use those + time fields from input
4. None of the above → read from configuration (`configuration.reports.csv.data_collection_settings.*`)

**Special variation handling:** if any variation ID equals `"current"` (case-insensitive), it is resolved to the actual running variation ID via `executionUtils.getVariationId`.

**Time range formats (explicit start/end):**
- `MM/dd/uuuu HH:mm:ss`
- `uuuu-MM-dd HH:mm:ss`

**Time range shortcuts:**
- `"today"` → midnight to end of current calendar day
- `last_x_hours=N` → now minus N hours to now (0 = current hour start)
- `last_x_days=N` → now minus N days to now (0 = today midnight)
- `last_x_months=N` → now minus N months to now (0 = first day of current month)

### 7.4 QcReportGenerator → QcReportService → S3

```
QcReportGenerator.generateCsvReport()
    ├─→ headerServiceFactory.getService(config) → HeaderService
    ├─→ headerService.generateHeaders(ctx) → HeaderInfo
    ├─→ qcReportService.generateReport() → List<String> (S3 URLs)
    └─→ qcFormatFileService.generateFormatFile() → String (format file S3 URL)
        ↓
    QCReport(reportLinks, formatFileLink)
```

**QcReportService.generateReport:**

1. Checks if there are transactions to process — returns `["Qc report is empty"]` if none.
2. Builds header list.
3. Gets `masterTransactionDate` from `TransactionService` (file timestamp only).
4. Creates `CsvConfig` via `CsvConfigFactory`:
   - `AUTO_QC_REPORT_SIZE` (megabytes, default 50 MB) — the file is split into multiple S3 parts if it exceeds this size
   - Name suffix is `exRecordId` when `isAutomatic`, otherwise the **current** BP run id (`CsvConfigFactory.resolveSuffix`). That is the opposite of "BP id when automatic".
   - Default pattern: `{prefix}QC_Names-Screening-{suffix}-{yyyy-MM-dd_HH-mm-ss}`. If `configuration.keep_input_file_name_for_qc_report=true`, the suffix is the file name itself (extension stripped) and the timestamp is omitted.
5. Opens `CsvStreamingWriter` (writes to a local temp file, uploads to S3 on close).
6. Cursor-based batch fetch of **COMPLETED** transactions joined to `QcReportData`. With no time window (the main-BP path) the filter is BP uuid plus `extRecordId` when that id is non-blank; a blank id matches every transaction in those BPs. With a time window the filter is BP uuid plus `startTime`, and `extRecordId` is not applied. Variation queries require a window.
7. For each `ReportRawData` row:
   - Parses JSON: `ScreenedData`, `WleData`, `AlertDecision`
   - If WLEs present: one CSV row per WLE hit (matched with its `WleDecision` by UUID)
   - If no WLEs: one CSV row with null WLE fields

**Important:** `AUTO_QC_REPORT_SIZE` is in **megabytes** (not transaction count). The `CsvStreamingWriter` splits output into multiple S3 files if the accumulated bytes exceed `DataSize.ofMegabytes(reportSize).toBytes()`.

---

## 7.5 Input-Compatible vs Non-Input-Compatible QC Report

Controlled by `INPUT_COMPATIBLE_QC` (`configuration.reports.csv.input_compatible_qc`). Changes three things: column structure, number of passes through the data, and which header/builder service pair is used.

### Column structure

**Non-input-compatible (default, `false`):**

Fixed, flat schema. Identifiers and additional data are aggregated into pipe-separated strings.

```
bp_uuid, transaction_uuid,
input_id, input_full_name, input_country, input_date, input_gender, input_type,
input_identifiers ("Passport = 1234 | Id = 000-11111"),
input_additional_data ("key = value"),
hit_id, hit_matched_name, hit_country, hit_date, ...,
model_decision, alert_decision, ...
```

**Input-compatible (`true`):**

Expanded, dynamic schema. Every alias, address component, date, identifier key, and additional-data key gets its own column. Column counts are determined by scanning the data before writing.

```
bp_run_id, transaction_uuid,
input_full_name, input_first_name, input_last_name,
input_alias1_name, input_alias2_name, ...,          ← one column per alias
input_address_1_street, input_address_1_city, input_address_1_country, ...,
input_date_full_1, input_date_type_1, ...,
input_Passport_identifier, input_TaxId_identifier, ...,
input_<key>_extdata, ...,
hit_matched_name, hit_alias1_name, ...,
hit_address_1_street, ..., hit_Passport_identifier, ...,
auto_qc, model_decision, alert_decision, ...
```

### Two-pass vs single-pass generation

**Non-input-compatible — single pass:**
Headers are known upfront from `StaticHeaderBuilder`. CSV is written in one scan.

**Input-compatible — two passes (logged as "Phase 1/2" and "Phase 2/2"):**
- **Phase 1/2 — Header discovery:** Iterates all transaction batches via `CsvHeaderDiscoveryService`. Finds which fields are populated and the maximum alias/address/date count across all rows.
- **Phase 2/2 — Writing CSV:** Iterates the same data again, writing rows using the discovered header set.

### Service pair

| Mode | Header service | Builder |
|------|---------------|---------|
| `false` | `FixedHeadersService` | `StaticHeaderBuilder` |
| `true` | `DynamicHeadersService` | `HeaderBuilder` |

Selected by `HeaderServiceFactory` / `HeaderBuilderServiceFactory` based on the config flag.

### Purpose

**Non-input-compatible** is faster (single pass, fixed schema). Used for internal audit/compliance review.

**Input-compatible** is designed so the CSV can be fed back into NSS or a compatible ingestion system as-is. Every piece of input data gets its own column matching the ingestion file schema — the report is machine-readable as an input file. The two-pass approach guarantees no column is absent even when different transactions have different numbers of aliases or addresses.

`QcFormatFileService` writes the companion format file (`nss_column` → `client_column`) **only** in input-compatible mode and only when there is at least one transaction. Otherwise `qcFormatFileLink` is an empty string. Decision columns (`auto_qc`, `model_decision`, `alert_decision`, scores, gold resolutions, `bp_run_id`, `transaction_uuid`, `hit_uuid`) are left out of the format file.

---

## 8. QC Report CSV Structure

Columns depend on configuration. The base ordering is:

```
bp_run_id
transaction_uuid
[ScreenedData fields: input_id, input_name, input_first_name, input_last_name, ...]
[Provider-specific input fields:]
  - Firco:  record_matching_string, list_matching_string, firco_business_unit, firco_unit, firco_system_id, firco_message_id
  - WC1:    case_system_id, wc1_group_id
  - CSV:    gold_decision (input)
[WleData fields: hit_id, hit_name, hit_first_name, ...]
[Provider-specific hit fields:]
  - CSV:    gold_decision (hit)
auto_qc                    ← header present only if AUTO_QC_ENABLE=true; value written only on hit rows ("Y"/"N"). No-hit rows skip this column and write alert_decision "No hits" (see §3.5)
model_decision
model_explanation
alert_decision
name_similarity            ← per-hit name score (WleDecision.nameDecision.score)
[If CSV_REPORT_ALL_FIELDS=true:]
  name_match, location_match, date_match, gender_match, type_match, identifier_match
alert_explanation
decision_score             ← per-HIT similarity (WleDecision.score); Real Score = 1 − decision_score
[If FlattenAliases enabled:]
  input_names_calculated, input_dates_calculated, input_location_calculated, ...
  hit_names_calculated, hit_dates_calculated, hit_location_calculated, ...
```

The `auto_qc` column values come from `ReportRawData.autoQcIndicator`:
- `Boolean.TRUE` → `"Y"`
- `Boolean.FALSE` or `null` → `"N"`

---

## 9. Configuration Reference

All paths are under `configuration.*` in `configuration.json`.

### AutoQC Configuration

| Config path | NssConfiguration enum | Type | Description |
|---|---|---|---|
| `configuration.auto_qc.enabled` | `AUTO_QC_ENABLE` | Boolean | Master on/off switch. Default false |
| `configuration.auto_qc.rate` | `AUTO_QC_RATE` | Double (0–100) | Default sampling rate as percent. Used in simple mode and as fallback in discrete mode |
| `configuration.auto_qc.discrete_auto_qc` | `DISCRETE_AUTO_QC` | Boolean | Enable risk matrix mode. Default false |
| `configuration.auto_qc.high_risk_categories` | `HIGH_RISK_CATEGORIES` | List<String> | Category values from ScreenedData that classify as HIGH |
| `configuration.auto_qc.medium_risk_categories` | `MEDIUM_RISK_CATEGORIES` | List<String> | MEDIUM category values |
| `configuration.auto_qc.low_risk_categories` | `LOW_RISK_CATEGORIES` | List<String> | LOW category values |
| `configuration.auto_qc.high_risk_score` | `HIGH_RISK_SCORE` | Double (0–100) | Offset below strong-mismatch threshold defining HIGH score band (as percent) |
| `configuration.auto_qc.medium_risk_score` | `MEDIUM_RISK_SCORE` | Double (0–100) | MEDIUM score band |
| `configuration.auto_qc.low_risk_score` | `LOW_RISK_SCORE` | Double (0–100) | LOW score band |
| `configuration.auto_qc.auto_qc_grid.high_score_high_category` | `HIGH_SCORE_HIGH_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.high_score_medium_category` | `HIGH_SCORE_MEDIUM_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.high_score_low_category` | `HIGH_SCORE_LOW_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.medium_score_high_category` | `MEDIUM_SCORE_HIGH_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.medium_score_medium_category` | `MEDIUM_SCORE_MEDIUM_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.medium_score_low_category` | `MEDIUM_SCORE_LOW_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.low_score_high_category` | `LOW_SCORE_HIGH_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.low_score_medium_category` | `LOW_SCORE_MEDIUM_CATEGORY_RATE` | Double (0–100) | Grid cell rate |
| `configuration.auto_qc.auto_qc_grid.low_score_low_category` | `LOW_SCORE_LOW_CATEGORY_RATE` | Double (0–100) | Grid cell rate |

### QC Report Configuration

| Config path | NssConfiguration enum | Type | Description |
|---|---|---|---|
| `configuration.reports.csv.enable` | `ENABLE_CSV_REPORT` | Boolean | Required. ANDed with automatic generation to produce the `automatic_report` gateway flag |
| `configuration.reports.csv.automatic_generation` | `REPORT_AUTOMATIC_GENERATION` | Boolean | Main BP calls the QC sub-process only when this and `csv.enable` are both true. Default false |
| `configuration.reports.csv.auto_qc_report_size` | `AUTO_QC_REPORT_SIZE` | Double | Max single file size in **megabytes** before splitting. Default 50 MB |
| `configuration.keep_input_file_name_for_qc_report` | `KEEP_INPUT_FILE_NAME_FOR_QC_REPORT` | Boolean | Use the name suffix as the file name. On the automatic path that suffix is `request_id` |
| `configuration.reports.csv.input_compatible_qc` | `INPUT_COMPATIBLE_QC` | Boolean | Enable input-compatible QC header mode (two-phase generation) |
| `configuration.reports.csv.data_collection_settings.time_range` | `REPORT_GENERATION_TIME_RANGE` | String | "today" or null |
| `configuration.reports.csv.data_collection_settings.time_range_hours` | `REPORT_GENERATION_TIME_RANGE_HOURS` | String | N hours back |
| `configuration.reports.csv.data_collection_settings.time_range_days` | `REPORT_GENERATION_TIME_RANGE_DAYS` | String | N days back |
| `configuration.reports.csv.data_collection_settings.time_range_months` | `REPORT_GENERATION_TIME_RANGE_MONTHS` | String | N months back |
| `configuration.reports.csv.data_collection_settings.date_from` | `REPORT_GENERATION_TIME_RANGE_DATE_FROM` | String | Explicit start (MM/dd/yyyy HH:mm:ss) |
| `configuration.reports.csv.data_collection_settings.date_to` | `REPORT_GENERATION_TIME_RANGE_DATE_TO` | String | Explicit end |
| `configuration.reports.csv.data_collection_settings.bp_ids` | `REPORT_GENERATION_BP_IDS` | List<String> | BP UUIDs to include |
| `configuration.reports.csv.data_collection_settings.variations` | `REPORT_GENERATION_VARIATIONS` | List<String> | Variation IDs to filter |
| `configuration.include_qc_report_in_rest` | `INCLUDE_QC_REPORT_IN_REST_RESPONSE` | Boolean | Include downloaded CSV body in REST response as JSON array |

### Manual Task AutoQC Config

| Config path | ManualTaskConfiguration enum | Type | Description |
|---|---|---|---|
| `manualTask.enable_auto_qc` | `MT_AUTO_QC` | Boolean | If true, AutoQC-selected alerts are routed to manual review regardless of other MT criteria |

---

## 10. QC Report BP

**Files (4.4.0 line — two zips are currently in the tree, which breaks the "exactly one BP zip" rule):**

Single-step BP. Contains one `<campaign>` pointing to `qc-report` task processor.

**Run inputs (passed as BP input parameters):**
- `business_process_ids` — list of UUIDs or comma-separated string
- `variations` — list of variation IDs or comma-separated string
- One time range: `last_x_hours`, `last_x_days`, `last_x_months`, `start_time`+`end_time`, or `"today"` (from config)
- Optional: `request_id` — for REST

**Output:** QCReport JSON with `reportLinks` (list of S3 URLs) and `qcFormatFileLink`.

---

## 11. Key classes

| Class | What it does |
|------|-------------|
| `AutoQcService` | Core selection logic — simple rate and risk matrix |
| `AlertReportProcessor` | Calls AutoQcService, sets AUTO_QC in row, updates analytics |
| `ScreeningSystemReportProcessor` | Reads AUTO_QC, routes to Firco/WC1 |
| `SelectForManualReviewProcessor` | Reads AUTO_QC, can force MT routing |
| `FinishTransactionProcessor` | Persists AUTO_QC to QcReportData DB table |
| `SendResultsBackToCallerProcessor` | Includes isAutoQc in REST AlertResponse |
| `QcReportProcessor` | Entry point for QC report generation |
| `QcReportGenerator` | Orchestrates headers + CSV + format file |
| `QcReportService` | Core CSV writing: batch fetch, per-row assembly, S3 upload |
| `QcReportContextBuilder` | Parses and normalizes report inputs (bp_ids, time range, REST body) |
| `ReportRowAssembler` | Builds one CSV row from ScreenedData + WleData + AlertDecision |
| `CsvConfigFactory` | Builds CsvConfig: file name, bucket, split size |
| `FircoTrustService` | Status routing + comment logic with AutoQC branch |
| `QcReportData` | JPA entity for qc_report_data table |
| `QcReportDataRepository` | `findByBpRunId`, `findByTransactionId` |
| `NssConfiguration` | All config paths as enums (AUTO_QC_* entries) |
| `ProcessingAttributes` | `AUTO_QC = "auto_qc"` row map key |
| `ManualTaskConfiguration` | `MT_AUTO_QC = "manualTask.enable_auto_qc"` |
| `ResponseConstants` | `INPUT_EXPLANATION_SELECTED_FOR_AUTO_QC` string constant |

---

## 12. Edge Cases and Gotchas

**AutoQC never fires for non-FP alerts.** The `ALL_FP` check is the first gate. `NEED_REVIEW`, `NO_HITS`, and MDP-exceeded alerts (which also get `NEED_REVIEW`) are never candidates.

**When DISCRETE_AUTO_QC=true but inputCategory is blank**, the code short-circuits and uses the default `AUTO_QC_RATE` instead of the matrix. Check: `StringUtils.isNotEmpty(inputCategory)`.

**The mismatch score uses `.min()`, not `.max()`** on WLE scores. This is intentional: take the worst (most borderline) match among all hits and use that to classify the alert's risk.

**Grid rate lookup returns `Optional.empty()` if the grid entry is absent from config.** In that case the code falls back to `AUTO_QC_RATE` (the default rate). If `AUTO_QC_RATE` is also 0, selection never fires.

**`AUTO_QC_REPORT_SIZE` is in megabytes** (not transaction count, not rows). Passed through `DataSize.ofMegabytes(reportSize.longValue()).toBytes()`. Default = 50 MB.

**`FinishTransactionProcessor` guards against duplicate QcReportData rows** with `DataIntegrityViolationException` catch. If a transaction retries and the row was already persisted on a prior attempt, it logs a warning and continues. The constraint is the `unique = true` on `transactionId`.

**`QcReportDataRepository.findByTransactionId` returns a bare `QcReportData` (not Optional)** — null if not found. This is a known code quality issue.

**Firco comment for AutoQC overrides parallel production.** In `getMessageComment` the `selectedForAutoQc` branch is **first**. It returns the fixed AutoQC string and forces `updateEnabled=false`, so the parallel-production branch never runs. Status then follows that flag: `fpStatus` only for `ALL_FP` with `updateEnabled` still true.

**A disabled manual-task category beats AutoQC.** `SelectForManualReviewProcessor` returns false for `MT_DISABLED_ALERT_CATEGORY` before it looks at `manualTask.enable_auto_qc`. `DISABLE_ALL` never looks at AutoQC at all.

**`last_x_*=0` is invisible to the "only one range" check** and hours win over days and months. Combining `last_x_hours=0` with another range does not error; it uses the current-hour window.

**On-demand reports do not update the analytics CSV link.** `updateCsvReportLink` runs only when `ReadContext.isAutomatic` is true, which is only the `bp_uuid` path.

**AutoQC-selected alerts sent to Firco as NMI even when ALL_FP.** This is by design — a sampled alert must be reviewed, so it cannot be automatically closed in Firco as a false positive.
