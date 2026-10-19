
## Overview

Firco Trust (TCMAPI) is an external sanctions screening system that holds alerts (messages) pending a decision.
NSS connects to it via **SOAP/HTTPS** — the `fircosoft-trust` client artifact (`com.workfusion.dw:fircosoft-trust:2.6`)
provides pre-generated JAXWS stubs. All wire traffic is XML. NSS downloads pending alerts, screens them through
its ML pipeline, and writes the decision back to Firco Trust.

The integration spans two modules:
- **`names-screening-firco-trust-connector`** — SOAP client wrapper, data conversion, format file handling
- **`names-screening-jnw`** — three `@TaskProcessor` classes that orchestrate the flow as JNW workflow steps

---

## The mental model — Firco is the queue, NSS is the reviewer

Read this first. Most wrong assumptions about the Firco provider start here.

**NSS does not screen names against Firco.** Firco has already done the matching and is
sitting on a pile of alerts awaiting a human decision. NSS logs , asks Firco for the alerts
that are still uncleared / in progress, and plays the reviewer: for each alert it decides
**False Positive** or **Need More Information**, then writes that decision back to Firco.

Nothing is ever pushed *to* NSS, and NSS never submits an entity to be screened. That makes
Firco fundamentally different from the CSV and WorkFusion-API inputs, where the caller hands
NSS the names to screen and NSS goes looking for hits.

### What the operator configures

The `fircoFields` fieldset in
— rendered in the DW config wizard **only** when Input = "Screening system" and
Screening system = "Firco Trust":

| Config key | Wizard label | Role |
|---|---|---|
| `provider.firco_trust_endpoint` | API URL | Host of the Firco Trust Case Manager API |
| `provider.firco_trust_inventory_port` | API port | TCMAPI inventory port (4 digits, default `5519`) |
| `provider.firco_trust_alias` | Credentials location | Secrets-vault key (default `nss.fircotrust.credentials`) |
| `provider.firco_trust_b_unit` | Firco Trust business unit | Single value — **which** slice of alerts to pull |
| `provider.firco_trust_unit` | Firco Trust unit | Tags → array — one or more units under that business unit |
| `provider.firco_trust_nmi_status` | 'Need More Information' update status | Name of the Firco status meaning "needs review" (default `PENDING`) |
| `provider.firco_trust_fp_status` | 'False Positive' update status | Name of the Firco status meaning "cleared" (default `FALSE`) |

**Business unit + unit(s) are the entire selection mechanism.** Every BP run pulls Firco's
whole pending inventory, keeps only the messages matching the configured business unit and
unit list, drops any `systemId` already in `firco_trust_messages`, and screens what remains.
A blank business unit or an empty unit list means "don't filter on it".

**The two status names exist because each Firco installation defines its own workflow
statuses.** NSS cannot guess which one means "cleared" — the operator names them, and
`FircoTrustConverter.resolveNextStatuses` looks those names up in the alert's own
`NextStatuses` list. See "SOAP Operations → receiveMessageRequest" below.

### The REST trigger is not a data input

`DownloadFircoMessagesProcessor` accepts a REST body (`FircoRequest`) that overrides
`firco_trust_business_unit` / `firco_trust_unit` for that run only, and stamps
`externalRecordId` on the pulled messages. **The alerts still come from Firco's inventory** —
a caller cannot feed entities into a Firco run. Do not confuse this with `INPUT_TYPE=API`,
which is a separate input path where the caller supplies the names to screen.

Practical consequence: `REQUEST_ID` / `_sys_ext_record_id` are not declared on the
`firco-message-details` input contract, so REST-request-status bookkeeping is effectively
inert from that step onward.

---

## The Three Processors — and Why Three?

Each processor owns one phase of the pipeline. They cannot be merged without coupling unrelated concerns.

| # | Processor | Scope | JNW type |
|---|-----------|-------|----------|
| 1 | `DownloadFircoMessagesProcessor` | Pull inventory — one SOAP call, save stubs to DB | Non-schema-based (single output row) |
| 2 | `FircoMessagesBatchProcessor` | Dequeue DB rows in batches, create transactions, fan out | Schema-based (N output rows) |
| 3 | `FircoMessageDetailsProcessor` | Fetch full message per alert, filter hits, build domain objects | Schema-based (one row per alert) |

