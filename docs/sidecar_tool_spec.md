# rddc-sidecar: contributor tool specification (Rust)

Oct 28, 2026 · Draft 0.1 · Targets sidecar schema 0.1.0 (`schema/rddc_sidecar.yaml`)

Contributors use `rddc-sidecar` to generate and validate a metadata sidecar
before upload. This draft specifies a Rust rewrite of the Python prototype in
`../rddc-sidecar`. That prototype targets the retired 0.2.0 schema, with
snake_case fields, groups, links and companion files.

If this specification conflicts with `schema/rddc_sidecar.yaml`, follow the
schema and update this document.

## 1. Goals and non-goals

**Goals**

- One executable per platform. Contributors need no separate runtime, network
  access or Rust toolchain.
- Generate a complete sidecar from a batch directory and an ACT-issued source
  descriptor, recording the origin of every auto-filled value.
- Validate a sidecar against the directory and the descriptor. This is the
  same check the receipt workflow runs, apart from live register lookups.
  Reports are machine-readable and name the file and field.
- Produce the same output for the same inputs and options, apart from
  `dateCreated` and the sidecar `@id`.
- Handle a 120,000-file batch on a laptop (section 9).

**Non-goals**

- Uploading. Contributors upload with `aws s3 sync`, the Synapse client or their
  own tooling, data files first and the sidecar last. The tool prepares a valid
  `_sidecar.json` on disk; it includes no upload client.
- Profile-level FHIR, US Core or OMOP content validation. That runs in the
  NORMALIZE lanes.
- De-identification. The tool detects likely direct identifiers and blocks the
  sidecar, but never alters data files.
- Receipt. It is not decided whether the receipt workflow will reuse this
  code. The tool reads local directories only and has no S3 implementation.
- Correction and resubmission workflows. Their design remains open.
- YAML authoring (requirements FR-16). Sidecars are generated and edited as
  JSON only.
- A Python API (requirements NFR-6, Could). Only the CLI is in scope;
  pipelines that need the results call it with `--format json`.

## 2. What the tool produces

A sidecar is one JSON-LD document, `_sidecar.json`, at the root of the
batch directory (and later of the batch prefix). It is a valid Croissant 1.1
dataset extended with RDDC terms. The tool must write documents that:

1. validate against `schema/generated/rddc_sidecar.schema.json` from the pinned
   rddc-model release;
2. embed `schema/generated/rddc_sidecar.context.jsonld` verbatim as
   `@context` (mlcroissant rejects remote contexts);
3. pass mlcroissant validation, which is checked in CI, not at run time
   (section 10).

Model details for implementers (see `examples/` in rddc-model):

| Concept | Representation |
| --- | --- |
| Sidecar | `@type: sc:Dataset`, `@id: urn:uuid:<v4>`, `conformsTo: [croissant/1.1, rddc/sidecar/<version>]` |
| Batch identity | `contributorId`, `sourceId`, `batchId`, `interaction`, `url` (`s3://bucket/prefix/`) |
| Data file | `@type: cr:FileObject` with an RDDC class in `additionalType` (`rddc:FhirNdjsonFile`, …) that decides the required fields |
| File set | `@type: cr:FileSet` with an RDDC class (`rddc:OmopCdmInstance`, …); members in `hasPart` and/or `includes` globs |
| Joins, data dictionaries | Croissant `recordSet` / `field` / `references` |
| Subjects | `subjects[]`, always inline, (`idSystem`, `identifierSystemUri`, `subjectId`) unique |
| Large batches | Everything inline. No companion files |

## 3. Architecture

Use a Cargo workspace with two crates. Deliver only the CLI. Keeping the
core logic in a library makes it easier to test and reuse later; the library
is not a published API.

| Crate | Kind | Contents |
| --- | --- | --- |
| `rddc-sidecar-core` | library | Model types, detection, generation, validation, reports. No CLI or terminal code |
| `rddc-sidecar` | binary | CLI (`clap`), human-readable rendering, progress display |

The core reads files through an internal trait, with local directories as
the only supported storage. This lets tests use an in-memory store and leaves
room for later reuse:

```rust
pub(crate) trait BatchStore {
    fn list(&self) -> Result<Vec<ObjectMeta>>;            // relative key, size
    fn open(&self, key: &RelPath) -> Result<Box<dyn Read + Send>>;
}
pub(crate) struct LocalDir { root: PathBuf, follow_symlinks: bool }  // the only implementation
```

Register checks likewise go through an internal trait whose only
implementation is the source descriptor:

```rust
pub(crate) trait Register {
    fn source(&self, source_id: &str) -> Option<&SourceRecord>;
    fn participants(&self) -> Option<&dyn ParticipantLookup>;  // always None locally
}
```

### 3.1 Model types

Write the serde types by hand in `core::model`. The tested generator cannot handle this schema. `gen-rust` from LinkML 1.11.1 rejects the schema (`equals_string` on
non-string ranges). After patching those ranges, it crashes on the `additionalType`
designator: its template expects a single string and the designator yields a
list. Revisit code generation when LinkML fixes these issues. The model has about 45 classes,
so hand-written types are manageable, and the conformance tests in section 10
check that the types still match the schema.

Rules for the types:

- `#[serde(deny_unknown_fields)]` everywhere, matching the closed JSON Schema.
- JSON keywords via `#[serde(rename = "@id")]`, `"@type"`, `"@context"`.
- The `@context` field is `serde_json::Value`. The writer always substitutes
  the bundled context and never trusts the input's.
- Distribution items are an internally tagged enum on `additionalType`:

```rust
#[derive(Serialize, Deserialize)]
#[serde(tag = "additionalType")]
pub enum DistributionItem {
    #[serde(rename = "rddc:FhirNdjsonFile")] FhirNdjsonFile(FhirNdjsonFile),
    #[serde(rename = "rddc:OmopTableFile")]  OmopTableFile(OmopTableFile),
    // … one variant per concrete class
    #[serde(rename = "rddc:FhirBulkExport")] FhirBulkExport(FhirBulkExport),
}
```

  Shared fields live in `FileCommon` / `DataFileCommon` / `FileSetCommon`
  structs, embedded with `#[serde(flatten)]`. Note that serde does not support
  `flatten` together with `deny_unknown_fields`. Either write the struct
  fields out per variant (a macro helps), or validate unknown fields through
  the JSON Schema pass, which runs anyway, and drop `deny_unknown_fields` on
  flattened structs. Choose an approach during the first prototype.
- Field order in the structs is the serialization order (section 6.5).

### 3.2 Bundled artifacts

At build time the core embeds, with `include_str!`, these files from the pinned
rddc-model tag:

- `rddc_sidecar.schema.json` and `rddc_source_descriptor.schema.json`;
- `rddc_sidecar.context.jsonld`;
- the schema version, which is written into `conformsTo` and checked when
  reading.

A `make vendor MODEL_REF=<tag>` target copies these from a sibling checkout or
a release URL into `crates/rddc-sidecar-core/schema/` and records the tag.
Never vendor from a branch.

## 4. Commands

```
rddc-sidecar generate <batch-dir> [options]      draft _sidecar.json
rddc-sidecar validate <sidecar> [options]        check; exit 1 on errors
rddc-sidecar confirm  <sidecar> [selectors]      accept or reject inferred values
rddc-sidecar notice   <withdraw|restrict|consent> [options]   file-free sidecars
rddc-sidecar from-table <manifest.csv> <batch-dir> [options]  start from a spreadsheet
rddc-sidecar inspect  <sidecar>                  summary: counts, sets, subjects, sensitivity
rddc-sidecar schema   [--json-schema|--context|--version]     print bundled artifacts
```

Global options: `--format text|json` (report output), `--quiet`,
`--threads N`, `--no-color`.

### 4.1 generate

```
rddc-sidecar generate ./batch --source rddc_source.json --batch-id 2026-10-b01 \
    --attest-direct-identifiers-removed [--previous old/_sidecar.json]
```

