"""Check example data file objects against the JSON Schema of the data module.

Usage: python scripts/check_data_files.py [SCHEMA]

SCHEMA defaults to schema/data.yaml. The script generates the closed JSON Schema
in memory and checks single distribution items, one class at a time:

1. Each object in VALID validates against the class its additionalType names.
2. Each mutation in INVALID makes its object fail against that same class.

It validates with jsonschema rather than `linkml validate`, whose loader drops
the JSON-LD keys @id and @type before validating. Exits non-zero on any
unexpected result.
"""

import copy
import json
import os
import sys

import jsonschema
from linkml.generators.jsonschemagen import JsonSchemaGenerator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHA = "0" * 64


def item(cls, n, **fields):
    """A minimal file object of class cls, with fields added."""
    return {
        "@id": f"urn:uuid:00000000-0000-4000-8000-{n:012d}",
        "@type": "cr:FileObject",
        "additionalType": f"rddc:{cls}",
        "name": fields.get("contentUrl", "file"),
        "contentSize": "1024 B",
        "sha256": SHA,
        **fields,
    }


REF = {"@id": "urn:uuid:00000000-0000-4000-8000-000000000099"}

VALID = {
    "fhir_bundle": item(
        "FhirBundleFile", 1, contentUrl="fhir/bundle.json", encodingFormat="application/fhir+json",
        bundleType="collection", subjectIds=["S1"],
    ),
    "fhir_resource": item(
        "FhirResourceFile", 2, contentUrl="fhir/patient.json", encodingFormat="application/fhir+json",
        resourceType="Patient",
    ),
    "fhir_ndjson": item(
        "FhirNdjsonFile", 3, contentUrl="fhir/Observation.ndjson.gz",
        encodingFormat="application/fhir+ndjson", compression="gzip",
        resourceType="Observation",
    ),
    "omop_table": item(
        "OmopTableFile", 4, contentUrl="omop/person.csv", encodingFormat="text/csv",
        cdmTable="person", omopCdmVersion="5.4",
    ),
    "ccda": item(
        "CcdaDocumentFile", 5, contentUrl="ccda/doc.xml", encodingFormat="application/xml",
        subjectIds=["S1"],
    ),
    "tabular": item(
        "TabularFile", 6, contentUrl="registry/visits.csv", encodingFormat="text/csv",
    ),
    "tabular_jsonlines": item(
        "TabularFile", 7, contentUrl="registry/pro.jsonl", encodingFormat="application/jsonlines",
    ),
    "consent": item(
        "ConsentFile", 8, contentUrl="consent/elements.csv", encodingFormat="text/csv",
        subjectIds=["S1", "S2"],
    ),
    "intake_form": item(
        "IntakeFormFile", 30, contentUrl="intake/responses.csv", encodingFormat="text/csv",
        formDefinition=REF, formVersion="3", subjectIds=["S1", "S2"],
    ),
    "intake_form_published": item(
        "IntakeFormFile", 31, contentUrl="intake/responses.jsonl", encodingFormat="application/jsonlines",
        formDefinition={"@id": "https://example.org/fhir/Questionnaire/intake"}, subjectIds=["S1"],
    ),
    "genetic_test": item(
        "GeneticTestResultFile", 32, contentUrl="genetics/results.json", encodingFormat="application/json",
        referenceGenome="GRCh38", reportDocuments=[REF], subjectIds=["S1"],
        sensitivity={"containsFreeText": True},
    ),
    "differential": item(
        "DifferentialDiagnosisFile", 33, contentUrl="ddx/candidates.csv", encodingFormat="text/csv",
        software="Face2Gene", softwareVersion="2026.1", diagnosisCodeSystems=["orphanet", "omim"],
        wasDerivedFrom=[REF], subjectIds=["S1"],
    ),
    "differential_pdf": item(
        "DifferentialDiagnosisFile", 34, contentUrl="ddx/S1.pdf", encodingFormat="application/pdf",
        subjectIds=["S1"],
    ),
    "scanned_report": item(
        "ClinicalDocumentFile", 9, contentUrl="notes/report.tif", encodingFormat="image/tiff",
        subjectIds=["S1"],
        processingHints=[{"@type": "sc:PropertyValue", "propertyID": "deid:ocrEngine", "value": "x"}],
    ),
    "referral_note": item(
        "ClinicalDocumentFile", 35, contentUrl="notes/referral.txt", encodingFormat="text/plain",
        documentType="referral_note", subjectIds=["S1"],
    ),
    "readme": item(
        "DocumentationFile", 21, contentUrl="README.md", encodingFormat="text/markdown",
    ),
    "documentation": item(
        "DocumentationFile", 10, contentUrl="docs/dictionary.csv", encodingFormat="text/csv",
        about=[REF],
    ),
    "reads": item(
        "SequenceReadsFile", 11, contentUrl="genomics/S1_R1.fastq.gz", encodingFormat="text/plain",
        compression="gzip", measurementTechnique="wgs", sequencingPlatform="illumina", pairedWith=REF,
    ),
    "alignment": item(
        "AlignmentFile", 12, contentUrl="genomics/S1.bam", encodingFormat="application/octet-stream",
        measurementTechnique="wgs", sequencingPlatform="pacbio_smrt", referenceGenome="GRCh38",
    ),
    "variants": item(
        "GermlineVariantFile", 13, contentUrl="genomics/S1.vcf.gz", encodingFormat="text/plain",
        compression="gzip", measurementTechnique="wes", sequencingPlatform="illumina", referenceGenome="T2T-CHM13v2.0",
    ),
    "somatic_variants": item(
        "SomaticVariantFile", 26, contentUrl="genomics/T1.maf", encodingFormat="text/plain",
        measurementTechnique="wes", sequencingPlatform="illumina", referenceGenome="GRCh38",
    ),
    "rna_reads": item(
        "SequenceReadsFile", 27, contentUrl="genomics/S1_rna_R1.fastq.gz", encodingFormat="text/plain",
        compression="gzip", measurementTechnique="rna_seq", sequencingPlatform="illumina",
    ),
    "expression": item(
        "GeneExpressionFile", 28, contentUrl="genomics/counts.tsv", encodingFormat="text/tab-separated-values",
        measurementTechnique="rna_seq", sequencingPlatform="illumina", subjectIds=["S1", "S2"],
    ),
    "expression_h5ad": item(
        "GeneExpressionFile", 29, contentUrl="genomics/counts.h5ad", encodingFormat="application/octet-stream",
        measurementTechnique="rna_seq", sequencingPlatform="illumina",
    ),
    "index": item(
        "IndexFile", 14, contentUrl="genomics/S1.bam.bai", encodingFormat="application/octet-stream",
        indexOf=REF,
    ),
    "imaging": item(
        "ImagingFile", 15, contentUrl="imaging/ct.dcm", encodingFormat="application/dicom", measurementTechnique="ct",
    ),
    "face": item(
        "FacialImagingFile", 16, contentUrl="imaging/face.jpg", encodingFormat="image/jpeg",
        measurementTechnique="photography", subjectIds=["S1"], sensitivity={"containsDates": False},
    ),
    "face_scan": item(
        "FacialImagingFile", 22, contentUrl="imaging/face_3d.obj", encodingFormat="model/obj",
        measurementTechnique="surface_scan_3d", subjectIds=["S1"],
    ),
    "face_scan_ply": item(
        "FacialImagingFile", 23, contentUrl="imaging/face_3d.ply", encodingFormat="application/octet-stream",
        measurementTechnique="surface_scan_3d", subjectIds=["S1"],
    ),
    "face_scan_material": item(
        "FacialImagingFile", 24, contentUrl="imaging/face_3d.mtl", encodingFormat="model/mtl",
        measurementTechnique="surface_scan_3d", subjectIds=["S1"],
    ),
    "audio": item(
        "AudioFile", 17, contentUrl="media/voice.wav", encodingFormat="audio/wav",
        sensitivity={"containsBiometricIdentifiers": True},
    ),
    "video": item(
        "VideoFile", 18, contentUrl="media/gait.mp4", encodingFormat="video/mp4",
    ),
    "sensor_signal": item(
        "SensorSignalFile", 19, contentUrl="wearable/S1_psg.edf", encodingFormat="application/octet-stream",
        measurementTechnique=["eeg", "ecg"], samplingRate=256, platform="Compumedics Grael", subjectIds=["S1"],
    ),
    "sensor_measure": item(
        "SensorMeasureFile", 25, contentUrl="wearable/S1_steps.parquet",
        encodingFormat="application/vnd.apache.parquet", measurementTechnique=["accelerometry"],
        platform="ActiGraph GT9X", subjectIds=["S1"],
    ),
    "generic": item(
        "GenericFile", 20, contentUrl="other/file.bin", encodingFormat="application/octet-stream",
    ),
}


