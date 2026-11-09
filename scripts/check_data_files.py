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
        fhirVersion="4.0.1", bundleType="collection", subjectIds=["S1"],
    ),
    "fhir_resource": item(
        "FhirResourceFile", 2, contentUrl="fhir/patient.json", encodingFormat="application/fhir+json",
        fhirVersion="4.0.1", resourceType="Patient",
    ),
    "fhir_ndjson": item(
        "FhirNdjsonFile", 3, contentUrl="fhir/Observation.ndjson.gz",
        encodingFormat="application/fhir+ndjson", compression="gzip",
        fhirVersion="4.0.1", resourceType="Observation",
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
    "scanned_report": item(
        "ClinicalDocumentFile", 9, contentUrl="notes/report.tif", encodingFormat="image/tiff",
        subjectIds=["S1"],
        processingHints=[{"@type": "sc:PropertyValue", "propertyID": "deid:ocrEngine", "value": "x"}],
    ),
    "documentation": item(
        "DocumentationFile", 10, contentUrl="docs/dictionary.csv", encodingFormat="text/csv",
        about=[REF],
    ),
    "reads": item(
        "SequenceReadsFile", 11, contentUrl="genomics/S1_R1.fastq.gz", encodingFormat="text/plain",
        compression="gzip", pairedWith=REF,
    ),
    "alignment": item(
        "AlignmentFile", 12, contentUrl="genomics/S1.bam", encodingFormat="application/octet-stream",
        referenceGenome="GRCh38",
    ),
    "variants": item(
        "VariantFile", 13, contentUrl="genomics/S1.vcf.gz", encodingFormat="text/plain",
        compression="gzip", referenceGenome="T2T-CHM13v2.0",
    ),
    "index": item(
        "IndexFile", 14, contentUrl="genomics/S1.bam.bai", encodingFormat="application/octet-stream",
        indexOf=REF,
    ),
    "imaging": item(
        "ImagingFile", 15, contentUrl="imaging/ct.dcm", encodingFormat="application/dicom",
    ),
    "face": item(
        "FacialImagingFile", 16, contentUrl="imaging/face.jpg", encodingFormat="image/jpeg",
        subjectIds=["S1"], sensitivity={"containsDates": False},
    ),
    "audio": item(
        "AudioFile", 17, contentUrl="media/voice.wav", encodingFormat="audio/wav",
        sensitivity={"containsBiometricIdentifiers": True},
    ),
    "video": item(
        "VideoFile", 18, contentUrl="media/gait.mp4", encodingFormat="video/mp4",
    ),
    "sensor": item(
        "SensorDataFile", 19, contentUrl="wearable/S1_accel.parquet",
        encodingFormat="application/vnd.apache.parquet", platform="ActiGraph GT9X", subjectIds=["S1"],
    ),
    "generic": item(
        "GenericFile", 20, contentUrl="other/file.bin", encodingFormat="application/octet-stream",
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
    "modality stated in the sidecar": put("omop_table", ["modality"], "clinical_omop"),
    "removed MediaFile class": put("audio", ["additionalType"], "rddc:MediaFile"),
    "audio file with a video media type": put("audio", ["encodingFormat"], "video/mp4"),
    "video file with an audio media type": put("video", ["encodingFormat"], "audio/wav"),
    "consent table without subjects": put("consent", ["subjectIds"], []),
    "face photo flags no biometric identifiers":
        put("face", ["sensitivity"], {"containsBiometricIdentifiers": False}),
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
    "data dictionary without about": put("documentation", ["about"], []),
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