| Option | Meaning |
| --- | --- |
| `--source <file>` | ACT source descriptor (JSON). Fills `contributorId`, `sourceId`, `url`, `registerVersion`. Without it, `--contributor-id --source-id --bucket --prefix` are required and a warning says register checks are deferred to receipt (FR-29) |
| `--batch-id` | Required |
| `--interaction` | `add` (default). File-free interactions use `notice` |
| `--previous <sidecar>` | Reuse earlier `@id`s (section 6.3) |
| `--attest-direct-identifiers-removed` | Sets `directIdentifiersRemoved: true`. Without it the field is `false` and validation fails for non-synthetic data |
| `--synthetic` | Sets `synthetic: true`; identifier findings become warnings |
| `--declare <flag>=<bool>` | Declares header sensitivity flags such as `containsZipCodes=false`. Only a contributor can declare a less restrictive value |
| `--fhir-subject id\|identifier --identifier-system <uri>` | How FHIR subject IDs are taken (default `Patient.id`) |
| `--exclude <glob>` | Leave files out (repeatable). Hidden files and the sidecar itself are always excluded |
| `--output <path>` | Default `<batch-dir>/_sidecar.json`. Refuses to overwrite without `--force` |
| `--sidecar-id`, `--created-at` | Set the ID and timestamp explicitly for tests and reproducible builds |

After writing, `generate` runs `validate` on its own output and prints the
report. A sidecar with errors is still written, so the contributor can fix and
confirm values, but the exit status is 1.

### 4.2 validate

```
rddc-sidecar validate ./batch/_sidecar.json [--data-dir ./batch] \
    [--source rddc_source.json] [--no-checksums]
```

- `--data-dir` defaults to the sidecar's directory. Without it (and with
  `--no-data`) only document-level stages run.
- `--no-checksums` skips hashing. Reconciliation and sizes still run, and an
  info finding records the skip. The receipt gate always verifies checksums.

### 4.3 confirm

Sets `confirmed: true` on matching `valueOrigins` entries, or removes the
inferred value. Selectors: `--all-inferred`, `--field <json-pointer>`,
`--node <@id>`, `--joins` (inferred `references`), `--reject` (drop instead of
confirm). Writes in place, keeping a `.bak` file.

### 4.4 notice

Writes a file-free sidecar: `--subjects <csv>` (columns `subjectId`,
`idSystem`, optional `identifierSystemUri`, `consentRef`), plus `--notice-ref`
(required for `withdraw`/`restrict`) or per-row `consentRef` (required for
`consent`). It takes the same identity options as `generate`.

### 4.5 from-table (FR-11)

Starts from a contributor manifest CSV with at least a `key` column (optional
`class`, `sha256`, `md5`, `subject_id`). Verify supplied checksums; a mismatch is an error. Detection fills the remaining fields.

## 5. Detection

Detection reads each file once and computes its checksums during that pass.
It inspects the first 1 MiB by default and parses the full content when the
format requires it. Each value records an origin: `detected` for repeatable
checks, `declared` for options or manifest values, or `inferred` for estimates
that need confirmation.