**Why not one processor?**
- Inventory (step 1) runs once per BP run — fetching the list is a single SOAP call unrelated to per-alert work.
- Batching (step 2) controls pagination and retry across multiple executions — it reads the DB cursor, not Firco.
- Details (step 3) runs once per alert row — its SOAP call (`getMessageById`) and heavy conversion logic
  belong at the per-message level where JNW can parallelise across workers.
- Error isolation: a bad message in step 3 doesn't abort the entire run.

---

## SOAP Operations

All calls go through `FircoTrustClient` (generated JAXWS proxy from `fircosoft-trust` artifact).

### 1. `receiveInventoryRequest` → `getInventoryMessages`

Called by: `FircoTrustService.getMessagesMetaInfo`

Returns stubs — no full message content:

```xml
<msg_ResponseReceiveInventoryRequest>
  <Messages>
    <Message>
      <Unit>CIF1</Unit>
      <BusinessUnit/>            <!-- optional -->
      <MessageID>00000012</MessageID>
      <SystemID>CIF1!6509398F-6CEAEF9F-1E7D31AC-A79089A1</SystemID>
    </Message>
    ...
  </Messages>
</msg_ResponseReceiveInventoryRequest>
```

### 2. `receiveMessageRequest` → `getMessageById`

Called by: `FircoTrustService.getFircoMessage(FircoMetaData)`

Returns the full `SendMessage` object:

```xml
<SendMessage>
  <Message>
    <CustomerInfo>
      <Name>AL-BARAKAT INTERNATIONAL</Name>
      <Account>123654789</Account>
      <City>PARIS</City>
      <Country>FRANCE</Country>
      <State/>
      <DateOfBirth/>
      <UserData1/>
      <UserData2/>
    </CustomerInfo>
    <MessageData>123654789|AL-BARAKAT INTERNATIONAL||PARIS|FRANCE|C</MessageData>
    <!-- ^ pipe-delimited; mapped via format file CSV -->
    <Hits>
      <Hit>
        <SolutionType>1</SolutionType>      <!-- 1=NAME, other=LOCATION -->
        <EntityText>BARAKAT INTL</EntityText>
        <MatchingText>AL-BARAKAT INTERNATIONAL</MatchingText>
        <HittedEntity>
          <ID>EURO000342</ID>
          <Type>O</Type>                   <!-- O=Org C=Company I=Individual P=Person -->
          <Batch>2022/02/11_000000001_CIF1</Batch>
          <!-- or: OBSOLETE-2022/02/11_000000001_CIF1 -->
          <Names>
            <Name>AL-BARAKAT INTERNATIONAL</Name>
            <Name>BARAKAT INTL</Name>
          </Names>
          <Addresses>
            <Address>
              <City>PARIS</City>
              <State/>
              <Country>FRANCE</Country>
              <PostalAddress/>
            </Address>
          </Addresses>
          <DatesOfBirth>1960-01-01;1961-06-15</DatesOfBirth>
        </HittedEntity>
      </Hit>
    </Hits>
    <NextStatuses>
      <Status>
        <ID>1</ID>
        <Name>FALSE</Name>
        <RoutingCode>2</RoutingCode>
        <Checksum>...</Checksum>
      </Status>
      <Status>
        <ID>4</ID>
        <Name>PENDING</Name>
        <RoutingCode>12</RoutingCode>
        <Checksum>...</Checksum>
      </Status>
    </NextStatuses>
  </Message>
</SendMessage>
```

`NextStatuses` lists **all valid transitions** for that specific alert. A real Firco installation
can have many statuses — not just two:

```xml
<NextStatuses>
  <Status><ID>1</ID><Name>FALSE</Name><RoutingCode>2</RoutingCode></Status>
  <Status><ID>4</ID><Name>PENDING</Name><RoutingCode>12</RoutingCode></Status>
  <Status><ID>7</ID><Name>REVIEW</Name><RoutingCode>5</RoutingCode></Status>
  <Status><ID>9</ID><Name>ESCALATE</Name><RoutingCode>8</RoutingCode></Status>
</NextStatuses>
```

