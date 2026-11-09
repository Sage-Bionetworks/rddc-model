# Metadata Sidecar Requirements

Oct 29, 2026 · RDDC Data Processing & Harmonization Workstream · Status: Draft v0.2

## Overview

Each deposit is one **batch** for one **source**, stored under one S3 prefix
in the contributor's bucket. A **metadata sidecar** describes the files,
their relationships and the subjects in the batch. It tells RDDC INTAKE what
to expect, and its arrival starts receipt. The sidecar supplies metadata for
routing, processing and validation. Source policies stay in the source register.

The plan defines two parts:

- the **manifest**: batch identity and one entry per file with location,
  checksums, modality and conformance, plus the links between files;
- the **subject table**: one row per subject ID in the deposit, used to check
  against the participants table and handle withdrawals and consent batches.

The sidecar works with the source register, batch register and Synapse
annotations to support automated processing and curator review.

## Terminology

From the Infrastructure Plan, Appendix A (Table 28).

| Term | Meaning |
| --- | --- |
| Contributor | An organization that sends data. |
| Source | One data set of one contributor that has one set of use terms. |
| Batch, deposit | One delivery of files for one source. |
| Metadata sidecar | The metadata that comes with each deposit. It has the manifest and a subject table. |
| Manifest | The batch's file list, with each file's checksum and modality. |
| Subject table | The coded subject IDs of the people in the deposit. |
| Source register | The list of sources. For each source, it gives the contributor, the use terms, the de-identification class, the date policy and the delivery role. Maintained by ACT. |
| Lane | The intake path for one input format. There are four lanes. |

## Scope

**In scope**

- Sidecar format, location, naming and upload order within a batch
- Batch identity: contributor, source, batch, requested interaction
- Per-file entries: identity, checksums, modality, format, conformance, and the typed fields needed to route, process and validate data
- Subject table and per-file subject references
- Links between files: membership, spec conformance (FHIR, OMOP, C-CDA), and relational keys
- Sensitivity labels needed by de-identification and routing
- Sidecar schema, validation and versioning
- Pipelines reading the sidecar to route and configure processing
- Tooling to draft, validate and normalize sidecars, and receive batches uploaded directly to S3

**Out of scope**

- Pipeline outputs and their provenance, which Synapse registers with the provenance tracked in Cirro, stored as W3C PROV (plan §4.3). Outputs do not get sidecars
- Use terms, access tier, de-identification class, date policy and delivery role, since these live in the source register and are set by the ACT (plan §7.2, §7.6)
- De-identification and QC tests themselves, which are pipelines (Cirro) that read the sidecar (plan §3.2)
- Storage, encryption and credentials for the data files
- Study-level or project-level metadata not needed per batch or per file
- Sidecar access control
- Release manifests, which may span sources and carry research IDs instead of subject IDs. A later release profile may reuse the file entry classes

**Assumptions**

- One sidecar per batch, not one per bucket; the batch register provides the bucket-wide view
- Sidecars may be generated or written by hand; both must pass validation
- Contributors upload using `aws s3 sync` or the Synapse client; the sidecar is an ordinary object under the batch prefix
- Contributor checks run locally before upload; bucket permissions are defined by the Infrastructure Plan
- The LinkML data model defines fields and allowed values; the sidecar schema is one module

## Users and consumers

| Consumer | Uses the sidecar to | Priority |
| --- | --- | --- |
| INTAKE receipt workflow | Detect batch completion, pair objects with entries, verify checksums, check subjects against the participants table, register files | Primary |
| NORMALIZE lane pipelines (Cirro) | Pick the lane and task configuration from modality and conformance, verify inputs | Primary |
| De-id and QC tasks (Cirro) | Pick checks by format and sensitivity facts, name failing files in reports | Primary |
| Data contributors | Draft, validate and upload the sidecar; signal that a deposit is complete; send withdrawals and consent batches | High |
| ACT (source register) | Issue a source descriptor at onboarding for the generator and validator | High |
| Curators | Review exceptions with the file and subject context in one place | High |
| Batch register, dashboards | Index batch state and per-file metadata as Synapse annotations | Medium |
| AI curation assistants | Read batch context without platform calls | Medium |

## Requirements

