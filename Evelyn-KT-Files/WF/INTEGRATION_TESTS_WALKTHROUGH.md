# NSS Integration Tests (`names-screening-integration-tests`) — Complete Walkthrough & Architecture Guide

Prepared for team onboarding & walkthrough session.
Covers:
1. **Repository & File Inventory** — every file in `names-screening-integration-tests` and `names-screening-test-utils` and what it does.
2. **The 3-Layer Framework Stack** — what is uplifted from **WorkFusion Spoke**`dw-test-framework`and **NSS custom extensions**.
3. **`spoke.properties`, Credentials, AuthN/AuthZ, and Maven Plugins** — how environments, credentials, tokens, and bundle imports actually work locally vs. in CI.
4. **End-to-End Walkthrough: `MaxDataPairsTest`** — a beginner-friendly, line-by-line trace from test startup to Control Tower execution and assertions.

---

## Part 1: High-Level Mental Model (For Beginners)

Unlike unit tests (`*Test.java` in `names-screening-jnw`) or component integration tests (`*IT.java` that run a single `@TaskProcessor` in memory with H2), the tests in **`names-screening-integration-tests`** are **true End-to-End (E2E) platform tests**:

1. They connect to a **real WorkFusion Control Tower environment** (e.g., `dw-dev2`, `dw-qa`, `dw-sandbox`).
2. They upload the packaged **Digital Worker Asset Bundle** (`names-screening-package-<version>.zip`) containing the Business Process `.zip` files, Liquibase datastore migrations, ML model, and `configuration.json`.
3. For each test method, they **clone a Digital Worker Variation** in Control Tower and apply a test-specific JSON configuration (`ConfigurationPayload`).
4. They **trigger the real Business Process** in Control Tower (either by uploading a CSV file, calling the Streaming REST API `/input-connector-rest`, or polling mocked external providers on WireMock port `9999`).
5. They **poll Control Tower, S3/MinIO, Datastores, and Elasticsearch** until the BP finishes, and assert on step outputs, REST responses, generated HTML/CSV QC reports, datastore rows, and Control Tower event logs.
6. Finally, if the test passes, they **stop all BP instances and delete the variation** so the environment stays clean. If the test fails, they **keep the variation alive** and print its exact Control Tower UI name so you can open Control Tower and inspect the failed run.

---

### 2.1 Build, Configuration, and Properties Files

| File | Role |
|---|---|
| `pom.xml` | Maven module definition. Imports `dw-test-framework` (`7.0.0-21`), `names-screening-test-utils`, `evelyn-nss-api`, `wiremock`, `kotlin-maven-plugin`, `maven-surefire-plugin` (skips E2E tests by default via `<surefire.skipTests>true</surefire.skipTests>`), and `frontend-maven-plugin` + `wagon-maven-plugin` for Cypress UI tests. |
| | Configures JUnit 5 parallel execution: `parallel.enabled=true`, `fixed.parallelism=10`, `mode.classes.default=concurrent` (test classes run in parallel across 10 threads; methods within the same class run `same_thread`). |
| `cypress.config.js` | Configures Cypress UI tests against `http://localhost:3010` (local `task-designer-ui` renderer server). |
| `README.md` | Quick-start instructions for local `spoke.properties` setup, Maven execution flags, and Cypress UI test commands. |

### 2.2 JUnit 5 Extension & Core Test Harness (`src/test/java/com/workfusion/dw/nss/extension/`)

| File | Role |
|---|---|
| `NssE2ETest.java` | Custom meta-annotation (`@ExtendWith(NssE2EExtension.class)`) placed on every E2E test class. |
| `NssE2EExtension.java` | **The heart of the E2E suite.** Extends `DigitalWorkersJunitSpec` and implements JUnit 5 `BeforeAllCallback`, `BeforeEachCallback`, `AfterEachCallback`, `AfterAllCallback`, and `ParameterResolver`. Handles one-time bundle import (`defaultVariation` and `csvIngestionVariation`) with SQL deadlock retry, injects a per-test `NssTestContext`, provides fail-fast BP polling, S3/Datastore helpers, and automatic variation cleanup after each test. |
| `NssE2EParameters.java` | Central constants file: reads `bp.version` and `wiremock` URL from `DigitalWorkerTestProperties`, defines `BUNDLE_PATH`, `DEFAULT_CONFIGURATION_PATH`, BP titles (`Names Screening v...`, `CSV File Ingestion v...`), and step names (`INPUT_BOT`, `PREPARE_FOR_ML_BOT`, `SAVE_MODEL_RESULTS_BOT`, etc.). |
| `CsvFlowRuns.java` | Java `record CsvFlowRuns(BusinessProcessRun nssProcess, BusinessProcessRun csvProcess)` pairing the parent `CSV File Ingestion` BP run with the child `Names Screening` BP run. |

### 2.3 WireMock Provider Mockers (`src/test/java/com/workfusion/dw/nss/extension/mocker/` & )

External watchlist providers (Factiva, World-Check One, Firco Trust) are mocked using a shared **WireMock** server running on the target environment's master node (`http://<master-host>:9999`). Tests push stub mappings to WireMock remotely via `new WireMock(MASTER_HOST, 9999)`:

| File | Role |
|---|---|
| `FactivaMocker.java` | Stubs Dow Jones Factiva `GET /v1/search/name?...` and `GET /v1/data/records/...` endpoints with XML response fixtures from `src/test/resources/stubs/factiva/`. |
| `WorldCheckOneMocker.java` | Stubs Refinitiv WC1 REST endpoints: `POST /v2/cases/screeningRequest`, `GET /v2/cases/{caseSystemId}/results`, `GET /v2/groups/{groupId}/resolutionToolkit`, and `PUT /v2/cases/{caseSystemId}/results/resolution` using JSON fixtures from `src/test/resources/stubs/wc1/`. |
| `FircoTrustMocker.java` | Stubs Firco Trust SOAP requests on `POST /TrustReceiveService`, matching XML body fragments (`msg_ReceiveInventoryRequest`, `msg_ReceiveMessageRequest`, `msg_ReceiveStatusUpdate`) + login + messageId, returning SOAP XML fixtures from `src/test/resources/stubs/firco/`. |
| | A `@Disabled` manual utility test that developers can run from their IDE to pre-load Firco SOAP stubs into WireMock for manual debugging or performance testing. |

### 2.4 End-to-End Test Classes (`src/test/java/com/workfusion/dw/nss/e2e/`)