NSS does not know which of these means "false positive" and which means "needs review" — that
mapping is a per-installation agreement. The configuration bridges the two:

```
FIRCO_TRUST_FP_STATUS  = "FALSE"    → when decision is FP,  pick the NextStatus named FALSE
FIRCO_TRUST_NMI_STATUS = "PENDING"  → when decision is NMI, pick the NextStatus named PENDING
```

`FircoTrustConverter.resolveNextStatuses` uses those names as a search key into the list
(case-insensitive match on `Status.Name`). It throws `FircoTrustFaultException` if either
configured name is not found — fail-fast before the ML pipeline runs rather than at write-back.

Each resolved status is stored as `"ID--NAME--RoutingCode"` (double-dash separator) in
`FircoMetaData` and travels through the entire BP via the output row, ready for
`ScreeningSystemReportProcessor` to build the `receiveStatusUpdate` SOAP call.

### 3. `receiveStatusUpdate` → `updateMessageStatus`

Called by: `FircoTrustService.updateMessageStatus(...)` → invoked from `ScreeningSystemReportProcessor`

```xml
<Message>
  <MessageID>00000012</MessageID>
  <SystemID>CIF1!6509398F-6CEAEF9F-1E7D31AC-A79089A1</SystemID>
  <Unit>CIF1</Unit>
  <BusinessUnit>BUNIT</BusinessUnit>
  <Operator>WORKFUSION</Operator>
  <Comment>False Positive. No match found.</Comment>
  <Status>
    <ID>1</ID>
    <Name>FALSE</Name>
    <RoutingCode>2</RoutingCode>
    <Checksum>md5_of_status_string</Checksum>
  </Status>
  <!-- Optional attachment -->
  <Attachment>
    <Name>00000012_workfusion_report_20240115T143022.csv</Name>
    <Contents>Base64_encoded_csv_here</Contents>
    <Comments>WORKFUSION. CIF1!... Hits detailed report.</Comments>
  </Attachment>
</Message>
```

Attachment CSV (Base64-decoded):
```
"HIT_ID","RESOLUTION","EXPLANATION"
"EURO000342","0","false positive — no match to customer"
"OFAC006954","1","review needed — partial name match"
```
- `0` = FALSE_POSITIVE, `1` = MORE_INFORMATION_NEEDED

---

## Processor 1 — `DownloadFircoMessagesProcessor` (`download-firco-messages`)

**JNW type**: Non-schema-based — single empty output row.

### Steps

1. Read connection config from UI (`FIRCO_TRUST_ENDPOINT`, `FIRCO_TRUST_INVENTORY_PORT`, `FIRCO_TRUST_ALIAS`); read business unit / units from UI unless a REST request body (`FircoRequest`) overrides them.
2. Call `FircoTrustService.init(alias, endpoint, port, bUnit)` — loads credentials from secrets vault, builds `ConfigurationProvider`.
3. Call `FircoTrustService.getMessagesMetaInfo` → SOAP `receiveInventoryRequest` → list of message stubs (systemId, messageId, unit, businessUnit).
4. Filter the list:
   - By `businessUnit` (if configured or from REST request)
   - By `unit` / units list (if configured or from REST request)
   - Skip messages whose `systemId` already exists in the `firco_trust_messages` table (deduplication)
5. Save filtered stubs to DB with `status = NEW`, tagged with current `bpRunId` and `externalRecordId` (REST request ID).
6. Return a single empty output row — this step is a trigger, not a per-message step.

---

## Processor 2 — `FircoMessagesBatchProcessor` (`firco-messages-batch`)

**JNW type**: Schema-based — emits one row per alert plus control rows.

### Steps

1. Read `FircoConfiguration` from DB (batchSize default 2000, waitTime default 2 s).
2. **Retry check**: If input row has `RETRY=true`:
   - Look up `FircoRetryMonitor` by `RETRY_UUID`.
   - If `retry=true` → set `retry=false`, call `reprocessAfter(waitTime)`, return early.
