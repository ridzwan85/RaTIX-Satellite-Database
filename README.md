# RaTIX Satellite Database

Public, machine-readable orbital-element catalogue for RaTIX. The database is updated independently of the Android APK.

## Data source and refresh

- Orbital elements: [CelesTrak GP active group](https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json), in JSON/OMM format.
- Object classification and catalogue metadata: [CelesTrak SATCAT](https://celestrak.org/pub/satcat.csv), joined by NORAD catalog ID.
- GP and SATCAT are separate authoritative datasets; the pipeline joins them rather than expecting OBJECT_TYPE inside GP OMM.
- GP refresh every 6 hours (UTC), with a manual GitHub Actions trigger. SATCAT is cached locally and refreshed at most once per 24 hours.
- Both source responses are validated before publication. Every GP record must have a valid UTC EPOCH and orbital elements; every active GP record must join to a SATCAT record with a recognized OBJECT_TYPE code.
- Object type is sourced from SATCAT (PAY, R/B, DEB, or UNCLASSIFIED when SATCAT explicitly reports UNK). Missing joins or missing/unsupported type codes fail the entire update; no guessed classification is published.
- SATCAT metadata source and source code are retained in each enriched record.
- Failed downloads or validation never replace the last published manifest or snapshot.
- Each published snapshot is immutable and identified by SHA-256. The updater retains the latest 10 snapshots.
- No Space-Track credentials, API keys or secrets are required.

## Layout

- `.github/workflows/update-catalogue.yml` — scheduled/manual updater.
- `scripts/update_catalogue.py` — fetch, validate and publish.
- `tests/test_update_catalogue.py` — offline validation tests.
- `data/` — versioned catalogue snapshots.
- `latest.json` — discovery manifest, created after the first successful update.

## App integration contract

RaTIX should fetch this manifest from:

`https://raw.githubusercontent.com/ridzwan85/RaTIX-Satellite-Database/main/latest.json`

Compare its `sha256` with the locally cached manifest. If changed, download the relative `file` path, verify SHA-256 before parsing, and retain the previous local catalogue if any step fails.

Manifest schema version 1 fields: `schema_version`, `updated_at_utc`, `source`, `source_url`, `metadata_source_url`, `format`, `file`, `sha256`, `record_count`, `latest_epoch_utc`.

Each enriched record retains the GP orbital fields and adds SATCAT fields such as `OBJECT_TYPE`, `OBJECT_TYPE_CODE`, `OBJECT_TYPE_SOURCE`, `OWNER`, launch metadata, operational status, and an explicit `SATCAT_METADATA_AVAILABLE` flag.

## Limitations and data terms

Orbital elements are estimates whose accuracy depends on element age and satellite manoeuvres. This database does not provide RF reception or decoding; compatible antenna and receiver hardware are required for that. CelesTrak availability and data terms are governed by CelesTrak. Source attribution is retained. This repository does not assert a separate licence for upstream orbital data; review upstream terms before redistribution beyond this project.

## Status

Bootstrap files are being prepared on a feature branch. The first manifest and data snapshot will be published only after validation and a successful updater run.
