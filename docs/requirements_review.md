# Review: Metadata Sidecar Requirements vs. RDDC Infrastructure Plan

Reviewed: `docs/sidecar_requirements.md` (then `Metadata_Sidecar_Requirements.md`) (draft, Oct 27 2026) against
`RDDC_Infrastructure_Plan_draft - COPY FOR TEAM REVIEW.docx` (Draft 0.2, October 2026).
Date of review: Oct 28 2026. The changes described here were applied to
requirements version 0.2.

This is a historical review, including decisions later revised. For the
current rules, use the LinkML schema and the current requirements and
decisions documents.

## Summary

The original draft described a general file manifest, with examples focused
on genomics and portals (RNA-seq, BAM, VCF, `assay`, `reference_genome`). The
infrastructure plan needs more: the sidecar defines a batch, starts receipt,
lists subjects, declares the interaction and identifies the processing lane.
Several of these details were missing or unclear. The draft also put use
terms in the sidecar, while the plan keeps them in the source register.

Severity scale used below: **Gap** = plan needs it, draft lacks it;
**Conflict** = draft contradicts the plan; **Weak** = present but too vague to implement; **OK** = aligned.

## Alignment table

| # | Plan statement (section) | Draft status | Finding | Change made in v0.2 |
|---|---|---|---|---|
| 1 | "A batch is one deposit: one delivery of files for one source. The manifest is a file that lists the files of the batch." (App. A) | Weak | Draft uses "file set (a submission or prefix)" and lists bounding as an open question. The plan already bounds it: one batch = one deposit = one sidecar. | Adopted plan vocabulary: contributor, source, batch, deposit. Closed the open question. |
| 2 | "The metadata sidecar ... has the manifest and a subject table. The subject table gives the subject ID of each person in the deposit." (App. A); "Sidecar check against the participants table" (Table 6, Q3) | **Gap** | No subject table in the draft; only an optional per-file `individual_id`. The participants-table check cannot run without it. | New FR-19: the sidecar carries a subject table (one row per subject ID). New FR-20: per-file subject references resolve to that table. |
| 3 | "The sidecar schema captures ... type of payload interaction (e.g. upsert or withdraw)" (3.2); withdrawal, restriction, rectification notices and consent batches (7.5) | **Gap** | No interaction type. Withdrawal notices have no files, only subject IDs, so the "one entry per file" model cannot express them. | New FR-21: typed `interaction` (`upsert`, `withdraw`, `restrict`, `consent`). Withdraw/restrict require a subject table and allow zero files. Rectification is an `upsert` that `supersedes` an earlier batch. |
| 4 | Source register holds "contributor, use terms (DUO), de-identification class, date policy, delivery role, access tier"; "a contributor's manifest cannot alter use terms or tests" (7.2, 7.6) | **Conflict** | Draft puts `consent_codes` and `access_level` on the header and per file as required fields. That makes the sidecar a second source of truth for use terms. | FR-18 rewritten: sidecar declares **sensitivity facts** (direct identifiers removed, dates/ZIP present, free text, biometrics) that de-id and routing need. Use terms and access tier live in the source register; the sidecar may only reference the `source_id`. Resolved the source-of-truth open question for this case. |
| 5 | "Completing the sidecar upload along with all the files listed in the sidecar triggers batch receipt"; "one workflow per batch is started by an AWS EventBridge rule on the sidecar object" (3.2, 3.3) | Weak | FR-1 says "e.g. a fixed name". An EventBridge rule needs an exact key suffix, and the ordering (files first, sidecar last) is a contract, not a suggestion. | FR-1 fixes the name `_sidecar.json` at the batch prefix root. New FR-22: the sidecar is uploaded last and is the completion signal. |
| 6 | "A deposit with no sidecar, a checksum failure, an incomplete batch at the Upload Task time limit is stopped at receipt." (3.2) | Weak | Validation gates in the draft (local, ingest, pre-processing) do not map onto the plan's receipt and de-id/QC stages. | Validation section re-mapped to the plan: Local, Receipt, De-id/QC hand-off, Pre-processing (NORMALIZE). Clarified that the sidecar validator does structural checks only; de-id and QC are Cirro tasks. |
| 7 | "Each source's delivery can write only to its own bucket location and cannot read or delete objects." (3.2) | **Gap** | Draft assumes tools can reconcile against the prefix and rewrite manifests (FR-9). With write-only credentials the contributor cannot list, read back, or overwrite. | Added assumption and consequences: checksums computed locally before upload; reconciliation runs on the platform; corrections are a new sidecar with `supersedes`; FR-9 scoped to platform-side tools. |
| 8 | Formats accepted: FHIR bundles, C-CDA 2.1, OMOP and other tables, files (genomics, wearable, photo, video, voice) (3.2); lanes 1–4 (4.2, 4.8); standards pinned to OMOP CDM 5.4, FHIR R4 + US Core, C-CDA 2.1 (4.5) | Weak | Draft's examples and required fields are omics-centric. First deliverables are clinical: OMOP snapshots and FHIR bundles (Q3), C-CDA (Q4), registry/PRO/claims/mortality tables (lane 4). | Added a typed `modality` enum aligned to the lanes and an initial-release table of modalities, formats and required fields. Omics fields kept as a later profile. Closed the "which specs first" open question: FHIR R4 (4.0.1) with US Core, OMOP CDM 5.4, C-CDA 2.1. |
| 9 | "information determining standard modality-specific downstream processing pipelines (e.g. FHIR-to-OMOP transforms)"; "Settings are automatically determined based on sidecar metadata information, processed by single-shot agentic workflows into target compute task configuration schemas" (3.2, fn 5) | Weak | `pipeline_hints` is free-form. An agentic step that turns sidecar fields into a task configuration needs typed, enumerated inputs (FR-5 already says so). | `processing` block defined as typed fields: modality, format, conformance (standard + version + profiles), group role. `processing_hints` kept but limited to a namespaced key–value map that no pipeline may branch on. |
| 10 | Table 3: Safe Harbor identifiers removed before transmission; a deposit with a direct identifier is stopped (3.2, Table 5) | **Gap** | NFR-4 bans PHI in the manifest but says nothing about object keys. Synthea-style file names (`Aliza77_Larkin917_<uuid>.json`) would put names into the sidecar. | New NFR-8: object keys and subject IDs contain no direct identifiers; generator warns on name-like tokens; sidecar carries a de-identification attestation. |
| 11 | "Synapse Upload Task ... registers files from the bucket into Synapse"; "File registration: a DRS reference" (3.2, Table 4) | OK / Weak | FR-6 leaves `file_id` minting open. Given write-only credentials the contributor cannot call a registry before upload. | Specified: the generator mints `file_id` (deterministic UUIDv5 from source, batch, path and SHA-256; carried forward from the previous sidecar when bytes match). The platform attaches its DRS/Synapse ID at registration as an `external_id`. Open question narrowed to DRS exposure. |
| 12 | "Batch and release register: Synapse file handles, annotations, and a JSON Schema on the batch folder" (Table 4, 7.4) | Weak | Draft FR-10 asked for a mapping from sidecar fields to annotations, which implies two models kept in step. The batch-folder JSON Schema is generated from the sidecar LinkML model, so no mapping exists to maintain. | FR-10 removed in v0.2; the processing section notes that the batch-folder schema derives from the sidecar model. |
| 13 | "Provenance tracked in Cirro and stored as standard W3C PROV provenance in Synapse" (4.3); "The release carries the file IDs of inputs and workflow outputs" (Table 18) | OK | Derived-manifest and PROV mapping requirements line up. | No change beyond vocabulary. |
| 14 | "All data and metadata schema are stored in LinkML schemas" (1.2) | OK | NFR-7 aligned. | No change. |
| 15 | "Buckets retain all versions"; rejected deposit: "an automated workflow removes all versions of the batch files"; contributor "resubmits a sidecar file along with any updated files, as needed" (3.2) | Weak | Draft's immutability rule ("immutable once consumed") doesn't say what a resubmission after rejection looks like, or whether unchanged files must be re-uploaded. | Versioning section: a resubmission is a full sidecar (every file listed) with `supersedes`; unchanged objects need not be re-uploaded if still present and checksum-identical. Flagged to the plan authors that 3.2 says rejected files are deleted, which forces re-upload. |
| 16 | "Every record carries its Research ID and proof of consent" (2.3); consent batches matched by PPRL linkage ID (7.5) | Weak | No way to deposit a consent batch. | Covered by `interaction = consent` and a subject table with an optional consent reference column. Content of consent elements left to the GOVERN register spec (open question). |
| 17 | Q1 exit criterion: "Sidecar specification and transfer protocol agreed across TA1, TA2 and TA3 teams" (Table 6); Month 4 MVP: "sidecar-triggered receipt" | Gap | No milestones in the draft. | Added a milestones section tied to the plan. |
| 18 | Each release is "a set of tables ... registered as a versioned Synapse Dataset"; "load job verifies files against the release manifest's checksums" (6.5) | OK | The same manifest model can describe a release; the draft already allows derived manifests. | Added a note that release manifests reuse the schema with `interaction = release`-free semantics handled by `generated_by` and provenance; out of scope for v0.2 tooling. |
| 19 | NFR-1 100,000 entries; "High-volume C-CDA intake" from HIE/HIN (Table 5) | OK | Scale target is justified by C-CDA volumes. | Noted the driver. |
| 20 | Manifest format candidates (FR-2): JSON + JSON Lines or Parquet | Weak | Undecided; a decision is needed for the Month 4 MVP. | Decided for v0.2: a JSON header document, with file entries and the subject table inline for small batches or in companion JSON Lines files (listed with checksums in the header) above a threshold. Parquet deferred. |