FR means functional requirement; NFR means non-functional requirement. Priorities follow MoSCoW: M = must, S = should, C = could. Could requirements are outside v1.

**Part A** defines the rules every sidecar must meet. **Part B** describes the
RDDC tools that help contributors meet those rules.

### Part A: sidecar model

#### Batch and sidecar identity

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-1 | Each batch has exactly one sidecar named `_sidecar.json` at the root of the batch prefix. The manifest has one entry per data object under that prefix; the sidecar itself is not a data object and has no entry | M | A fixed name lets the EventBridge rule match on key suffix (plan §3.3). Entry keys are relative to the batch prefix, so every entry refers to an object under it |
| FR-2 | The sidecar is one UTF-8 JSON document containing all file entries and subject rows inline | M | Receipt accepts JSON only; YAML authoring is a tooling option (FR-16) |
| FR-3 | The sidecar declares its schema name and version | M | The schema version follows semantic versioning (see Part A, Versioning) |
| FR-21 | The sidecar declares the **payload interaction** | M | Plan §3.2 and §7.5 suggest `upsert` (new or replacement data), `withdraw`, `restrict`, or `consent`. Notice batches (withdraw, restrict) list no files and name the GOVERN notice they carry out; consent batches give a consent reference for every subject and may list consent files |
| FR-23 | The sidecar identifies the contributor, source, batch and storage location | M | Location is the bucket and batch prefix. At receipt these must match the source register and the delivery role used for upload (plan §7.5); this is a registry check, not a local one. Locally they are checked for form, and against the source descriptor when one is supplied (FR-28). The batch ID is unique within a source |
| FR-28 | A machine-readable **source descriptor** provides the registered source information needed to draft and validate sidecars offline | S | The ACT supplies the descriptor at onboarding. It carries the contributor and source IDs, bucket, prefix pattern, registered modalities and register version. The sidecar schema defines its structure; values come from the source register. The sidecar records the register version used when drafting. Tooling support is FR-29 |

#### File entries

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-4 | Each file entry records the object key relative to the prefix, its size, and at least a SHA-256 checksum; MD5 may be added. The entry names each checksum algorithm | M | SHA-256 checks file integrity. Optional MD5 supports comparison with Synapse file handles and single-part S3 ETags |
| FR-5 | Metadata used for pipeline decisions has defined types and allowed values | M | This covers modality, format, standard and version, file-set role, and sensitivity flags. Allowed values come from enumerations in the declared schema version; where a term has an ontology ID it is stored as both label and CURIE. Processing hints are informational: fields used for pipeline decisions must be defined in the schema |
| FR-6 | Each file has a unique, stable identifier | M | The identifier is a UUID. IDs are unique within the sidecar, never reused for another file, and retained across platform moves and re-registration. Changed content or separate object keys require distinct IDs. ID generation is a tooling choice (FR-12). External IDs supplied with a file contain only contributor IDs; platform IDs (Synapse, DRS) stay in platform metadata |
| FR-24 | Each file entry identifies the data modality and file format | M | The file's class identifies both. Each data file class has exactly one modality from the schema's allowed values, so the entry does not state it separately; a new kind of data gets a new class. Initial modalities are listed under "Initial data types" |

#### Subjects

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-19 | The sidecar carries a subject table with one row per subject in the batch. A subject is identified by its ID system, a system URI where the ID system needs one, and its subject ID; this combination must be unique in the table and identify the same person across the source's batches | M | Plan App. A and Table 6. Rows carry only coded IDs. The ID system says where the ID comes from, for example a FHIR `Patient.id`, or a `Patient.identifier` value together with its system URI. One batch may mix systems, for example FHIR and OMOP IDs. Stable IDs let withdrawals find earlier deposits. The table is non-empty for `withdraw`, `restrict` and `consent`, and for an `upsert` with any file that is not documentation. An `upsert` that carries only documentation, such as a data dictionary or README, may have an empty table |
| FR-20 | A file entry may list the subjects it contains; each must resolve to a row of the subject table. The list is required for per-subject formats | M | Required for FHIR JSON bundles in a FHIR bundle collection, C-CDA documents, clinical text documents and images. Optional for multi-subject tables and NDJSON |