| Test Class | JUnit `@Tag` | What It Tests |
|---|---|---|
| **`MaxDataPairsTest.java`** | `streaming-api` | **(Walkthrough Example)** Verifies that alerts whose cross-product of enabled fields across hits exceeds `configuration.max_data_pairs` skip the Python AutoML model (`DATA_PAIRS_LIMIT_EXCEEDED=true`) and are routed straight to `save-model-results-processor` with `MORE_INFORMATION_NEEDED` and explanation `"Please review manually. Alert is too big for automated processing."` |
| `FullAlertScreeningTest.java` | `streaming-api`, `PSI` | Comprehensive Streaming API (`API` input mode) suite: full alert screening, location WLEs (`hit_record_type: Location`), mixed WLEs, middle-name matching modes (`ignore`, `lenient`, `strict`), unchecked model fields, identifier-only rules, HTML & QC report generation in S3, invalid JSON / missing required field error handling, and billing events. |
| `MatchingScoreTest.java` | `streaming-api` | Verifies composite hit score calculation (`MultiFactorScoringService`) in `save-model-results-processor` across 3 different model rule configurations (name-only, location+date without name, name+location). |
| `FactivaProviderTest.java` | `factiva`, `rest` | Dow Jones Factiva screening via both CSV upload and Streaming API: hits , no hits , missing `input_full_name`, invalid API URL, invalid Vault credentials alias, identifiers/additional data in QC report, and billing. |
| `WorldCheckOneProviderTest.java` | `wc1`, `rest` | Refinitiv World-Check One screening via CSV and Streaming API: no entity type, `INDIVIDUAL`, `ORGANISATION`, no hits, screening by `case_system_id`, invalid URL/alias/groupId error handling, and billing. |
| `FircoProviderTest.java` | `firco` (`@Isolated`) | Firco Trust SOAP batch ingestion: standard messages, fixed-width format files, pipe-separated format files, short/unparsable fixed-width messages (verifies `firco_message_parsing_failed=true`, `ERROR` status in DB, and `PENDING` NMI write-back in WireMock request journal), BUnit format files, alias fallback when name is missing, obsolete (>90 days) & non-`NAME` hit filtering. |
| `FircoRestProviderTest.java` | `firco-rest` (`@Isolated`) | Triggering Firco Trust screening on demand via Streaming API (`firco_trust_unit` payload overriding configured units, empty units array, no messages ). |
| `CsvProviderTest.java` | `csv` | Two-BP asynchronous CSV flow (`CSV File Ingestion` → `Names Screening`): general flow, QC off, AutoQC sampling rate (`~3%`), ticker enrichment narrative, gold decision persistence in `alert_analytics`/`hit_analytics`, valid record types filtering, and missing format/data file error handling. |
| `ModelTest.java` | `model` | Tests Python classification model behavior via CSV flow: date matching scenarios (full date match, year-only match, year-only delta > threshold, mixed format, threshold boundary) and verifies `unified_name_matcher` is used across `INDIVIDUAL`, `SECURITIES`, and `ORGANIZATION`. |
| `LocationEnrichmentTest.java` | `location_enrichment` | Verifies Google Geocoder address enrichment on `screened_data` (New York) and `wle_list` (Houston) at the `address-lookup-prepare-data-task-processor` step when enabled vs. disabled. |
| `ManualReviewTest.java` | `manual_task` (`@Disabled`) | Tests human-in-the-loop routing (`prepare-data-for-manual-review-processor`) and saving mocked manual task review results (`MOCKED_MANUAL_TASK`). |
| `TickerDownloadTest.java` | `tickers-download` | Runs the standalone `Name Screening Ticker Lookup` BP after seeding SMTP configuration into `uc_B_AML_PEP_configuration_v3_0` and verifies `<N> tickers found` in INFO logs. |
| `PerformanceTest.java` | `performance` (`@Isolated`) | Runs a 1,000-alert synthetic CSV benchmark, waits for 12,755 hit submissions, downloads the QC report, and calculates TP/TN/FP/FN, Automation Rate, Error Rate, and Hits/Hour into `target/PerfStats.txt`. |

### 2.5 Utilities, DTOs, and Kotlin Helpers (`utils/`, `dto/`, `specs/synthetic/`)

| File | Role |
|---|---|
| | Kotlin singleton object holding `@JvmStatic` `JsonObject` test payloads for Streaming API tests (`donaldTrump`, `joeDoe`, `fullAlert`, `fourDataPairsOneWle`, `threeDataPairsOneWle`, `fourDataPairsTwoWLEs`, `threeDataPairsTwoWLEs`, middle-name fixtures, etc.). Java tests call them as static getters (`getFourDataPairsOneWle`). |
| | `synchronized` rate-limiter enforcing a `1500ms` minimum gap between Keycloak OAuth2 token requests across the 10 parallel test threads so Keycloak's brute-force protection (`quickLoginCheckMilliSeconds=1000`) does not lock out `aqa_user`. |
| | Uses Spoke's XML `Modification.Builder` to rewrite `<externalSignalId>` and `<signalId>` inside the `Names Screening`, `CSV File Ingestion`, and `Names Screening QC Report` BP XMLs at bundle-import time so CSV tests use a run-isolated signal ID (`csv-ingestion-<uuid>`). |
| & `QCReportColumns.java` | Parses `qc_reports` JSON (`{"report_links":["https://..."]}`), downloads CSV reports from S3/MinIO, and defines expected column-order maps per provider (`withDefaultColumnsOrder`, `withFactivaColumnsOrder`, `withCsvColumnsOrder`, `withWorldCheckOneColumnsOrder`, `withFircoTrustColumnsOrder`). |
| | Deserializes `StepOutcome.getOutputData` JSON (`records.content.data`) for manual review step assertions. |
| & `MockPerformanceStatistics2.java` | Computes confusion matrix metrics (`tp`, `tn`, `fp`, `fn`, `automationRate`, `errorRate`, `hitsPerHour`) by comparing `hit_gold_resolution` vs `model_decision` in QC report CSVs. |
| & `AlternateElkModels.kt` | Custom Koin-injected `ElasticsearchClient` helper querying `billing-assistant-*` index by `dw_name="Evelyn"` and `run_uuid`. Created because `dw-test-framework`'s built-in `ElkRequester` requires a non-null `dw_code` field and fails deserializing into Kotlin data classes without `KotlinModule`. |
|, `DataObjects.kt`, `RandomData.kt` | Kotest (`DigitalWorkersFunSpec`) synthetic data generator using Faker to produce realistic individual/company/security alerts and hits with pre-calculated `hit_gold_resolution` and `alert_gold_resolution`. |
| `src/test/java/.../dto/*` (`ModelResult.java`, `StatisticsDto.java`, `HitStatisticsDto.java`, `TotalStatisticsDto.java`, `StatusDto.java`) | Java records/POJOs for deserializing `model_result` JSON (handling `attrs.hits` encoded as a nested JSON string via `@JsonAdapter(EmbeddedHits.class)`) and performance stats. (Note: `src/main/java/dto/` holds legacy duplicate `StatusDto`/`StatisticsDto` classes.) |

### 2.6 Companion Module: `names-screening-test-utils`

Located at `/names-screening-test-utils`, this module provides the **Fluent Configuration Builder DSL** used by both processor integration tests (`*IT.java`) and E2E tests:
- `ConfigurationPayload`: Entry point (`ConfigurationPayload.API`, `.CSV(format, data)`, `.FACTIVA`, `.WC1`, `.FIRCO`). Serializes via `new Gson.toJson(this)` into the exact JSON structure of `configuration_payload.json`.
- `ConfigurationData`, `Model`, `ProvidersConfiguration`, `EnrichmentData`, `ManualTask`, `FactorDecisionsOption`: Strongly-typed Java mirrors of the sections.

### 2.7 Cypress UI Tests (`src/test/cypress/ui/`)

Tests the Digital Worker Wizard UI form (`configuration.json` + `configuration_payload.json`) rendered locally in Electron via WorkFusion's `task-designer-ui` bundle:
- `ConfigurationForm.test.js`: Tests the 5 wizard tabs (`Input`, `Enrichment`, `Model`, `Human In the Loop`, `Output`), including `configuration.max_data_pairs` validation (`0` to `100000`, default `2000`).
- `ModelStep.test.js`: Tests rule checkboxes, middle-name matching strategy (`ignore`, `lenient`, `strict`), incomplete date threshold, and location matching level checkboxes.
- `HumanInTheLoopStep.test.js`: Tests HITL criteria (`DISABLE_ALL`, `ENABLE_ALL`, `ENABLE_NMI`, `ENABLE_FP`) and discrete AutoQC risk-matrix grid validation.
- `ScreeningSystemOptions.test.js`: Verifies the screening system dropdown options (Dow Jones Factiva, World-Check One, Firco Trust, Thomson Reuters CLEAR).

---

## Part 3: What Code & Functionalities Are Uplifted from Underlying Repositories (`spoke` & `dw-test-framework`)

When a beginner opens `MaxDataPairsTest.java`, they will notice fields and methods that don't appear anywhere in this repository—such as `tokenRequester`, `secretsVaultRequester`, `bpInputRequester`, `bpRunDwEvents(...)`, `importDigitalWorker(...)`, `tower`, `digitalWorker`, and `StepOutcome`.