## Details that needed clarification

- **"File set" vs batch.** The draft never says who decides where a file set starts and ends. The plan does: the contributor, by writing one sidecar per deposit under one prefix. Fixed.
- **Header inheritance.** "Values shared by every file sit on the header and are inherited" had no precedence rule. Now: entry value > group value > header value, and a validator can report the effective value.
- **Confidence.** FR-12 asked for confidence without a scale. Now: a float in [0, 1] plus a `method` string; `inferred` values must be confirmed (`confirmed: true`) before validation passes.
- **Checksums.** FR-4/FR-17 left the algorithm choice open. Now: SHA-256 required, MD5 optional (recommended for Synapse/S3 single-part ETag comparison). Algorithms are an enum.
- **Pipeline hints.** Free-form hints violate FR-5. Now typed, and anything a pipeline branches on must be a schema field.
- **Validation gate names** did not match the plan's receipt / de-id / QC / NORMALIZE sequence. Re-mapped.
- **`individual_id` / `specimen_id` / `tissue` / `diagnosis`** per file are specimen-centric. For clinical deposits the subject table carries subject IDs and per-file `subject_ids` link to it; diagnosis and tissue are data, not manifest fields, and would reintroduce PHI-adjacent content into the sidecar. Removed from the core; left to an omics profile.
- **Schema deprecation window** and **extension namespace approval** remain open; proposed defaults are stated so the MVP can proceed.