def drop(key, path):
    def mutate(docs):
        doc = docs[key]
        for k in path[:-1]:
            doc = doc[k]
        del doc[path[-1]]
    return key, mutate


def put(key, path, value):
    def mutate(docs):
        doc = docs[key]
        for k in path[:-1]:
            doc = doc[k]
        doc[path[-1]] = value
    return key, mutate


INVALID = {
    "modality stated in the sidecar": put("omop_table", ["modality"], "clinical_omop"),
    "removed MediaFile class": put("audio", ["additionalType"], "rddc:MediaFile"),
    "audio file with a video media type": put("audio", ["encodingFormat"], "video/mp4"),
    "video file with an audio media type": put("video", ["encodingFormat"], "audio/wav"),
    "consent table without subjects": put("consent", ["subjectIds"], []),
    "face photo flags no biometric identifiers":
        put("face", ["sensitivity"], {"containsBiometricIdentifiers": False}),
    "FHIR version on a file": put("fhir_ndjson", ["fhirVersion"], "4.0.1"),
    "resource type of no accepted FHIR version": put("fhir_resource", ["resourceType"], "ActorDefinition"),
    "implementation guides on a file": put("fhir_ndjson", ["implementationGuides"], ["hl7.fhir.us.core#6.1.0"]),
    "FHIR resource file holding a Bundle": put("fhir_resource", ["resourceType"], "Bundle"),
    "OMOP table not in CDM 5.4": put("omop_table", ["cdmTable"], "attribute_definition"),
    "contentUrl with empty segment": put("generic", ["contentUrl"], "a//b"),
    "contentUrl with trailing slash": put("generic", ["contentUrl"], "a/b/"),
    "contentUrl with backslash": put("generic", ["contentUrl"], "a\\b"),
    "contentUrl with .. segment": put("generic", ["contentUrl"], "a/../b"),
    "contentUrl with leading slash": put("generic", ["contentUrl"], "/a/b"),
    "unregistered JSON Lines type": put("tabular_jsonlines", ["encodingFormat"], "application/jsonl"),
    "BAM with an invented media type": put("alignment", ["encodingFormat"], "application/x-bam"),
    "index that is not binary": put("index", ["encodingFormat"], "text/plain"),
    "unknown reference genome": put("variants", ["referenceGenome"], "hg38"),
    "table name on a tabular file": put("tabular", ["tableName"], "visits"),
    "template IDs on a C-CDA file": put("ccda", ["templateIds"], ["2.16.840.1.113883.10.20.22.1.2:2015-08-01"]),
    "processing hint key without namespace": put("scanned_report", ["processingHints", 0, "propertyID"], "ocr"),
    "data dictionary with an empty about list": put("documentation", ["about"], []),
    "genomics file without measurementTechnique": drop("alignment", ["measurementTechnique"]),
    "assay not in GenomicsAssayEnum": put("reads", ["measurementTechnique"], "WGS"),
    "genomics file without sequencingPlatform": drop("reads", ["sequencingPlatform"]),
    "INSDC platform token instead of the enum value": put("reads", ["sequencingPlatform"], "OXFORD_NANOPORE"),
    "sequencing platform on a sensor file": put("sensor_signal", ["sequencingPlatform"], "illumina"),
    "old assay key": put("reads", ["assay"], "wgs"),
    "image without measurementTechnique": drop("imaging", ["measurementTechnique"]),
    "sensor file without measurementTechnique": drop("sensor_measure", ["measurementTechnique"]),
    "sensor file with an empty measurementTechnique list": put("sensor_measure", ["measurementTechnique"], []),
    "sensor measurementTechnique as a string, not a list": put("sensor_signal", ["measurementTechnique"], "ecg"),
    "genomics assay on a sensor file": put("sensor_signal", ["measurementTechnique"], ["wgs"]),
    "derived measures as EDF": put("sensor_measure", ["encodingFormat"], "application/octet-stream"),
    "negative sampling rate": put("sensor_signal", ["samplingRate"], -1),
    "sampling rate on derived measures": put("sensor_measure", ["samplingRate"], 1),
    "removed SensorDataFile class used directly": put("sensor_measure", ["additionalType"], "rddc:SensorDataFile"),
    "imaging assay on a genomics file": put("reads", ["measurementTechnique"], "mri"),
    "abstract VariantFile used directly": put("variants", ["additionalType"], "rddc:VariantFile"),
    "somatic variants without a reference genome": drop("somatic_variants", ["referenceGenome"]),
    "expression quantified from a DNA assay": put("expression", ["measurementTechnique"], "wgs"),
    "expression matrix as an image": put("expression", ["encodingFormat"], "image/png"),
    "reference genome on an expression matrix": put("expression", ["referenceGenome"], "GRCh38"),
    "intake form without a form definition": drop("intake_form", ["formDefinition"]),
    "form definition as a bare string": put("intake_form", ["formDefinition"], "intake-v3"),
    "intake form without subjects": drop("intake_form", ["subjectIds"]),
    "scanned intake form as a PDF": put("intake_form", ["encodingFormat"], "application/pdf"),
    "form definition on a tabular file": put("tabular", ["formDefinition"], REF),
    "genetic test results as a PDF": put("genetic_test", ["encodingFormat"], "application/pdf"),
    "genetic test results without subjects": drop("genetic_test", ["subjectIds"]),
    "genetic test with an empty report list": put("genetic_test", ["reportDocuments"], []),
    "genetic test with a UCSC build name": put("genetic_test", ["referenceGenome"], "hg19"),
    "empty differential code system list": put("differential", ["diagnosisCodeSystems"], []),
    "differential code systems as a string": put("differential", ["diagnosisCodeSystems"], "omim"),
    "unknown diagnosis code system": put("differential", ["diagnosisCodeSystems"], ["ORDO"]),
    "differential diagnoses as an image": put("differential", ["encodingFormat"], "image/png"),
    "LOINC code instead of a document type": put("referral_note", ["documentType"], "57133-1"),
    "several document types on one file": put("referral_note", ["documentType"], ["referral_note", "consult_note"]),
    "document type on a tabular file": put("tabular", ["documentType"], "progress_note"),
    "face image from microscopy": put("face", ["measurementTechnique"], "microscopy"),
    "face scan with an invented PLY media type": put("face_scan", ["encodingFormat"], "model/ply"),
    "empty subject list": put("face", ["subjectIds"], []),
}


def cls_of(key):
    """The class of VALID[key], read before any mutation changes additionalType."""
    return VALID[key]["additionalType"].split(":", 1)[1]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "schema", "data.yaml")
    schema = json.loads(JsonSchemaGenerator(path, not_closed=False).serialize())

    def errors(doc, cls):
        sub = {**schema, "$ref": f"#/$defs/{cls}"}
        sub.pop("type", None)
        sub.pop("additionalProperties", None)
        return list(jsonschema.Draft202012Validator(sub).iter_errors(doc))

    bad = 0
    for key, doc in VALID.items():
        errs = errors(doc, cls_of(key))
        bad += bool(errs)
        print(f"{'FAIL' if errs else 'ok  '} valid: {key}")
        for e in errs:
            print(f"       {e.json_path}: {e.message[:150]}")
    for label, (key, mutate) in INVALID.items():
        docs = copy.deepcopy(VALID)
        mutate(docs)
        rejected = bool(errors(docs[key], cls_of(key)))
        bad += not rejected
        print(f"{'ok  ' if rejected else 'FAIL'} invalid: {label}")
    print(f"\n{bad} failure(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