#### File sets and links

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-26 | Group files that form a standard collection into a file set. Give the set a type, declare its standard, version and any profiles or vocabulary release, and give each member a role | M | File set types in the first release: FHIR bulk export, FHIR bundle collection, OMOP CDM instances, C-CDA document set |
| FR-27 | Declare joins between files only when no standard defines them | S | Ad hoc CSV joins |

##### Links between files

File sets reference existing specifications for file relationships. A batch can contain several file sets, such as a FHIR bulk export, an OMOP instance and a document set.

| Link kind | What it records | Example |
| --- | --- | --- |
| Membership | Member entries and each member's role | OMOP table name; FHIR resource type per NDJSON file; `transaction` bundle |
| Conformance | Spec and version the collection follows | OMOP CDM 5.4 + vocabulary v5.0 25-AUG-2026; FHIR 4.0.1 + US Core 6.1.0 |
| Relational keys | Joins between members, only when no spec defines them | `visits.csv:patient_id` → `patients.csv:id` |

- **FHIR:** references live inside the records, so the file set records resource type per file, bundle type, export time and FHIR version; a Bulk Data `$export` status manifest supplies these details.
- **OMOP:** foreign keys are fixed by the CDM, so the file set records which tables are present, CDM and vocabulary versions, and CDM source details.
- **C-CDA:** one document per subject encounter; the file set records the C-CDA release. Template IDs stay in each document's header and are not repeated in the sidecar.
- Validators check for expected members using the declared spec and version (for OMOP, at least `person` and `observation_period`; for FHIR bulk, at least `Patient`).

#### Initial data types

Standards are pinned per the plan (§4.5): FHIR R4 (4.0.1) with US Core as the
exchange format, OMOP CDM 5.4 as the target model, C-CDA 2.1 as a document
format.

Modalities and file set types are named descriptively here; their
enumeration values and class names are defined in the schema and published
with the RDDC data model. Each data file class has one modality, so a file's
class determines its modality. The lanes, formats and standards come from the plan.

| Modality | Formats | File set | Lane | First accepted |
| --- | --- | --- | --- | --- |
| FHIR clinical data | JSON Bundle (one per subject or collection), NDJSON (Bulk Data) | FHIR bundle collection, FHIR Bulk Data export | 2 | Q3 (Month 7–9) |
| OMOP clinical data | CSV or Parquet per CDM table | OMOP CDM instance | 1 | Q3 |
| C-CDA clinical documents | XML | C-CDA document set | 3 | Q4 |
| Other clinical tables (registry, PRO, claims, mortality) | CSV, Parquet | Tabular dataset | 4 | Q3–Q4 |
| Clinical text | TXT, PDF | Document set | de-id (Comprehend Medical) then 4 | Q3 |
| Consent | CSV, JSON | Tabular dataset | GOVERN | Q3 |
| Genomics, imaging, video, audio, wearable sensor data | FASTQ, BAM, CRAM, VCF, DICOM, media | File collection | omics and image workflows | Q5 |
| Documentation (data dictionaries, run metadata) | any | With the files it describes | none | — |
| Other | any | File collection | curator decision | — |

Per-modality and per-file-set required fields (conformance, roles, subject
lists, omics profile fields) are defined in the schema (NFR-7).

#### Sensitivity and de-identification

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-18 | The sidecar declares sensitivity facts for de-identification and routing in the header, with per-file overrides | M | Flags: an attestation that direct identifiers were removed; whether the data contains dates, ZIP codes, free text or biometric identifiers; whether it is synthetic. These flags describe the data. Use terms, access tier and date policy come from the source register and cannot be set in a sidecar (plan §7.6). See "Sensitivity flags" for inheritance, overrides and defaults |

##### Sensitivity flags

Only sensitivity flags inherit from the header to file entries. An unset
flag means unknown and uses the default below. Validators report the value
that applies to each file after overrides and defaults.

| Flag | Where set | File override | Default |
| --- | --- | --- | --- |
| Direct identifiers removed (attestation) | Header only, required | Not allowed | — (attestation, no default) |
| Synthetic | Header only | Not allowed | false |
| Contains dates, ZIP codes, free text, biometric identifiers | Header or file | Yes | true |

#### Receipt

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-15 | The sidecar supplies the batch metadata required for automated receipt and validation, regardless of upload method | M | Plan §3.2–3.3: EventBridge rule, Step Functions receipt workflow. Registry checks also use the source register and participants table |