## Questions for the plan authors

1. Section 3.2 says a rejected deposit's files are removed in all versions, then says the contributor resubmits "any updated files, as needed". These statements conflict; the requirements assume full re-listing in the sidecar and re-upload only of missing objects.
2. Table 6 (INTAKE) and Table 27 (program) disagree on the Month 1 calendar (Sep vs Aug 2026). Sidecar milestones below use Table 6.
3. The plan's Appendix A defines the subject table as subject IDs only. If consent elements or PPRL linkage status must also accompany a deposit (2.3, 7.5), the subject table schema needs those columns defined by GOVERN.
4. Whether FHIR bundles are validated against US Core at receipt (QC task) or only in lane 2 (NORMALIZE). The requirements assume structural checks at receipt and profile validation in lane 2.

## Follow-up review: wording, scope and quality of v0.2

Reviewed Oct 28, 2026. This follow-up checked the wording and consistency of
the requirements at that time. It did not audit the implementation. The
findings below record decisions needed then, rather than new requirements.

### Wording changes applied

Simplified the overview, assumptions, requirements introduction, selected
functional requirements, processing lifecycle and validation descriptions.
For example, the phrase "if a downstream step needs a value to decide what to
do with a file, that value is in the sidecar" now reads: "It supplies the file
metadata needed for routing, processing and validation; source policies remain
in the source register."

