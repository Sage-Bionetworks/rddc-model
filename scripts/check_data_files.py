"""Check example data file objects against the JSON Schema of the data module.

Usage: python scripts/check_data_files.py [SCHEMA]

SCHEMA defaults to schema/data.yaml. The script generates the closed JSON Schema
in memory and checks single distribution items, one class at a time:

1. Each object in VALID validates against the class its additionalType names.
2. Each mutation in INVALID makes its object fail.

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
        modality="clinical_fhir", fhirVersion="4.0.1", bundleType="collection", subjectIds=["S1"],
    ),
    "fhir_resource": item(
        "FhirResourceFile", 2, contentUrl="fhir/patient.json", encodingFormat="application/fhir+json",
        modality="clinical_fhir", fhirVersion="4.0.1", resourceType="Patient",
    ),
    "fhir_ndjson": item(
        "FhirNdjsonFile", 3, contentUrl="fhir/Observation.ndjson.gz",
        encodingFormat="application/fhir+ndjson", compression="gzip", modality="clinical_fhir",
        fhirVersion="4.0.1", resourceType="Observation",
        implementationGuides=["hl7.fhir.us.core#6.1.0"],
    ),
    "omop_table": item(
        "OmopTableFile", 4, contentUrl="omop/person.csv", encodingFormat="text/csv",
        modality="clinical_omop", cdmTable="person", omopCdmVersion="5.4",
    ),
    "ccda": item(
        "CcdaDocumentFile", 5, contentUrl="ccda/doc.xml", encodingFormat="application/xml",
        modality="clinical_ccda", subjectIds=["S1"],
        templateIds=["2.16.840.1.113883.10.20.22.1.2:2015-08-01", "2.16.840.1.113883.10.20.22.1.1"],
    ),
    "tabular_consent": item(
        "TabularFile", 6, contentUrl="registry/consent.csv", encodingFormat="text/csv",
        modality="consent", tableName="consent",
    ),
    "tabular_jsonlines": item(
        "TabularFile", 7, contentUrl="registry/pro.jsonl", encodingFormat="application/jsonlines",
        modality="clinical_tabular", tableName="pro",
    ),
    "scanned_report": item(
        "ClinicalDocumentFile", 8, contentUrl="notes/report.tif", encodingFormat="image/tiff",
        modality="clinical_text", subjectIds=["S1"],
        processingHints=[{"@type": "sc:PropertyValue", "propertyID": "deid:ocrEngine", "value": "x"}],
    ),
    "documentation": item(
        "DocumentationFile", 9, contentUrl="docs/dictionary.csv", encodingFormat="text/csv",
        modality="metadata", about=[REF],
    ),
    "reads": item(
        "SequenceReadsFile", 10, contentUrl="genomics/S1_R1.fastq.gz", encodingFormat="text/plain",
        compression="gzip", modality="genomics", pairedWith=REF,
    ),
    "alignment": item(
        "AlignmentFile", 11, contentUrl="genomics/S1.bam", encodingFormat="application/octet-stream",
        modality="genomics", referenceGenome="GRCh38",
    ),
    "variants": item(
        "VariantFile", 12, contentUrl="genomics/S1.vcf.gz", encodingFormat="text/plain",
        compression="gzip", modality="genomics", referenceGenome="T2T-CHM13v2.0",
    ),
    "index": item(
        "IndexFile", 13, contentUrl="genomics/S1.bam.bai", encodingFormat="application/octet-stream",
        modality="genomics", indexOf=REF,
    ),
    "imaging": item(
        "ImagingFile", 14, contentUrl="imaging/ct.dcm", encodingFormat="application/dicom",
        modality="imaging",
    ),
    "face": item(
        "FacialImagingFile", 15, contentUrl="imaging/face.jpg", encodingFormat="image/jpeg",
        modality="imaging", subjectIds=["S1"], sensitivity={"containsDates": False},
    ),
    "media": item(
        "MediaFile", 16, contentUrl="media/voice.wav", encodingFormat="audio/wav",
        modality="audio", sensitivity={"containsBiometricIdentifiers": True},
    ),
    "generic": item(
        "GenericFile", 17, contentUrl="other/file.bin", encodingFormat="application/octet-stream",
        modality="other",
    ),
}


def put(key, path, value):
    def mutate(docs):
        doc = docs[key]
        for k in path[:-1]:
            doc = doc[k]
        doc[path[-1]] = value
    return key, mutate


INVALID = {
    "OMOP table with imaging modality": put("omop_table", ["modality"], "imaging"),
    "FHIR file with genomics modality": put("fhir_ndjson", ["modality"], "genomics"),
    "TabularFile with genomics modality": put("tabular_consent", ["modality"], "genomics"),
    "MediaFile with imaging modality": put("media", ["modality"], "imaging"),
    "face photo flags no biometric identifiers":
        put("face", ["sensitivity"], {"containsBiometricIdentifiers": False}),
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
    "template ID not an OID": put("ccda", ["templateIds"], ["ccd-1.1"]),
    "processing hint key without namespace": put("scanned_report", ["processingHints", 0, "propertyID"], "ocr"),
    "data dictionary without about": put("documentation", ["about"], []),
    "empty subject list": put("face", ["subjectIds"], []),
}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "schema", "data.yaml")
    schema = json.loads(JsonSchemaGenerator(path, not_closed=False).serialize())

    def errors(doc):
        cls = doc["additionalType"].split(":", 1)[1]
        sub = {**schema, "$ref": f"#/$defs/{cls}"}
        sub.pop("type", None)
        sub.pop("additionalProperties", None)
        return list(jsonschema.Draft202012Validator(sub).iter_errors(doc))

    bad = 0
    for key, doc in VALID.items():
        errs = errors(doc)
        bad += bool(errs)
        print(f"{'FAIL' if errs else 'ok  '} valid: {key}")
        for e in errs:
            print(f"       {e.json_path}: {e.message[:150]}")
    for label, (key, mutate) in INVALID.items():
        docs = copy.deepcopy(VALID)
        mutate(docs)
        rejected = bool(errors(docs[key]))
        bad += not rejected
        print(f"{'ok  ' if rejected else 'FAIL'} invalid: {label}")
    print(f"\n{bad} failure(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