3. Query a page of `NEW` messages from `firco_trust_messages` scoped to current `bpRunId` + `externalRecordId`, page size = batchSize.
4. For each message in the page:
   - Create a `Transaction` via `TransactionService.startNewTransaction`
   - Initialise alert analytics via `AnalyticsService.initAlertAnalytics`
   - Update message `status → PROCESSING`, store `transactionId`
   - Build `FircoMetaData` (systemId, messageId, unit, businessUnit, uuid, extRecordId)
   - Emit output row: `FIRCO_MESSAGE_META_DATA` + `TRANSACTION_ID` + `STOP=false` + `RETRY=false`
5. Pagination logic after the loop:
   - **Page full (returned == batchSize)**: More messages may remain → create `FircoRetryMonitor` record, emit extra row with `RETRY=true`, `RETRY_UUID`.
   - **Page not full**: Last page → emit `STOP=true`.
   - **Zero messages total**: Emit `STOP=true`, `NO_ALERTS=true`.

---

## Processor 3 — `FircoMessageDetailsProcessor` (`firco-message-details`)

**JNW type**: Schema-based — one row per alert.

### Steps

1. Read `FircoMetaData` and `TRANSACTION_ID` from the input row (produced by step 2).
2. Re-initialise `FircoTrustService` using the business unit from the metadata.
3. Call `FircoTrustService.getFircoMessage(metaData)` → SOAP `receiveMessageRequest` → full `SendMessage`.
4. Call `FircoTrustService.getScreenedData(...)`:
   a. Resolve `fpStatus` / `nmiStatus` from `NextStatuses` — validate both are present; store in `metaData`.
   b. Try to download CSV format file from S3 (`<unit>_format.csv` → `<businessUnit>_format.csv` → absent).
   c. **With format file**: Split `MessageData` by `|`, map each token to an NSS field name via the CSV index; merge with CustomerInfo mapping (format file wins for primary fields).
   d. **Without format file**: Fall back to CustomerInfo mapping only.
   e. Build `ScreenedData` — merges names via `AliasMerger`, dates via `DateMerger`, locations via `LocationMerger`.
5. **Obsolete hit filter** (if `FIRCO_TRUST_ENABLE_OBSOLETE_FILTER=true`):
   - Extract date from `HittedEntity.batch` (pattern `OBSOLETE-YYYY/MM/DD_…`).
   - Drop hit if `(batch_date + obsolete_period_days) <= today`.
6. **Non-name hit filter** (if `ENABLE_LOCATION_WLE=false`):
   - Drop hits where `SolutionType != 1` (keeps only NAME-type hits).
   - Set `isFilteredTransaction=true` if any hit was removed.
7. Call `FircoTrustService.getWleData(filteredHits,...)` → maps each `Hit` to `WleData` via `FircoTrustMapper`.
8. Call `AnalyticsService.initHitsAnalytics(transactionId, wleData)`.
9. Emit output row.

### Output row keys

| Key | Value |
|-----|-------|
| `SCREENED_DATA` | `ScreenedData` (customer identity fields) |
| `WLE_LIST` | `List<WleData>` (sanctions hits) |
| `WLE_COUNT` | `int` — size of WLE_LIST |
| `FIRCO_MESSAGE_META_DATA` | `FircoMetaData` — now includes `fpStatus`, `nmiStatus` |
| `TRANSACTION_ID` | `UUID` |
| `FILTERED_TRANSACTION` | `boolean` — true if non-name hits were stripped |

---

## Data Flow

```
Firco Trust TCMAPI
        |
        | SOAP: receiveInventoryRequest (1 call per run)
        v
DownloadFircoMessagesProcessor          — saves NEW message stubs to DB
        |
        | (DB rows, not in-memory)
        v
FircoMessagesBatchProcessor             — fans out one row per alert, handles pagination/retry
        |
        | FIRCO_MESSAGE_META_DATA, TRANSACTION_ID (per alert)
        v
FircoMessageDetailsProcessor            — SOAP: receiveMessageRequest per alert
        |                               — filters hits, builds ScreenedData + WleData
        v
    ML Pipeline (PrepareForMl → AutoML → SaveModelResults)
        |
        | AlertDecision
        v
ScreeningSystemReportProcessor
        |
        | SOAP: receiveStatusUpdate (writes decision + CSV attachment back to Firco)
        v
    Firco Trust — alert resolved
```

