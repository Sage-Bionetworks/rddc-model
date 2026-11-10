# Processing rules and orchestration (draft)

What must happen to the files a sidecar describes, written once and used both to
**verify** the rules and to **orchestrate** each batch. The orchestrator is the rules
engine. From the sidecar, the source register entry and the batch state, it works out
which workflow to dispatch next on which files, with their inputs, where the output
goes and the parameters. Most workflows are **Cirro processes**: Nextflow, WDL on
Cromwell, or AWS HealthOmics Ready2Run, run in a Cirro environment on Cirro datasets
([Cirro Data API](https://app.cirro.bio/openapi/cirro-data-latest.yml)). Others are
containers or services, such as GOVERN.

**This is a draft.** The workflows (including the Cirro process and environment ids), zone
locations and register values in this directory and in `../examples/registers/` are
provisional placeholders.

| File | What it is |
| --- | --- |
| `../schema/processing.yaml` | LinkML module: rule sets (`RuleSet`), source register entries (`SourceRegister`), batch state (`Plan`) |
| `rules.yaml` | The rule set: data properties, standards, zones, workflows, targets, obligations, prohibitions, interaction rules |
| `engine.lp` | The semantics, in Answer Set Programming ([clingo](https://potassco.org/clingo/) 5): reachable states and violations |
| `route.lp` | Replays each file's route (the steps that ran, with what they reported) and reports what it breaks |
| `plan.lp` | Chooses, from where each file is now, the shortest continuation to its target that breaks no rule |
| `../examples/registers/source_register.json` | An example source register |
| `../examples/plans/` | The first plan for each example sidecar |

```sh
pip install clingo
python scripts/check_rules.py            # verify rules.yaml
python scripts/orchestrate.py examples/deposit_fhir_omop.json \
    --register examples/registers/source_register.json          # first plan
python scripts/orchestrate.py examples/deposit_fhir_omop.json \
    --register examples/registers/source_register.json --state PLAN.json   # next plan
python scripts/orchestrate.py examples/deposit_fhir_omop.json \
    --register examples/registers/source_register.json --simulate          # simulated dispatcher
python scripts/check_orchestration.py    # routes, batch states, dispatch
```

`make check` runs both checkers, and so does CI.

## On the documentation site

`python scripts/build_site.py` generates a **Processing configuration (prototype)** section from
`rules.yaml` (code in `scripts/rules_site.py`):

- **Rules and targets** (`processing-rules.html`): where each data class ends up by
  default and which single changes send it elsewhere (the targets map); every target,
  obligation, prohibition and workflow as a sentence; and what the checker proved when
  the page was built.
- **Data trajectory** (`data-trajectory.html`): describe a file (class,
  standard, sensitivity flags) and its source (register values, registered
  modalities) and see its target, route, duties and release options. The routes are
  computed at build time by `rules_engine.deposit_routes`, which picks routes the way
  the orchestrator does. `check_orchestration.py` checks that the two agree. The
  address bar holds the description, so a link can be shared.

## How the rules are read

An **item** is a file at deposit. Its **state** is its data class, the standard it
conforms to, the zone it is in, and a set of **data properties** (`dates`,
`free_text`, `identifying`, `needs_expert_review`, ...). A property starts out true
if any of its sources says so. A source can be a class annotation (`identifying`,
`biometric`), the data class itself, a sensitivity flag, or the **source register**:
a register field value, or the file's modality not being one the source is registered
for. **A missing flag counts as present**, and so does a missing register field.

A **workflow** accepts items whose state matches its `consumes` condition, in one of its
`readsFrom` zones. It writes them to `writesTo`, and may change their class
(`produces`) and standard (`producesStandard`), clear properties (`clears`) and set
them (`sets`). A property with no sources, such as `deid_unconfirmed`, starts false,
and only workflows set it. A
condition matches when every slot that is set matches; within a slot, any listed value
matches. `sourceFacts` tests the source's register entry: a field must have one of
`anyOf` and none of `noneOf`. For example, open publication requires `accessTier` to
be `open`, and the date masking workflow used depends on `datePolicy`.

Each item gets the matching **target** with the lowest priority number. The target
says where the item must end up: a zone, and optionally a class and standard. Holding a
file for a curator (the `curation` zone) is a deliberate target, not a gap.

An **obligation** (an ODRL duty) says an item matching a condition must go through a
workflow of the required kind before it enters a zone, or before a named workflow runs
on it. That workflow discharges the duty only if its output no longer matches the
condition. A step that makes the item match again reopens the duty. So does a step of
another kind that clears the property: that doesn't count as de-identification. A
**prohibition** says an item matching a condition never enters a zone.

## What `check_rules.py` proves

It runs the engine over every kind of deposit that can matter to the rules: each
concrete data class in the pinned release, with each standard it can conform to (or
none), and each combination of flag-decided properties, registered or unregistered
modality, file set classes, techniques, interactions and **source register values**.
For register values, one value stands for each distinct behaviour: each listed value,
an unlisted one and a missing one, merged where the rules treat them alike. Over every
reachable state:

- **Coverage**: every deposit has exactly one target and a route to it.
- **Obligations and prohibitions** hold on *every* route, not only on the planned one.
- **No cycles.**
- **Withdraw and restrict** cover every zone data can reach.

For each violation it prints an example deposit and route. It also checks names:
every class, file set class, flag, annotation, technique, interaction, sidecar field,
register field and register enum value the rules use must exist in the release that
`modelRelease` pins, read from that git tag. Until the tag exists, it uses the working
tree. Every schema module in the release must declare the pinned version. Finally it
applies **seeded broken rules** and checks that each one is caught.

## Cirro

A workflow with `runner: cirro` names its Cirro process (`cirroProcess`, Cirro's
`Process.id`) and executor (`cirroExecutor`: `INGEST`, `NEXTFLOW`, `CROMWELL` or
`OMICS_READY2RUN`, Cirro's `Executor`). A zone with a `cirroEnvironment` is a Cirro environment, which the Cirro Data API calls a project (`projectId` in the paths below).
Cirro processes work on datasets, so the checker enforces three things:

- deposited files reach an environment only through an **ingest** (an `INGEST` process,
  kind `ingest`);
- a Cirro process other than an ingest reads only from environment zones;
- only Cirro processes write into environment zones.

A ready Cirro step maps onto the API as follows:

| Plan step | Cirro API |
| --- | --- |
| ingest: `cirroEnvironment`, `cirroProcess`, `inputs[].location` | `POST /projects/{cirroEnvironment}/datasets/upload` with `processId` and `expectedFiles`; the dispatcher copies the files to the returned `uploadPath` |
| analysis: `cirroEnvironment`, `cirroProcess`, `sourceDatasets`, `parameters`, `dispatchId` | `POST /projects/{cirroEnvironment}/execution` (`RunAnalysisRequest`): `processId`, `sourceDatasetIds`, `params`, `name` |
| `results[]`: `dataset`, `location` | The new dataset's `id` and `s3` |
| `status` | The dataset's `status`: `COMPLETED` to succeeded; `FAILED` to failed; `PENDING`, `STARTING`, `RUNNING` and `STOPPING` to running |

Container and service steps get an `outputLocation` from their zone's template instead.
A step that records a finding and writes no data (kinds `confirm` and `expert_review`)
leaves its files where they were. It may write to a Cirro environment zone without
being a Cirro process. A parameter literal can contain `{sourceId}`, `{batchId}` and
`{dispatchId}`, for example the S3 prefix a service writes its report to.

## Pipelines are specific to a data type

Only the ingest is generic: `ingest_files` brings files of any type into INTAKE. Every
de-identification, QC and normalization pipeline is specific to a data type and has its
own Cirro process and version (`pipelineVersion`), and the site shows the version on
every step. The site's "Pipelines by data type" table lists them for each class.

- **De-identification:** `deid_fhir` (FHIR narrative and notes), `deid_ccda` (C-CDA
  sections), `deid_tabular` (tables), `deid_clinical_documents` (notes and scans),
  `deid_omop_notes` (a deposited OMOP instance's note tables), `imaging_deid` (DICOM
  headers).
- **QC:** `qc_sensory`, the only INTAKE pipeline for sensor data, which has no
  de-identification pipeline. Sensor data passes it before the normalized store
  (`sensor_qc_before_loading`). A sensor file with free text (or an unstated
  `containsFreeText`) is held for a curator.
- **Normalization:** `fhir_to_omop`, `ccda_to_omop`, `omop_load`, `tabular_load`,
  `sensor_to_measures` and `sensor_load`, `vcf_to_vrs`.

## Confirming de-identification

Free text is de-identified before it enters the normalized store or a release, in
every lane (`text_deid_before_loading`): tables and documents (lane 4), and also FHIR
narrative and notes (lane 2), C-CDA sections (lane 3) and deposited OMOP note tables.
The seed rule named lane 4 only. Each de-identification pipeline clears `free_text` and
`direct_identifiers` and sets `deid_unconfirmed`, and the file keeps its class and
format. `confirm_deid` is a service step, the same for every type, that runs an Amazon Comprehend
Medical PHI detection job (`StartPHIDetectionJob`) over the de-identified files in
S3. It needs a data access role, a language code and an output S3 prefix for its
report, and it clears `deid_unconfirmed`. The obligation `confirm_deid_before_loading`
requires a `confirm` step before such data enters the normalized store or a release.
If the job finds PHI, the dispatcher reports `free_text` and `direct_identifiers` for
those files. With no automatic retries, the files are then blocked for a person.

## Normalizing variants to GA4GH VRS

Variant files (VCF) are a normalization requirement: `vcf_to_vrs` represents their
variant calls as GA4GH VRS 2.0 alleles and loads them into the normalized store (target
`vrs`). VRS is an output-only standard (`outputOnly: true`): workflows produce it and
sidecars never declare it, so it is not one of the release's pinned `conformsTo` values,
and no deposited file takes it. A variant file the target does not take (one with free
text or biometric identifiers) stays in INTAKE under the general genomics target.

## How orchestration works

The batch state is the `Plan` the orchestrator last wrote, after the dispatcher has
updated it. For each step, the dispatcher records its status (`running`, `succeeded`,
`failed`), and for each file, the output location and, if the workflow checked, the
data properties the output still has. Reported properties replace the predicted ones,
so the rules react to what actually happened. Each call:

1. **Replays** each file's steps against the rules. If a step broke a rule, the batch
   is `stopped`.
2. **Plans** the shortest continuation from each file's current state. A file whose
   last step failed, or with no route from where it is, is blocked; the group says
   why and the rest of the batch goes on. **A workflow runs at most once on a file**,
   so nothing is retried automatically. For example, if text de-identification
   reports residual free text, no automatic route remains, and the file waits for a
   person. A history that runs a workflow twice on a file stops the batch.
3. **Writes** the plan. Files in the same file set with the same history and the same
   steps to come form a group. A group's next step is `ready` unless a step is running
   or a problem blocks it; the steps after it are `pending`. A ready step has a
   `dispatchId` (stable across calls with the same state), the runner and Cirro process
   or pipeline, each file's current location and Cirro dataset, the Cirro environment or
   output location, and parameters from the sidecar and the source register.

If two continuations tie, the lower total workflow `priority` wins; if they still tie,
orchestration fails rather than pick one.

**Files of one file set that share a target move together** (`rules/plan.lp`): they take
the same steps, so a step such as FHIR-to-OMOP runs once on the whole set. If one of them
needs a step, all of them take it. In the example deposit, `Patient.ndjson` is
de-identified and confirmed along with `Observation.ndjson`, which has free text. If one
is blocked (a failure, or a finding such as PHI after de-identification), so is the set.
Files with different targets still part, for example a member flagged with biometric
identifiers, which is held for a curator. A de-identification pipeline therefore accepts
files of its type without free text, and runs at most once per file
(`deid_unconfirmed`, then `deid_confirmed`).

**For discussion:** instead, members could take only the steps they need and wait for
each other before a step that needs the whole set, so that a de-identified file rejoins
the rest before FHIR-to-OMOP. That spares clean files a de-identification run, but it
needs the rules to say which steps need the whole set.

## Known limits

- **Workflows, zones, locations and register values are placeholders.** Each zone
  belongs to a platform module (INTAKE, NORMALIZE, DISCOVER). The TRE is part of
  DISCOVER and is reached only after release, so no zone before release is TRE.
- **GOVERN is not a zone.** It holds registers and approvals, not patient-level data.
  The rules read its source register. Workflows of kind `record` write register
  entries to it and no data files; for example, `record_consent` writes a consent
  file's consent elements to the participants table, and the file stays in INTAKE.
- **One standard per item**: the first rule set standard listed in the file set's
  `conformsTo`.
- **Moving file sets together is checked only when planning.** `check_rules.py` proves
  properties for each kind of deposit on its own; it does not prove that every file set
  has a route all its members can share. A set with none is reported as blocked.
- **Per-file parameters**: a parameter can read the sidecar header or the file set, not
  a file. `vcf_to_vrs` will need each file's `referenceGenome`.
- **Files are tracked by their input identity.** A transform's output (OMOP tables from
  FHIR) is tracked under the FHIR files it came from, at the step's output location.
- **Use terms** are read only for open publication; access decisions stay in GOVERN.
- **No retries.** A failed step, or a finding a step reports, waits for a person.
- **How Comprehend Medical findings become properties** (which entity types, what
  confidence threshold) is the dispatcher's job and is not specified yet. Its job
  status maps to step status in the same way as a Cirro dataset's.
- **Analyses that leave the rules' view of the data unchanged** (genomics QC, facial
  phenotyping) are not in the catalog: as routing steps they would be cycles. They run
  in the INTAKE de-id/QC environment on the ingested datasets.
- **Cirro's own process graph** (`childProcessIds`, `parentProcessIds`) is not
  checked. A check with Cirro credentials could confirm that each Cirro step on a
  route may follow the one before it, and that each `cirroProcess` exists with the
  declared executor (`GET /processes/{processId}`).
- Not built yet: a dispatcher that calls Cirro and the other runners, and audit of
  PROV traces.