| Content | RDDC class | encodingFormat | Facts |
| --- | --- | --- | --- |
| JSON, `resourceType: Bundle` | `FhirBundleFile` | `application/fhir+json` | `bundleType`, subjects from `Patient` entries, US Core profiles seen |
| JSON, other `resourceType` | `FhirResourceFile` | `application/fhir+json` | `resourceType` |
| NDJSON, one `resourceType` | `FhirNdjsonFile` | `application/fhir+ndjson` | `resourceType`, `recordCount`, subjects from `Patient` |
| Bulk `$export` status JSON | (metadata; not a data file unless listed) | | Declared outputs reconciled with present files; `exportTime` |
| CSV/TSV/Parquet whose columns match a CDM 5.4 table | `OmopTableFile` | `text/csv` / `text/tab-separated-values` / `application/vnd.apache.parquet` | `cdmTable`; CDM version from version-specific columns; `cdm_source` row; subjects from `person.person_source_value` |
| XML `ClinicalDocument` with C-CDA templates | `CcdaDocumentFile` | `application/xml` | Release from the header template IDs (2015-08-01 → 2.1), checked against the set's `conformsTo`; subject from `recordTarget/patientRole/id`. The template IDs are not written to the sidecar |
| Other delimited tables | `TabularFile` | as above | `recordCount`, columns, direct-identifier-like columns. Consent tables (`ConsentFile`) and sensor data (`SensorDataFile`) are declared, not detected |
| Text, PDF, RTF | `ClinicalDocumentFile` | `text/plain`, `application/pdf`, `application/rtf` (scans: `image/tiff`, `image/jpeg`, `image/png`, declared) | `containsFreeText: true` |
| FASTQ / BAM, CRAM / VCF | `SequenceReadsFile` / `AlignmentFile` / `VariantFile` | see 5.2 | `referenceGenome` from VCF `##reference`/BAM `@SQ` when present; R1/R2 pairing (`inferred`) |
| `.bai`, `.crai`, `.tbi`, `.csi` | `IndexFile` | `application/octet-stream` | `indexOf` from name pairing (`detected` when the target exists) |
| DICOM, PNG, JPEG, TIFF | `ImagingFile` | `application/dicom`, `image/*` | `containsBiometricIdentifiers` left to the contributor; a warning when not declared |
| Photographs of faces | `FacialImagingFile` (declared, not detected) | `image/jpeg`, `image/png`, `image/tiff`, `image/heic`, `application/dicom` | Always biometric; the tool cannot tell a face from other images, so the contributor declares the class |
| MP4, MOV, … | `VideoFile` | `video/*` | as imaging |
| WAV, MP3, … | `AudioFile` | `audio/*` | as imaging |
| Data dictionary next to tables (`*dictionary*`, `*codebook*`) | `DocumentationFile` | by format | `about` (`inferred`) |
| Anything else | `GenericFile` | from magic bytes, else `application/octet-stream` | |

### 5.1 Compression

A gzip, bzip2, xz or zstd magic number sets `compression`. Detection then runs
on the decompressed stream. `encodingFormat` names the inner media type, while
`sha256`, `md5` and `contentSize` describe the stored (compressed) bytes.
Archives (zip, tar) are `GenericFile` with their own media type. Their
contents are not described in v1.

### 5.2 Media types without an IANA registration

Define these in one core table and update them only with the model. Proposed: FASTQ `text/x-fastq`, BAM `application/x-bam`, CRAM
`application/x-cram`, VCF `text/x-vcf`, JSONL `application/jsonl`. The schema
currently constrains media types only for FHIR, OMOP, C-CDA, tabular and
clinical document classes.

### 5.3 File sets

The generator proposes file sets from detected classes:

| Condition | File set | Notes |
| --- | --- | --- |
| ≥1 `FhirNdjsonFile` in one directory | `FhirBulkExport` | `exportTime` from the status manifest, else required from `--export-time` |
| ≥1 `FhirBundleFile` | `FhirBundleCollection` | |
| `OmopTableFile`s in one directory | `OmopCdmInstance` | `vocabularyVersion` and `cdmSource` from `cdm_source.csv`, else required options |
| `CcdaDocumentFile`s | `CcdaDocumentSet` | |
| Related `TabularFile`s in one directory | `TabularDataset` | |

Each set gets `includes` globs covering its directory. Sets of 10,000 members
or fewer also get `hasPart`; larger sets use globs alone, to keep the document
smaller. `conformsTo` is filled from the pinned list (FHIR R4 and US Core
6.1, OMOP CDM 5.4, C-CDA 2.1); `--us-core <version>` overrides it. Set `@id`s
are deterministic: the class name in snake_case, plus `-2`, `-3`, … when a
class repeats.

### 5.4 Joins (FR-13)