Those come from **two underlying WorkFusion libraries** imported :

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Layer 3: NSS Integration Test Harness (this repo)                          │
│   @NssE2ETest -> NssE2EExtension -> NssTestContext                         │
│   + ConfigurationPayload / ProvidersConfiguration (names-screening-test-utils)
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │ extends
┌───────────────────────────────────────▼────────────────────────────────────┐
│ Layer 2: DW Test Framework (com.workfusion.dw:dw-test-framework:7.0.0-21)  │
│   DigitalWorkersJunitSpec -> implements DigitalWorkersBaseSpec (Kotlin)    │
│   + Koin DI Container (ApiClientModules)                                   │
│   + DigitalWorkerTestProperties (loads spoke.properties / JVM sysprops)    │
│   + 18 *Requester clients (bpInputRequester, tokenRequester,               │
│     secretsVaultRequester, dataStoreRequester, AwsRequester, etc.)         │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │ wraps & delegates to
┌───────────────────────────────────────▼────────────────────────────────────┐
│ Layer 1: WorkFusion Spoke Framework (com.workfusion.spoke:spoke-*)         │
│   ControlTower, ControlTowerApi, AssetBundle, ExistingDigitalWorkerVariation│
│   BusinessProcess, BusinessProcessRun, StepExpectations, StepOutcome,      │
│   MockStep, Modification.Builder, OpenAPI/Retrofit ctclient (*Api)         │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Layer 1: WorkFusion Spoke Framework (`com.workfusion.spoke.*`)

**Spoke** is WorkFusion's Java client SDK for automating Control Tower operations in tests. Here is everything NSS uplifts from Spoke:

| Spoke Class / Package | What It Does for NSS |
|---|---|
| `ControlTower` & `ControlTowerApi` | Authenticates against Control Tower (`/workfusion/api/dologin` with `username`/`password`) and provides an authenticated Retrofit/OkHttp client (`tower.getControlTowerApi().getService(...)`). Under the hood (`ControlTowerAuthenticator`) this is a **session login**: it form-posts `j_username`/`j_password`, keeps the session cookie, adds CT's CSRF token header to every request, and logs in again automatically when CT answers 403 "CSRF token... not found". No bearer token is involved. |
| `AssetBundle` (`com.workfusion.spoke.bundle`) | Reads `names-screening-package-<version>.zip` from disk, applies in-memory XML/JSON modifications (`withBusinessProcess(...)`, `ConfigurationPayload.fromFile(...)`) without mutating the file on disk, and uploads the modified bundle to Control Tower via `BundleImportApi`. |
| `MockStep` & `Modification.Builder` (`com.workfusion.spoke.mock`) | Allows `NssE2EExtension` to rewrite BP `project.xml` on the fly before importing—used by `MOCKED_MANUAL_TASK` (replacing the human review step with an automated mock step) and `SignalIdUtils` (rewriting `<signalId>` and `<externalSignalId>` via XPath/`XmlEngine`). |
| `ExistingDigitalWorkerVariation` (`com.workfusion.spoke.dw`) | Represents an imported Digital Worker variation in Control Tower. Provides:<ul><li>`.copy(variationName)` — clones the base variation for a single test</li><li>`.updateConfiguration(jsonConfig)` — pushes the test's `ConfigurationPayload` JSON into the variation</li><li>`.getBusinessProcessByTitle(BP_NAME)` — looks up a BP inside the variation</li><li>`.delete()` — deletes the variation in `afterEach` cleanup</li></ul> |
| `BusinessProcess` & `BusinessProcessRun` (`com.workfusion.spoke.bp`) | Starts a BP in Control Tower and tracks the running instance:<ul><li>`.run()` / `.runAsIs()` — starts BP with its default or pre-attached CSV data</li><li>`.run(InputData)` — uploads a local CSV file and starts the BP</li><li>`.runWithInputFromExternalSource()` — starts the BP in **listener/streaming mode** and returns `BusinessProcessRun` (whose `.getDefinitionUUID()` is passed to `bpInputRequester.startRaw(...)`)</li><li>`.stop()` — stops a running BP instance</li><li>`.waitFor(Await).untilStep(stepName).hasSuccessfulSubmissions(...)` — polls a specific step inside the BP and returns its `StepOutcome`</li><li>`.getIntermediateResult(QC_REPORTS)` — fetches intermediate/final CSV output columns</li></ul> |
| `StepOutcome` & `BusinessProcessSuccessfulResult` | Inspects execution results: `stepOutcome.getOutputData` returns the raw JSON output of a schema-based JNW processor step; `bpResult.getRecordsCountPassedThroughStep(stepName)` asserts how many records passed through each step of the BP flow. |
| `com.workfusion.spoke.ctclient.api.*` | Low-level generated Swagger/Retrofit clients for Control Tower internal REST endpoints (`BpInstancesApi`, `DefinitionsApi`, `EventsApi`, `SecretsVaultApi`, `DataStoreInternalRestControllerApi`). |

### 3.2 Layer 2: Digital Workers Test Framework (`com.workfusion.dw:dw-test-framework:7.0.0-21`)

Written in Kotlin, **`dw-test-framework`** sits on top of Spoke and provides a batteries-included test harness (`DigitalWorkersJunitSpec` implementing `DigitalWorkersBaseSpec`).

When `NssE2EExtension.beforeAll` calls `super.beforeAll`, `DigitalWorkersJunitSpec` does three major things:
1. Initializes **`DigitalWorkerTestProperties.INSTANCE`** (which reads `spoke.properties` or Maven Surefire system properties).
2. Starts a **Koin Dependency Injection application** (`startKoinApp` with `ApiClientModules`: `externalModule`, `internalModule`, `spokeModule`) that wires up Retrofit HTTP clients, AWS S3 clients, MinIO clients, Elasticsearch clients, and the Spoke `ControlTower` singleton.
3. Populates **pre-configured `*Requester` fields** directly onto `DigitalWorkersJunitSpec` (which every test class and `NssE2EExtension` inherits):

| Inherited Field / Method on `DigitalWorkersJunitSpec` | How NSS Tests Use It |
|---|---|
| `tower` (`ControlTower`) | Used by `NssE2EExtension` to access `BpInstancesApi`, `DefinitionsApi`, `EventsApi`, and `RunBusinessProcessClient`. |
| `digitalWorker` (`ExistingDigitalWorkerVariation`) | Set by `importDigitalWorker(...)` after uploading the asset bundle zip; cached in `NssE2EExtension.defaultVariation` and `csvIngestionVariation`. |
| `secretsVaultRequester` (`SecretsVaultRequester`) | Calls Control Tower's Secrets Vault (`/workfusion/api/...` via `SecretsVaultApi`).<ul><li>`secureEntry("aqa-test")` fetches the test user credentials stored in Vault.</li><li>`createSecureEntry(alias, login, password)` seeds provider test credentials (e.g., Firco test aliases).</li></ul> |
| `tokenRequester` (`TokenRequester`) | Calls Keycloak (`/auth/realms/WorkfusionRealm/protocol/openid-connect`) with a `SecureEntry` from Vault to obtain an OAuth2 `access_token` and saves it into `SharedApiProperties.bearerToken`. |
| `bpInputRequester` (`BpInputRequester`) | Client for the **Input Connector REST API** (`/input-connector-rest`), automatically attaching `Authorization: Bearer <token>` from `SharedApiProperties.bearerToken`:<ul><li>`startRaw(definitionUuid, jsonObject)` — `POST start-record-raw/{signal-id}`: submits a raw JSON alert payload to a running streaming BP and returns `requestId` (async)</li><li>`startJson(definitionUuid, jsonObject)` — `POST start-record-json/{signal-id}`: same, but the payload is wrapped as `{"send_request": "<json string>"}`</li><li>`executeRaw` / `executeJson` — the synchronous `execute-record-*` variants</li><li>`checkStatus(requestId)` — `GET check-record-status/{id}`: polls status (`IN_PROGRESS`, `COMPLETED`, `FAILED`)</li><li>`getResult(requestId)` — `GET get-record-result/{id}`: fetches the final REST response (`AlertResponse` JSON)</li></ul>NSS tests pass the BP **definition UUID** as the `{signal-id}` path value. |
| `dataStoreRequester` (`DataStoreRequester`) | Executes SQL-like queries against Control Tower Datastores (`uc_B_AML_PEP_transaction_v3_0`, `uc_B_AML_PEP_firco_configuration_v3_0`, etc.): `selectWhereEquals`, `selectWhereIn`, `selectStar`, `insertRow`, `insertRows`, `deleteWhereLike`. |
| `cephRequester` / `s3Requester` (both `AwsRequester`, two different clients) | **`cephRequester`** (`CONTROL_TOWER_S3`) is the one NSS uses: an AWS SDK v2 `S3Client` with `cephKeyId`/`cephKeyValue`, pointed at the environment's own object store `cephApi` (`https://<env>-s3.cloud.workfusion.com`). It uploads CSV input/format files and downloads HTML/QC reports from the `doc-upload` bucket (`NssTestContext.uploadObjectToS3` creates the same kind of client). **`s3Requester`** (`DIGITAL_WORKER_S3`) is a separate client for **real AWS** (`us-east-1`, `awsKeyId`/`awsKeyValue`, default bucket `wf-digital-worker`). It is only used by the framework's `copyS3FileToCeph` helpers. |
| `bpRunDwEvents(runningProcess)` / `bpRunDwEvents(runningProcess, LevelTypeEnum)` | Fetches Control Tower execution logs (`EventEntityDto` → mapped to `DwEvent(step, message, logLevel)`) for a BP run via `EventsRequester`. |
| `importDigitalWorker(bundlePath, modifications, defaultConfigPath, waitMinutes, deleteStaleBps)` | Assembles the bundle with Spoke `Modification.Builder`s, uploads it to Control Tower, polls until import finishes, and sets `this.digitalWorker`. |

