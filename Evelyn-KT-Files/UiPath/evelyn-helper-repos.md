# Evelyn's helper repos: Firco Trust, Address Lookup, World-Check One, NSS contract

Read-only: files and `git` only, nothing built, run or fetched. Three
agents each read one repo; Claude spot-checked the claims that matter most. Claude added the NSS
contract section.

**Path prefixes**

| Prefix | Path (under `NSS/`) | Read at |
|---|---|---|
| `FT/` | `fircosoft-trust` | `feature/EXPERT-39644-fix-snyk-vulns-firco` @ `c781e84` |
| `AL/` | `address-lookup` | `feature/EXPERT-39644-fix-snyk-vulns-address-lookup` @ `51fc186` |
| `WC/` | `world-check-one` | `feature/EXPERT-37324-upgrade-java21` @ `28281fb` ; `origin/master` `6fece51` has the same tree |
| `NC/` | `names-screening-contract` | `origin/master` @ `f955971`, read with `git show`; the working tree is on `feature/EXPERT-39840-…` @ `9e648b6` |
| `NS/` | Evelyn, `names-screening-copy/names-screening` | See the note below |
| `UW/` | `UiPath-WorkFusion` | |

**Which Evelyn checkout:** the working tree is on `bugfix/EXPERT-39666-…` @ `709318dcb`, 33 commits
past the `master` snapshot `6dcf7f9d3`. The Firco, WC1 and contract citations are from `master`,
read with `git show`. The Address Lookup citations, and the `1.2.0` contract pin, are from the
working tree.

## The short version

| | Firco Trust | Address Lookup | World-Check One |
|---|---|---|---|
| **What it is** | SOAP client jar for the client's Firco **Trust Case Manager API** (TCMAPI) | Small WorkFusion bundle: one worker step (`address-lookup-task`) plus a data-model jar | REST client jar for Refinitiv WC1 API v2 (180 of its 192 classes are generated models) |
| **How Evelyn uses it** | Maven jar, wrapped by `NS/names-screening-firco-trust-connector` | Its worker step is **embedded in Evelyn's own BP**; model jar as a Maven dependency | Maven jar, wrapped by `NS/wc1-connector` |
| **BP_CALL / signal id?** | No | No | No |
| **Talks to** | Client's on-premise TCMAPI over plain HTTP SOAP (**Inference**: on premise) | Google Geocoding and Places (or a WorkFusion proxy) | WC1 REST, HMAC-SHA256 signed |
| **Writes back to a vendor?** | **Yes:** status update on the client's case manager | No | **Yes:** case resolution (on by default) |
| **Its own storage** | None (Evelyn has 3 Firco tables) | None | None |
| **Likely UiPath shape** (Inference) | Python SOAP client module inside Evelyn's function; time or API trigger for downloads | One function operation plus `httpx` | Python module of about 150 lines (`hmac` + `httpx`) inside Evelyn's function |
| **Biggest risk** | Byte-level response quirks, plus whether cloud robots can reach TCMAPI | Old bugs that parity may have to reproduce; Google data-sharing sign-off | Exact HMAC signing; every live call creates a WC1 case |

**What this means for the port:**

1. **None of the three is a separate business process that Evelyn calls.** Two are client
   libraries; Address Lookup's worker step runs inside Evelyn's BP. In UiPath they become Python
   modules or operations inside Evelyn's function(s): no extra Flows, jobs or signal ids.
2. **The real logic is in Evelyn's adapter layers**: `names-screening-firco-trust-connector`,
   `wc1-connector` and the two address-lookup processors in `names-screening-jnw`. Those, not the
   helper repos, hold the mapping to `ScreenedData`/`WleData` and the write-back rules.
3. **Two providers write to systems the customer or vendor owns.** Parity runs must use recorded
   fixtures, or a sandbox with write-back off. Never live.