For `TabularDataset`s, candidate foreign keys come from matching column names
and value overlap above a threshold (sampled; default 95% of sampled child
values in the parent's column, parent column unique in the sample). Each
candidate becomes a `recordSet` field with `references`, plus a sidecar-level
`valueOrigins` entry (`origin: inferred`, `confidence`, `confirmed: false`).
Validation fails until the join is confirmed or rejected. Joins defined by a
standard (OMOP, FHIR) are never proposed.

## 6. Generation rules

### 6.1 Header

`@id` is a random v4 UUID URN. `conformsTo` is the Croissant 1.1 and RDDC
schema URIs. `name` is `<sourceId>/<batchId>`. `dateCreated` is UTC to the
second. `wasAttributedTo` is `{"@type": "sc:SoftwareApplication", "name":
"rddc-sidecar", "softwareVersion": <crate version>}`.

### 6.2 Sensitivity

Header flags are written only when declared (`--declare`) or detected as
`true`. An absent flag means unknown and reads as `true`. Per-file overrides
are written when detection shows a file differs from the header in the
restrictive direction (for example, free text in one file of a tabular batch).
`directIdentifiersRemoved` is always written: `true` only with
`--attest-direct-identifiers-removed`.

### 6.3 File identity

- New files: `urn:uuid:` + UUIDv5 with namespace `uuid5(NAMESPACE_URL,
  "https://w3id.org/rddc/sidecar")` and name
  `"{sourceId}/{batchId}/{contentUrl}#sha256:{sha256}"`. This is the same
  namespace and name format as the Python prototype, so IDs it minted stay
  stable.
- With `--previous`, an entry keeps the earlier `@id` when `contentUrl` and
  `sha256` both match. Otherwise it keeps the `@id` when `sha256` matches
  exactly one unmatched earlier entry (a move). Otherwise it gets a new ID.
- Two files with identical bytes are two files with two IDs. The name includes
  `contentUrl`, so their IDs differ.

### 6.4 Subjects

Each class's extractor returns (`idSystem`, `identifierSystemUri`, `subjectId`)
triples. Combine them into one subject table, remove duplicates, and sort by
(`idSystem`, `subjectId`). Each data file gets `subjectIds` where its class
requires them (`FhirBundleFile`, `CcdaDocumentFile`, `ClinicalDocumentFile`).
Otherwise `subjectIds` is written when the file holds at most 1,000 subjects;
above that the file's subjects contribute only to the table.

### 6.5 Output form

- UTF-8, LF line endings, two-space indent, one trailing newline.
- Key order: `@context`, `@id`, `@type`, then struct field order.
- `distribution`: file sets sorted by `@id`, then data files sorted by
  `contentUrl`, so a reader sees the batch's structure before its file list.
  `subjects` sorted as in 6.4. `recordSet` sorted by `@id`.
- The same inputs and options produce identical bytes, apart from `@id` and
  `dateCreated` unless both are fixed by option.

## 7. Validation

### 7.1 Stages

The stages run in order. A failure in stages 1–2 stops validation, because
later stages need a well-formed model. From stage 3 on, every stage runs and
all findings are reported.

| # | Stage | How | Rules (IDs in 7.2) |
| --- | --- | --- | --- |
| 1 | Syntax | `serde_json` parse; UTF-8 | `syntax.*` |
| 2 | Schema | Bundled JSON Schema via the `jsonschema` crate (draft 2019-09), **checked by each item's class** (7.3); then typed deserialization | `schema.*` |
| 3 | Identity | Code | `identity.*` |
| 4 | Reconciliation | `BatchStore::list` vs `distribution` | `reconciliation.*` |
| 5 | Integrity | Sizes; SHA-256 and MD5 (parallel) | `integrity.*` |
| 6 | References | Code | `references.*` |
| 7 | Subjects | Code | `subjects.*` |
| 8 | Sensitivity | Code + header and key scans | `sensitivity.*` |
| 9 | Conformance | Code + content sniffing | `conformance.*` |
| 10 | Confirmation | Code | `confirmation.*` |
| 11 | Register | Source descriptor (participants only at receipt) | `register.*` |

### 7.2 Rules not expressible in JSON Schema

The tool checks these rules in addition to JSON Schema. Rule IDs are stable.
Adding a rule requires a minor tool release. Severity: E = blocking error,
W = warning, I = information.

| Rule | Sev | Check |
| --- | --- | --- |
| `schema.conforms_to` | E | `conformsTo` contains `http://mlcommons.org/croissant/1.1` and `https://w3id.org/rddc/sidecar/<v>` |
| `schema.version_unsupported` | E | `<v>` is not a version this build supports (current and previous major) |
| `identity.duplicate_id` | E | `@id` unique across dataset, files, file sets, record sets, fields |
| `identity.duplicate_content_url` | E | `contentUrl` unique |
| `identity.reserved_name` | E | No entry for `_sidecar.json` |
| `identity.url_batch_mismatch` | W | `url` prefix does not end with `…/<batchId>/` per the descriptor's `prefixPattern` |
| `reconciliation.missing_object` | E | An entry has no file |
| `reconciliation.unlisted_object` | E | A file has no entry (excluding the sidecar and `--exclude`) |
| `integrity.size_mismatch` | E | `contentSize` ≠ stored size |
| `integrity.checksum_mismatch` | E | `sha256` or `md5` mismatch |
| `integrity.skipped` | I | `--no-checksums` |
| `references.unknown_node` | E | `hasPart`, `about`, `indexOf`, `pairedWith`, `wasDerivedFrom`, `fileObject`, `fileSet`, `key`, `references.field` must resolve in the document, to the right kind of node |
| `references.member_not_file` | E | `hasPart` names a file set or record set |
| `references.glob_empty` | E | A file set's `includes` matches no listed file |
| `references.glob_member_mismatch` | W | A `hasPart` member is not matched by `includes` (when both are given) |
| `references.self` | E | A node derives from itself |
| `subjects.duplicate` | E | Duplicate (`idSystem`, `identifierSystemUri`, `subjectId`) |
| `subjects.empty_table` | E | Empty table in a `withdraw`, `restrict` or `consent` batch, or in an `add` batch with any data file that is not a `DocumentationFile` |
| `subjects.unresolved` | E | A file's `subjectIds` value is not a `subjectId` in the table |
| `subjects.files_in_notice` | E | `withdraw` or `restrict` lists data files |
| `subjects.consent_ref_missing` | E | `consent` row without `consentRef` |
| `subjects.name_like_id` | E (W synthetic) | A subject ID looks like a name |
| `subjects.unreferenced` | W | A subject in the table appears in no file (when every file lists `subjectIds`) |
| `sensitivity.attestation` | E | `directIdentifiersRemoved` false and not `synthetic` |
| `sensitivity.identifier_column` | E (W synthetic) | A tabular header matches the direct-identifier column list (names, SSN, MRN, address, phone, email, …) |
| `sensitivity.identifier_in_key` | E (W synthetic) | `contentUrl` contains name-like tokens or SSN/email/phone patterns (requirements NFR-8) |
| `sensitivity.free_text_contradiction` | W | The effective `containsFreeText` is false for a `ClinicalDocumentFile` |
| `sensitivity.biometrics_undeclared` | W | Imaging, video or audio file without an effective `containsBiometricIdentifiers` declared (not for classes annotated `biometric`: they always count as biometric, whatever the batch default, and the schema does not let them set the flag) |
| `conformance.class_mismatch` | E | Content does not match the declared class (for example `FhirNdjsonFile` that is not NDJSON) |
| `conformance.resource_type_mismatch` | E | NDJSON lines are not all `resourceType` |
| `conformance.set_member_class` | E | A member's class does not fit the set (an `OmopTableFile` in a `FhirBulkExport`) |
| `conformance.omop_required_tables` | E | `OmopCdmInstance` lacks `person` or `observation_period` |
| `conformance.fhir_bulk_patient` | E | `FhirBulkExport` has no `Patient` file |
| `conformance.pinned_standard` | E | A file set's `conformsTo` value is not in the pinned list |
| `conformance.compression` | E | `compression` disagrees with the magic number |
| `conformance.unassigned` | E | A FHIR, OMOP or C-CDA file belongs to no file set. The set's `conformsTo` is the only place the file's FHIR version, OMOP vocabulary release or C-CDA release is declared |
| `conformance.resource_type_version` | E | A FHIR file's `resourceType` is not a resource type of the FHIR version in its file set's `conformsTo` |
| `confirmation.unconfirmed_inferred` | E | A `valueOrigins` entry with `origin: inferred` and not `confirmed` |
| `register.descriptor_absent` | W | No descriptor; register checks deferred to receipt |
| `register.mismatch` | E | `contributorId`, `sourceId`, bucket or prefix pattern differ from the descriptor |
| `register.modality` | E | The modality of a file's class is not registered for the source |
| `register.descriptor_stale` | W | Descriptor `registerVersion` differs from the sidecar's |

Scan reports never contain the matched value. They name the rule, file and
column (for example "column `SSN` matches pattern `ssn`"), so a report can be
shared without leaking identifiers.

### 7.3 Schema stage performance

The generated JSON Schema types `distribution` items as an `anyOf` over 23
classes. Checking each item against every class is slow. In Python
`jsonschema`, a 120,000-file sidecar took 89 s; checking each item only
against `$defs/<class from additionalType>` gave the same result in 6.5 s. The
tool must compile one validator per class and choose it using `additionalType`. An
unknown `additionalType` is reported directly as `schema.unknown_class`. The
document without its `distribution` items is validated against the root
schema.

### 7.4 Report

```json
{
  "tool": {"name": "rddc-sidecar", "version": "1.0.0"},
  "schemaVersion": "0.1.0",
  "sidecar": "batch/_sidecar.json",
  "ok": false,
  "counts": {"error": 1, "warning": 2, "info": 0},
  "findings": [
    {"severity": "error", "rule": "integrity.checksum_mismatch",
     "path": "/distribution/12/sha256", "contentUrl": "omop/person.csv",
     "message": "sha256 does not match the file"}
  ]
}
```

`path` is a JSON pointer into the sidecar. `contentUrl` is present when a
finding concerns a file. Text output groups findings by file. Findings are
sorted by severity, stage and path. Exit codes: 0 = no errors (warnings
allowed), 1 = errors, 2 = usage or I/O failure (unreadable sidecar, missing
directory).

## 8. Source descriptor

JSON, validated against the bundled `rddc_source_descriptor.schema.json`. It
supplies `contributorId`, `sourceId`, `bucket`, `prefixPattern`
(`{sourceId}`, `{batchId}` placeholders), `modalities`, `registerVersion`.
The tool never contacts the register. A descriptor that fails its schema is a
usage error (exit 2), not a finding.

## 9. Performance and resource targets

Measured with `rddc-sidecar` (`scripts/scale.sh`) on a synthetic 120,000-file
C-CDA batch, 8-core laptop, SSD: the sidecar is 93 MB of JSON (each entry
carried MD5, two template IDs and subject IDs; entries no longer carry template IDs); generate takes 2.4 s at
1.06 GB peak RSS, validate 1.5 s at about 690 MB, checksums included.

| Operation | Target (laptop, 8 cores, SSD) |
| --- | --- |
| Validate 10,000 entries, no checksums | < 2 s (requirements NFR-2: < 60 s) |
| Validate 120,000 entries, no checksums | < 15 s, < 1 GB RSS |
| Generate or validate with checksums | Limited by file read speed: hash in parallel (`rayon`), one read per file |
| Generate, 10,000 one-patient FHIR bundles | < 10 s excluding I/O wait |

Load the whole sidecar into typed structs. A streaming reader is not needed at
this size. Limit memory use by reading file headers and streaming
content. Never hold a whole data file in memory.

## 10. Testing

| Layer | What |
| --- | --- |
| Conformance | For every rddc-model `examples/*.json`: deserialize, re-serialize, validate (round trip with no loss). Port the must-fail mutations from rddc-model `scripts/check_examples.py` into Rust tests; each must fail with the expected rule |
| Cross-check | Every sidecar the tests generate must pass the vendored JSON Schema (`jsonschema` crate) **and**, in CI, `mlcroissant` 1.1.x (Python step) |
| Golden | Generate from fixtures (Synthea FHIR bundles, Synthea Bulk export, OMOP 5.4 structural fixture, C-CDA samples, tabular with a join) with fixed `--sidecar-id`/`--created-at`; compare byte-for-byte with committed sidecars |
| Rules | One test per rule ID (passing and failing case) |
| Determinism | `proptest`: shuffled directory listings and thread counts give identical output |
| Robustness | `cargo fuzz` targets for the sidecar parser and each detector; hostile file names (Unicode, spaces, `..`, very long paths) |
| Scale | Generated 120,000-file batch checks the section 9 targets in a nightly job |

Fixtures come from the Python prototype's `testdata/` (Synthea, OMOP CDM 5.4)
and the Synthea jar it documents. Synthea file names contain patient names,
which is useful: they must trigger `sensitivity.identifier_in_key`.

## 11. Distribution

- Release binaries for Linux (x86_64, aarch64; musl static), macOS (arm64,
  x86_64) and Windows (x86_64), built in CI and published as GitHub release
  assets with SHA-256 sums.
- `rddc-sidecar --version` prints the tool version and the bundled schema
  version and rddc-model tag.

## 12. Security and privacy

- No network access, telemetry or update checks. The tool reads the batch
  directory and the descriptor, and writes only the sidecar (and a `.bak` on
  `confirm`).
- Does not follow symlinks out of the batch directory by default
  (`--follow-symlinks` to allow, still confined to the directory).
- Reports and logs never contain data values, only rule IDs, JSON pointers,
  file keys and column names. This matters because some file keys are the
  very identifiers being flagged; text output may shorten such keys.
- Treats every input as untrusted: bounded reads, no XML external entities
  (`quick-xml` does not resolve them), decompression-bomb limits on sniffing.

## 13. Suggested crates

Check versions and licenses during the first prototype.

| Need | Crate |
| --- | --- |
| JSON | `serde`, `serde_json` (`preserve_order` off; field order comes from structs) |
| JSON Schema | `jsonschema` (draft 2019-09, which the generated schema declares) |
| CLI | `clap` (derive) |
| Hashing | `sha2`, `md-5` |
| IDs | `uuid` (`v4`, `v5`) |
| Parallelism | `rayon` |
| Directory walk, globs | `walkdir` or `ignore`; `globset` |
| Compression | `flate2`, `bzip2`, `xz2`, `zstd` |
| Formats | `csv`; `parquet` (metadata only); `quick-xml`; `noodles` (FASTQ, BAM, CRAM, VCF headers); `dicom-object` (headers); `infer` (magic bytes) |
| Errors | `thiserror` in the core, `anyhow` in the CLI |
| Testing | `insta` (golden), `proptest`, `cargo-fuzz` |

## 14. Carry over from the Python prototype

| Keep | Drop |
| --- | --- |
| Detection heuristics (`detect.py`), the direct-identifier column list and patterns, the CDM 5.4 table catalogue (`omop_cdm.py`) | Groups, links, companion files, YAML conversion, the Python API |
| Rule IDs where the rule still applies (renamed `registry.*` → `register.*`) | `schema.name`, `reconciliation.missing_companion`, group and link rules |
| UUIDv5 namespace and name format | Pydantic models; the vendored 0.2.0 schema |
| Fixtures and the Synthea scripts | |

Archive the Python repository when the Rust tool passes the same golden-fixture checks.

## 15. Open questions

- **Q1** Thresholds: `hasPart` cut-off (10,000), per-file `subjectIds` cut-off
  (1,000), join overlap (95%). These are proposals.
- **Q2** Media types for formats without IANA registrations (5.2) should be
  fixed in the model, not only in the tool.

Schema issue found during this review: `gen-rust` rejects `equals_string`
on the `type` (range `uriorcurie`) and `encodingFormat` (range `MediaType`)
slots. Giving both slots range `string`, with the pattern on the slot, keeps
the JSON Schema identical and makes the schema acceptable to stricter LinkML
generators.
