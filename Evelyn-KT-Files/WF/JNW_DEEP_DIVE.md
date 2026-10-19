# JNW (Java Native Worker) — Deep Dive

How the WorkFusion JNW framework works under the hood, and how Names Sanctions Screening (NSS) is built on top of it.

---

## 1. The Big Picture: Where JNW Sits

```
ODF2 Platform
 ├── Control Tower (CT)          — BP orchestrator, REST API, task lifecycle owner
 ├── Task Dispatcher Service (TDS) — routes tasks CT → worker queues via RabbitMQ
 ├── Worker Management Service (WMS) — spawns worker JVMs via Marathon/Mesos
 └── CT-Worker                   — JVM process that runs your Java code
         ↑
         └── THIS is JNW. A Spring Boot fat-JAR that CT-Worker launches.
             Your processors live here.
```

**ODF2** = WorkFusion's Orchestration/Decisioning Framework v2. The platform that runs Business Processes (BPs), manages workers, and routes tasks.

**JNW** = Java Native Worker. The replacement for legacy WebHarvest XML-based bot tasks. Instead of XML scripts, you write Spring-managed Java classes. The JNW framework (`com.workfusion.spa.jnative.worker`) provides the runtime contract, queue plumbing, and module system that your Java code plugs into.

---

### Stage 1 — User Triggers BP

```
User clicks Run in CT UI
  └── PUT /api/ui/business-process/{uuid}/run
        └── DirectInstanceActionService.runBusinessProcess()
              ├── Promotes draft Run → active Run  (MSSQL: run.status = IN_PROGRESS)
              ├── Creates step Run rows per BP step
              └── @Async: BpInstanceLaunchService.startDataParsing()
                    └── DefaultBotTaskProcessingService: builds TaskInput list
```

### Stage 2 — CT Builds the Task Payload

CT constructs a `CTTaskInputData` containing everything the worker needs:

| Field | Content |
|---|---|
| `RunDto` | Run ID, BP name, instance UUID |
| `CampaignDto` | Step config, timeout, worker GAVP |
| `InputData` map | Record data for this task (key-value pairs) |
| `PreviousData` | Output from prior BP steps |
| `DigitalWorkerInfo` | Worker GAVP to dispatch to |
| `instanceConfiguration` | Step-level config (= `configuration.json` data) |

Task channel name: `exec.control-tower.task.{bpInstanceUuid}-{stepId}`

### Stage 3 — CT Publishes to RabbitMQ

```
QueueTaskChannel / RabbitAsyncSender
  └── RabbitMQ vhost: bep
        Queue: exec.control-tower.task.{bpInstanceUuid}-{stepId}
        Headers: task_uuid, task_type=ct, step_id, bp_name,
                 replyTo=exec.control-tower.result.{bpInstanceUuid}-{stepId}
        Body: JSON-serialized CTTaskInputData
        Publisher confirms: mandatory=true, waits for broker ACK
```

### Stage 4 — Task Dispatcher Service (TDS) Routes to Worker

```
Every 5 seconds:
  QueuesScanner → RabbitMQ Management REST API → GET /api/queues/bep
    Finds: exec.control-tower.task.* queues
    Checks: is BP instance still active? (ZooKeeper)

New queue found:
  TaskDispatcher → TaskBrokerFactory.getTaskBroker(workerGroupDescriptor)
    ├── Creates worker queue: exec.{appId}.worker.{gavp}.{groupId}
    └── MessageForwarder:
          Consume from task queue
          Add header: TIMESTAMP_ROUTED_TO_WORKER
          Re-publish to worker queue
          ACK task queue only after worker queue confirms receipt
          Timeout 5 min → NACK → message requeued
```

**Key**: TDS matches task → worker by **GAVP** (GroupId:ArtifactId:Version:Packaging) embedded in the queue name. For NSS this is `com.workfusion.dw:names-screening-jnw:3.8.0-dev:jar`.

### Stage 5 — Worker Executes Your Java Processor