#### Non-functional and security

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| NFR-1 | A sidecar supports at least 100,000 file entries and can be read incrementally | M | Needed for large C-CDA deposits from HIE/HIN records (plan Table 5). Consumers can stream the JSON document |
| NFR-4 | Sidecars contain no direct identifiers or PHI: no names, MRNs, dates of birth, addresses or contact details. Subject IDs are coded | M | Safe Harbor list in plan Table 3 |
| NFR-8 | Object keys listed in the sidecar contain no direct identifiers; the generator warns on name-like tokens and the receipt check rejects known patterns | M | Synthea-style `<First>_<Last>_<uuid>.json` keys must not reach a bucket |
| NFR-7 | The sidecar schema is defined in LinkML and published with the RDDC data model | M | Plan §1.2. The schema defines field names, types, cardinality and conditional requirements; this document does not repeat them. |

#### Versioning

Each sidecar records the model and tool versions it uses:

| Version | Declared in | Set by |
| --- | --- | --- |
| RDDC sidecar schema | Sidecar conformance | Author of the sidecar |
| Data standards (FHIR, US Core, OMOP CDM, OHDSI vocabulary, C-CDA) | File set conformance; pinned per plan §4.5 | Contributor |
| Source register | Register version | Source descriptor (FR-28) |
| Authoring tool | Authoring tool and version | Tool |

The validator checks data files against the declared standard and version (for
example, required OMOP tables) but not concept IDs.

Schema releases:

- Schema versions follow semantic versioning from 1.0. Before 1.0, any release may change anything, and breaking changes increase the minor version.
- From 1.0, a **minor** release only adds optional fields, enumeration values or deprecations. A deprecated value stays valid and produces a warning.
- A **major** release is needed for any change that can make a valid sidecar invalid: a new required field, a removed or renamed field or value, a changed type, or a stricter rule.

Validity across versions:

- A sidecar is validated against the declared schema version.
- Within a major version, a sidecar valid under x.y is valid under every later x.z.

#### Validation rules

Every sidecar must pass two kinds of check:

- **Intrinsic checks** use only the sidecar, the files and the schema, and give the same result wherever they run.
- **Registry checks** compare the sidecar with the source register (contributor and source IDs, bucket, modalities, delivery role) and the participants table (subject IDs).

Checks, in order:

1. **Syntax:** valid UTF-8 JSON.
2. **Schema:** types, required fields, enumerations, conditional rules by interaction, modality and file set type; unknown fields rejected except as namespaced extensions.
3. **Vocabulary:** enumerated values are valid in the declared schema version; values deprecated in a later version produce a warning.
4. **Identity:** file IDs, object keys, file set IDs and subject identities are unique; source and batch IDs have valid formats.
5. **Reconciliation:** every object under the prefix (or local directory), other than the sidecar, has an entry, and every entry has an object.
6. **Integrity:** checksums match the objects; internal references resolve within the sidecar.
7. **Subjects:** the subject table is non-empty unless the batch is an `upsert` whose files are all documentation; per-file subject lists resolve to it; subject IDs are not name-like.
8. **Sensitivity:** the direct-identifiers attestation is true for non-synthetic data; tabular headers and object keys do not match known direct-identifier patterns (names, SSN, MRN, address, phone, email); media files flagged for biometrics.
9. **Conformance:** declared file set type matches detected content; required members present for the declared standard; CDM version consistent across tables.
10. **Confirmation:** no unconfirmed `inferred` values remain.
11. **Registry:** contributor ID, source ID and bucket match the source descriptor (local) or the source register (receipt); the prefix matches the source's pattern; every file's modality (from its class) is one the source is registered for; subject IDs resolve in the participants table (receipt only).

### Part B: tooling

These requirements cover the RDDC command-line tools for drafting, checking
and converting sidecars. Contributors using other tools need only meet Part A.

#### Validator

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-8 | The validator runs independently and offline before upload, checking checksums and matching entries to files in the local directory | M | Contributors' delivery credentials are write-only. All intrinsic checks (see Part A, Validation rules) run offline. Source descriptor checks (FR-28) run locally; live registry checks run at receipt. The validator ships every schema version it accepts |
| FR-29 | The generator fills the header from a source descriptor (FR-28) and the validator checks the sidecar against it offline. The descriptor is optional for local validation; without it, the validator warns that registry checks are deferred to receipt | S | Depends on FR-28 |

