"""Check example data file objects against the JSON Schema of the data module.

Usage: python scripts/check_data_files.py [SCHEMA]

SCHEMA defaults to schema/data.yaml. The script generates the closed JSON Schema
in memory and checks single distribution items, one class at a time:

1. Each object in examples/data_files/valid.json (VALID) validates against the
   class its additionalType names.
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

# One valid object per concrete class (some classes have several), shared with the
# documentation site, which shows them on the data class pages.
EXAMPLES = os.path.join(ROOT, "examples", "data_files", "valid.json")
with open(EXAMPLES) as f:
    VALID = json.load(f)


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


REF = {"@id": "urn:uuid:00000000-0000-4000-8000-000000000099"}

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
    "OMOP CDM version on a table file": put("omop_table", ["omopCdmVersion"], "5.4"),
    "clinical document flags no free text": put("scanned_report", ["sensitivity"], {"containsFreeText": False}),
    "contentUrl with empty segment": put("generic", ["contentUrl"], "a//b"),
    "contentUrl with trailing slash": put("generic", ["contentUrl"], "a/b/"),
    "contentUrl with backslash": put("generic", ["contentUrl"], "a\\b"),
    "contentUrl with .. segment": put("generic", ["contentUrl"], "a/../b"),
    "contentUrl with leading slash": put("generic", ["contentUrl"], "/a/b"),
    "unregistered JSON Lines type": put("tabular_jsonlines", ["encodingFormat"], "application/jsonl"),
    "BAM with an invented media type": put("bam", ["encodingFormat"], "application/x-bam"),
    "index that is not binary": put("index", ["encodingFormat"], "text/plain"),
    "unknown reference genome": put("variants", ["referenceGenome"], "hg38"),
    "table name on a tabular file": put("tabular", ["tableName"], "visits"),
    "template IDs on a C-CDA file": put("ccda", ["templateIds"], ["2.16.840.1.113883.10.20.22.1.2:2015-08-01"]),
    "processing hint key without namespace": put("scanned_report", ["processingHints", 0, "propertyID"], "ocr"),
    "data dictionary with an empty about list": put("documentation", ["about"], []),
    "genomics file without measurementTechnique": drop("bam", ["measurementTechnique"]),
    "assay not in GenomicsAssayEnum": put("fastq", ["measurementTechnique"], "WGS"),
    "genomics file without sequencingPlatform": drop("fastq", ["sequencingPlatform"]),
    "INSDC platform token instead of the enum value": put("fastq", ["sequencingPlatform"], "OXFORD_NANOPORE"),
    "sequencing platform on a sensor file": put("edf", ["sequencingPlatform"], "illumina"),
    "old assay key": put("fastq", ["assay"], "wgs"),
    "image without measurementTechnique": drop("dicom_image", ["measurementTechnique"]),
    "sensor file without measurementTechnique": drop("sensor_measure", ["measurementTechnique"]),
    "sensor file with an empty measurementTechnique list": put("sensor_measure", ["measurementTechnique"], []),
    "sensor measurementTechnique as a string, not a list": put("edf", ["measurementTechnique"], "ecg"),
    "genomics assay on a sensor file": put("edf", ["measurementTechnique"], ["wgs"]),
    "derived measures as EDF": put("sensor_measure", ["encodingFormat"], "application/octet-stream"),
    "negative sampling rate": put("edf", ["samplingRate"], -1),
    "sampling rate on derived measures": put("sensor_measure", ["samplingRate"], 1),
    "removed SensorDataFile class used directly": put("sensor_measure", ["additionalType"], "rddc:SensorDataFile"),
    "imaging assay on a genomics file": put("fastq", ["measurementTechnique"], "mri"),
    "abstract VariantFile used directly": put("variants", ["additionalType"], "rddc:VariantFile"),
    "abstract SequenceReadsFile used directly": put("fastq", ["additionalType"], "rddc:SequenceReadsFile"),
    "abstract AlignmentFile used directly": put("bam", ["additionalType"], "rddc:AlignmentFile"),
    "abstract ImagingFile used directly": put("dicom_image", ["additionalType"], "rddc:ImagingFile"),
    "abstract SensorSignalFile used directly": put("edf", ["additionalType"], "rddc:SensorSignalFile"),
    "CRAM as text": put("cram", ["encodingFormat"], "text/plain"),
    "VCF compressed with bzip2": put("variants", ["compression"], "bzip2"),
    "FASTQ compressed with zstd": put("fastq", ["compression"], "zstd"),
    "variant calls as an image": put("variants", ["encodingFormat"], "image/png"),
    "FASTQ flags dates": put("fastq", ["sensitivity"], {"containsDates": True}),
    "FASTQ flags no free text": put("fastq", ["sensitivity"], {"containsFreeText": False}),
    "expression matrix flags no biometrics": put("expression", ["sensitivity"], {"containsBiometricIdentifiers": False}),
    "index flags no dates": put("index", ["sensitivity"], {"containsDates": False}),
    "DICOM image as JPEG": put("dicom_image", ["encodingFormat"], "image/jpeg"),
    "non-DICOM image as DICOM": put("image", ["encodingFormat"], "application/dicom"),
    "EDF as CSV": put("edf", ["encodingFormat"], "text/csv"),
    "DICOM waveform as EDF": put("dicom_waveform", ["encodingFormat"], "application/octet-stream"),
    "vendor signal without platform": drop("vendor_signal", ["platform"]),
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
