# RaTIX Satellite Database

Public, machine-readable orbital-element catalogue for RaTIX. The database is updated independently of the Android APK.

## Data source and refresh

- Primary source: [CelesTrak GP active group](https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json), in JSON format.
- Scheduled refresh every 6 hours (UTC), with a manual GitHub Actions trigger.
- A response is published only after structural, identifier, epoch, uniqueness and orbital-range validation.
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

Manifest schema version 1 fields: `schema_version`, `updated_at_utc`, `source`, `source_url`, `format`, `file`, `sha256`, `record_count`, `latest_epoch_utc`.

## Limitations and data terms

Orbital elements are estimates whose accuracy depends on element age and satellite manoeuvres. This database does not provide RF reception or decoding; compatible antenna and receiver hardware are required for that. CelesTrak availability and data terms are governed by CelesTrak. Source attribution is retained. This repository does not assert a separate licence for upstream orbital data; review upstream terms before redistribution beyond this project.

## Status

Bootstrap files are being prepared on a feature branch. The first manifest and data snapshot will be published only after validation and a successful updater run.