Where validation runs:

- Intrinsic checks run identically at every gate.
- Local validation runs registry checks against the source descriptor (FR-28). Without a descriptor, they are deferred to receipt with a warning. Participant checks run only at receipt.

Validation gates follow the plan's stages:

| Gate | Who | When | On failure |
| --- | --- | --- | --- |
| Local | Contributor CLI | Before upload | Error report; upload should not proceed. Intrinsic rules; registry rules against the source descriptor if present |
| Receipt | INTAKE workflow | Sidecar arrives | Batch stopped at receipt; report names failing files and fields (plan §3.2). Intrinsic rules plus registry rules against the live source register and participants table |
| Screening hand-off | De-id and QC tasks | Before tests run | Tasks stop if format or sensitivity information is missing |
| Pre-processing | NORMALIZE lane | Compute task reads an entry or file set | Task stops and names the missing or invalid field |

Validation errors are machine-readable (severity, rule ID, JSON pointer, file
key, message) so tools and AI assistants can suggest fixes. Exit status is
non-zero when any error remains; warnings do not block.

#### Generator

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| FR-12 | The generator can draft sidecars from file types and embedded metadata. For each auto-filled value, the generator records its origin (`detected`, `declared`, `inferred`), method and confidence | S | If the generator is provided, it must record value origins. The generator mints new file IDs as UUIDv5 from source, batch, key and SHA-256, and carries them forward from a previous sidecar, if supplied, when key and SHA-256 match (or SHA-256 alone matches exactly one unmatched entry). Its namespace is documented with the tooling; other producers need not reproduce these IDs |
| FR-13 | The generator can propose file relationships and distinguish spec-defined links from inferred links. Inferred values require human confirmation to pass validation | S | Depends on FR-12 |
| FR-14 | The generator can compute missing checksums | S | Depends on FR-12. Existing checksums (for example from a tabular manifest, FR-11, or an S3 inventory) are retained and verified against the files; the verification result is recorded as a value origin |
| FR-25 | The generator fills the subject table from the data where the format defines it (FHIR `Patient`, OMOP `person`, C-CDA `recordTarget`), records the ID system of each ID and the method used | S | Depends on FR-12. The tooling design defines extraction rules per format |
| FR-11 | A sidecar can be created from an existing tabular manifest (CSV with at least a key column) | S | Lets sources reuse spreadsheet manifests |
| FR-16 | The tooling can convert YAML sidecars to JSON | C | Only the JSON form is uploaded and accepted at receipt |
| FR-32 | The tooling can upgrade an unsubmitted sidecar to a new major schema version | C | Needed only once a major version follows 1.0. Received sidecars are never rewritten; validators accept the previous major version during the deprecation window |

The generator drafts a sidecar from file types, embedded metadata and file
relationships. It records each generated value's origin. Required fields
left empty fail validation.

| Layer | Method | Examples | Confidence |
| --- | --- | --- | --- |
| Checksums | Computed in one pass over the file | SHA-256 + MD5 | Exact |
| File type | Magic bytes, headers, content sniffing | JSON with `resourceType: Bundle`; NDJSON with one `resourceType` per file; CSV whose columns match an OMOP CDM 5.4 table; XML `ClinicalDocument` with C-CDA template IDs; gzip, BAM/CRAM, VCF, DICOM | High |
| Embedded metadata | Parse format headers | FHIR bundle type, resource counts, US Core profiles; OMOP `cdm_source` row; C-CDA template extension; BAM `@RG`/`@PG`; VCF `##reference` | High |
| Subjects | Extract per the declared spec and record the ID system | FHIR `Patient.id`; OMOP `person.person_source_value`; C-CDA `recordTarget` | High |
| Spec-defined relations | Resolve against the declared spec | FHIR references across NDJSON files; OMOP foreign keys against the CDM | High |
| Conventions | Filename and pairing patterns | R1/R2 reads; `.bai` beside `.bam` | Medium |
| Ad hoc relations | Shared column names + value overlap | Candidate key between two CSVs | Low, needs confirmation |

