# Billing Workflow — Names Screening

How NSS reports transaction billing data to the WorkFusion billing platform.

---

## Overview

Every completed screening transaction emits a billing event. The event travels:

```
FinishTransactionProcessor
        │
        │  BillingInfo (typed record)
        ▼
BillingInfoService.send()          ← module-billing 2.1.0.28
        │
        │  JSON message
        ▼
RabbitMQ exchange: billing.exchange.billing-info
routing key:       billing-info
        │
        ▼
Logstash pipeline: billing-assistant-rmq
        │
        │  indexed document
        ▼
Elasticsearch index: billing-assistant-{customer_id}-{environment_id}-rmq-YYYY.MM
```

---

## NSS Code — Where Billing Is Sent

**File:**

`sendBillingInformation` runs at the end of every successful transaction, before `finishTransactionWithSuccess`.

```java
BillingInfo billingInfo = new BillingInfo.Builder()
    .withBaseSku(BASE_SKU)                           // "DGWEVLNSSR0000XXXXETC"
    .withItemType(ITEM_TYPE)                         // "Digital Worker"
    .withDwName(DW_NAME)                             // "Evelyn"
    .withDwJob(executionUtils.getVariationId())      // variation ID from BP runtime context
    .withDwSkill(DW_SKILL)                           // "Name Sanctions Screening"
    .withCustomerId(...)                             // tenant ID, null if WorkfusionRealm
    .withTransactionStatus(TransactionStatus.PROCESSED.name())
    .withRunUuid(executionUtils.getBPRunId())
    .withTransactionUuid(transactionUuid)
    .withTransactionCount(1)
    .withLastModifiedDate(ZonedDateTime.now())
    .build();

billingInfoService.send(billingInfo);
```

`send` throws `BillingInfoNotDeliveredException` — caught and logged at WARN level.

---

## BillingInfo Fields

| Field | Value | Notes |
|---|---|---|
| `baseSku` | `"DGWEVLNSSR0000XXXXETC"` | SKU code for NSS |
| `itemType` | `"Digital Worker"` | Always fixed |
| `dwName` | `"Evelyn"` | Evelyn is the NSS DW brand name |
| `dwJob` | `executionUtils.getVariationId` | **AI Agent Variation** — identifies which BP variation processed this transaction (CSV, WC1, Firco, etc.) |
| `dwSkill` | `"Name Sanctions Screening"` | **AI Agent Skill** — used as a queryable field in Kibana |
| `customerId` | tenant ID or `null` | `null` when tenant is `WorkfusionRealm` |
| `transactionStatus` | `"PROCESSED"` | Always `PROCESSED` at this point — errors take a different path |
| `runUuid` | BP run UUID | Links billing event to the BP execution |
| `transactionUuid` | transaction UUID | Links to `ds_uc_B_AML_PEP_transaction_v3_0` |
| `transactionCount` | `1` | Always 1 — one event per transaction |
| `lastModifiedDate` | `ZonedDateTime.now` | Timestamp of the billing event |

Fields `type`, `uom`, `environmentId`, `environmentType`, `deploymentCode`, `deploymentDesc`, `fullName` exist on `BillingInfo` but are not populated by NSS — left null for the billing platform to fill if needed.

---

## module-billing Internals

**Artifact:** `com.workfusion.spa.java.native.worker:module-billing:2.1.0.28`
**Managed by:** `java-native-worker-parent:2.1.0.32` BOM

### Bean registration

`BillingInfoServiceConfig` registers **one** bean named `javaWorkerBillingInfoService`, chosen by `@ConditionalOnProperty`:

| Property | Value | Bean registered |
|---|---|---|
| `jnw-module-service-mock-enabled` | `false` (default) | `JavaWorkerBillingInfoService` — sends via RabbitMQ |
| `jnw-module-service-mock-enabled` | `true` | `StubBillingInfoService` — no-op |

Both variants share the same bean name, so Spring always sees exactly one `BillingInfoService` bean at runtime. IntelliJ may flag a false-positive "multiple beans" warning — suppressed by `@Qualifier("javaWorkerBillingInfoService")` on the field.

### RabbitMQ dispatch

`JavaWorkerBillingInfoService.send` publishes to a RabbitMQ exchange. Exchange and routing key are configured via `BillingConnectionProperties`:

| Property | Default |
|---|---|
| `bep.worker.ct.rabbitmq.billing.exchange` | `billing.exchange.billing-info` |
| `bep.worker.ct.rabbitmq.billing.routing-key` | `billing-info` |

If `billingConnectionProperties.isEnabled == false`, the send is skipped silently.