---

### What "obsolete" means in Firco

When a sanctions list provider removes or supersedes an entity, Firco marks the corresponding list
entry as obsolete and stamps the date in the `HittedEntity.batch` field. The hit still appears in
screening results — Firco does not suppress it automatically — but the batch string changes format:

```
Normal:   2022/02/11_000000001_CIF1           ← active entry, always processed
Obsolete: OBSOLETE-2022/02/11_000000001_CIF1  ← marked obsolete on 2022/02/11
```

### Configuration

| Config field | Enum constant | Default | Meaning |
|---|---|---|---|
| `provider.firco_trust_enable_filter.enable_obsolete_filter` | `FIRCO_TRUST_ENABLE_OBSOLETE_FILTER` | `false` | Master switch — filter is off unless explicitly enabled |
| `provider.firco_trust_obsolete_period` | `FIRCO_TRUST_OBSOLETE_PERIOD` | `null` | Grace period in **days** — if null, filter does not run even if enabled |

Both must be set for filtering to take effect.

### How the threshold works

The `obsolete_period` is a **grace period**, not a maximum age:

```
obsoleteDate  = date extracted from batch string  (e.g. 2022/02/11)
thresholdDate = obsoleteDate + obsolete_period_days

if today < thresholdDate  →  within grace period  →  KEEP the hit
if today ≥ thresholdDate  →  grace period expired →  DROP the hit
```

Example — `obsolete_period = 30`:
- Hit marked obsolete on 2022/02/11 → threshold = 2022/03/13
- Processed on 2022/02/20 → still within grace → **kept**
- Processed on 2022/03/15 → grace expired → **dropped**

The intent: newly-obsoleted entries may still be relevant (sanctions lists have lag), so a grace
period allows them to clear the pipeline before being silently ignored.

### Code path (`FircoMessageDetailsProcessor`)

```java
private static final Pattern OBSOLETE_PATTERN = Pattern.compile("\\d{4}/\\d{2}/\\d{2}");

private boolean isNonObsolete(String batch, int obsoleteThreshold) {
    Matcher matcher = OBSOLETE_PATTERN.matcher(batch);
    if (batch.toUpperCase().startsWith("OBSOLETE") && matcher.find()) {
        Date batchDate    = DateUtils.parseDate(matcher.group(), "yyyy/MM/dd");
        Date thresholdDate = DateUtils.addDays(batchDate, obsoleteThreshold);
        return thresholdDate.after(new Date());  // true = keep
    }
    return true;  // non-OBSOLETE batch → always keep
}
```

Key points:
- Only hits whose batch **starts with "OBSOLETE"** (case-insensitive) are evaluated
- The date is extracted by regex `\d{4}/\d{2}/\d{2}` — matches wherever it appears in the string
- `DateUtils.addDays` is used → threshold is in **days** (the variable was historically named
  `monthObsoleteThreshold` but the unit is days — a naming artefact)
- If the date cannot be parsed → `FircoTrustFaultException` is thrown (non-retryable)
- Hits that pass the filter are logged: `"Firco Alert {id} contains Obsolete hits older than {n} days: {kept} out of {total} will be processed."`

### Interaction with the non-name hit filter

Obsolete filtering runs **first** (step 5), non-name filtering runs **second** (step 6).
Both operate on the same hit list sequentially. `isFilteredTransaction` is only set by the
non-name filter, not by obsolete filtering.

---

## Format File Mapping (S3)

S3 path: `doc-upload/name_sanctions_screening/firco_format_files/`

Lookup order:
1. `{unit}_format.csv` (e.g. `CIF1_format.csv`)
2. `{businessUnit}_format.csv`
3. Absent → fall back to CustomerInfo only

**CSV structure:**

```
index,nss_column
1,INPUT_FULL_NAME
2,INPUT_ID
3,INPUT_ADDRESS_FIELD_1_COUNTRY
```

