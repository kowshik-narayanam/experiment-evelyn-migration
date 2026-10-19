# Evelyn's model on UiPath: how the ports host a model

How an ML model runs inside a UiPath coded Function, from the two ports that do it (Evan,
OrgClas), and what that means for Evelyn's `nss-classification-model`. Read-only; nothing was run.

Short paths:

| Short | Where |
|---|---|
| `UW/` | `UiPath-WorkFusion/`, `main` @ `0b55aa86` |
| `ESF/` | `UW/Evan/EvanUiPath/EvanScoreFunction/` |
| `OCF/` | `UW/OrganisationClassification/OrganisationClassificationUiPath/OrganisationIndustryClassificationFunction/` |
| `MDL/` | `NSS/nss-classification-model`, `master` @ `ee3129e4` (5.4.0-dev; Evelyn ships 5.3.0) |
| `NS/` | the Evelyn repo, read with `git show master:<path>` |

## The short version

1. **The model files live in a storage bucket.** The Function downloads and unpacks them to a temp
   folder when the job starts, and reuses that folder while the robot stays warm.
2. **The model runs in a child Python process,** not inside the Function. The model pins old
   libraries that need Python 3.11, and they clash with the `uipath` SDK's own. The two processes
   talk through `request.json` and `response.json` files.
3. **The model gets its own function project,** so only that project needs a big robot.
4. **Robot size is set after deploy,** by the pipeline, never by the package. 1 GB robots die with
   no error.
5. **Everything must fit in the 15-minute job cap,** so batch several items into one child run.
6. **Evelyn's model is mostly a rules engine, not trained weights.** It's small except for its
   Python environment, which makes it easier to host than Evan's.