- For each auto-filled value, the generator records its origin (`detected`, `declared`, `inferred`), method and confidence in [0, 1].
- The generator can use a less restrictive sensitivity value only when the contributor declares it. Missing flags use the defaults under "Sensitivity flags". The direct-identifiers attestation must be declared by the contributor.
- Generated and hand-written sidecars use the same validator.
- The generator runs from the CLI (NFR-3) on a batch directory and can retain file IDs from a previous sidecar.

#### Non-functional and security

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| NFR-2 | Validating 10,000 entries, excluding checksum computation, takes under 1 minute on a laptop; checksum verification depends on file read speed | S | Replaces the earlier 5-minute figure, to be confirmed with pipeline owners |
| NFR-3 | A CLI reads, writes, validates and normalizes sidecars | M | Callable from any pipeline language |
| NFR-6 | A Python library exposes the same read, write, validate and generate functions as the CLI | C | Lowered from S: the CLI (NFR-3) with JSON output serves pipelines in v1 |
| NFR-9 | Validation output is deterministic, with JSON and human-readable formats | S | Needed by AI curation assistants (plan Table 5) |
| NFR-5 | Schema, validator and library are open source and documented with an example sidecar per modality | S | Schema and examples live with the data model; validator and library with the tooling |

#### Versioning

- Tool versions are independent of schema versions. Each tool release bundles the schema versions it supports, taken from tagged schema releases, and reports them with its own version.
- Validators accept the current schema major version and, during a deprecation window, the previous one (proposed: two quarters, to be confirmed). They ship every version they accept, so validation needs no network (FR-8).
- A validator that receives a sidecar declaring a schema version it does not bundle reports the sidecar as unsupported, naming the declared version.
- Generated sidecars record the authoring tool and its version, and declare the newest schema version the tool bundles.
- Migration tooling can upgrade unsent sidecars across major schema versions (FR-32).

## Processing integration

Pipelines read the sidecar for the batch they process. The steps follow the plan's INTAKE sequence (§3.2) and NORMALIZE tasks (§4.2):

1. **Draft.** The contributor runs the generator on the batch directory to identify file types, compute checksums, extract subject IDs, propose file sets and assign file IDs.
2. **Validate locally.** The validator checks schema, vocabulary, reconciliation against the directory, checksums, subject references and sensitivity attestations. Inferred values are confirmed or corrected.
3. **Upload.** Data objects first, then the sidecar, under one prefix in the contributor's bucket, using short-term write-only credentials. The sidecar signals that the deposit is complete.
4. **Receive.** An EventBridge rule starts one receipt workflow when the sidecar arrives. It verifies the delivery role and source ID, waits for every listed object, verifies checksums, reports objects missing from the sidecar or the bucket, checks the subject table against the participants table, and registers files in Synapse (DRS references) with sidecar fields as annotations. If listed objects are still missing at the time limit, the workflow stops the batch with a report.
5. **Screen.** De-id and QC tasks run in Cirro, reading format and sensitivity facts from the sidecar. Exceptions go to curators with file and subject context.
6. **Process.** NORMALIZE picks the lane from each file's modality (from its class) and conformance, reads task parameters from the file set and entries, and verifies inputs by checksum.
7. **Register outputs.** Synapse registers workflow outputs with the pipeline provenance tracked in Cirro, stored as W3C PROV; each output inherits the access rules of its inputs (plan §4.3). Outputs do not get sidecars. Release manifests are out of scope for this version.

The batch-folder JSON Schema for Synapse annotations (plan Table 4) is generated from the same LinkML model as the sidecar. Registration can copy some sidecar fields directly into annotations.

What pipelines can rely on:

- Entries provide file metadata for processing
- Sidecars are immutable once received; pipelines never change an input sidecar
- Shared tooling makes reading and validation consistent across pipelines
- Generator output is deterministic for the same inputs and options, apart from timestamps and the sidecar ID

## Relevant milestones

From the Infrastructure Plan, Tables 6 and 27.

| When | Sidecar deliverable |
| --- | --- |
| Q1, by Nov 2026 | Specification v1 and LinkML schema agreed across TA1, TA2 and TA3; generator and validator prototype on synthetic data |
| Month 4, Dec 2026 | Sidecar-triggered receipt in the deposit path MVP; FHIR bundle and OMOP snapshot examples |
| Month 6, Feb 2027 | Validator used by the de-id and QC module hand-off |
| Q3, Mar–May 2027 | Subject table checked against the participants table; FHIR bundles and OMOP snapshots accepted from external contributors; withdrawal notices |
| Q4, Jun–Aug 2027 | C-CDA document sets |
| Q5, Sep–Nov 2027 | Omics and imaging profiles |