Removed similarly broad claims that the sidecar contains everything needed
for receipt or processing. Clarified that offline descriptor checks cover only
the source values available in that descriptor, while participant checks run
at receipt. Removed the claim that existing checksums can be verified against
files without recomputation. Requirement IDs and priorities are unchanged.

### Data model decisions

The data model defines what a sidecar means and when it is valid. These
findings concern those rules. Uploads, receipt and downstream actions belong
to the workflow design.

All eight findings were accepted in requirements v0.3 (Oct 28, 2026). The
matching schema changes are recorded after the table. Later drafts revised
some of these decisions.

| Area and evidence | Model decision needed | Resolution (v0.3) |
| --- | --- | --- |
| **Corrections and supersession.** FR-21 says `supersedes` names a batch, while versioning says it names a `sidecar_id`. Versioning requires a new batch but permits reuse of unchanged objects. | Define the target of `supersedes`, whether a correction describes a complete batch or a change, and whether file references are confined to the current batch prefix. How files are copied or uploaded is an operational decision. | **Accepted.** New FR-31. `supersedes` names a `sidecar_id` and `supersedes_batch` a `batch_id`, matching the schema. A correction is a change set under its own prefix: new and replacement files (`supersedes_file`) plus `retired_file_ids`. Effective contents are the earlier contents with these changes applied. A rejected batch contributes nothing, so its resubmission is complete. This fits write-only credentials, under which contributors cannot copy objects between prefixes. |
| **Deposits, derived outputs and releases.** Processing step 7 requires release manifests to reuse the schema, but the contract assumes one contributor/source and contributor subject IDs. Terminology says those IDs never appear in a release. | State which artifact types the model supports and their required fields, source cardinality and permitted subject identifiers. Separate profiles are one option; explicitly deferring release support is another. | **Accepted.** New FR-30 `sidecar_type`: `deposit` or `derived`. A derived sidecar covers one source, keeps its IDs, may carry subject IDs (it stays inside the platform) and requires provenance per entry (FR-7). Release manifests are out of scope; step 7 now says so. |
| **Subject identity and interactions.** FR-19 allows an ID system; generation examples use FHIR `Patient.id` while FR-19 references `Patient.identifier.system`. Consent content remains open, and `restrict` does not identify the restriction to apply. | Define the subject identifier namespace and uniqueness rules, and the meaning and required information for each interaction. Restriction or consent details may remain in a register if the sidecar provides an unambiguous reference. Add effective-time fields only if the agreed semantics require them. | **Accepted.** FR-19: a subject is (`id_system`, `identifier_system_uri`, `subject_id`). It is unique in the table and stable across the source's batches; `id_system` is required, and systems may be mixed within a batch. The FHIR example now names both `Patient.id` and `Patient.identifier`. FR-21: `withdraw` and `restrict` list no files and require `notice_ref` to the GOVERN notice; `consent` requires `consent_ref` per row. No effective-time fields were added; consent content stays an open question. |
| **Required fields.** The content table marks whole rows required even when they contain optional fields such as `description`, `external_ids` and `supersedes`. FR-20 is Should but requires subject references for some formats. | State when each field is required, including interaction, modality and artifact type. Distinguish an optional capability from a field that becomes mandatory when that capability is used. | **Accepted.** The content table now has Required / Required when / Optional columns and is declared authoritative. FR-20 is raised to M as a conditional requirement: `subject_ids` is required for per-subject formats and optional otherwise. |
| **File identity and external identifiers.** FR-6 expects identity to survive moves; checksum-based carry-forward does not explain duplicate identical files. Registration adds external IDs, although received sidecars are immutable. Versioning mentions file-level supersession without defining its field. | Define what `file_id` identifies, when identity persists, how identical content relates to identity, and how file supersession is represented. Clarify whether external IDs belong in submitted sidecars, later derived records or platform metadata. | **Accepted.** FR-6 defines `file_id` as one file of the source. It persists across platform moves and re-uploads of the same content. Identical content under two keys gives two `file_id`s, and changed content gets a new ID that names the old one in `supersedes_file`. Submitted `external_ids` are contributor-supplied only; platform IDs live in platform metadata and derived sidecars. |
| **Manifest membership and references.** FR-1 covers data objects, while reconciliation says every object must have an entry. Lineage references can point to files in earlier batches. | Define which objects belong in the manifest, uniqueness rules, and which references must resolve within the sidecar versus an external namespace. Specify the meaning and scope of external references; lookup mechanisms belong to tooling. | **Accepted.** FR-1 and reconciliation exclude the sidecar and its companions. New rules cover uniqueness (`file_id`, `key`, `group_id`, subject identity), internal references (`subject_ids`, members, links, `derived_from_groups`) and external references (`supersedes*`, `retired_file_ids`, `derived_from`). External references point to the same source's sidecars and resolve against the batch register at receipt. |
| **Inheritance and sensitivity.** Entry > group > header precedence does not address conflicting groups or identify inheritable fields. “Most restrictive value” is undefined per flag. | List inheritable fields, conflict rules and defaults. Distinguish unknown values, conservative defaults and contributor attestations, including whether overrides may relax defaults. | **Accepted.** Groups carry no sensitivity fields, so the three-level rule is removed. Only sensitivity flags inherit, from the header to entries. A per-flag table gives each flag's level, override rule and default. `direct_identifiers_removed` is a required header-only attestation, `synthetic` is header-only, and `contains_*` may be overridden in either direction. Absent means unknown and takes the conservative value. |
| **Vocabulary and schema compatibility.** Vocabulary checks require “current, non-deprecated” terms, while standards are pinned. Minor versions may add enum values that older consumers reject. | Define how allowed vocabulary values are bound to a schema version and what compatibility is promised between versions. Offline distribution and consumer migration are tooling concerns. | **Accepted.** Enum values are bound to the declared schema version, so values deprecated later stay valid with a warning. External terminologies are declared and pinned in conformance and not checked by the sidecar validator. Compatibility is forward within a major version. A consumer facing a newer minor version validates against the declared version or reports the sidecar as unsupported, not invalid. Removing an enum value now requires a major version. |