```
SimpleMessageListenerContainer
  Queue: exec.{appId}.worker.{gavp}.{groupId}
  prefetch = 1  ← one task at a time per thread

BaseMessageProcessor.onMessage()
  ├── 1. Extract replyTo from header
  ├── 2. Convert Message → TaskInput (TaskMessageConverter)
  ├── 3. TTL check — is task expired?
  ├── 4. Redelivery check — limit = 3 attempts
  ├── 5. Bot source validation (ZooKeeper)
  └── 6. Duplication control lock (ZooKeeper distributed lock)
        │
        ▼
  TaskProcessor.processTask()
    └── WorkerExecutorRegistry.getExecutor(taskType="ct")
          └── ActiveTaskHandlerService.processAndTrackTask()
                └── YOUR @TaskProcessor bean.process(TaskInputData)
```

### Stage 6 — Result Returns to CT, BP Advances

```
Worker → RabbitMQ: exec.control-tower.result.{bpInstanceUuid}-{stepId}
  Publisher confirms, 60s timeout, up to 5 retries

CT: ClusterBotTaskResultQueueProcessor
  ├── Acquire lock (by task ID)
  ├── Persist output to DB (AwsHitQuestion rows)
  ├── Update in-memory task state:
  │     executableTasksStorage → executedTasksStorage
  └── Fire Spring event:
        More steps remain → BotTaskStreamingRequest
                              → BatchedCompositeStepTransitionService
                                → new TaskInput for next step → loops to Stage 3
        Last step → StepCompletionRequest
                      → RunCompletionService
                        → run.status = COMPLETED
```

---

## 3. Worker Deployment: WMS + Marathon + Mesos

WMS runs continuously in the background — independent of any single BP run.

```
WMS reads worker GAVP from BP step configuration
  └── Calls Marathon REST API: POST /v2/apps
        └── Marathon schedules worker container on Mesos agent
              └── Mesos agent:
                    ├── Downloads worker JAR from Nexus (by GAVP)
                    └── Launches JVM: java -jar names-screening-jnw-3.8.0-dev.jar
                          └── Spring Boot starts
                                └── ApplicationReadyListener fires
                                      └── TaskInputService creates
                                            SimpleMessageListenerContainer
                                              → starts consuming worker queue
```

Worker is now live. TDS can route tasks to it.

**worker.yml** specifies the resource contract Marathon uses:

```yaml
command: ${java} -XX:+UseSerialGC -Xmx${heap}M -XX:MaxMetaspaceSize=${metaspace}M
         -Dexecution.task.queue.input=${tasks.queue} ...
         -jar ${worker.jar}
cpu: 0.4
memory:
  heap: 1024
  metaspace: 256
health-checks:
  - protocol: MESOS_HTTP
    path: /actuator/health   # Spring Boot Actuator
java-version: 17
```

---

### 4.1 The `odf2-jnw-compiler` Annotation Processor

At **compile time**, Maven invokes the `odf2-jnw-compiler` APT (Java Annotation Processor). It scans every class annotated with `@TaskProcessor` and generates a descriptor — a registry of `task-id → GAVP`. This descriptor is bundled into the JAR.

```xml
<!-- pom.xml — compilerArgs feed the APT -->
<compilerArgs>
    <arg>-AgroupId=com.workfusion.dw</arg>
    <arg>-AartifactId=names-screening-jnw</arg>
    <arg>-Aversion=3.8.0-dev</arg>
</compilerArgs>
```

ODF2 reads this descriptor at deployment time to know:
- Which task IDs this worker can handle
- Which GAVP owns them (for routing in TDS)

The GAVP in the BP's `<campaign>` element must match the deployed worker's GAVP exactly — this is the thread connecting CT → TDS → worker.

### 4.2 Spring Boot as the Container

`JavaWorkerApplication` is a standard `@SpringBootApplication`. JNW hooks into Spring lifecycle events:

```java
SpringApplication app = new SpringApplication(JavaWorkerApplication.class);
app.addListeners(
    new ApplicationReadyListener(),    // fires after context up → connects to queue
    new ApplicationFailedListener()    // fires on startup failure → graceful shutdown
);
app.run(args);
```

`ApplicationReadyListener` is where JNW bootstraps:
- Creates the `SimpleMessageListenerContainer` bound to the worker queue (`${execution.task.queue.input}`)
- Registers all `@TaskProcessor` Spring beans in `WorkerExecutorRegistry`
- Starts the ZooKeeper heartbeat
- Publishes initial health state