## Changelog

### v0.2

Updates v0.1 (Oct 27, 2026) to follow the RDDC Infrastructure Plan (Draft
0.2, Oct 2026). v0.1's "file set" (one submission or prefix) is now the plan's
**batch**, and v0.1's manifest is now the **metadata sidecar**, which holds the
manifest and a subject table. v0.1's groups of related files are now called
file sets.

Structure:

- Adds Terminology (from plan Appendix A) and Relevant Milestones.
- Groups requirements into Part A (the sidecar model, required for all producers) and Part B (RDDC tooling). Versioning and validation are split between the two parts. Open questions moved to a separate document.
- Removes the field table. Field names, types, cardinality and conditional rules are defined only in the LinkML schema (NFR-7), and requirements use plain terms.

Sidecar model:

- One UTF-8 JSON document named `_sidecar.json` at the root of the batch prefix, uploaded after the data files (FR-1 to FR-3), replacing v0.1's candidate JSON header with JSON Lines or Parquet entries.
- New requirements: batch identity (FR-23); payload interaction, with notice and consent references (FR-21); subject table and per-file subject lists (FR-19, FR-20); modality and format per file (FR-24); file sets with conformance (FR-26); joins only where no standard defines them (FR-27); the per-source descriptor (FR-28).
- The subject table may be empty only for an `upsert` whose files are all documentation.
- FR-18 replaces access level, PHI flag and consent codes with facts about the payload: a direct-identifiers attestation; whether the data contains dates, ZIP codes, free text or biometric identifiers; whether it is synthetic. Use terms, access tier and date policy stay in the source register. Only sensitivity flags inherit from the header to files, with conservative defaults.
- FR-4 requires SHA-256 and allows MD5, absorbing FR-17.
- FR-6: file IDs are UUIDs assigned without a registry. External IDs are contributor IDs only; platform IDs stay in platform metadata.
- Pipelines read sidecars but do not write them. Synapse registers pipeline outputs with their provenance (plan §4.3), so FR-7 (derived-output manifests) removed. Release manifests are out of scope.
- Initial data types are FHIR R4 with US Core, OMOP CDM 5.4 and C-CDA 2.1, with lanes and first-accepted quarters from the plan. Modality, set by the file's class, replaces `data_type`; biospecimen fields are dropped; enumeration labels are left to the schema.
- Sidecars are not versioned: they are immutable once received, `supersedes` is removed, and corrections are an open question. Schema semantic versioning applies from 1.0, a stricter rule needs a major release, and a sidecar is validated against the schema version it declares.

Validation:

- Separates intrinsic checks (offline, same result everywhere) from registry checks (source register and participants table), and adds the receipt and screening gates.
- Checks grow from 6 to 11, adding identity, subjects, sensitivity, conformance, confirmation and registry checks; the cross-entry consistency check is dropped; vocabulary is bound to the declared schema version.

Tooling:

- The validator runs offline against the source descriptor (FR-8, FR-29) and reports machine-readable findings with an exit status. Tool versions are independent of schema versions.
- The generator adds the `inferred` origin with human confirmation (FR-12, FR-13), UUIDv5 file IDs, subject extraction (FR-25), C-CDA and FHIR bundle detection, and verification of supplied checksums (FR-14). LLM vocabulary suggestions are removed. YAML authoring becomes YAML-to-JSON conversion (FR-16), and migration tooling becomes FR-32 (Could).
- NFR-2 becomes under 1 minute for 10,000 entries excluding checksums (was 5 minutes). NFR-6 (Python library) is lowered to Could. NFR-8 (no identifiers in object keys) and NFR-9 (deterministic validation output) are new.

Removed: FR-7 (derived-output manifests), FR-9 (preserving unknown fields when tools rewrite manifests), FR-10 (annotation mapping; the Synapse annotation schema is generated from the same model instead) and FR-17 (folded into FR-4); the Discover and Sync processing steps; portals and search as a consumer.