---

## Part 4: `spoke.properties`, Credentials, AuthN/AuthZ, and Maven Plugins

This is one of the most important architectural topics for the team to understand clearly, because **Maven plugins** and **`spoke.properties`** work together across build time, deployment time, and test runtime.

### 4.1 What Is in `spoke.properties` and How Does `dw-test-framework` Load It?

The template contains 6 properties:

```properties
apiRoot=https://dw-dev2.cloud.workfusion.com/workfusion/api
authenticationEndpoint=https://dw-dev2.cloud.workfusion.com/workfusion/api/dologin
username=replace_me
password=ReplaceMe2
cephKeyId=access_key
cephKeyValue=access_value
```

#### The 4-Step Credential Resolution Chain (`DigitalWorkerTestProperties`)

When the test JVM starts, `DigitalWorkerTestProperties.INSTANCE.getTestProperties` resolves credentials and URLs using this exact priority order:

1. **JVM System Property `-Dspoke.configuration=<path>`** (mapped from `<spoke.config>` ):
   - If you run Maven with, `maven-surefire-plugin` passes `<spoke.configuration>${spoke.config}</spoke.configuration>` to the test JVM, and `dw-test-framework` loads that file.
2. **Environment Variable `SPOKE_CONFIG`**:
   - If `SPOKE_CONFIG` is set in the shell environment, `dw-test-framework` loads the file at that path.
3. **Maven Surefire System Properties (Used in Bitbucket Pipelines CI!)**:
   - Look at lines 250–266:
     ```xml
                         <systemPropertyVariables>
                             <bp.version>${project.version}</bp.version>
                             <spoke.configuration>${spoke.config}</spoke.configuration>
                             <!--suppress UnresolvedMavenProperty -->
                             <api>${CT_ENVIRONMENT_URL}/workfusion/api</api>
                             <!--suppress UnresolvedMavenProperty -->
                             <auth>${CT_ENVIRONMENT_URL}/workfusion/api/dologin</auth>
                             <!--suppress UnresolvedMavenProperty -->
                             <user>${CT_AUTH_USERNAME}</user>
                             <!--suppress UnresolvedMavenProperty -->
                             <ctpw>${CT_AUTH_PASSWORD}</ctpw>
                             <!--suppress UnresolvedMavenProperty -->
                             <cephKeyId>${CEPH_ACCESS_KEY}</cephKeyId>
                             <!--suppress UnresolvedMavenProperty -->
                             <cephKeyValue>${CEPH_SECRET_KEY}</cephKeyValue>

                         </systemPropertyVariables>
     ```
   - If neither `spoke.configuration` nor `SPOKE_CONFIG` is set, `DigitalWorkerTestProperties` checks if the system property `user` (`-Duser=...`) is non-empty.
   - In **Bitbucket Pipelines**, repository/deployment variables (`CT_ENVIRONMENT_URL`, `CT_AUTH_USERNAME`, `CT_AUTH_PASSWORD`, `CEPH_ACCESS_KEY`, `CEPH_SECRET_KEY`) are injected by `maven-surefire-plugin` as system properties (`api`, `auth`, `user`, `ctpw`, `cephKeyId`, `cephKeyValue`). **No `spoke.properties` file is needed in CI!**
   - When you right-click a test in IntelliJ and click **Run** (or run Maven locally without `CT_AUTH_USERNAME` set), `spoke.configuration`, `SPOKE_CONFIG`, and `user` are all blank.

> **To make it explicit, pass the file:**. That is step 1 and beats everything else. The README's alternative is editing `<spoke.config/>` in the pom, which you must not commit.

#### How `DigitalWorkerTestProperties` Auto-Derives 11 Service URLs from `apiRoot`

You only specify `apiRoot=https://dw-dev2.cloud.workfusion.com/workfusion/api` in `spoke.properties`. From that single URL, `DigitalWorkerTestProperties` automatically rewrites the hostname/path to derive every endpoint in the environment:

| Property in `TestProperties` | Auto-Derived Value (for `dw-dev2`) | Used By |
|---|---|---|
| `ctApiUrl` | `https://dw-dev2.cloud.workfusion.com/workfusion/api` | Spoke `ControlTower` |
| `auth` | `https://dw-dev2.cloud.workfusion.com/workfusion/api/dologin` | Spoke `ControlTower` login |
| `bpApiUrl` | `https://dw-dev2.cloud.workfusion.com/input-connector-rest` | `bpInputRequester` (Streaming API) |
| `tokenUrl` | `https://dw-dev2-auth.cloud.workfusion.com/auth/realms/WorkfusionRealm/protocol/openid-connect` | `tokenRequester` (Keycloak JWT) |
| `wiremock` | `http://dw-dev2-master1.cloud.workfusion.com:9999` | `NssE2EExtension.wireMock` (`MASTER_HOST:9999`) |
| `cephApi` | `https://dw-dev2-s3.cloud.workfusion.com` | `AwsRequester` (`CONTROL_TOWER_S3`) |
| `minioApi` | `https://dw-dev2-minio.cloud.workfusion.com` | `MinioRequester` |
| `elk` | `dw-dev2-superset1.cloud.workfusion.com` | `AlternateElkRequester` (Billing ELK) |
| `superset` | `https://dw-dev2-analytics.cloud.workfusion.com/api/v1` | `SupersetRequester` |
| `workspaceApi` | `https://dw-dev2-workspace.cloud.workfusion.com/workspace/api/v1` | `WorkspaceRequester` (Manual tasks) |
| `boxManipulator` | `http://dw-dev2-master1.cloud.workfusion.com:8083/api` | `BoxManipulatorRequester` |

---

### 4.2 The Two Authentication & Authorization Flows at Test Runtime

Beginners often ask: *"If `spoke.properties` already has `username` and `password`, why does `MaxDataPairsTest` also call `tokenRequester.generateBearerToken(secretsVaultRequester.secureEntry("aqa-test"))` in `@BeforeEach`?"*