### 4.3 The Data Model: TaskInputData is a Map

Everything flowing between BP steps is a flat `Map<String, Object>`:

```
TaskInputData
  └── getData() → Map<String, Object>
        Keys = field names (string constants from ProcessingAttributes.java)
        Values = JSON-serialized strings

JsonTaskInputData  (wraps TaskInputData)
  └── getValueAsType("screened_data", ScreenedData.class)
        → reads raw string from map → Gson.fromJson → typed object

JsonTaskOutputRow
  └── putValue("screened_data", screenedData)
        → Gson.toJson(screenedData) → stores back as JSON string in map
```

Each BP step reads what it needs, writes what the next step needs. The map accumulates fields as it moves through the pipeline.

### 4.4 The `@TaskProcessor` Annotation and Routing

```java
@TaskProcessor(id = "input-task")   // id must match <campaign> task id in BP zip
@RequiredArgsConstructor
public class InputTaskProcessor extends NSSSchemaBasedTaskProcessor { ... }
```

At runtime, `WorkerExecutorRegistry` (JNW framework) holds a map of `task-id → ITaskProcessor bean`. When a message arrives with task type `input-task`, the registry finds the right bean and calls `process`.

### 4.5 ZooKeeper's Role

| Role | Detail |
|---|---|
| Duplication control | Distributed lock per `duplication_control_id` — prevents same task running twice if redelivered |
| Bot source constraints | Rules on which worker groups can execute which task types |
| BP instance status | TDS checks this before routing — won't route to a stopped BP |
| Worker heartbeat | `execution-control-v2` module publishes heartbeat every 20s to `exec._sys.worker.control` |

### 4.6 JNW Module System

Optional platform services injected as Spring beans:

| Module | Dependency | What you get |
|---|---|---|
| `module-event` | `com.workfusion.spa.java.native.worker:module-event` | `EventLogger` — logs visible in Control Tower UI, not just file |
| `module-secrets` | `module-secrets` | `SecretService` — reads credentials from HashiCorp Vault |
| `module-billing` | `module-billing` | `BillingInfoService` — reports transaction counts to ODF2 billing engine |
| `module-distributed-services` | `module-distributed-services` | `ObjectPoolRunnerFactory` — shared objects across parallel task threads |

NSS uses `module-event`, `module-secrets`, and `module-billing`.

---

### 5.1 Base Processor Classes

NSS wraps `ITaskProcessor` in two abstract base classes that every processor inherits:

**`NSSTaskProcessor`** — for flat `TaskInputData` (old-style string map):

```java
public abstract class NSSTaskProcessor implements ITaskProcessor {
    public void init(TaskInputData input) { }          // override: setup
    public boolean shouldRun(TaskInputData input) { return true; }  // override: guard
    public abstract TaskOutputData run(TaskInputData input);        // implement: logic
    public TaskOutputData afterRunning(TaskOutputData output) { ... }

    @Override
    public TaskOutputData process(TaskInputData input) {
        init(input);
        TaskMdcUtil.addTransactionIdToMdc(input);      // MDC for structured logging
        TaskOutputData out = shouldRun(input) ? run(input) : insteadOfRunning(input);
        return afterRunning(out);                       // clears MDC
    }
}
```

**`NSSSchemaBasedTaskProcessor`** — for JSON-typed `JsonTaskInputData` (schema BPs):

```java
public abstract class NSSSchemaBasedTaskProcessor implements ITaskProcessor {
    public void init(JsonTaskInputData input) { }
    public boolean shouldRun(JsonTaskInputData input) { return true; }
    public abstract JsonTaskOutputData run(JsonTaskInputData input);

    @Override
    public TaskOutputData process(TaskInputData raw) {
        JsonTaskInputData input = new JsonTaskInputData(raw);  // wrap
        init(input);
        TaskMdcUtil.addTransactionIdToMdc(input);
        JsonTaskOutputData out = shouldRun(input) ? run(input) : insteadOfRunning(input);
        return afterRunning(out);
    }
}
```

`insteadOfRunning` passes the input map through unchanged — used when `shouldRun` returns false (e.g. wrong provider, wrong BP variant).

### 5.2 All 31 NSS Processors

