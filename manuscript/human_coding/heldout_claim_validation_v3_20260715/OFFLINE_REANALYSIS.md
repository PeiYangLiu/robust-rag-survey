# Offline real-data reanalysis and deidentified release

Run this workflow only on the offline machine that holds the valid independent
human blind package. Do not place that package or the deidentification key in
the networked repository.

## Required package state

The input root must contain:

```text
<blind-package-root>/
  manifest.json
  participant_index.csv
  adjudicator_packet_registry.json
  stage2/          # exactly 24 auditor CSVs and 3 gold CSVs
  adjudication/    # exactly 2 adjudicator CSVs
```

`manifest.json` must have schema
`heldout-v3-offline-input-manifest-v1`. Its top-level `status` must equal
exactly `VALID`, `COMPLETE`, or `COMPLETE_VALID` (uppercase, with no surrounding
space). Substrings and unknown values are invalid: `NOT VALID`,
`NO LONGER VALID`, and `VALID_WITH_UNKNOWN_SUFFIX` all fail. Its `files` array
must list exactly every CSV used from `stage2/` and `adjudication/`, with a
root-relative POSIX `path`, lowercase SHA-256, and data-row count:

```json
{
  "schema_version": "heldout-v3-offline-input-manifest-v1",
  "status": "COMPLETE_VALID",
  "adjudicator_packet_registry": {
    "path": "adjudicator_packet_registry.json",
    "sha256": "<64 hex>",
    "registry_sha256": "<64 hex>"
  },
  "files": [
    {"path": "stage2/auditor_A_01.csv", "sha256": "<64 hex>", "rows": 240}
  ]
}
```

Every hash and row count is recomputed before parsing. Unlisted, extra,
replaced, symlinked, hash-mismatched, or row-mismatched inputs fail.
`participant_index.csv` has the exact columns
`participant_id,role,arm,file_path`, one unique row per response file and
participant: 24 `auditor` (six per A/B/C/D), 3 `gold`, and 2 `adjudicator`.
`arm` is blank for gold/adjudicators. File content must match each indexed
identity, role, and arm.

The coordinator registry is mandatory and must use the exact
`coordinator-adjudicator-packet-registry-v1` schema and
`adjudicator-packet-v1` packet version. `adjudicator_registry.json` and other
locally invented substitutes are rejected. The manifest binds both the
registry file SHA-256 and its canonical `registry_sha256` root. Validation
reconstructs both issued blank packets row by row from the frozen claims,
canonical concatenated gold CSV rows, and the active public-role projection.
It binds the two named adjudicator roles and participants, deterministic
`adjudication_id`, claim, ordered `disputed_outputs`, blinded gold IDs,
raw-material hash, registry row/root hashes, and issued blank-packet hashes.
Completed response files must retain the exact formal packet header.

An alternative blind export is valid only if it carries that canonical
registry, its manifest file/root binding, the two complete formal packet
responses (including every immutable registry field), the participant index,
and gold rows in canonical participant-file/row order. An export that lacks
enough metadata to reproduce the public-role projection, blinded gold
material, registry rows/root, or issued blank packet bytes fails closed.

README prose is never keyword-scanned. Rejection is based only on the exact
top-level manifest status, structured fields in root status JSON files,
obvious invalidation filenames such as `README_SUPERSEDED*.md` and
`INVALIDATION_REPORT*.json`, and known legacy root paths. Thus a normal README
may accurately describe historical packages as “superseded.”

The cohort and response checks are deliberately strict: 480 unique claims,
80 sources with 6 claims each; 24 auditors, 6 per arm and 240 rows per auditor;
3 ratings per claim/arm; 3 gold raters with 480 rows each; and two independent
adjudicators covering exactly every complete-gold disagreement. Claim/source
links, IDs, roles, headers, response statuses, missing-reason codes, and labels
must all be consistent. Each adjudication file must retain the exact formal
`adjudicator-packet-v1` schema. Adjudication, participant, claim, source, and
status identifiers must be nonempty; adjudication IDs are globally unique.

These checks authenticate package bytes and make identity/coverage anomalies
fail closed. **The manifest authenticates package bytes but cannot by itself
prove behavioral independence.** In particular, the tool does not claim to
verify `other_adjudicator_response_seen`; the same limitation is emitted in
analysis output.

## One command

Create a secret of at least 32 random bytes on the offline machine and keep it
outside the output directory. For example:

```bash
python -c 'import secrets; open("v3_release_hmac.key","wb").write(secrets.token_bytes(32))'
python -B build_offline_analysis_release.py \
  --blind-package-root /offline/valid-v3-independent-human-package \
  --deidentification-key-file v3_release_hmac.key \
  --output /offline/v3_analysis_release
```

The output path must not exist or must be empty. By default, frozen claims are
read from this protocol directory's `frozen_test_claims.csv`. To use an
independently copied frozen file, add `--frozen-claims /offline/frozen_test_claims.csv`.
Both paths must byte-match canonical SHA-256
`36b2d0d2c29836e04be8be192f8542cb1acd736a5c5d4148498c7358574677ce`.
The tool also pins the exact `heldout-v3-frozen-claims-v1` header and
`v3.0.0-test-freeze` row version, and cross-checks the hash against
`sampling_freeze_summary.json` (including its post-correction anchor) and
`MANIFEST.sha256`. Audit by running `sha256sum frozen_test_claims.csv` and
comparing all three values. It then requires exactly 480 unique claims, 80
sources, 6 claims/source, and only `c2_decisive`/`c5_decisive`, 240 each.
The normal command fixes the preregistered bootstrap at 100,000 replicates.
Only the Python standard library is required.

The output layout is:

```text
v3_analysis_release/
  private_analysis/       # complete analysis; remains offline
  public_release/         # HMAC-deidentified release
  paper_results/          # aggregate JSON, macros, and complete tables
  TRANSFER_ONLY_THESE.txt
  SHA256SUMS              # offline integrity inventory
```

`private_analysis/` contains original-ID participant analyses and must remain
offline. The raw response package is never copied into the output. The HMAC
key, key path, timestamps, free text, and original participant IDs are not
written to either transferable directory.

## Transfer boundary

Transfer **only** these two directories back to the networked project:

```text
public_release/
paper_results/
```

Do not transfer `private_analysis/`, `SHA256SUMS`, the blind package, the key,
or any raw response file. This boundary retains the aggregate paper results
and opaque release IDs without exposing linkable participant identities.

Before transfer, verify the offline inventory from inside the output root:

```bash
sha256sum -c SHA256SUMS
```

## Synthetic validation

The self-test uses Python `tempfile` under this protocol directory and deletes
its synthetic 480-claim package. It covers exact status rejection without
README prose scanning; invalid status filenames; missing, wrong-schema, and
tampered formal registries; ID/hash/participant/disputed-output tampering;
frozen hash and strata; manifest replacement/row binding; exact coverage;
one-byte key rejection; HMAC non-disclosure; paper fragments; and SHA-256
output. It does not read `files/` or any real/old response package.

```bash
python -B build_offline_analysis_release.py --self-test
python -B analyze_collected_results.py --self-test
python -m py_compile build_offline_analysis_release.py analyze_collected_results.py
```