The main model priorities are supported artifact types, identifier and reference
semantics, interaction-specific requirements, conditional field requirements and
inheritance. These affect whether producers and consumers interpret the same
sidecar consistently.

Schema changes applied in `schema/rddc_sidecar.yaml` 0.3.0 (Oct 28, 2026):

- Added `SidecarTypeEnum` and a required `sidecar_type` on the batch, plus `notice_ref` (required for `withdraw` and `restrict`). `retired_file_ids` was added to the header.
- Moved `supersedes_batch` from the batch block to the header, next to `supersedes`; a rule requires the two together. `retired_file_ids` requires `supersedes`.
- `id_system` is required on `SubjectEntry`, `subject_id` is no longer the class identifier, and `fhir_patient_identifier` requires `identifier_system_uri`.
- Header `sensitivity` and `direct_identifiers_removed` are required. File entries use a new `FileSensitivity` class with only the `contains_*` flags.
- Inline and companion forms are now mutually exclusive (`exactly_one_of`) for both files and subjects. OMOP conformance requires `vocabulary_version` and `cdm_source`, and `foreign_key` links require both fields.
- Fixed two problems in the generated JSON Schema that dated from 0.2.0. Rules without preconditions were emitted as a `then` with no `if` and so had no effect; this applied to the old subjects rule. They now use an always-true precondition on `schema_name`. Rule postconditions that override `range` (group type → `OmopConformance`) are dropped by `gen-json-schema`, so OMOP requirements are now keyed on `standard` in `Conformance`.