| `@TaskProcessor(id = ...)` | Class | Base | Description |
|---|---|---|---|
| `input-task` | `InputTaskProcessor` | Schema | Parse input record; start transaction; build ScreenedData + WleList |
| `prepare-for-ml-task` | `PrepareForMlProcessor` | Schema | Build ML document; check data pairs limit |
| `save-model-results-task` | `SaveModelResultsProcessor` | Schema | Store ML scores; determine FP/NMI decision |
| `alert-report-task` | `AlertReportProcessor` | Schema | Generate alert report data |
| `html-report-task` | `HtmlReportProcessor` | Schema | Render HTML report via Freemarker |
| `send-results-back-to-caller` | `SendResultsBackToCallerProcessor` | Schema | Reply to caller: `rest_response` (external REST) or typed fields (internal BP call, e.g. CSV/OBP). `@SendResultToCaller` result is delivered only to synchronous callers — see MAIN_BP_FLOW.md "How results reach a caller" |
| `qc-report` | `QcReportProcessor` | Schema | Generate QC compliance report |
| `screening-system-report` | `ScreeningSystemReportProcessor` | Schema | Generate screening system report |
| `select-for-manual-review-task` | `SelectForManualReviewProcessor` | Schema | Decide if alert goes to manual review |
| `prepare-data-for-manual-review` | `PrepareDataForManualReviewProcessor` | Schema | Format data for MT (manual task) UI |
| `save-manual-review-results` | `SaveManualReviewResultsProcessor` | Schema | Persist MT reviewer's decision |
| `reformat-mt-results` | `ReformatMtResultsProcessor` | Schema | Normalize MT result format |
| `factiva-task` | `FactivaTaskProcessor` | Schema | Call Factiva (Dow Jones) enrichment API |
| `world-check-one-task` | `WorldCheckOneTaskProcessor` | Schema | Call WC1 screening API |
| `thomson-reuters-data-prepare` | `ThomsonReutersDataPrepareProcessor` | Schema | Prepare TR request payload |
| `thomson-reuters-response` | `ThomsonReutersResponseProcessor` | Schema | Process TR response |
| `firco-message-details` | `FircoMessageDetailsProcessor` | Schema | Fetch Firco message details |
| `firco-messages-batch` | `FircoMessagesBatchProcessor` | Schema | Batch-process Firco messages |
| `download-firco-messages` | `DownloadFircoMessagesProcessor` | Schema | Download messages from Firco Trust |
| `address-lookup-prepare-data-task` | `AddressLookupPrepareDataTaskProcessor` | Schema | Prepare location enrichment request |
| `save-address-lookup-data-task` | `SaveAddressLookupDataTaskProcessor` | Schema | Store address lookup result |
| `ticker-lookup-task` | `TickerLookupTaskProcessor` | Schema | Look up ticker symbols |
| `ticker-lookup-download-processor` | `TickerLookupDownloadTaskProcessor` | Schema | Download ticker data |
| `csv-task` | `CsvTaskProcessor` | Schema | Process CSV ingestion record |
| `csv-monitor-task` | `CsvMonitorTaskProcessor` | Schema | Monitor CSV ingestion progress |
| `csv-schema-producer` | `CsvSchemaProducerProcessor` | Schema | Generate CSV schema |
| `finish-transaction` | `FinishTransactionProcessor` | Schema | Mark transaction complete; send billing info |
| `select-master-record` | `SelectMasterRecordProcessor` | Schema | Select master record in aggregation |
| `wait-for-completion` | `WaitForCompletionProcessor` | Schema | Wait for parallel branches to complete |
| `purge-datastore-task` | `PurgeDatastoreProcessor` | Schema | Purge old datastore records |
| `populate-analytics-master` | `PopulateAnalyticsDataProcessor` | Direct `ITaskProcessor` | Rebuild analytics aggregate table (SQL) |

### 5.3 The NSS Pipeline Data Flow

Each step reads from and writes to the shared `JsonTaskInputData` map. Keys defined in `ProcessingAttributes.java`:

```
[input-task]
  reads:  REST request payload / flat input fields / configuration.json
  writes: TRANSACTION_ID, SCREENED_DATA, WLE_LIST, WLE_COUNT,
          CONFIGURATION, PROVIDER_ID, INTERNAL_REQUEST,
          LOCATION_ENRICHMENT_ENABLED, REQUEST_ID

[prepare-for-ml-task]
  reads:  SCREENED_DATA, WLE_LIST, TRANSACTION_ID
  writes: DOCUMENT (ML input JSON), MODEL_ID_ATTRIBUTE, MODEL_PARAMETERS,
          GO_FORWARD_ON_FAILURE, DATA_PAIRS_LIMIT_EXCEEDED, TRANSACTION_ID

  (if DATA_PAIRS_LIMIT_EXCEEDED=true → Drools routes directly to save-model-results,
   skipping the AutoML Bridge step entirely)

[AutoML Bridge — ODF2 internal step, not a JNW processor]
  reads:  DOCUMENT, MODEL_ID_ATTRIBUTE
  writes: MODEL_RESPONSE (ML scores)

[save-model-results-task]
  reads:  WLE_LIST, SCREENED_DATA, MODEL_RESPONSE, TRANSACTION_ID,
          DATA_PAIRS_LIMIT_EXCEEDED
  writes: ALERT_DECISION, AUTO_QC, TRANSACTION_ID

[alert-report-task / html-report-task / send-results-back-to-caller]
  reads:  ALERT_DECISION, SCREENED_DATA, WLE_LIST, TRANSACTION_ID
  writes: report artifacts; final API response

[finish-transaction]
  reads:  TRANSACTION_ID, SCREENED_DATA, WLE_LIST, ALERT_DECISION, AUTO_QC
  writes: TRANSACTION_ID (pass-through)
  side-effects: DB transaction marked COMPLETED; billing info sent to ODF2
```

### 5.4 Configuration Access: `TaskConfigurationProvider`

