# Links for the Evelyn port

The Python SDK home covers coded functions and coded agents: https://uipath.github.io/uipath-python/

The split to keep in mind is "Build a function" versus "Build an agent".

## UiPath Python SDK docs

- https://uipath.github.io/uipath-python/core/functions/ — Coded Functions: writing, running and publishing a Python function.
- https://uipath.github.io/uipath-python/core/studio_web/ — Pushing a local coded project to Studio Web and pulling it back. Studio Web's "Create New" has no Function option, so this is how local code gets there.
- https://uipath.github.io/uipath-python/core/assets/ — `sdk().assets`: `retrieve`, `retrieve_secret`, `retrieve_credential`. They need a robot context or the asset's `AllowDirectApiAccess` flag.
- https://uipath.github.io/uipath-python/core/processes/ — `sdk().processes.invoke`: start a job from code and get its job key.

## Repositories

- https://github.com/UiPath/UiPath-WorkFusion — The migration repo: Isaac, Evan, OrgClas, OWS, IDP and EDE ported to UiPath. Read-only reference.
- https://github.com/UiPath/CoreWF — UiPath's .NET port of Windows Workflow Foundation. Not a migration dependency ([corewf.md](corewf.md)).

**Evelyn and its helpers** (Bitbucket workspace `work-fusion`, taken from the local clones' remotes):
- https://bitbucket.org/work-fusion/names-screening — Evelyn itself.
- https://bitbucket.org/work-fusion/names-screening-contract — The `nss_schema` contract: `ScreenedData`, `WleData` and the decision classes.
- https://bitbucket.org/work-fusion/nss-classification-model — Evelyn's ML model. It also runs the decision-rules matrix ([equivalent.md §13](equivalent.md#13-the-configuration-page-and-the-decision-rules-matrix)).
- https://bitbucket.org/work-fusion/fircosoft-trust — SOAP client for the client's Firco Trust Case Manager ([evelyn-helper-repos.md](evelyn-helper-repos.md)).
- https://bitbucket.org/work-fusion/address-lookup — Google geocoding step embedded in Evelyn's BP ([evelyn-helper-repos.md](evelyn-helper-repos.md)).
- https://bitbucket.org/work-fusion/world-check-one — REST client for Refinitiv World-Check One, with HMAC signing ([evelyn-helper-repos.md](evelyn-helper-repos.md)).
- https://bitbucket.org/work-fusion/name-matching — A Python name-matching library. Not investigated yet.
- https://bitbucket.org/work-fusion/names-screening-api-client — A client for Evelyn's API. Not investigated yet.

## UiPath docs home

- https://docs.uipath.com/ — The official product docs: Orchestrator, Maestro, Data Fabric, Integration Service, Functions, Studio Web and the rest. Every link in the next section lives under it. Start here when a question is about how a UiPath product behaves.
- https://docs.uipath.com/llms.txt — An index written for AI assistants. It explains the URL pattern and links one index per product, e.g. [Functions](https://docs.uipath.com/llms-functions.txt), [Maestro](https://docs.uipath.com/llms-maestro.txt), [Data Fabric](https://docs.uipath.com/llms-data-service.txt), [Orchestrator](https://docs.uipath.com/llms-orchestrator.txt). The Orchestrator one is about 1 MB, so search it rather than read it whole. The home page doesn't link this file.
- URL pattern: `docs.uipath.com/<product>/<delivery-model>/<version>/<guide>/<page>`. Automation Cloud pages use `automation-cloud/latest`. Add `.md` to any page URL to get Markdown. Data Fabric pages still use the old `data-service` product name.
- https://docs.uipath.com/functions/automation-cloud/latest/user-guide/about-functions — The official coded Functions docs, Python and JavaScript. They overlap the SDK site above; not yet compared with [coded-functions.md](coded-functions.md).
- https://docs.uipath.com/coding-agents/coding-agents/index — "UiPath for Coding Agents". Not read yet.

## UiPath product docs

**Storage and secrets**
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/about-storage-buckets — Storage bucket providers: Orchestrator, Azure, Amazon S3, GCS. The replacement for Evelyn's S3.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/managing-storage-buckets — Creating a bucket, including an S3-backed or read-only one.
- https://docs.uipath.com/integration-service/automation-cloud/latest/user-guide/uipath-amazon-webservices — The AWS connector (S3, EC2). It has no events, so it can't trigger a run.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/about-assets — Asset types. Caveat: Secret assets are documented as working "only with coded agents"; whether functions count is unconfirmed.
- https://docs.uipath.com/activities/other/latest/workflow/get-robot-asset — Get Asset's `CacheStrategy`, the only native cache found.

**Data Fabric (formerly Data Service)**
- https://docs.uipath.com/data-service/automation-cloud/latest/release-notes/june-2025 — The rename from Data Service to Data Fabric .
- https://docs.uipath.com/data-service/automation-cloud/latest/release-notes/may-2026 — The Data Fabric connector going GA .
- https://docs.uipath.com/data-service/automation-cloud/latest/user-guide/enabling-the-data-service — Limits: 200 fields per entity, 5,000 API calls per minute.
- https://docs.uipath.com/data-service/automation-cloud/latest/user-guide/license-allocation — What one Enterprise unit buys: storage and 10K API calls per day.
- https://docs.uipath.com/data-service/automation-cloud/latest/user-guide/using-entities-in-projects — Querying entities; at most 1,000 records per query.
- https://docs.uipath.com/data-service/automation-cloud/latest/user-guide/uploading-data-from-csv-using-batch-activities — Batch writes: at most 1,000 records per call.
- https://docs.uipath.com/data-service/automation-cloud/latest/user-guide/managing-the-data-for-an-entity — CSV import limits: 10 MB and 30,000 rows.

**Maestro Flow**
- https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/what-is-flow — What a Flow is. A published Flow runs as an Orchestrator agentic process.
- https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/subflows — Inline subflows, the equivalent of an embedded sub-BP.
- https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/node-rpa-workflow — Job nodes: wait for completion, read `$vars.<id>.output`.
- https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/node-delay — The Delay node. Avoid it for waits (a Delay node once left a parent Flow Running with no incident; see also Isaac D32).
- https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/custom-instance-id — Custom instance ID, e.g. to show a `transaction_id` in the instance list.
- https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/add-human-approval — Human task nodes delivered via Action Center.
- https://docs.uipath.com/maestro/automation-cloud/latest/release-notes/september-2026 — Flow GA . "Coded Functions as nodes" is still Preview.

**Triggers, jobs and queues**
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/about-triggers — Trigger types: time, queue, event, API.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/call-modes-explained — API trigger modes: AsyncRequestReply, LongPolling, FireAndForget.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/release-notes/november-2025 — The AsyncCallback mode removed .
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/event-triggers — Integration Service event triggers. There is no bucket "file arrived" trigger.
- https://docs.uipath.com/integration-service/automation-cloud/latest/user-guide/uipath-microsoft-onedrive-events — OneDrive and SharePoint "file created" events, the nearest thing to a file trigger.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/api-guide/jobs-requests — The StartJobs REST API: release key plus input arguments, returns job keys.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/about-queues-and-transactions — Queues: unique `Reference`, 256K characters per item. A possible home for Firco retries.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/business-exception-vs-application-exception — Auto-retry covers application exceptions only.
- https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/queue-item-statuses — Items stuck In Progress for about 24 h become Abandoned.