4. **Version pins don't match any release:**
   - Firco: `NS` master pins untagged `4.3.0`; the branch pins untagged `2.6`.
   - WC1: master pins `2.0-SNAPSHOT`; the branch pins `1.12`.
   - Address Lookup: Evelyn pins `1.4.2`/`1.3.2`, while the repo is at `4.3.0-SNAPSHOT`.
   - NSS contract: Evelyn `master` pins `4.2.0` and the 3.10 line pins `1.2.0`, while the repo is
     at `4.3.0-SNAPSHOT` ([below](#nss-contract-nc)).

   Pin the reference source per repo before capturing parity.
5. **No precedent in UiPath-WorkFusion for SOAP or HMAC.** The HTTP-client and Secret-asset
   patterns from Evan and OWS still apply.

## Firco Trust (`FT/`)

**What it is.** A plain jar ("Fircosoft Trust Api Client", `FT/pom.xml:6-9,412-414`).
- Apache CXF generates it from `FT/src/main/resources/wsdl/TrustCaseManagerAPI.wsdl` (1,362 lines).
- Java 21; one module of 16 Java files (8 main, 8 test); 123 commits .
- Latest tag `fircosoft-trust-4.2.0` .
- Four operations (`FircoTrustClient.java:29-75`): `getInventoryMessages`, `getMessageById`,
  `updateMessageStatus` and `sendMessage`. Evelyn never calls `sendMessage`.

**How Evelyn uses it.** `NS/names-screening-firco-trust-connector` (26 main Java files) sits on
top of the jar and adds:
- the Vault lookup
- status logic
- hit mapping (`FircoTrustConverter`, `FircoTrustMapper`)
- format files from S3

The "Firco sub-BP" is an **embedded sub-process**, "Firco Trust Screening" (`BP[Names Screening]:12643`).
1. It is selected when `provider_id EQ FIRCO_TRUST` (`:12483`).
2. Inside it: `download-firco-messages` → `firco-messages-batch` → rule "Process?" (process, retry or
   stop) → `firco-message-details` (`:12729-12739`).
3. Later, `screening-system-report` posts the decision back (`ScreeningSystemReportProcessor.java:95-107`).

**How messages flow**
- **In:** Evelyn polls TCMAPI over SOAP, not via file drops or SFTP.
  - The inventory call uses `SearchCriterion "ALL"`.
  - It filters by unit and business unit (`DownloadFircoMessagesProcessor.java:96-114`) and
    dedupes by `system_id` (`:80-81`).
  - It then fetches each message with its hits and customer info.
- **Back:**
  - `ReceiveStatusUpdate`, operator `WORKFUSION`; the `StatusInfo` checksum is the MD5 of
    `"ID--Name--RoutingCode"` (`FircoTrustService.java:255-264`).
  - `fpStatus` is used only for ALL_FP when updates are enabled, otherwise `nmiStatus` (`:267-273`).
  - It attaches a base64 CSV of `HIT_ID, RESOLUTION, EXPLANATION` (`:344-367`).
- **Format files** only map client columns to Evelyn columns. They are downloaded from S3 and
  cached (`FircoTrustFormatFileDownloaderService.java:28-60`).

**Contracts.**
- `firco-messages-batch`: in {`request_id`, `_sys_ext_record_id`}, out {`transaction_id`, `firco_message_meta_data`}.
- `firco-message-details`: out adds `screened_data`, `wle_list`, `filtered_transaction` and
  `firco_message_parsing_failed`.

**Configuration and data.**
- Config keys: `provider.firco_trust_{endpoint, inventory_port, alias, fp_status, nmi_status,
  b_unit, unit, update_enable, enable_filter, obsolete_period}` and `provider.{pipe,fixed}_format_file`
  (`FircoTrustConfigurationFields.java:9-21`). The login comes from a Vault alias.
- Tables: `firco_messages_v3_0`, `firco_configuration_v3_0` and `firco_retry_monitor_v3_0`
  (migrations `031_1`, `031_2`, `038`).
- Batches are capped at 1,000 rows, with a `reprocessAfter(waitTime)` retry loop
  (`FircoBatchTransactionalService.java:40,75-82,120-124`).

**Hard parts.**
- **Byte-level quirks to reproduce:**
  - `EscapeInterceptor` joins response lines **without newlines** and turns every `&` into `&amp;`
    (`EscapeInterceptor.java:31-42`).
  - Reflective jsoup then unescapes every string (`HtmlEntityConverter.java:20-93`).
  - The fixed-length MessageData parsing depends on both.
- **Endpoint rewriting:** placeholders are rewritten at runtime (`EndpointInterceptor.java:21-23`);
  the `SendMessage` port is hardcoded to 5516 (`wsdl:1332`).
- **Network reach:** can UiPath cloud robots reach an on-premise TCMAPI at all? Unknown.
- **Compliance-sensitive write-back:** the MD5 checksum, status names, `update_enable` and the
  auto-QC "parallel production" modes all touch the client's production case manager.

**Tests.**
- `FT`: 10 Mockito tests and 4 WireMock ITs, with 4 SOAP fixtures, e.g. `InventoryRequest.xml`
  (144 messages) and `Message_Request_FIMG15&R.MMSAN.xml` (12 hits).
- `NS`: 15 connector test files, 7 format CSVs, `FircoProviderTest` (11 e2e tests).
- `NS` mocks TCMAPI with WireMock: in process for the `jnw` ITs, and as a shared server on the
  environment's master host, port 9999, for the e2e tests. UiPath can't host that server; the mock
  moves into the client's `httpx` transport instead: [wire-mock-replacement.md](wire-mock-replacement.md).

**UiPath (Inference).**
- The client becomes a Python SOAP client module with the WSDL bundled.
- The sub-BP becomes a subflow or a separate Flow ([equivalent.md §3](equivalent.md#3-sub-bps)).
- The download step needs a time trigger, or an API trigger for the REST variant.
- The batch and retry loop becomes polling inside a function under the 15-minute cap, or one
  queue item per message.
- The Vault alias becomes a Credential asset; the format files go in a bucket.

**Questions for the team:**
- Which clients use Firco, and where does TCMAPI live?
- Is there a Firco sandbox for capturing parity cases?
- What starts production runs: a REST call or a schedule?
- Has 4.3.0 been released?

## Address Lookup (`AL/`)

**What it is.** WorkFusion use case `ADDRESS_LOOKUP` (`AL/pom.xml:7-11,22`): Java 21, 51 Java
files (34 main, 1,249 lines; 17 test, 30 test methods), 69 commits . It has no
README. It contains:
- the worker step `address-lookup-task` (`AddressLookupTask.java:27`);
- a standalone BP, "Location Enrichment", with no signal id;
- a Form.io config page.

The `address-lookup-api-client` module, an AWS Lambda proxy, is commented out of the build
(`pom.xml:89`). `address-lookup-model` is an OpenAPI data model (request, response, `Address`,
`Provider` enum), **not ML**.

**How Evelyn uses it.** It is not called; its step is embedded. The jars are `address-lookup-model`
1.3.2 (`NS/names-screening-jnw/pom.xml:15,73-75`) and `address-lookup-jnw` 1.4.2, bundled
(`NS/pom.xml:24`).

The path is Names Screening → sub-BP "Data Enrichment" → sub-BP "Address Enrichment"
(`BP[Names Screening]:11312,11324-11409`):
1. Rule `location_enrichment_enabled` (`:2750-2766`).
2. `address-lookup-prepare-data-task`.
3. Rule "Address Present?" (`:11361`).
4. `address-lookup-task` (`:10853-10856`).
5. `save-address-lookup-data-task`.

**What moves.**
- **Prepare** sends only `LocationEntity.original.address`, and only when country, street, city and
  state are all empty (`AddressBuilder.java:12-24`). Its output is `lookup_address`, a
  de-duplicated set of strings.
- **The task** adds `lookup_address_results`: a list of `{address, results[Address], errorMessage}`
  (`AddressLookupTask.java:54-65`).
- **Save** fills `LocationEntity.enriched[]`, with lat/lon as strings, and sets `source`. It drops
  `countryIso2`, `streetNumber` and `placeId`, and errors are only logged
  (`SaveAddressLookupDataTaskProcessor.java:87-101`).
- **Timing:** synchronous, blocking, one address at a time; no polling.

**External services.**
- **Google Geocoding:** GET with `address` and `key` (`GoogleGeocoderService.java:45-48`).
- **Google Places:** Autocomplete `types=(cities)`, then one Details call per prediction
  (`GooglePlacesApiService.java:88-92,119-129`).
- **"Indirect" mode:** POST to a WorkFusion proxy with `x-api-key`, from a Vault alias
  (`WorkfusionLocationService.java:62-64`). Evelyn's form offers only `direct`
  (`NS/.../configuration.json:1492`).
- **Nominatim:** a stub, not wired in.
- **The API key** sits in the digital-worker config (`enrichment.location.apiKey`), **not Vault**.

**Hard parts.**
- **Thread safety:** keys live in static fields, and one shared response object can carry errors
  across addresses (`WorkfusionLocationService.java:30,39,68,78`).
- **Error handling:**
  - On any error the geocoder calls `Thread.interrupt()` (`GoogleGeocoderService.java:68-69`).
  - Errors are detected with `content.contains("error_message")`, so ZERO_RESULTS or a quota
    response passes as empty.
  - One failed Details call fails the whole address.
- **Data shape:**
  - `partialMatch` and `locationType` are never set by the geocoder mapper (`GoogleApiMapper.java:59-87`;
    lines 38-52 are the Places mapper), yet a fixture contains them.
  - JSON casing is ambiguous: the core mapper is SNAKE_CASE, the fixtures are camelCase.
- **Resilience:** no timeouts, retries or rate limits (`HttpClients.createDefault()`).
- **Possible Evelyn bug:** `isLocationEnrichmentEnabled` returns true when the provider key is
  missing (`NS/.../InputTaskProcessor.java:100-103`).

**Tests and fixtures.** Recorded Google responses with expected outputs, e.g.
`jnw/src/test/resources/integration/service-response/google_places_api/{Irbid,california}-*.json`
→ `lookup-service-response.json` and `geocoder-response-call-{1,2}.json`. Evelyn's save ITs cover
the mapping into `enriched[]`.

**UiPath (Inference).**
- The task becomes a `lookup_addresses` operation in Evelyn's function, with Evan's dispatcher
  (`UW/Evan/EvanUiPath/EvanAmmFunction/entrypoints.py:150-163`) and `httpx` as in Evan's Google
  client (`evan_amm/google/client.py:52`).
- The key goes in a Secret asset (`entrypoints.py:388-402`).
- The Address Enrichment sub-BP and its two rules become an inline subflow or decision nodes.
- The standalone BP has no UiPath equivalent: nothing in Evelyn uses it.
- No bucket or Data Fabric is needed.

**Questions for the team:**
- Which provider and connection type do customers use? Is the WorkFusion proxy still live?
- Who owns the Google key and its billing under UiPath? Is the legacy Places API still enabled?
- Does compliance allow sending screened addresses to Google?
- Should the port reproduce the bugs above for parity?

## World-Check One (`WC/`)

**What it is.** `com.workfusion.gorilla:world-check-one:2.0-SNAPSHOT`, a client for the WC1 REST
API v2 (`WC/pom.xml:5-6`, `WC/README.md:1-5`).
- Java 21, google-http-client and Gson.
- 192 main Java files, 180 of them generated from the OpenAPI 2.2.0 spec; 10 test files.
- 226 commits .
- The README calls `screeningRequest` asynchronous, but Evelyn uses it synchronously.

**How Evelyn uses it.** `NS/wc1-connector/pom.xml:18` pins `2.0-SNAPSHOT`. `wc1-connector` is
Evelyn's adapter: it builds the clients (`WorldCheckOneProviderFactory.java:40-58`), converts
results to `WleData` and writes decisions back. Only `CaseApiClient` and `GroupsApiClient` are
used.
- **Inference:** the MediaCheck code serves Evan. In the Evan port that provider is "stored only"
  (`UW/Evan/.../WorldCheckOneProvider.tsx:20`).

**Processors.**
- `world-check-one-task` (the contract files are named `wc1-task-processor.*`):
  - In: `screened_data`, `transaction_id`.
  - Out: `screened_data` (plus `additionalData.case_system_id`), `wle_list`, `transaction_id`,
    and `wle_count`. `wle_count` is missing from the out contract (`WorldCheckOneTaskProcessor.java:37-55`).
  - With a `case_system_id`, it fetches that case's results. Otherwise it creates a case with
    provider types WATCHLIST and MEDIA_CHECK (`NS/wc1-connector/.../WorldCheckOneProvider.java:45-67,127-134`).
- `screening-system-report` writes the decision back unless the resolution is NO_HITS
  (`ScreeningSystemReportProcessor.java:85-86,111-134`).

**API.** Everything is under `{refinitiv_url}/v2` (`CaseApiClient.java:28-71`, `GroupsApiClient.java:22-34`):
- `POST /cases/screeningRequest`
- `GET /cases/{id}/results`
- `PUT /cases/{id}/results/resolution`
- `GET /groups/{groupId}/resolutionToolkit`

**Auth: HMAC-SHA256** (`WC/.../provider/CredentialsProvider.java:26-61`).
- The signed string covers `(request-target)` (method plus path, without the query), `host` and an
  RFC 1123 GMT `date`.
- POST and PUT also sign `content-type`, `content-length` (UTF-8 bytes) and the body.
- Calls are synchronous: no polling, retries, 429 handling or explicit timeouts. Rate limits are unknown.

**Mapping results to WLEs** (`WorldCheckOneWleConverter.java:63-111,187-208`).
- `id` = `resultId`, `name` = `matchedTerm`.
- `entityType` is **INDIVIDUAL if a gender is present, else ORGANIZATION**.
- Dates are kept only when the year has 4 digits.
- `uuid` is random, and `matchStrength` is not mapped.

**Write-back** (`WorldCheckOneProvider.java:69-125`). Status, risk and reason labels become ids via
the group's resolution toolkit. "Parallel production" and auto-QC force UNSPECIFIED/UNKNOWN.

**Configuration.**
- Config keys: `provider.WORLD_CHECK_ONE_{URL, GROUP_ID, ALIAS}`,
  `provider.world_check_one_update_enable` (default **true**), and the `parallel_production`,
  `reason`, `{nmi,fp}_update_{status,risk}` keys.
- Secret: a Vault alias, default `nss.nn.wc1.credentials`; key = API key, value = API secret.

**Cache bug (Inference).** Evelyn's `@Cacheable("resolution-toolkit")` key includes a client that is
created fresh on every run and has no `equals`. So the cache never hits and grows without limit.

**Tests and fixtures.**
- `WC`: 28 test methods.
- The better parity source is Evelyn's: `NS/wc1-connector/src/test/resources/json/` holds 5
  recorded responses, paired with **expected WLE outputs** in `results/convertor_result*.json`.
- Plus `WorldCheckOneProviderTest` (9 e2e tests).

**UiPath (Inference).**
- The client becomes a Python module of about 150 lines (stdlib `hmac`/`hashlib`/`base64` plus
  `httpx`, as OWS does in `UW/OWS/OpenWebSearchUiPath/OpenWebSearchFunction/ows/service/http.py`).
- The connector becomes `wc1-screen` and `wc1-resolve` operations.
- The Vault alias becomes a Credential asset (OWS `secrets.py:24,43`).
- The toolkit is fetched once per job.

**Hard parts.**
- **Signing:** sign the exact bytes you send (serialize once and send with `content=`), and leave
  the query out of the signed path. Build golden test vectors from the Java code first.
- **Side effects:** every new screening creates a WC1 case, and write-back is on by default.
- **Licence and network:**
  - Is the API key WorkFusion's or the customer's?
  - Are UiPath cloud IPs allowed, and where does the screened personal data reside?
- **Throughput:** each name costs 2 sequential calls, so batch names per job under the
  15-minute cap.
- **Parity quirks:** the gender-based entity type, the random uuid, and dropped non-4-digit years.

**Questions for the team:**
- Is WC1 live for any customer? The default provider is FACTIVA.
- Is MEDIA_CHECK needed when Evelyn ignores its results?
- What quota comes with the key? Is there a sandbox?

## NSS contract (`NC/`)

**What it is.** It contains no Java code. It is one OpenAPI 3.0 file,
`NC/src/main/resources/nss_schema.yaml` (347 lines, 22 schemas), shipped as the jar
`com.workfusion.dw:names-screening-contract` (`NC/pom.xml:8-9`). Of the 6 files on `master`, the
others are the changelog, Jenkins scripts and the pom.
- **Schemas:**
  - entities: `NameEntity`, `DateEntity`, `LocationEntity`…;
  - `ScreenedData`, the record being screened (`:90-133`);
  - `WleData`, a watchlist hit;
  - decisions: `AlertDecision`, `WleDecision` and one decision type per factor;
  - `FircoMetaData` and `QCReport`.
- **Two version numbers, unrelated to each other:**
  - the release tag, which Evelyn pins;
  - `info.version` (`:5`), filled at build time from `usecase.schema-version`
    (`NC/pom.xml:17,35`; `1.1.1` on `master`).

**How Evelyn uses it.** Evelyn doesn't import ready-made classes; it generates them at build time.
1. `NS/names-screening-schema/pom.xml:109` unpacks `nss_schema.yaml` from the jar.
2. `:162-192` runs `openapi-generator` (the `spring` generator, models only) into package
   `com.workfusion.dw.nss`, with Lombok annotations and **Gson** serialization.
3. Five modules depend on the generated classes:
   - `names-screening-jnw`
   - `wc1-connector`
   - `factiva-connector`
   - `names-screening-firco-trust-connector`
   - `names-screening-package`

**Which version.** The pin is `usecase.schema-contract-version` (`NS/pom.xml:23`).

| Evelyn line | Pins | Schema content |
|---|---|---|
| `master` @ `6dcf7f9d3` | `4.2.0`, since `bfca17ab7` | Same as tags `1.3.0` and `1.3.1` and contract `master` |
| `bugfix/EXPERT-39666-…-310` @ `709318dcb`; the 3.10 line (**Inference**, from the branch name) | `1.2.0`, since `137a2c62d` | Only `ScreenedData.add_to_ongoing_monitor` is missing |
| Contract branch `feature/EXPERT-39840-…` @ `9e648b6`, not merged | Not pinned yet | Adds `ScreenedData.originalTransaction` (uuid) |

**Schema details that matter for a Python port.**
- **Optionality:** no field is `required` and none is `nullable`, so every field is optional.
- **Casing:** property names are mostly camelCase. `client_id`, `additional_data`,
  `add_to_ongoing_monitor`, `report_links` and `format_file` are snake_case. The YAML names are the
  names on the wire.
- **Defaults:** `client_id` is `"1"` (`:98-100`) and `add_to_ongoing_monitor` is `false` (`:131-133`).
- **Maps:** `identifiers` and `additional_data` are free string-to-string maps.
- **Mixed JSON libraries:** `QCReport` adds Jackson `@JsonProperty` annotations
  (`x-field-extra-annotation`, `:341,347`), while the rest is generated for Gson.
- **Enums:** six, e.g. `EntityType`, `AlertResolution` and the inline `manualReviewStatus` (`:295`).

**The per-step contracts live in Evelyn, not in this repo.**
- `NS/names-screening-jnw/src/main/resources/configs/main/` holds 52 `*.{in,out}-contract.yaml`
  files for 28 processors.
- Each one `$ref`s `nss_schema.yaml`. For example, `wc1-task-processor.in-contract.yaml` takes
  `screened_data` (`ScreenedData`) and `transaction_id` (uuid).
- The unmerged contract branch `feature/EXPERT-36487-add-nss-contracts-schema` (`707964b`,
  ) holds 47 such files under `src/main/resources/taskprocessor/contracts/`. Compared with
  Evelyn `master`:
  - 37 are byte-identical;
  - 8 differ;
  - 7 of Evelyn's are missing from the branch (`custom-configuration`, `reformat-tr-results`,
    `send-results-back-to-caller`, and `qc-report`'s out contract);
  - the branch's `api-response` pair is not in Evelyn `master`.

  Treat Evelyn's copy as the source; the branch is stale.

**UiPath (Inference).**
- **Model generation:**
  - Generate Pydantic models with `datamodel-codegen`, as Isaac does
    (`UW/Isaac/scripts/generate_contract_models.py`).
  - Each Function is packaged alone and can import only what it ships
    (`UW/Isaac/tests/foundation/test_function_projects_are_self_contained.py:1-7`). So vendor one copy
    into each Function and add a byte-identity test
    (`UW/Isaac/tests/foundation/test_contract_copies_are_identical.py`).
- **Wire names:** keep the YAML names as aliases, as Isaac's models do
  (`UW/Isaac/IsaacUiPath/IsaacRulesFunction/isaac_contracts/models.py:17`), and dump with
  `by_alias=True`.
- **Strictness:** nothing is required, so Isaac's nullability patches
  (`generate_contract_models.py:37-55`) shouldn't be needed. Enums are the risk: Pydantic rejects an
  unknown value, and what Evelyn's generated Gson classes do with one is unverified. Settle it with a
  test.
- **Per-step contracts:** they become each operation's `Input` and `Output` models.
  - Their `$ref`s point at a build-time path, `schema/com/workfusion/dw/nss/nss_schema.yaml`.
  - So copy the schema to that path before generating, or rewrite the refs.
- **Reference pins:** pin `NC` to the tag that Evelyn's parity baseline uses, and take the per-step
  contracts from that same `NS` commit.

**Questions for the team:**
- Which Evelyn line is the parity baseline: `master` (contract `4.2.0`) or the 3.10 line (`1.2.0`)?
- Will `originalTransaction` (EXPERT-39840) land before the reference outputs are captured?
- Is the EXPERT-36487 branch abandoned, or is the plan still to move the per-step contracts here?

## Committed secrets spotted (values not copied)

These are worth raising with the repo owners: rotate the key if it is real, then remove it from
the files and their git history.

- **Google API key:** a Google-API-key-shaped value at
  `AL/address-lookup-jnw/src/test/resources/integration/configuration/google_places_api_configuration.json:5`.
  Five commits in history match.
- **Google API key in Evelyn:** another Google-key-shaped value at
  `NS/names-screening-test-utils/.../ConfigurationPayload.java:280`.
- **Firco login:** all four FT fixtures in `FT/src/test/resources/firco/__files/` have
  `UserLogin`/`UserPassword` at lines 7-8.
  - The two inventory files (`InventoryRequest.xml`,
    `Inventory_request_that_contains_html_entities.xml`) hold a 22-character password that is not
    an obvious placeholder.
  - The two message files have a short login and an empty password.
- **WC1 credentials:** `WC/src/test/resources/wc1_credentials.properties:1-3` has
  `API_KEY`/`API_SECRET`/`GROUP_ID`. The values are 3–6 characters, so probably placeholders;
  verify.