Because WorkFusion has **two separate API gateways** with different authentication mechanisms:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ AUTH FLOW 1: Control Tower API (/workfusion/api/*)                           │
│                                                                              │
│ spoke.properties (username + password)                                       │
│   └──► POST /workfusion/api/dologin                                          │
│          └──► Authenticates Spoke `ControlTower` client:                     │
│                 • Importing/copying/deleting Digital Worker variations       │
│                 • Starting/stopping BPs & polling step outcomes              │
│                 • Querying Datastores (`dataStoreRequester`)                 │
│                 • Reading BP Event Logs (`eventsRequester`)                  │
│                 • Reading Secrets Vault (`secretsVaultRequester`)            │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        │ 1. `secretsVaultRequester.secureEntry("aqa-test")`
                                        │    fetches the `aqa-test` credentials from CT Vault
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ AUTH FLOW 2: Input Connector REST / Streaming API (/input-connector-rest/*)  │
│                                                                              │
│ `tokenRequester.generateBearerToken(secureEntry)`                            │
│   └──► POST https://<env>-auth.../realms/WorkfusionRealm/.../openid-connect  │
│          └──► Returns OAuth2 Bearer JWT (`access_token`)                     │
│          └──► Stored in `SharedApiProperties.bearerToken`                    │
│                 │                                                            │
│                 ▼                                                            │
│ `bpInputRequester.startRaw(...)` / `checkStatus(...)` / `getResult(...)`     │
│   └──► Sends `Authorization: Bearer <access_token>` to                       │
│        `https://<env>.cloud.workfusion.com/input-connector-rest/...`         │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Why `BearerTokenThrottle.throttle(...)` wraps the token call**:
  Because `junit-platform.properties` runs **10 test classes concurrently** (`fixed.parallelism=10`), all 10 threads would hit Keycloak's token endpoint at the exact same millisecond using the same `"aqa-test"` user. Keycloak's brute-force detector (`quickLoginCheckMilliSeconds = 1000ms`) would flag this as a brute-force attack and temporarily disable the user (`401 user_temporarily_disabled`). `BearerTokenThrottle` is a `synchronized` gate that spaces token generation calls at least **1,500 ms** apart.

---

### 4.3 The Role of Maven Plugins & `m2-settings.xml`

Maven plugins play a critical role across **three stages**: (A) Building & Version-Stamping the Bundle, (B) Importing the Bundle to Control Tower via CLI/CI, and (C) Passing Environment & Auth Properties into the Integration Test Runner.

#### Stage A: Building & Assembling the Asset Bundle

Before any integration test can run, the deployable bundle must exist. Three Maven plugins build it:

1. **`bundle-versions-maven-plugin` (`com.workfusion.odf:bundle-versions-maven-plugin:0.0.35`)**
   - Activated via profile `-P update-bundle-version` (with `-Dbundle.update.force=true`).
   - Runs in the `prepare-package` phase (`BundleVersionsSetPluginMojo`).
   - Automatically updates all version references inside `names-screening-package` to match `${project.version}`:
     - Renames the BP `.zip` files in `src/main/resources/business-process/` (e.g., `Names+Screening+_v_4.4.0-dev.zip`).
     - Rewrites `project.xml` inside each BP `.zip` so every machine step's JNW worker GAVP (`com.workfusion.dw:names-screening-jnw:<version>:jar`), bot task config, and human task version match `${project.version}`.
     - Updates `meta-info.json` and Liquibase datastore migration references.
2. **`wagon-maven-plugin` (`2.0.2`) + `maven-s3-wagon` (`1.3.3`) + `truezip-maven-plugin` (`1.2`)**
   - Activated via profile `-P ml-model`.
   - Authenticates against AWS S3 using `<server><id>nss-model-s3-releases-repository</id>` from **`m2-settings.xml`** (`S3_DW_RELEASES_ACCESS_KEY_ID` / `S3_DW_RELEASES_SECRET_ACCESS_KEY`).
   - Downloads `nss-classification-model-v5.3.0.zip` and unzips it into the package `model/` directory so the Python model is packaged inside the bundle.
   - *(In the integration-test module, these same two plugins download and unpack `task-designer-ui-10.2.8.5.tar.gz` from Nexus using `<serverId>wf-dependencies</serverId>` for Cypress UI tests.)*
3. **`maven-assembly-plugin` (`3.3.0`)**
   - Runs in the `package` phase of `names-screening-package` using the package assembly descriptor.
   - Zips up `business-process/*.zip`, `datastore/migrations/*`, `model/*`, `configuration.json`, `configuration_payload.json`, and `meta-info.json` into the package zip.

#### Stage B: How Bundles Get Imported into Control Tower (Two Mechanisms!)

There are **two ways** the asset bundle gets imported into a Control Tower environment, and it is important to distinguish them:

| Aspect | Mechanism 1: Maven CLI Plugin (`bundle-maven-plugin`) | Mechanism 2: JUnit Runtime Import (`NssE2EExtension` + Spoke) |
|---|---|---|
| **How it is triggered** | (or `-P remote`) | Automatically in `NssE2EExtension.beforeAll` when JUnit 5 starts any `@NssE2ETest` class |
| **Underlying class** | `com.workfusion.odf:bundle-maven-plugin:10.3.1.4` (`BundleImportPluginMojo`) | `dw-test-framework`'s `DigitalWorkersBaseSpec.importDigitalWorker(...)` → Spoke's `ControlTower.importDigitalWorker(...)` |
| **Does it modify the bundle before upload?** | **No.** Uploads as-is (used for real environment deployments like `deploy-models-psi`). | **Yes!** Uses Spoke's `AssetBundle` API in memory to apply `MOCKED_MANUAL_TASK` (for `defaultVariation`) and `SignalIdUtils.signalIdModifications(...)` (for `csvIngestionVariation`). |
| **Other goals provided** | `mvn bundle:pull-model -Dmodel=...` (downloads a trained model from CT) and `mvn bundle:drop-data-stores` (drops use-case tables & Liquibase history). | Retries once (after 60s) if Control Tower hits a SQL Server deadlock on `component_contract_object_schema_link` (`importBundleWithDeadlockRetry`). |

---

## Part 5: Step-by-Step Walkthrough of `MaxDataPairsTest`

Now let's walk through **`MaxDataPairsTest.java`** from top to bottom.

### 5.1 What Business Rule Is `MaxDataPairsTest` Testing?

In Names Sanctions Screening, an alert consists of:
- **1 Screened Entity (`input`)**: has names (full name + aliases), dates (e.g., DOB), locations (addresses), identifiers (passports/TINs), gender, and entity type.
- **\(N\) Watchlist Hits (`wle_list` / `hits`)**: each hit also has names, dates, locations, identifiers, gender, and entity type.

When the Python Classification Model (`nss-classification-model`) evaluates a hit, its field matchers compare every input value against every hit value (a **cartesian cross-product** per field). If a corporate entity has dozens of aliases, addresses, and dates across 50 watchlist hits, the number of comparisons can explode into tens of thousands of pairs, stalling the worker.

To protect the system, **`PrepareForMlProcessor.java`** (`names-screening-jnw`) calculates the **Data Pairs Count** before calling the Python model:

```java
    private int countPairsForWle(ScreenedData screened, WleData wle) {
        return getPairsCountIfEnabled(nameEnabled, countNameFields(screened.getName(), screened.getAliases()), countNameFields(wle.getName(), wle.getAliases()))
             + getPairsCountIfEnabled(dateEnabled, collectionSize(screened.getDates()), collectionSize(wle.getDates()))
             + getPairsCountIfEnabled(locationEnabled, collectionSize(screened.getLocations()), collectionSize(wle.getLocations()))
             + getPairsCountIfEnabled(identifierEnabled, nonNullMapSize(screened.getIdentifiers()), nonNullMapSize(wle.getIdentifiers()))
             + getPairsCountIfEnabled(genderEnabled, presentCount(screened.getGender()), presentCount(wle.getGender()))
             + getPairsCountIfEnabled(typeEnabled, presentCount(screened.getEntityType()), presentCount(wle.getEntityType()));
    }

    private int getPairsCountIfEnabled(boolean enabled, int screenedCount, int wleCount) {
        return enabled ? screenedCount * wleCount : 0;
    }
```

For an alert as a whole:
\[\text{Total Data Pairs} = \sum_{\text{wle} \in \text{hits}} \text{countPairsForWle}(\text{input}, \text{wle})\]

**What happens when \(\text{Total Data Pairs} > \text{max\_data\_pairs}\)?**
1. `PrepareForMlProcessor.isDataPairsLimitExceeded(...)` logs an `INFO` message:
   ```java
   logger.info("Alert [{}]: Current data pairs count: {}, Max allowed pairs: {}",
           screenedData.getId(), dataPairsCount, maxPairs);
   ```
2. It outputs a row with **`data_pairs_limit_exceeded = true`** (and **no** model `document`).
3. Inside the **Names Classification Model** subprocess in the BP, a Drools gateway rule (`"Max Data Pairs"`) inspects `data_pairs_limit_exceeded`:
   - If `false`: routes to **`Execute AutoML Model:Bridge`** (the Python classification model) → then **`save-model-results-processor`**.
   - If `true`: **bypasses `Execute AutoML Model:Bridge` completely** and routes directly to **`save-model-results-processor`**.
4. `SaveModelResultsProcessor` sees `isMaxDataPairsExceeded == true` and immediately marks the alert as `NEED_REVIEW` and every hit as:
   - `resolution = MORE_INFORMATION_NEEDED`
   - `explanation = "Please review manually. Alert is too big for automated processing."`

---

### 5.2 Tracing `MaxDataPairsTest.java` Line by Line

Let's look at the full test class and trace what happens at each step:

```java
@Slf4j
@NssE2ETest
@Tag("streaming-api")
class MaxDataPairsTest extends DigitalWorkersJunitSpec {

    private NssE2EExtension.NssTestContext nssTestContext;

    @BeforeEach
    void init(NssE2EExtension.NssTestContext nssTestContext) {
        this.nssTestContext = nssTestContext;
        BearerTokenThrottle.throttle(() ->
            tokenRequester.generateBearerToken(secretsVaultRequester.secureEntry("aqa-test")));
    }
```

#### Step 1: Class Declarations & JUnit Lifecycle Startup (`beforeAll`)
- **`extends DigitalWorkersJunitSpec`**: Inherits all the `dw-test-framework` requesters (`tokenRequester`, `secretsVaultRequester`, `bpInputRequester`, `bpRunDwEvents`, etc.).
- **`@NssE2ETest`**: Registers `NssE2EExtension`.
- **`@Tag("streaming-api")`**: Allows selective execution via `-Dsurefire.tags=streaming-api`.
- **When JUnit starts the class (`NssE2EExtension.beforeAll`)**:
  2. Checks if `defaultVariation` has already been imported in this JVM run. If not, calls `importBundleWithDeadlockRetry("Default bundle", MOCKED_MANUAL_TASK)`, which uploads to Control Tower and caches the resulting `ExistingDigitalWorkerVariation` in `defaultVariation`.
     - **Once per JVM, under a lock.** `defaultVariation` is `static`, so with 10 classes running in parallel only the first class imports. The others wait on `BUNDLE_IMPORT_LOCK` and then reuse the result.
     - **The path is relative** to the module directory (the surefire/IDE working directory), so the package zip must already be built. Running the tests does **not** build it.
     - **Import wait and retry.** Spoke polls the import for up to 30 minutes and retries once, after 60 s, but **only** on SQL Server deadlock or lock errors. A poll timeout is never retried, because the server-side import keeps running and a second upload would stack on top of it.
     - **Failures are cached.** If the import fails, the exception is stored in `defaultImportFailure`, and every later class fails fast with "Default bundle import already failed earlier in this run". When you see that message, look for the *first* failure in the log.
     - **`MOCKED_MANUAL_TASK` applies to every test.** The human-review step `Name Screening Manual Review v<version>` is replaced at import time by a bot step that exports a canned `data_on_review_output` (hit `3_1` reviewed, decision 1). That is why no E2E run ever waits for a person.
  3. The test class's own inherited `@BeforeAll` (`DigitalWorkersJunitSpec.beforeAll`, `PER_CLASS` lifecycle) then runs and initialises the requester fields on the **test instance**. The extension and the test class are two separate `DigitalWorkersJunitSpec` objects that share one global Koin container.

#### Step 2: Parameter Injection & `@BeforeEach init(...)`
- JUnit calls `NssE2EExtension.resolveParameter(...)` to create a fresh `NssTestContext` named `"MaxDataPairsTest-MaxDataPairs1"` with a timestamped variation name (`MaxDataPairsTest-MaxDataPairs1-yyyyMMdd-HHmmssSSS`).
- Inside `@BeforeEach init(...)`:
  1. Saves `this.nssTestContext = nssTestContext`.
  2. Calls `secretsVaultRequester.secureEntry("aqa-test")` (using Control Tower auth from `spoke.properties`) to read the `"aqa-test"` credentials from Control Tower's Secrets Vault.
  3. Passes those credentials to `tokenRequester.generateBearerToken(...)` (wrapped in `BearerTokenThrottle.throttle(...)`) to obtain an OAuth2 Bearer token from Keycloak for the Streaming API (`/input-connector-rest`).

---

#### Step 3: The `// given` Block — Building the Configuration & Creating a Variation

```java
    @Test
    @DisplayName("MaxDataPairs1")
    void shouldRunBpWhereSomeAlertsExceedMaxPairLimit() {
        //given
        String jsonConfiguration = ConfigurationPayload.API()
            .withModelFields(true, true, true, true, false, false)
            .clearModelRules()
            // Note: identifier is not ticked, so subtract a pair from the input.
            // None of the alerts include gender on the input side, so that doesn't count as a pair either.
            .withMaxDataPairs(3)
            .withModelRule(FactorDecisionsOption.strong_mismatch, null, null, null, null, null)
            .withQcReport(false, false)
            .build();
        nssTestContext.createVariation(jsonConfiguration);
```

Let's unpack every builder call on `ConfigurationPayload` (from `names-screening-test-utils`):
1. **`ConfigurationPayload.API`**: Sets `configuration.INPUT_TYPE = "API"` and `configuration.PROVIDER_ID = "API"`. This tells the main BP that alerts arrive already populated with hits via the REST API (so the `Screening System?` gateway skips Factiva/WC1/Firco).
2. **`.withModelFields(true, true, true, true, false, false)`**:
   - Signature: `withModelFields(name, location, date, type, gender, identifier)`
   - Enables **4 fields**: `name = true`, `location = true`, `date = true`, `type = true`.
   - Disables **2 fields**: `gender = false`, `identifier = false`.
   - *Why this matters*: `PrepareForMlProcessor.countPairsForWle` only counts cross-products for **enabled** fields! Even though the test inputs contain `"hit_gender": "female"`, `genderEnabled` is `false` (and `input_gender` is absent anyway), so gender contributes `0` pairs.
3. **`.clearModelRules` + `.withModelRule(FactorDecisionsOption.strong_mismatch, null, null, null, null, null)`**:
   - Replaces the default rules with a single auto-clear rule: **if `name == strong_mismatch`, then clear the hit as `FALSE_POSITIVE` (`decision = 0`)**.
4. **`.withMaxDataPairs(3)`**:
   - Sets `configuration.max_data_pairs = 3`.
   - Any alert with **\(\le 3\)** total data pairs will go to the Python model.
   - Any alert with **\(> 3\)** (i.e. 4 or more) total data pairs will exceed the limit and skip the model!
5. **`.withQcReport(false, false)`**:
   - Disables CSV QC report generation (`enable = false`, `automatic_generation = false`) so the test runs faster and doesn't need to wait for the `Qc Report Sub-process`.
6. **`nssTestContext.createVariation(jsonConfiguration)`**:
   - Calls `defaultVariation.copy(variationName)` in Control Tower to clone the base Digital Worker variation, and then calls `testCaseVariation.updateConfiguration(jsonConfiguration)` to apply our custom JSON settings to this test's isolated variation.

---

#### Step 4: The `// when` Block — Starting the BP and Sending 4 Streaming Alerts

```java
        // when
        String definitionUuid = nssTestContext.runBusinessProcessWithExternal();

        String requestID1 = bpInputRequester.startRaw(definitionUuid, getThreeDataPairsOneWle());
        nssTestContext.waitForCompletion(requestID1);

        String requestID2 = bpInputRequester.startRaw(definitionUuid, getFourDataPairsOneWle());
        nssTestContext.waitForCompletion(requestID2);

        String requestID3 = bpInputRequester.startRaw(definitionUuid, getThreeDataPairsTwoWLEs());
        nssTestContext.waitForCompletion(requestID3);

        String requestID4 = bpInputRequester.startRaw(definitionUuid, getFourDataPairsTwoWLEs());
        nssTestContext.waitForCompletion(requestID4);
```

1. **`nssTestContext.runBusinessProcessWithExternal`**:
   - Finds `"Names Screening v4.4.0-dev"` in `testCaseVariation` and calls Spoke's `.runWithInputFromExternalSource()`.
   - This launches the BP in Control Tower in **external listener mode** (staying `IN_PROGRESS` waiting for REST requests) and returns the BP's `definitionUuid`.
2. **Sending the 4 requests via `bpInputRequester.startRaw(definitionUuid,...)`**:
   - Each `startRaw` call sends an HTTP `POST` (with the Keycloak Bearer token) to `/input-connector-rest/start-record-raw/{definitionUuid}` with one of the 4 JSON payloads from `StreamingInputs.kt`, and gets back a `requestId`.
   - Let's do the **exact Data Pairs math** for each of the 4 payloads (remember: enabled fields are `name`, `location`, `date`, `type`; `max_data_pairs = 3`; and in all 4 payloads the input has `1 name`, `1 type ("INDIVIDUAL")`, `1 address`, `1 date`):

| Request | Fixture in `StreamingInputs.kt` | `input_id` | Hits (`wle_list`) & Fields Present | Data Pairs Calculation (`name + location + date + type`) | Exceeds Max (`> 3`)? | Path Taken in BP |
|---|---|---|---|---|---|---|
| `requestID1` | `getThreeDataPairsOneWle` | `2` | **1 WLE** (`hit_id="2"`):<br>• `name`: `"Bettie Davis"` (1)<br>• `type`: `"INDIVIDUAL"` (1)<br>• `address`: *none* (0)<br>• `date`: `1949-` (1) | \((1\times1)_{\text{name}} + (1\times0)_{\text{loc}} + (1\times1)_{\text{date}} + (1\times1)_{\text{type}} = \mathbf{3}\) | **No** (\(3 \le 3\)) | Runs Python Model → `"Three data Pairs One WLE"` vs `"Bettie Davis"` is a strong name mismatch → **`FALSE_POSITIVE`** |
| `requestID2` | `getFourDataPairsOneWle` | `1` | **1 WLE** (`hit_id="1"`):<br>• `name`: `"Bettie Davis"` (1)<br>• `type`: `"INDIVIDUAL"` (1)<br>• `address`: `USA/NY` (1)<br>• `date`: `1949-` (1) | \((1\times1)_{\text{name}} + (1\times1)_{\text{loc}} + (1\times1)_{\text{date}} + (1\times1)_{\text{type}} = \mathbf{4}\) | **Yes!** (\(4 > 3\)) | **Skips Model** (`DATA_PAIRS_LIMIT_EXCEEDED=true`) → **`MORE_INFORMATION_NEEDED`** (`"Alert is too big..."`) |
| `requestID3` | `getThreeDataPairsTwoWLEs` | `4` | **2 WLEs**:<br>• `hit_id="4_1"`: `name` (1), `type` (1) → **2 pairs**<br>• `hit_id="4_2"`: `name` (1), `gender` (ignored) → **1 pair** | \(\text{WLE}_{4\_1}(2) + \text{WLE}_{4\_2}(1) = \mathbf{3}\) | **No** (\(3 \le 3\)) | Runs Python Model → `"Three data Pairs Two WLEs"` vs `"Bettie Davis"` is a strong name mismatch → **`FALSE_POSITIVE`** |
| `requestID4` | `getFourDataPairsTwoWLEs` | `3` | **2 WLEs**:<br>• `hit_id="3_1"`: `name` (1), `type` (1) → **2 pairs**<br>• `hit_id="3_2"`: `name` (1), `date` (1), `gender` (ignored) → **2 pairs** | \(\text{WLE}_{3\_1}(2) + \text{WLE}_{3\_2}(2) = \mathbf{4}\) | **Yes!** (\(4 > 3\)) | **Skips Model** (`DATA_PAIRS_LIMIT_EXCEEDED=true`) → **`MORE_INFORMATION_NEEDED`** (`"Alert is too big..."`) |

*(Beginner Tip: Notice the slightly confusing method names in `StreamingInputs.kt`! The method `getThreeDataPairsOneWle` has `input_id: 2` and `hit_id: "2"`, while `getFourDataPairsOneWle` has `input_id: 1` and `hit_id: "1"`. Always check `hit_id` in `StreamingInputs.kt` when reading `expectedResults`!)*

3. **How `nssTestContext.waitForCompletion(requestID)` works**:
   - Uses Awaitility to poll `bpInputRequester.checkStatus(requestId)` every 20 seconds (up to 20 minutes) until the status is no longer `"IN_PROGRESS"`.
   - On every poll tick, it also calls `failIfBusinessProcessesHaveErrors(List.of(runningProcess))` so that if the BP throws an error in Control Tower, the test fails immediately instead of waiting 20 minutes!
   - Once finished, asserts `assertEquals("COMPLETED", status)`.

---

#### Step 5: The `// then` Block (Part 1) — Inspecting `save-model-results-processor` Step Output

```java
        List<Map<String, Object>> expectedResults = List.of(
            Map.of("id", "1", "resolution", "MORE_INFORMATION_NEEDED", "explanation", "Please review manually. Alert is too big for automated processing."),
            Map.of("id", "2", "resolution", "FALSE_POSITIVE", "explanation", "False Positive.\nStrong name mismatch (\"Three data Pairs One WLE\", \"Bettie Davis\"). "),
            Map.of("id", "3_1", "resolution", "MORE_INFORMATION_NEEDED", "explanation", "Please review manually. Alert is too big for automated processing."),
            Map.of("id", "4_1", "resolution", "FALSE_POSITIVE", "explanation", "False Positive.\nStrong name mismatch (\"Three data Pairs Two WLEs\", \"Bettie Davis\"). ")
        );

        final int EXPECTED_ALERT_COUNT = 4;

        StepOutcome stepOutcome = nssTestContext.waitUntilStepHasContentRows(SAVE_MODEL_RESULTS_BOT, EXPECTED_ALERT_COUNT);
```

1. **Why `waitUntilStepHasContentRows(SAVE_MODEL_RESULTS_BOT, 4)`?**
   - `SAVE_MODEL_RESULTS_BOT` resolves to `"Names Screening JNW v4.4.0-dev (save-model-results-processor)"`.
   - Both normal alerts (after `Execute AutoML Model:Bridge`) and oversized alerts (routed around the model by the `"Max Data Pairs"` Drools rule) converge at `save-model-results-processor`.
   - As documented in `NssE2EExtension.waitUntilStepHasContentRows`, Spoke's `hasSuccessfulSubmissions(4)` checks the task counter first and downloads the step's JSON content in a second HTTP call. Polling until `records.content.size() >= 4` guarantees all 4 alert rows are materialized in `stepOutcome.getOutputData()`.
2. **Parsing the Step Output JSON**:
   - For a schema-based JNW processor, Control Tower stores step output in this JSON envelope. The example below is *illustrative*: the `records.content[i].data.alert_decision` path is exactly what the test reads, but the other values are shown only to give the shape.
     ```json
     {
       "records": {
         "totalElements": "4",
         "content": [
           {
             "data": {
               "alert_decision": "{\"id\":\"1\",\"resolution\":\"NEED_REVIEW\",\"explanation\":\"Please review manually. Alert is too big for automated processing.\",\"wleDecisions\":[{\"id\":\"1\",\"resolution\":\"MORE_INFORMATION_NEEDED\",\"explanation\":\"Please review manually. Alert is too big for automated processing.\"}]}",
               "transaction_id": "..."
             }
           }
         ]
       }
     }
     ```
   - Notice that `alert_decision` is a JSON-serialized string inside `data`! That's why lines 94–104 first extract `alert_decision` as a `String` and then parse it a second time with `JsonParser.parseString(alertDecisionJson).getAsJsonObject`.
   - From `wleDecisions.get(0)`, the test extracts `id`, `resolution`, and `explanation`, puts them in a `Map`, and asserts that `expectedResults` contains that exact entry:
     - Hits `"1"` (4 pairs, 1 WLE) and `"3_1"` (4 pairs, 2 WLEs) → `MORE_INFORMATION_NEEDED` with `"Please review manually. Alert is too big for automated processing."`
     - Hits `"2"` (3 pairs, 1 WLE) and `"4_1"` (3 pairs, 2 WLEs) → `FALSE_POSITIVE` with `"False Positive.\nStrong name mismatch (...)"`

---

#### Step 6: The `// then` Block (Part 2) — Verifying Control Tower Event Logs

```java
        List<DwEvent> infoLogs = bpRunDwEvents(nssTestContext.runningProcess).stream()
            .filter(event -> event.getLogLevel()
                .equals(LevelTypeEnum.INFO.toString()))
            .toList();

        assertThat(infoLogs).isNotEmpty();

        String expectedString = "Current data pairs count: 4, Max allowed pairs: 3";

        assertThat(infoLogs)
            .extracting(DwEvent::getMessage)
            .filteredOn(msg -> msg.contains(expectedString))
            .as("Expected exactly 2 Info logs containing \"%s\", but got a different count. All INFO messages: %s",
                expectedString,
                infoLogs.stream()
                    .map(DwEvent::getMessage)
                    .toList())
            .hasSize(2);
```

- Where do `bpRunDwEvents(nssTestContext.runningProcess)` logs come from?
  - In `PrepareForMlProcessor.java` (lines 91–93), the JNW worker injects the platform `Logger` bean (`ClientIdLoggerDecorator` wrapping `EventLogger`).
  - Unlike normal SLF4J file logs, messages logged via the `EventLogger` bean in a JNW processor are **published back to Control Tower's Event Log** for that BP run!
  - `bpRunDwEvents(...)` (from `DigitalWorkersJunitSpec` / `dw-test-framework`) calls Control Tower's `EventsApi` to fetch all `EventEntityDto` records for `runningProcess` and converts them to `DwEvent` objects.
  - Because 2 of the 4 alerts had 4 data pairs (`input_id=1` and `input_id=3`), `PrepareForMlProcessor` logged `"Alert [1]: Current data pairs count: 4, Max allowed pairs: 3"` and `"Alert [3]: Current data pairs count: 4, Max allowed pairs: 3"`.
  - The test asserts `.hasSize(2)`.

---

#### Step 7: Test Teardown (`NssE2EExtension.afterEach`)

Once `shouldRunBpWhereSomeAlertsExceedMaxPairLimit` finishes:
1. `NssE2EExtension.afterEach` stops `testContext.runningProcess` (which was running in external listener mode).
2. Calls `endAllBpInstances(testContext.testCaseVariation)`. This lists every instance of every BP definition in the variation and **actively ends** any instance that is not yet `DRAFT`/`COMPLETED`/`DELETED`/`DELETING` (`PUT end`). It re-checks every 5 s for up to 60 s.
3. Because the test passed and all instances ended, it calls `testContext.testCaseVariation.delete()` to remove the variation from Control Tower. If instances were *still* live after 60 s, the variation is **kept** even though the test passed: deleting it would return a 422 (`cannot.delete.digital.worker.variation`) and fail a green test. It is logged as `PASSED TEST, VARIATION KEPT ...` and left for the next cleanup.
4. *(If the test had failed, it would skip `.delete()` and log: `FAILED TEST -> CONTROL TOWER VARIATION: test='MaxDataPairsTest#shouldRunBpWhereSomeAlertsExceedMaxPairLimit', UI variation name='Version 4.4.0-DEV-MaxDataPairsTest-MaxDataPairs1-...'` so you can inspect it in the Control Tower UI!)*

---

### 1. Local Setup (One-Time)
3. Build the package zip (with version update + ML model). Run this from the repo root:
   ```bash
   mvn clean install -DskipTests -Dcypress.skipTests=true -P update-bundle-version,ml-model -Dbundle.update.force=true
   ```
   - **Why `update-bundle-version` matters:** the tests look up BPs by **versioned title** (`"Names Screening v" + bp.version`) and modify zips by **versioned file name** (`Names+Screening+_v_<version>.zip`). If you changed the version (`versions:set`, as CI does per branch) without re-running this profile, the lookups fail.
   - **Why `ml-model` matters:** it downloads the classification model from S3 into the bundle. `MaxDataPairsTest`'s non-exceeded alerts go through `Execute AutoML Model:Bridge`, so they need it.
   - **Ignore the README's "Enable the `e2e-tests` maven profile" step.** No `e2e-tests` profile exists in any pom. The README step is stale.

### 2. Running `MaxDataPairsTest`
- **From IntelliJ IDE**: Open `MaxDataPairsTest.java` and click the green Run arrow next to `shouldRunBpWhereSomeAlertsExceedMaxPairLimit`. The working directory must be the `names-screening-integration-tests` module, because `BUNDLE_PATH` is relative. Normally IntelliJ forwards surefire's `systemPropertyVariables` (including `bp.version`). If the log shows `Names Screening vnull`, it did not, and you must add `-Dbp.version=<project version>` to the VM options.
- **From Maven CLI (Single Test Class)**. `surefire:test` runs **already compiled** test classes, so run step 3 first:
  ```bash
  mvn surefire:test -pl names-screening-integration-tests -Dsurefire.skipTests=false -Dtest=MaxDataPairsTest -Dspoke.config=spoke.properties
  ```
- **From Maven CLI (By Tag, e.g., all `streaming-api` tests)**:
  ```bash
  mvn surefire:test -pl names-screening-integration-tests -Dsurefire.skipTests=false -Dsurefire.tags=streaming-api -Dspoke.config=spoke.properties
  ```
- **Where it runs in CI:** `MaxDataPairsTest` is tagged `streaming-api`. It runs in the manual PR step "Run CSV, Firco and Rest Tests" (`-Dsurefire.tags=csv,streaming-api,firco`), in `regression-test-psi`, and in every untagged `int-test-*` / `release` run.

---

## Part 7: Review Notes: Rough Edges Worth Knowing (verified against source)

These are observations, not changes. Mention them in the session so nobody "learns" an accident as a convention.

1. **`MaxDataPairsTest` only checks the first WLE of each alert.** It reads `wleDecisions.get(0)` for all 4 rows. For the two-WLE alerts, hits `3_2` and `4_2` are never asserted. Hit order in the step output is not guaranteed either, which is why the test uses `contains` and not index-by-index equality.
2. **One comment in `MaxDataPairsTest` is stale.** "identifier is not ticked, so subtract a pair from the input" doesn't match the data: no payload has identifiers at all. The counts work purely from the `countPairsForWle` formula in Part 5.1. The other comment, about gender, is accurate.
3. **`max_data_pairs = 0` means "off" (`if (maxPairs != 0)`).** The UI default is `2000`, but the Java builder field `ConfigurationData.maxDataPairs` is a primitive `int`. So every E2E test that doesn't call `.withMaxDataPairs(...)` sends `0` and runs with the limit **disabled**, unlike a real customer configuration.
4. **The bearer token is one global value.** `SharedApiProperties.bearerToken` is a single static `lateinit var` shared by all 10 parallel classes. Every `@BeforeEach` overwrites it. That works only because every class logs in as the same `aqa-test` user. Don't add a test that logs in as someone else.
5. **The CI test command may run the E2E suite twice. Check one CI log before relying on this.** Pipelines run `mvn verify surefire:test... -Dsurefire.skipTests=false`. In this module, `skipTests` is bound to `${surefire.skipTests}` at plugin level. That should apply to the default `test`-phase execution inside `verify` *and* to the explicit `surefire:test` goal, so the suite would run once in each.
6. **Most tags never appear in a pipeline filter.** Only `csv`, `streaming-api`, `firco` and `performance` are used in `bitbucket-pipelines.yml`. Classes tagged `factiva`, `wc1`, `rest`, `firco-rest`, `model`, `location_enrichment` or `tickers-download` run only in the untagged `int-test-*` and `release` runs.