Rules the JSON Schema cannot express, left to the validator: uniqueness of `file_id`, `key`, `group_id` and subject identity; internal and external reference resolution; per-entry provenance in derived sidecars; no files in `withdraw`/`restrict`; a non-empty subject table except for an `add` batch whose files all have modality `metadata`; `consent_ref` on every row of a consent batch; `subject_ids` for per-subject formats; and the match between `group_type` and conformance `standard`.

### Format and tooling requirements

These findings belong to the serialization and tooling contract. Track them separately from questions about what the model means.

| Area | Clarification needed | Resolution (v0.3) |
| --- | --- | --- |
| **Companion files.** FR-2 permits inline entries or JSON Lines companions. | Define companion paths, reference/checksum representation and whether inline and external entries may coexist. Separately define whether the generator's 5,000-entry threshold counts files, subjects or both; that setting need not constrain valid sidecars. | **Accepted.** FR-2 now gives fixed paths at the batch root and one object per line. The `files_ref`/`subjects_ref` representation carries key, size, record count and SHA-256. Inline and companion forms are mutually exclusive per part, chosen independently for files and subjects. The threshold is counted per part and is explicitly not a validity rule. |
| **Identifier generation.** FR-6 specifies deterministic UUIDv5 generation. | Specify the namespace and input encoding if independent producers must generate identical IDs. Otherwise, define valid identifiers and identity semantics in the model and leave generation details to tooling. | **Accepted (second option).** Independent producers need not reproduce generator IDs, because `file_id`s are minted once and carried forward. FR-6 now accepts any UUID and defines identity semantics. UUIDv5 minting and carry-forward matching moved to FR-12 notes; the namespace is documented with the tooling. |
| **Authoring and migration support.** YAML is Could in FR-16 but described as accepted elsewhere; migration tooling is promised without a priority or milestone. | Align the tooling commitments and priorities. These do not determine the required fields of the JSON sidecar. | **Accepted.** FR-2, FR-16 and Decisions now say only JSON is accepted at receipt and YAML authoring is an optional (Could) tooling feature. Migration is new FR-32 (Could), limited to sidecars not yet uploaded and needed only once a major version follows 1.0. |
| **Extraction and reference checking.** Generators extract subject IDs; validators check references and use vocabulary definitions offline. | Define extraction/mapping procedures, external-reference lookup behavior and offline dependency packaging once the model semantics are agreed. | **Partly accepted.** The requirements now cover the parts that affect the contract. The generator records `id_system` per extracted ID (FR-25, generation table). The validator ships every schema version it accepts, checks external references for form offline, and resolves them at receipt or against a supplied previous sidecar (FR-8, check 11). Step-by-step extraction procedures are **dismissed** for the requirements doc; they belong to the tooling design. |

### Operational requirements

The following workflow and tooling questions still matter to the broader
requirements. They do not all need answers before the sidecar model can be
defined.

- **Receipt and correction workflow:** prefix allocation, copying or re-uploading
  unchanged objects, upload order, failed deposits, retries and duplicate events.
- **Validation responsibilities:** which component runs each check, at which gate,
  and how deeply it inspects payload content. Clarify the boundary between
  metadata validation and de-id/QC. The model must define validity constraints;
  the workflow assigns their execution.
- **Interaction execution:** participant matching and the workflows that apply
  withdrawals, restrictions and consent changes.
- **Acceptance criteria:** receipt timeouts, performance fixtures and resource
  baselines, and identifier-detection heuristics and severity. Any intended
  identifier syntax constraints should also be explicit in the model.
- **Descriptor maintenance:** ownership, refresh procedures and treatment of stale
  descriptors at receipt.

### Overall assessment

The reviewed model had a clear batch boundary, stable requirement IDs,
explicit subjects and file relationships, and separate model and tooling
requirements. Several meanings still needed clarification.

The main problem was consistency: requirements, examples and decisions
sometimes gave different meanings to the same fields. Producers and consumers
need the same rules for identity, corrections, interactions, required fields,
inheritance and supported document types.

Track model decisions, format and tooling commitments, and operational
requirements separately. State which definitions take precedence and label
illustrative examples. Add passing and failing examples for the supported
cases, and assign owners to open questions. Operational gaps do not all
need to block the model.