---

## Infrastructure — Logstash to ELK

Configured in **`workfusion-installer`**, deployed via Ansible. Two independent pipelines exist:

### Pipeline 1 — RabbitMQ pipeline (real-time)

**Template:** `installer/roles/logstash/templates/pipelines/billing-assistant-rmq.conf.j2`
**Pipeline ID:** `billing-assistant-rmq`

Logstash consumes from the RabbitMQ queue bound to the billing exchange. Indexes documents to:

```
billing-assistant-{billing_customer_id}-{billing_environment_id}-rmq-YYYY.MM
```

Example: `als-billing-assistant-amerant-preprod-rmq-YYYY.MM`

The `dwSkill`, `dwJob`, `dwName` fields from `BillingInfo` land as **document fields** in this index — they are not part of the index name in the RabbitMQ pipeline. Used in Kibana to filter/aggregate by skill, variation, and DW name.

The filter handles edge cases: empty `customer_id` is replaced with the static `billing_customer_id` var; missing `transaction_count` defaults to `1`; missing `item_sku` defaults to `"BASE"`.

**`@timestamp` behaviour (changed in CORE-65046):** The pipeline previously ran a `date` filter that parsed `last_modified_date` (ISO8601) into `@timestamp` and then removed `last_modified_date` from the document. That block was removed. `@timestamp` is now set by Logstash's own ingestion time, not by the value NSS sends in `BillingInfo.lastModifiedDate`. The `last_modified_date` field remains in the document as a queryable field.

### Pipeline 2 — JDBC pipeline (scheduled, SQL Server)

**Template:** `installer/roles/logstash/templates/pipelines/billing-assistant.conf.j2`
**Pipeline ID:** `billing-assistant-{dw_skill_id}` (one pipeline per DW)

Polls SQL Server on a cron schedule, runs a SQL query against the NSS database. Indexes to:

```
billing-assistant-{billing_customer_id}-{billing_environment_id}-{dw_skill_id}-YYYY.MM
```

`dw_skill_id` here is an **Ansible deployment variable** (not derived from `BillingInfo`). This pipeline exists for legacy/fallback data collection from the DB.

### Pipeline 3 — Billing Aggregator BP (UiPath integration, CORE-65046)

**Role:** `installer/roles/billing-aggregator-bp/`
**Deployed only when:** `is_external_partner: true`

A separate WorkFusion BP ("Billing Aggregator Business Process") is imported and scheduled to run every 3 hours (`0 0 */3 * * ?`). It reads aggregated billing data (from the ELK index) and forwards it to UiPath's external billing system. NSS has no code changes related to this — it's purely infrastructure-side. Relevant if you're debugging missing billing data on an external-partner deployment.

### Ansible variables that control index naming

| Variable | Example value | Effect |
|---|---|---|
| `billing_customer_id` | `als` | First segment of index name after `billing-assistant-` |
| `billing_environment_id` | `prod` / `preprod` | Second segment |
| `billing_rabbitmq_exchange` | `billing.exchange.billing-info` | Must match module-billing default |
| `billing_rabbitmq_routing_key` | `billing-info` | Must match module-billing default |
| `billing_rabbitmq_queue` | deployment-specific | Queue bound to the exchange |
| `dw_skill_id` | `nss` | Used in JDBC pipeline ID and index name only |
| `billing_for_dw_skills` | comma-separated list | Controls which JDBC pipelines are deployed |

---

## What EXPERT-37509 Fixed

Before this ticket, NSS used the deprecated `sendInfo(String json)` path via its own `BillingServiceInfoDto` class. That DTO only populated 9 fields and **omitted `dwJob`, `dwSkill`, and `dwName`** (the AI Agent fields). Documents in Kibana had no skill/variation/name to filter.

**Changes made:**
- `FinishTransactionProcessor` — switched to `BillingInfo.Builder` + `billingInfoService.send(BillingInfo)`; added `dwJob`, `dwSkill`, `dwName`
- `BillingServiceInfoDto` — left in place; no longer used by production code
- `IntegrationTestConfiguration` — removed stale `sendInfo` stub; mock is now no-op by default (correct for void `send`)
- `lombok.config` — added `lombok.copyableAnnotations += org.springframework.beans.factory.annotation.Qualifier`
- `FinishTransactionProcessor.billingInfoService` field — added `@Qualifier("javaWorkerBillingInfoService")` to resolve the IntelliJ false-positive ambiguity

---

## Testing

