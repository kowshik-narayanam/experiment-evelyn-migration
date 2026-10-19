# Replacing Evelyn's WireMock (Firco) on UiPath

Read-only: files, `git` and public docs; nothing built, deployed or run
against a tenant. Three agents each read one source (Evelyn, `UiPath-WorkFusion`, docs.uipath.com);
Claude re-checked every citation below. Background on Firco itself:
[evelyn-helper-repos.md](evelyn-helper-repos.md#firco-trust-ft).

**Path prefixes**

| Prefix | Path | Read at |
|---|---|---|
| `NS/` | `NSS/names-screening-copy/names-screening` | `master` @ `6dcf7f9d3`, read with `git show` |
| `IT/` | `NS/names-screening-integration-tests/src/test/` | as `NS/` |
| `JNW/` | `NS/names-screening-jnw/src/test/java/com/workfusion/dw/` | as `NS/` |
| `UW/` | `UiPath-WorkFusion` | `main` @ `20b0e240` |

**Which Evelyn checkout:** the working tree is on `bugfix/EXPERT-39666-…` @ `709318dcb`, 33 commits
ahead of and 64 behind `master`. Its Firco e2e tests and fixtures differ (`master` adds
fixed-width, pipe-separated and index-based cases), but the mock works the same way on both.

## The short version

- **Don't port the mock server. Move the mock into the HTTP client.** Nothing in UiPath Automation
  Cloud can answer a raw SOAP `POST`, and the existing ports run no mock servers. They fake the
  HTTP layer inside the Python code. No Flask.
- **One `httpx` transport serves both tiers:** a dict of fixtures in pytest, and a bucket prefix in
  a live e2e run.
- **It must never fall through to the network.** The status update writes into the client's
  production case manager.

| Evelyn today | UiPath replacement | Precedent |
|---|---|---|
| In-process WireMock in the `JNW` ITs | pytest with a fake `httpx` transport passed to the client, plus a socket guard | TrClear |
| Shared WireMock on the environment's master host, port 9999 (e2e) | The same transport inside the Function, reading recorded files from a bucket prefix, switched on per run | Evan's `MockFilesTransport` (unmerged branch) |
| `MockStep` on the manual-review step (e2e) | Flow **output mocking** on that node | Maestro docs |
| A real network round trip | Only if someone insists: WireMock (not Flask) reached through Relay, a VPN or an IP allowlist | None |

## 1. What Evelyn mocks today

Both tiers use WireMock, and both serve recorded TCMAPI XML.

| | `JNW` ITs (one worker step) | e2e (`names-screening-integration-tests`) |
|---|---|---|
| **Server** | `WireMockServer` started inside the test JVM (`JNW/test/tools/MockServer.java:23-26`), dependency `org.wiremock:wiremock-standalone` (`NS/names-screening-jnw/pom.xml:210-215`) | A standalone WireMock that already runs on the WorkFusion environment. Its URL is the `wiremock` test property, else `http://<env>-master1…:9999` (`dw-test-framework` 6.6.0-21 sources, `DigitalWorkerTestProperties.kt:63,79,106`; `IT/java/…/nss/extension/NssE2EParameters.java:19-23`) |
| **Who starts it** | The test, in `@BeforeAll` | Unknown. Nothing in the repo provisions it |
| **Fixtures** | `NS/names-screening-jnw/src/test/resources/firco/__files/` | `IT/resources/stubs/firco/` |
| **How stubs get there** | `stubFor(...)` on the local server | Pushed over WireMock's admin API: `new WireMock(MASTER_HOST, WIREMOCK_PORT)` (`IT/java/…/nss/extension/NssE2EExtension.java:171`), then `importStubMappings` (`…/extension/mocker/FircoTrustMocker.java:21-53`) |
| **Matching** | `POST` to the path with a `Content-Type` containing the type; no body match (`MockServer.java:30-34`) | Substrings of the SOAP body: `msg_ReceiveInventoryRequest` + login, `msg_ReceiveMessageRequest` + message id + login, `msg_ReceiveStatusUpdate` (`FircoTrustMocker.java:25,46,52`) |
| **How the bot reaches it** | `http://localhost` and a port per test: 9091 (`…/nss/task/firco/DownloadFircoMessagesProcessorIT.java:44`), 9090 (`…/FircoMessageDetailsProcessorIT.java:76`), 9093 (`…/nss/task/report/it/ScreeningSystemReportProcessorIT.java:78`) | The test sets the Firco config to endpoint `http://<master host>`, port `9999` (`IT/java/…/nss/e2e/FircoProviderTest.java:75,143-144`). The bot runs on the same network |
| **Post-back checked?** | Yes. A request listener records the `ReceiveStatusUpdate`, and the test parses `Comment` and `Attachment` (`ScreeningSystemReportProcessorIT.java:155,166-169,195,210-219`) | No. No `verify`, scenario or request-journal call anywhere in `IT/`. The only check is zero ERROR events (`NssE2EExtension.java:1141-1145`) |

- **Why the login is in the e2e match:** 10 test threads run in parallel (`IT/resources/junit-platform.properties:3`)
  against one shared server, so the login keeps one test's stubs apart from another's.
- **The e2e also fakes a worker step:** `MOCKED_MANUAL_TASK` replaces the manual-review bot with a
  `MockStep` (`NssE2EExtension.java:172`).
- **wc1 and Factiva** use the same shared server and the same pattern.

## 2. Why it doesn't port as-is

The e2e mock works only because WorkFusion gives you a machine next to the bot. UiPath doesn't.

- **Serverless robots run in UiPath's cloud.** The Build tenant's serverless pool sends its traffic
  from Azure Dublin (`UW/EDE/docs/sos-lookup.md:116-117`). It can't reach a WorkFusion master host
  or your `localhost`.
- **Nothing in Automation Cloud can act as the mock:**

| UiPath option | Why it can't serve a SOAP mock |
|---|---|
| JS/TS Function HTTP trigger | The path becomes an Orchestrator HTTP-trigger slug, not `/TrustReceiveService`. Callers need a bearer token from an External Application. Input is limited to about 10,000 characters |
| API Workflow | Accepts only `application/json` and `application/x-www-form-urlencoded` |
| Orchestrator API trigger | Starts a job and returns its output as JSON. Needs a PAT or OAuth token |
| Integration Service HTTP Webhook | A trigger: accepts only JSON and starts a workflow. It can't answer the caller with recorded XML (**Inference**) |
| Coded Apps | Static hosting only |

So a Flask app would need hosting you run yourself, plus a route in: Relay, a VPN, or a public host
with UiPath's outbound IPs allowlisted. The port doesn't need that infra.

## 3. What the ports do instead (`UW/`)

No mock server is deployed anywhere on `main`. Each domain fakes the HTTP layer in process.

| Domain | Offline | Live e2e | Evidence |
|---|---|---|---|
| **TrClear** (XML over HTTPS, the closest to SOAP) | A route-table fake behind `httpx.MockTransport`; a socket guard that fails any non-loopback connection | No scenarios yet. A replay mock is **planned, not built**. The paid-call Bool asset `tr_clear_call_tr_clear` ships `false` | `UW/TrClear/tests/conftest.py:38-43,187`; `UW/TrClear/TrClearUiPath/TrClearFunction/trclear/transport.py:142-154`; `UW/TrClear/README.md:127,203-207` |
| **Evan** | `httpx.MockTransport` for Google and article downloads | `evan-mode: stub` returns a canned answer with no network (merged). `evan-mode: test` replays recorded files from a bucket prefix (**unmerged**) | `UW/shared/e2e/scenarios/Evan/stub-two-subjects.yaml:1-9`; branch `origin/feature/EXPERT-39847-e2e-tests-for-evan-articles` @ `95a978d0`, file `Evan/EvanUiPath/EvanAmmFunction/evan_amm/function/mocks.py` |

- **Evan's replay lets unmatched requests through:** "Requests without a mock file go to the
  network" (commit `95a978d0`).
- **Evan's replay isn't on `main` yet:** the same commit says "Not for main before a guard exists".
  The run's input alone switches it on.

## 4. The replay transport (sketch)

It matches requests the way `FircoTrustMocker.java:25,46,52` does, and it keeps every request, as
WireMock's request journal does. Claude ran this sketch's self-check on against
hand-made envelopes, **not** against a real CXF request. The WSDL does have a `MessageID` element
in `ReceiveMessageRequest` (`NSS/fircosoft-trust/src/main/resources/wsdl/TrustCaseManagerAPI.wsdl:893-960`).

```python
import re
import httpx

def _fixture_for(body: str) -> str | None:
    # same substring matching as FircoTrustMocker.java:25,46,52
    if "msg_ReceiveInventoryRequest" in body:
        return "response_inventory_messages.xml"
    if "msg_ReceiveMessageRequest" in body:
        message_id = re.search(r"MessageID>([^<]+)<", body).group(1)
        return f"receive_message_request_{message_id}.xml"
    if "msg_ReceiveStatusUpdate" in body:
        return "response_update_message.xml"
    return None

class FircoReplayTransport(httpx.BaseTransport):
    """Plays TCMAPI from recorded files. Never falls through to the network."""

    def __init__(self, read):          # read(name) -> bytes | None: dict.get in pytest, a bucket read in e2e
        self.read = read
        self.requests: list[str] = []  # WireMock's request journal: assert the post-back from here

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        self.requests.append(body)
        name = _fixture_for(body)
        answer = self.read(name) if name else None
        if answer is None:             # WireMock answers 404 when no stub matches
            return httpx.Response(404, text=f"no recorded answer for {name}", request=request)
        return httpx.Response(200, content=answer, headers={"Content-Type": "text/xml"}, request=request)
```

Wiring: `httpx.Client(transport=FircoReplayTransport(read) if test_mode else None)`, where `None`
means the real TCMAPI. TrClear's `connect(..., transport=)` is the same seam.

**Rules for the real version**

- **No pass-through, unlike Evan.** A missed fixture must fail. Falling through could post a status
  update into a client's production case manager.
- **Two switches, not one.** A run input such as `firco-mode: test` plus a deployment Bool asset
  that is `false` in production, so an input file alone can't turn the mock on. This is the guard
  Evan's commit says is missing. TrClear's paid-call asset is the same idea.
- **One scenario = one bucket prefix.** Each prefix holds the three file shapes. `master`'s
  per-test fixtures, such as `response_inventory_messages_fixed_width.xml`, are copied in under the
  plain name. Each run gets its own transport, so the login drops out of the match.
- **Serve bytes untouched.** The Firco quirks (the `&` escaping, `&#x0002;`) depend on the raw bytes, so never
  parse and re-serialize a fixture.
- **Check the post-back in e2e.** At the end of a test run, write `transport.requests` to the
  bucket so the scenario can assert the `ReceiveStatusUpdate`. That beats WorkFusion's e2e, which
  never checks it.
- **Message ids with `&`** appear as `&amp;` in the request body. The e2e fixtures use numeric ids
  (`10000001`…), so the sketch ignores this.
- **Keep the fixtures free of credentials.** Lines 7–8 of FT's fixtures hold logins that look real
  (the Firco fixtures).

## 5. Questions for the team

- Is a test mode inside the shipped Function acceptable for a compliance product? If not, the mock
  stays in pytest only, and the live tier needs a Firco sandbox, which is still an open question.
- Who runs the WireMock on port 9999 today, and does any other team depend on it?
- Should Firco scenarios live in `UW/shared/e2e/scenarios/`, as Evan's do?

## Sources (docs.uipath.com, read )

| Claim | Page |
|---|---|
| Function HTTP triggers: slug, bearer token, size limits | https://docs.uipath.com/functions/automation-cloud/latest/user-guide/javascript-http-triggers |
| API Workflows accept JSON and form-urlencoded only | https://docs.uipath.com/studio-web/automation-cloud/latest/user-guide/faq |
| API triggers start jobs, need a token | https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/api-triggers |
| HTTP Webhook connector | https://docs.uipath.com/integration-service/automation-cloud/latest/user-guide/uipath-http-webhook |
| Flow output mocking: test runs only, off on publish | https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/output-mocking |
| Relay: serverless robots call on-premises APIs | https://docs.uipath.com/robot/automation-cloud/latest/user-guide/calling-on-premises-apis-via-relay |
| Local runtime (preview): Function jobs on your own unattended robot; needs Robot 2026.10 LTS or 26.0.200 STS | https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/local-agents-and-functions |
