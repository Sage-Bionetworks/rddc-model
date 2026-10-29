# Review: Metadata Sidecar Requirements vs. RDDC Infrastructure Plan

Reviewed: `Metadata_Sidecar_Requirements.md` (draft, Oct 27 2026) against
`RDDC_Infrastructure_Plan_draft - COPY FOR TEAM REVIEW.docx` (Draft 0.2, October 2026).
Date of review: Oct 28 2026. The changes described here were applied to the
requirements doc as version 0.2.

## Summary

The requirements draft is a sound general-purpose file-manifest specification,
but it was written from a genomics/portal vantage point (RNA-seq, BAM, VCF,
`assay`, `reference_genome`) and does not yet reflect how the infrastructure
plan actually uses the sidecar. In the plan the sidecar is a **deposit
contract**: it bounds a batch, triggers receipt, carries the subject table that
is checked against the participants table, declares the payload interaction
(upsert vs. withdraw), and names the modality and conformance that decide which
NORMALIZE lane runs. Several of those are missing or under-specified in the
draft. The draft also lets the sidecar carry use terms, which the plan reserves
for the source register.

Severity scale used below: **Gap** = plan needs it, draft lacks it;
**Conflict** = draft contradicts the plan; **Weak** = present but not specific
enough to build against; **OK** = aligned.

## Alignment table

| # | Plan statement (section) | Draft status | Finding | Change made in v0.2 |
|---|---|---|---|---|
| 1 | "A batch is one deposit: one delivery of files for one source. The manifest is a file that lists the files of the batch." (App. A) | Weak | Draft uses "file set (a submission or prefix)" and lists bounding as an open question. The plan already bounds it: one batch = one deposit = one sidecar. | Adopted plan vocabulary: contributor, source, batch, deposit. Closed the open question. |
| 2 | "The metadata sidecar ... has the manifest and a subject table. The subject table gives the subject ID of each person in the deposit." (App. A); "Sidecar check against the participants table" (Table 6, Q3) | **Gap** | No subject table in the draft; only an optional per-file `individual_id`. The participants-table check cannot run without it. | New FR-19: the sidecar carries a subject table (one row per subject ID). New FR-20: per-file subject references resolve to that table. |
| 3 | "The sidecar schema captures ... type of payload interaction (e.g. upsert or withdraw)" (3.2); withdrawal, restriction, rectification notices and consent batches (7.5) | **Gap** | No interaction type. Withdrawal notices have no files, only subject IDs, so the "one entry per file" model cannot express them. | New FR-21: typed `interaction` (`upsert`, `withdraw`, `restrict`, `consent`). Withdraw/restrict require a subject table and allow zero files. Rectification is an `upsert` that `supersedes` an earlier batch. |
| 4 | Source register holds "contributor, use terms (DUO), de-identification class, date policy, delivery role, access tier"; "a contributor's manifest cannot alter use terms or tests" (7.2, 7.6) | **Conflict** | Draft puts `consent_codes` and `access_level` on the header and per file as required fields. That makes the sidecar a second source of truth for use terms. | FR-18 rewritten: sidecar declares **sensitivity facts** (direct identifiers removed, dates/ZIP present, free text, biometrics) that de-id and routing need. Use terms and access tier live in the source register; the sidecar may only reference the `source_id`. Resolved the source-of-truth open question for this case. |
| 5 | "Completing the sidecar upload along with all the files listed in the sidecar triggers batch receipt"; "one workflow per batch is started by an AWS EventBridge rule on the sidecar object" (3.2, 3.3) | Weak | FR-1 says "e.g. a fixed name". An EventBridge rule needs an exact key suffix, and the ordering (files first, sidecar last) is a contract, not a suggestion. | FR-1 fixes the name `_rddc_sidecar.json` at the batch prefix root. New FR-22: the sidecar is uploaded last and is the completion signal. |
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

## Items that were poorly specified for the intended scope

- **"File set" vs batch.** The draft never says who decides where a file set starts and ends. The plan does: the contributor, by writing one sidecar per deposit under one prefix. Fixed.
- **Header inheritance.** "Values shared by every file sit on the header and are inherited" had no precedence rule. Now: entry value > group value > header value, and a validator can report the effective value.
- **Confidence.** FR-12 asked for confidence without a scale. Now: a float in [0, 1] plus a `method` string; `inferred` values must be confirmed (`confirmed: true`) before validation passes.
- **Checksums.** FR-4/FR-17 left the algorithm choice open. Now: SHA-256 required, MD5 optional (recommended for Synapse/S3 single-part ETag comparison). Algorithms are an enum.
- **Pipeline hints.** Free-form hints violate FR-5. Now typed, and anything a pipeline branches on must be a schema field.
- **Validation gate names** did not match the plan's receipt / de-id / QC / NORMALIZE sequence. Re-mapped.
- **`individual_id` / `specimen_id` / `tissue` / `diagnosis`** per file are specimen-centric. For clinical deposits the subject table carries subject IDs and per-file `subject_ids` link to it; diagnosis and tissue are data, not manifest fields, and would reintroduce PHI-adjacent content into the sidecar. Removed from the core; left to an omics profile.
- **Schema deprecation window** and **extension namespace approval** remain open; proposed defaults are stated so the MVP can proceed.

## Items raised for the plan authors (not resolvable in the requirements doc)

1. Section 3.2 says a rejected deposit's files are removed in all versions, then says the contributor resubmits "any updated files, as needed". One of these needs to give; the requirements assume full re-listing in the sidecar and re-upload only of missing objects.
2. Table 6 (INTAKE) and Table 27 (program) disagree on the Month 1 calendar (Sep vs Aug 2026). Sidecar milestones below use Table 6.
3. The plan's Appendix A defines the subject table as subject IDs only. If consent elements or PPRL linkage status also need to ride with a deposit (2.3, 7.5), the subject table schema needs those columns defined by GOVERN.
4. Whether FHIR bundles are validated against US Core at receipt (QC task) or only in lane 2 (NORMALIZE). The requirements assume structural checks at receipt and profile validation in lane 2.