`FircoTrustMapper.toMap(Message, csvRecords)` splits `MessageData` on `|` and maps token at `index-1` to the
corresponding `nss_column`. Throws `FormatFileIndexMismatchException` if the index exceeds the token count.

---

## Decision Write-Back (ScreeningSystemReportProcessor)

**Status selection:**

| Condition | Status used |
|-----------|------------|
| `AlertResolution.ALL_FP` AND NOT `selectedForAutoQc` | `fpStatus` |
| anything else | `nmiStatus` |

**Attachment / comment matrix:**

| selectedForAutoQc | updateEnabled | Comment | Attachment |
|-------------------|---------------|---------|------------|
| true | any | "WorkFusion processing for parallel production, please review the alert as normal." | none |
| false | false | same as above | none |
| false | true | readable resolution + explanation | Base64 CSV (HIT_ID, RESOLUTION, EXPLANATION) |

After the SOAP call, `FircoTrustMessage.status` is updated to `COMPLETED`.

---

### `FircoTrustService`
Spring `@Service`. Wraps `FircoTrustClient` (JAXWS proxy).
- `init(alias, endpoint, port, bUnit)` — credentials from secrets vault, builds `ConfigurationProvider`
- `getMessagesMetaInfo` — inventory poll
- `getFircoMessage(metaData)` — full message fetch with validation (message, customerInfo, hits must be non-null)
- `getScreenedData(...)` — delegates to `FircoTrustConverter`
- `getWleData(hits,...)` — delegates to `FircoTrustConverter`
- `updateMessageStatus(info, alertDecision, selectedForAutoQc, updateEnabled)` — decision write-back

### `FircoTrustConverter`
Converts raw SOAP objects → NSS domain objects (`ScreenedData`, `WleData`).
- Calls `FircoTrustMapper` to produce `Map<String, String>` from SOAP objects
- Calls `ScreenedDataUtils` / `WleDataUtils` to build typed domain objects from those maps
- Merges format-file data (primary) with CustomerInfo (secondary) via `AliasMerger`, `DateMerger`, `LocationMerger`

### `FircoTrustMapper`
Static. Produces flat `Map<String, String>` for both `ScreenedData` and `WleData` paths:
- `toMap(Message, csvRecords)` — format file path
- `toMap(Message)` — CustomerInfo fallback
- `toMap(Hit)` — per-hit map for `WleData`

### `FircoTrustFormatFileDownloaderService`
Downloads optional CSV format files from S3. Returns `List<CSVRecord>` or empty if not.

---

### `FircoTrustMessage` — `ds_uc_B_AML_PEP_firco_messages_v3_0`

| Field | Notes |
|-------|-------|
| uuid | PK, auto-generated |
| systemId | Unique per Firco message, used for dedup in step 1 |
| messageId | Firco message ID |
| unit / businessUnit | From inventory response |
| transactionId | Set in step 2 when transaction is created |
| bpRunId | Current BP run, scopes queries in steps 2–3 |
| externalRecordId | REST request ID if triggered via API |
| status | NEW → PROCESSING → COMPLETED (or ERROR) |

### `FircoRetryMonitor` — `ds_uc_B_AML_PEP_firco_retry_monitor_v3_0`

Persists pagination state. Created when batch is full; `retry` flag toggled to `false` when picked up.

### `FircoConfiguration` — `ds_uc_B_AML_PEP_firco_configuration_v3_0`

| Field | Default |
|-------|---------|
| batchSize | 2000 |
| waitTime | 2 (seconds) |

---

## Configuration Fields (`FircoTrustConfigurationFields`)