`FinishTransactionProcessorIT` covers the happy path and retry scenario. `billingInfoService` is mocked in `IntegrationTestConfiguration` — `send` is a void method, Mockito's default no-op is correct. No explicit stubbing needed.

---

## Kibana DevTools Queries

Paste these into **Kibana → Management → Dev Tools**. Replace `als` / `preprod` with actual customer and environment IDs for the target deployment. The wildcard index pattern `billing-assistant-*-rmq-*` covers all customers/environments/months.

---

### 1. List all billing indices (find the right index name)

```
GET /_cat/indices/billing-assistant-*?v&h=index,docs.count,store.size&s=index
```

---

### 2. Check the field mapping (confirm dwSkill, dwJob, dwName are present)

```
GET /billing-assistant-*-rmq-*/_mapping
```

Look for `dw_skill`, `dw_job`, `dw_name` in the field list. If they are absent on older documents, those were created before EXPERT-37509 was deployed.

---

### 3. Fetch the 10 most recent NSS billing documents

**Post-EXPERT-37509 (dw_skill populated):**
```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 10,
  "sort": [{ "@timestamp": { "order": "desc" } }],
  "query": {
    "term": { "dw_skill.keyword": "Name Sanctions Screening" }
  }
}
```

**Pre-EXPERT-37509 / verifying billing works before the fix is deployed:**

`base_sku` is the only NSS-specific field present in both old and new documents. Use this when `dw_skill` returns 0 results.

**Important:** `base_sku` is mapped as `text` only in this index (no `.keyword` sub-field) — confirmed by investigating the live `billing-assistant-wf-dw-dev2-rmq-*` index. Using `term` on `base_sku.keyword` returns 0 results with `_shards.skipped: N` (can_match pre-filter fires because the sub-field doesn't exist). Use `match` instead:

```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 10,
  "sort": [{ "@timestamp": { "order": "desc" } }],
  "query": {
    "match": { "base_sku": "DGWEVLNSSR0000XXXXETC" }
  }
}
```

---

### 4. Verify a specific transaction was billed

Replace `<transaction-uuid>` with the UUID from `ds_uc_B_AML_PEP_transaction_v3_0`.

```
POST /billing-assistant-*-rmq-*/_search
{
  "query": {
    "term": { "transaction_uuid.keyword": "<transaction-uuid>" }
  }
}
```

---

### 5. Count billed transactions by BP variation (dwJob)

Shows which variations are generating billing events and how many transactions each has processed.

```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 0,
  "query": {
    "term": { "dw_skill.keyword": "Name Sanctions Screening" }
  },
  "aggs": {
    "by_variation": {
      "terms": { "field": "dw_job.keyword", "size": 20 }
    }
  }
}
```

---

### 6. Count billed transactions by day (last 30 days)

```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "dw_skill.keyword": "Name Sanctions Screening" } },
        { "range": { "@timestamp": { "gte": "now-30d/d", "lte": "now/d" } } }
      ]
    }
  },
  "aggs": {
    "by_day": {
      "date_histogram": {
        "field": "@timestamp",
        "calendar_interval": "day",
        "format": "yyyy-MM-dd"
      }
    }
  }
}
```

---

### 7. Check documents missing dwSkill / dwJob (pre-EXPERT-37509 documents)

Documents created before the fix will have no `dw_skill` field. Use this to measure how many old-format documents still exist.

```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must_not": { "exists": { "field": "dw_skill" } }
    }
  },
  "sort": [{ "@timestamp": { "order": "desc" } }]
}
```

---

### 8. Verify last_modified_date is present in documents (CORE-65046 change)

After CORE-65046, `last_modified_date` is no longer removed by Logstash. This confirms it now lands in the document.

```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 1,
  "sort": [{ "@timestamp": { "order": "desc" } }],
  "query": {
    "term": { "dw_skill.keyword": "Name Sanctions Screening" }
  },
  "_source": ["@timestamp", "last_modified_date", "transaction_uuid", "dw_skill", "dw_job", "dw_name"]
}
```

`@timestamp` = Logstash ingestion time. `last_modified_date` = time `ZonedDateTime.now` was called in `FinishTransactionProcessor`. The two values should be within seconds of each other.

---

### 9. Total transaction count per customer (multi-tenant deployment)

```
POST /billing-assistant-*-rmq-*/_search
{
  "size": 0,
  "query": {
    "term": { "dw_skill.keyword": "Name Sanctions Screening" }
  },
  "aggs": {
    "by_customer": {
      "terms": { "field": "customer_id.keyword", "size": 50 },
      "aggs": {
        "total_transactions": { "sum": { "field": "transaction_count" } }
      }
    }
  }
}
```