Every processor that needs the DW configuration (from `configuration.json` / the BP step's `instanceConfiguration`) uses:

```java
@Autowired
private final TaskConfigurationProvider taskConfigurationProvider;

@Override
public void init(JsonTaskInputData input) {
    JsonConfiguration config = taskConfigurationProvider.getDigitalWorkerConfiguration();
    // typed access:
    int maxPairs = Integer.parseInt(config.getRequiredProperty("configuration.ml.max_data_pairs"));
    boolean nameEnabled = config.getRequiredProperty("configuration.rules.fields.name", Boolean.class);
    // optional access:
    String modelId = config.getProperty("configuration.ml.model_id").orElse("");
}
```

`TaskConfigurationProvider` is a JNW toolkit bean (`jnw-toolkit-configuration`) injected by the framework. It reads from the `instanceConfiguration` field of `CTTaskInputData` delivered in the task message — so each task execution gets the configuration snapshot active at BP-run time, not at worker startup time.

Path strings come from `NssConfiguration` enum:
```java
MAX_MDP_PAIRS("configuration.ml.max_data_pairs"),
MODEL_ID("configuration.ml.model_id"),
ONGOING_MONITORING("configuration.input.ongoing_monitoring"),
// ...
```

### 5.5 Platform Services in NSS

**Billing** (`FinishTransactionProcessor`):
```java
// Uses ODF2's own transaction UUID for reconciliation
BillingServiceInfoDto dto = BillingServiceInfoDto.withDefaults()
    .customerId(getTenantId())
    .transactionStatus(TransactionStatus.PROCESSED)
    .runUUID(executionUtils.getBPRunId())
    .transactionUuid(transactionUuid)
    .odfTransactionUuid(transactionUuid)   // ODF2 billing link
    .transactionCount(1)
    .toJson();
billingInfoService.sendInfo(dto);
```

**Secrets** (`EmailService`, `FircoTrustService`, `WorldCheckOneProviderFactory`, `FactivaConfigurationBuilder`):
```java
Optional<SecretDto> secret = secretService.getSecret("smtp-password-alias");
```

**Task Context** (`FinishTransactionProcessor`):
```java
// ITaskContextHolder provides runtime context like tenantId
String tenantId = contextHolder.getContext().getTenantId();
```

### 5.6 The `odfTransactionUuid` Field

In `FinishTransactionProcessor`, NSS sends both its own internal transaction UUID and the `odfTransactionUuid` to the billing service. These are the same value — NSS uses its internal UUID as the ODF2 billing reference, creating a 1:1 link between NSS's `ds_uc_B_AML_PEP_transaction_v3_0` table and ODF2's billing ledger.

---

## 6. Testing JNW Processors in NSS

JNW provides a test framework (`com.workfusion.jnw.test`) that runs processors in a lightweight Spring context without a real RabbitMQ or ZooKeeper. NSS uses it in two test tiers:

### Unit tests (`*Test.java`)
Plain JUnit5 with Mockito. No Spring context. Mock `TaskConfigurationProvider`, build `JsonTaskInputData` manually.

### Integration tests (`*IT.java`)
Use `@JnwJunitConfig` — a JNW-provided Spring test context:

```java
@JnwJunitConfig(classes = {IntegrationTestConfiguration.class})
@ExtendWith(DatabaseCleanerExtension.class)
class InputTaskProcessorIT {

    @BeforeEach
    void setup(JnwTaskFactory taskFactory) {
        inputTaskProcessor = taskFactory.fromClass(InputTaskProcessor.class);
    }

    @Test
    void shouldRun_API() {
        TaskResult<TaskOutputData> actual = inputTaskProcessor
            .withBpExecutionUuid(bpRunID)
            .withVariationJsonConfig(ConfigurationPayload.API().build())  // configuration.json snapshot
            .withStringInputData(REQUEST_FIELD_NAME, inputJson)
            .isSchemaBased(true)
            .buildAndRun();

        TaskResultAssert.assertThat(actual)
            .isSuccessful()
            .hasSize(1);
    }
}
```

`SingleTaskLauncher.buildAndRun` calls `process` directly on the processor bean, bypassing the queue entirely. `TaskResult.getData` returns the `TaskOutputData` that would have been sent back to RabbitMQ.

`ConfigurationPayload` (from `names-screening-test-utils`) builds valid `configuration.json` snapshots for each connector type. `IntegrationTestConfiguration` provides H2 (in-memory SQL), WireMock (HTTP), and mocked JNW toolkit beans.

---

### Queue names for NSS

| Queue | Direction | Content |
|---|---|---|
| `exec.control-tower.task.{bpUuid}-{stepId}` | CT → TDS | NSS task (CTTaskInputData) |
| `exec.ct.worker.com.workfusion.dw:names-screening-jnw:3.8.0-dev:jar.{group}` | TDS → NSS worker | Same task, forwarded |
| `exec.control-tower.result.{bpUuid}-{stepId}` | NSS worker → CT | TaskResult with output map |
| `exec._sys.worker.control` | NSS worker → platform | Heartbeat every 20s |

### Key JNW packages in NSS

| Package | Source |
|---|---|
| `com.workfusion.spa.jnative.worker.core.*` | Core: `ITaskProcessor`, `TaskInputData`, `TaskOutputData` |
| `com.workfusion.spa.jnative.worker.core.task.TaskProcessor` | `@TaskProcessor` annotation |
| `com.workfusion.spa.jnative.worker.core.api.JsonTaskInputData` | JSON-typed task input |
| `com.workfusion.spa.jnative.worker.core.listener.*` | `ApplicationReadyListener`, `ApplicationFailedListener` |
| `com.workfusion.spa.jnative.worker.core.processor.ITaskContextHolder` | Runtime context (tenant ID, BP run) |
| `com.workfusion.spa.jnative.worker.module.billing.BillingInfoService` | ODF2 billing |
| `com.workfusion.spa.jnative.worker.module.secret.SecretService` | Vault secrets |
| `com.workfusion.jnw.toolkit.configuration.TaskConfigurationProvider` | DW configuration access |
| `com.workfusion.jnw.toolkit.datastores.*` | DataStore utilities (Gson, etc.) |

### Safety net — polling fallback in CT

If a Spring event is missed (e.g. CT restarts mid-execution), two scheduled jobs in `ProcessCompletedMachineRunService` recover execution:

| Job | Interval | What it does |
|---|---|---|
| `processBotTaskTransition` | every 5s | Re-publishes `BotTaskStreamingRequest` for runs with executed but untransitioned tasks |
| `processCompletedMachineRuns` | every 40s | Re-publishes `StepCompletionRequest` for runs ready for completion |