In WorkFusion terms: the Python Bridge (Java starting the model's Python) becomes the Function
starting a child Python. Model files in S3 become model files in a bucket.

## How Evan and OrgClas do it

| Question | Evan (`EvanScoreFunction`) | OrgClas |
|---|---|---|
| Where the files come from | 5 blobs in a bucket, downloaded and unpacked to `{tmp}/evan-amm-artifacts` (`ESF/evan_amm/mlhosting/model/artifacts.py:358-367`): model 53 MB, `deps-data` 3.35 GB, vendor environment 485 MB, a standalone CPython zip, wheels (`UW/Evan/docs/model-artifacts.md`) | 4 blobs in bucket `OrganisationClassificationModels`: interpreter, environment, model, wheels (`OCF/bindings.json:6-14`; `OCF/orgclas/runtime.py:60-70`) |
| In process or child | Child (`classifier-engine: model-subprocess`). The pickles pin numpy 1.26.4 and scikit-learn 1.5.2, which means Python 3.11 (`UW/Evan/docs/model-hosting.md:15-22`) | Child by default (`OCF/orgclas/runtime.py:61`) |
| How they talk | `request.json` → child → `response.json`, not pipes (`ESF/evan_amm/mlhosting/subprocess/__init__.py:109`) | Same file protocol |
| Robot size | **Large.** Peak memory 4.0 GB (5.2 GB on the older model) (`UW/pipelines/README.md:1237`) | **Medium**, 4 GB. 1 GB dies mid-download with no error (`UW/OrganisationClassification/OrganisationClassificationUiPath/README.md:496`) |
| Kept warm | Unpacked files stay on disk; the child exits after each call (`artifacts.py:327,348`) | The loaded pipeline stays in a module global (`OCF/main.py:68-69,122`) |
| Batching | One child per subject, all that subject's articles at once (`ESF/evan_amm/mlhosting/engine.py:310-380`) | `classify-batch`: one child for all inputs (`OCF/orgclas/pipeline.py:149-156`) |
| Timeouts | Child 600 s by default; a test keeps it under the 15-minute cap with headroom (`UW/Evan/tests/unit/mlhosting/subprocess/test_classifier_subprocess_engine.py:2251-2260`). Cold download about 85 s | Child 600 s (`OCF/orgclas/runtime.py:70`) |
| Offline tests | A fake model package run by the real runner under the test's own Python (`test_classifier_subprocess_engine.py:220-238`) | A fake interpreter, wheels and model (`UW/OrganisationClassification/tests/unit/test_ner_engine.py:145-260`) |

- **Robot size, how:** a PATCH of `RobotSize` on the deployed process (an Orchestrator release)
  through the OData API. Neither the package, the deploy config nor `uip or processes update` can
  set it (`UW/pipelines/templates/set-robot-size.steps.yml:1-13`; Evan's call at
  `UW/pipelines/evan-deploy.yml:472-476`).
- **The Flow node:** Evan's "Score all subjects" node (`scoreAllSubjects1`) takes `manifests` from
  a Script node and `configuration` from the load step
  (`UW/Evan/EvanUiPath/EvanAmmFlow/EvanAmmFlow.flow:1628-1638`). The model project is called like
  any other function node.
- **Unverified shortcut:** both `uipath.json` files declare a `models` package (`ESF/uipath.json:22-28`;
  `OCF/uipath.json:18-23`), and the code uses it first if the folder is filled. Only a commit message
  says the serverless robot honours it. Treat the bucket download as the real path.
- **Read next:** `UW/Evan/docs/model-hosting.md`, sections "Running the real model INSIDE the
  Function" (`:65`) and "Paying the model's cost once, not N times" (`:409`).

## Evelyn's model

| Fact | Evidence |
|---|---|
| Entrypoint `nss_model.app`: `App().set_model(NssPipeline())` | `MDL/model.yml:11`; `MDL/nss_model/app.py:7-14` |
| In: `data.{input, hits[], configuration}`, packed as a JSON string in `document.content`. `uuid` is required on the input and on every hit. It raises if no rules are configured | `MDL/nss_model/nss_classification/pipeline.py:36-60`; `entity.py:35`; `model_config.py:32` |
| Out: one decision per hit, matched back by `hit_uuid`: **0** = false positive, **1** = escalate, **-1** = only a location matched and no rule covers location | `MDL/nss_model/nss_classification/model.py:66-94,130`; `NS/.../WleModelResponse.java:134` |
| Quirk: `attrs.hits` comes back as a JSON-encoded **string**, which Java casts and parses | `NS/names-screening-jnw/src/test/resources/ml-steps/save-model-results/model_success.json:11`; `SaveModelResultsProcessor.java:150` |
| The Java side builds the request from the configuration's thresholds and rules | `NS/names-screening-jnw/.../task/ml/service/ModelDocumentBuilder.java:55-148` |
| Python 3.11.10; numpy 1.26.4, pandas 2.2.0, scikit-learn 1.5.1, **pydantic 2.4.0**, plus WorkFusion wheels `automl`, `wf_name_matcher`, `wfrules` | `MDL/META-INF/worker/worker-execution-python.yml`; `MDL/requirements/requirements.txt:16`; `MDL/deps/wheels/` |
| **Small model:** the trained `parameters.json` is 2 bytes; data 668 KB, code 512 KB. The bulk is the Python environment: 202 MB zipped, 656 MB unpacked, no torch | `MDL/deploy_unpacked/.../config/parameters.json`; `MDL/python-envs/python3.11.10-nss-v9.zip` (202 MB; the unpacked size was not re-measured) |
| WorkFusion allows the child 4096 MB and 150 s. These are ceilings, not measurements | `MDL/META-INF/worker/worker-execution-python.yml:1,5-7` |
| **Not in the model, port separately:** the explanations (`ModelExplanationProvider`), `MultiFactorScoringService`, and the pair-count cap that skips the model and returns NEED_REVIEW | `SaveModelResultsProcessor.java:161-203`; `PrepareForMlProcessor.java:82` |

## What this means for Evelyn (Inference)

- **Copy Evan's shape:** a separate model function project (e.g. `EvelynScoreFunction`), model
  files in a bucket, a Python 3.11 child process. The pydantic clash alone forces the child: Evan's
  Function needs `pydantic>=2.12.5` (`ESF/pyproject.toml:11`), Evelyn's model pins `2.4.0`.
- **Robot size:** probably Medium (4 GB) is enough, given the small model and the 656 MB
  environment. Measure before deciding.
- **Batch per job:** score all hits of an alert, or several alerts, in one child run. One job per
  hit would pay about 50 s of cold start each time.
- **Parity:** run the same reference alerts through WorkFusion and the UiPath child and compare the
  decisions hit by hit. The model's own code doesn't change, only where it runs.
- **Open:** memory at inference (unmeasured), whether the `wfrules` and `automl` wheels may be
  shipped (ownership), and whether the `models` package shortcut works.