| Enum constant | Config path | Required |
|---|---|---|
| `FIRCO_TRUST_ENDPOINT` | `provider.firco_trust_endpoint` | Yes |
| `FIRCO_TRUST_INVENTORY_PORT` | `provider.firco_trust_inventory_port` | Yes |
| `FIRCO_TRUST_ALIAS` | `provider.firco_trust_alias` | Yes — secrets vault key |
| `FIRCO_TRUST_FP_STATUS` | `provider.firco_trust_fp_status` | Yes — status name for False Positive |
| `FIRCO_TRUST_NMI_STATUS` | `provider.firco_trust_nmi_status` | Yes — status name for NMI |
| `FIRCO_TRUST_B_UNIT` | `provider.firco_trust_b_unit` | No — filters by business unit |
| `FIRCO_TRUST_UNIT` | `provider.firco_trust_unit` | No — filters by unit(s) |
| `FIRCO_TRUST_UPDATE_ENABLE` | `provider.firco_trust_update_enable.enable_ft_update` | No |
| `FIRCO_TRUST_ENABLE_OBSOLETE_FILTER` | `provider.firco_trust_enable_filter.enable_obsolete_filter` | No |
| `FIRCO_TRUST_OBSOLETE_PERIOD` | `provider.firco_trust_obsolete_period` | No — days threshold |

---

## Exception Hierarchy

| Exception | Base | When thrown |
|-----------|------|-------------|
| `FircoTrustConnectivityException` | `NssRetriableException` | SOAP network/transport failure — triggers JNW retry |
| `FircoTrustFaultException` | `NssNonRetriableException` | Validation error: missing message/CustomerInfo/hits, bad NextStatuses |
| `FormatFileIndexMismatchException` | `NssNonRetriableException` | Format file CSV index exceeds MessageData token count |
| `PropertyNotFoundException` | `NssNonRetriableException` | Required field absent on Hit (e.g. ID, Names) |

---

## Retry Mechanism

Every task processor (schema-based and non-schema-based) extends `NSSSchemaBasedTaskProcessor` /
`NSSTaskProcessor`. Both override `process` and delegate ALL uncaught exceptions to
`CustomErrorHandling.handleException`.

### How `CustomErrorHandling` works

```
exception thrown by run()
        │
        ▼
NSSSchemaBasedTaskProcessor.process() catch (Exception e)
        │
        ▼
CustomErrorHandling.processException(e, transactionId)
        │
        ├─ shouldRetry = (e instanceof NssRetriableException)
        ├─ maxAttempts  = context.getStepExecutionRetryLimit()   // JNW-controlled, default 10
        ├─ currentAttempt = context.getStepExecutionAttemptCount()
        │
        ├─ if (!shouldRetry || currentAttempt >= maxAttempts):
        │       fircoTrustMessageRepository.updateStatus(ERROR)   // Firco only
        │       transactionService.finishTransactionWithError(...)
        │       requestStatusService.createOrUpdateStatus(ERROR)
        │
        └─ throw NSSProcessingException(errorMessage, e)         // always
```

**Key distinction — what `Retryable` / `NonRetryable` actually controls:**

The `NssRetriableException` / `NssNonRetriableException` split does **not** directly tell the JNW
framework whether to retry the step — JNW retries all uncaught exceptions up to its own
`stepExecutionRetryLimit`. What the split controls is **when `CustomErrorHandling` finalises the
transaction as ERROR in the DB**:

| Exception type | DB / transaction finalised as ERROR | JNW retries step? |
|---|---|---|
| `NssRetriableException` | Only on the last attempt (`currentAttempt >= maxAttempts`) | Yes (up to limit) |
| `NssNonRetriableException` | Immediately on the first attempt | Yes (JNW still retries), but transaction already closed — subsequent retries do nothing useful |

So for `NssNonRetriableException`, even though JNW may fire the step again, the transaction is
already marked ERROR and the alert is effectively dead after the first failure.

### Retry limit

Configured by the JNW platform (WorkFusion UI / BP configuration). Accessed at runtime via
`ITaskContextHolder.getContext.getStepExecutionRetryLimit`. Defaults to **10** in
`CustomErrorHandling` if the context returns `null`.

---

## SSL Note

SOAP calls go over HTTPS. JNW worker JVM is Java 17. Firco Trust server certificate (or its CA) must be in that JVM's truststore. Missing cert → `PKIX path building failed` wrapped in `FircoTrustConnectivityException`.

Fix: import the cert into the Java 17 `cacerts` used by the JNW worker:

```bash
keytool -importcert -alias firco-trust -file firco-ca.pem \
  -keystore $JAVA_17_HOME/lib/security/cacerts -storepass changeit
```
