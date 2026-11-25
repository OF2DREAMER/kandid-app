# KINDID — N-16.1 Item 1: Deployed Vector Evidence Package (v2.1)

**Status: NOT EXECUTED.** No PostgreSQL engine execution has been performed. No production or deployed database has been contacted. Every PostgreSQL result in this document is an **assertion** derived from v1.3.16's documented semantics and from the SQL text, not an observation. Static SQL validation is not runtime validation.

**Supersedes for review purposes only:** `KINDID_N-16.1_Item1_Vector_Evidence_Package_v2.md`
(SHA-256 `7d8ef226afb71ac8c3f5471e4e7a067ff1ab8af9a8cb32b4500d7f1909b49953`, 21,292 bytes), which in turn superseded v1 (`c2adcfa9b5ad79c7575e69316b323055b15de35a23d1a3b2c38f59eb3ac494b7`, 9,787 bytes). **v1 and v2 are preserved unchanged.** This file is a document-only correction of v2 (C-01 to C-04, Section 1.1). It is not an amendment revision, closes no finding, and moves no gate.

**Baseline audited:** `KINDID_Phase_1A_Amendment_v1.3.16.md`
SHA-256 `8bd2d5538372e5ea285a3749a637809ef9d7bbbf08e552d171f41ad4c69bdcad`
MD5 `4cf764337f361100d33ca127f4a0a0c8`, 411,689 bytes, 2,690 lines. Unmodified.

**Requirement served** (N-16.1 item 1, v1.3.16): "The synthetic matrix above is executed as a `VALUES` list - never against production rows - on the deployed instance, recording `version()`, `server_encoding`, `datcollate`, `datctype` and the collation actually derived for the expression. Every row must return the PostgreSQL result asserted for it; the non-ASCII row must be recorded as **not reproduced** unless the deployed behaviour proves otherwise."

**This package is an execution artifact. It is not proof that N-16.1 item 1 is closed, and it cannot be until both records are executed on the target server and reviewed together.**

**Separation rule (unchanged and enforced).** Query A is a pure `VALUES` expression: it reads no user table and no catalog. Query A2 reads system catalogs only (`pg_database`), never application data. Query B is the v1.3.16 R4b block, which does read `users`; it is a separate statement requiring separate authorization and must never be merged with Query A.

---

## 1. Correction log (D1-D6 from the v1 review)

| ID | Defect in v1 | Change applied in v2 (retained in v2.1) |
|---|---|---|
| **D1** | Row 16's pass criterion asserted `ascii_ok = FALSE` unconditionally, which is not a valid expectation on every deployment. | Replaced by an encoding-independent rule: row 16 must satisfy `domain_status <> 'supported'` and `cell IS NULL` wherever the row is testable; `ascii_ok = FALSE` is asserted **only** where the deployed encoding makes the byte-length test fire. Section 6 states the rule against **observed** `ascii_ok` / `is_utf8` values rather than against encoding labels (revised in v2.1 under C-01). |
| **D2** | No `domain_status` in the output, so "outside the supported domain" was inferred from `ascii_ok` rather than observed. | `domain_status` is computed with the **exact** v1.3.16 `detected` `CASE` (source lines 1375-1380), including its clause order and `ELSE 'supported'`, plus `cat_non_ascii` and `cat_unsupported_control` (lines 1373-1374), and a per-row `domain_assertion_met`. Unchanged in v2.1. |
| **D3** | `cell_if_classified` printed `visibility_other_profiles` - a **reachable** cell - for row 16. | Two faithful stages: `scoped` gates the candidate exactly as v1.3.16 does, and `cell` then applies `per_user`'s guard. Excluded rows print `cell = NULL`. The unguarded value survives only under the explicitly counterfactual `cell_if_domain_gate_were_open`. Unchanged in v2.1. |
| **D4** | Environment evidence relied on `current_setting('lc_collate'/'lc_ctype', true)`, which can silently return NULL, and did not consult the authoritative source. | Query A2 records `pg_database.datcollate` / `datctype` as authoritative, keeps the `current_setting` values as secondary context, and requires non-NULL on the authoritative pair. v2.1 adds `standard_conforming_strings` to the same record (C-02). |
| **D5** | `pg_collation_for()` availability and semantics were assumed. | Retained with a documented fallback and limitation (PostgreSQL 9.5 or later; its return value is the derived collation label, not the database default). Unchanged in v2.1. |
| **D6** | No compatibility handling for the collation provider. | Query A2 captures `to_jsonb(d) - 'datacl'`, so `datlocprovider` and any version-specific locale column appear only where the server defines them. Unchanged in v2.1. |

### 1.1 v2.1 corrections (C-01 to C-04)

| ID | Defect in v2 | Change in v2.1 |
|---|---|---|
| **C-01** | Section 6 classified Row 16 by **encoding name**: it listed `SJIS` beside `EUC_JP` as "multibyte non-UTF8", and `LATIN1`/`SQL_ASCII` as "single-byte non-UTF8", and asserted an outcome per label. `SJIS` is not a PostgreSQL **server** encoding, so it can never be a `server_encoding` value; no encoding was shown to represent `U+00A0`; and `SQL_ASCII` was presented as an ordinary single-byte set, which misstates its semantics. | Section 6 is rewritten around **observed** `ascii_ok` / `is_utf8` values, not labels. `SJIS` is removed from the decision logic and explicitly identified as not a server encoding. `EUC_JP` and `LATIN1` are removed as example branches. `SQL_ASCII` is described by its actual semantics and given no asserted `ascii_ok` value. A representability failure mode is added. No encoding name now carries an asserted Row 16 outcome. |
| **C-02** | The checklist captured `standard_conforming_strings` but never made its value a precondition or a PASS/FAIL check. | `standard_conforming_strings` is captured by Query A2, made a mandatory **precondition** (Section 7, P0) and an explicit PASS/FAIL gate: if it is not `on`, the run is **BLOCKED — PRECONDITION FAILED** and no vector may be recorded PASS. Recording the setting is explicitly not treated as proof that it was `on`. |
| **C-03** | Row 16's observed conclusion and its counterfactual value were distinguished, but encoding-specific outcomes were still asserted from labels. | The `domain_status` CASE order is **unchanged** (no defect was demonstrated in it). Section 6 now separates: what is established statically (the trim-set property, the Python behaviour, the logical consequence of the CASE), what must be **observed** (`ascii_ok`, `is_utf8`, `control_ok`, representability), and what is **unverified** until execution. `domain_status` is never confused with `cell_if_domain_gate_were_open`; `cell IS NULL` remains the required gate behaviour. |
| **C-04** | The execution boundaries were stated but not in one place with all four evidence classes. | The header and Section 10 now state explicitly: no engine execution, no database contact, static validation is not runtime validation, encoding-specific outcomes remain unverified until executed, and the package is an execution artifact rather than evidence that item 1 is closed. |

Unchanged from v2: all 16 vectors and their values, labels, Python expectations, candidate expectations, route cells and `expect_match` flags; the D1-D6 corrections and their intent; Query A and Query A2 separation; Query B / block 8 separation; the provenance table; the evidence capture workflow; the distinction between database metadata and derived collation information.

---

## 2. Test vectors and asserted results

Python results were independently recomputed in CPython 3 and agree with the v1.3.16 matrix column 16/16. PostgreSQL results remain unexecuted.

| # | Stored value | Python | Candidate `vis_norm` asserted | Route cell (`expected_cell`) | `expect_match` | Domain |
|---|---|---|---|---|---|---|
| 1 | `NULL` | `public` | `public` | `visibility_null_profiles` | TRUE | supported |
| 2 | `''` | `public` | `public` | `declared_public_profiles` | TRUE | supported |
| 3 | `'public'` | `public` | `public` | `declared_public_profiles` | TRUE | supported |
| 4 | `'private'` | `private` | `private` | `private_profiles` | TRUE | supported |
| 5 | `' private '` | `private` | `private` | `private_profiles` | TRUE | supported |
| 6 | `'PRIVATE'` | `private` | `private` | `private_profiles` | TRUE | supported |
| 7 | `'Private'` | `private` | `private` | `private_profiles` | TRUE | supported |
| 8 | `E'\tprivate\t'` | `private` | `private` | `private_profiles` | TRUE | supported |
| 9 | `E'\nprivate\n'` | `private` | `private` | `private_profiles` | TRUE | supported |
| 10 | `E'\rprivate\r'` | `private` | `private` | `private_profiles` | TRUE | supported |
| 11 | `E' \t\r\nprivate\n\t '` | `private` | `private` | `private_profiles` | TRUE | supported |
| 12 | `'   '` | `''` | `''` | `visibility_other_profiles` | TRUE | supported |
| 13 | `E'\t'` | `''` | `''` | `visibility_other_profiles` | TRUE | supported |
| 14 | `E'\n'` | `''` | `''` | `visibility_other_profiles` | TRUE | supported |
| 15 | `'SECRET'` | `secret` | `secret` | `visibility_other_profiles` | TRUE | supported |
| 16 | `U&'\00A0private\00A0'` | `private` | **not reproduced** | `private_profiles` (route) | **FALSE** | outside domain - see Section 6 |

`expected_cell` is the **route's** classification (what `.strip().lower()` implies). It is a test expectation, never a claim about what R16 emits. R16 emits `cell = NULL` for every out-of-domain row.

---

## 3. Query A2 - environment record (catalogs only, no application data)

Run first, in the same session as Query A. `to_jsonb(d) - 'datacl'` is version-adaptive: `datlocprovider` (PostgreSQL 15+) and any version-specific locale column appear as keys only where the server defines them, so a single statement works on every supported version and fails on none. `datacl` is removed deliberately; no other column is.

```sql
SELECT current_database()                             AS database_name,
       version()                                      AS version,
       current_setting('server_version_num')::int     AS server_version_num,
       d.datcollate                                   AS datcollate_authoritative,
       d.datctype                                     AS datctype_authoritative,
       d.encoding                                     AS database_encoding_oid,
       pg_encoding_to_char(d.encoding)                AS database_encoding,
       current_setting('server_encoding', true)       AS server_encoding_setting,
       current_setting('lc_collate', true)            AS lc_collate_setting,
       current_setting('lc_ctype', true)              AS lc_ctype_setting,
       current_setting('standard_conforming_strings', true)
                                                      AS standard_conforming_strings_setting,
       to_jsonb(d) - 'datacl'                         AS pg_database_record
FROM pg_database d
WHERE d.datname = current_database();
```

The authoritative pair is `datcollate_authoritative` / `datctype_authoritative`. If either is NULL the run must be recorded as **environment evidence incomplete**; the `current_setting` values are context and must not be substituted for them. `standard_conforming_strings_setting` is a precondition input, not mere context: Section 7 makes its value a PASS/FAIL gate.

## 4. Query A - synthetic vector test (`VALUES` only, reads no table and no catalog)

The row-16 vector is written with `U&` Unicode-escape syntax. Its representability depends on the server encoding, which this package cannot determine statically; Section 6.1 defines how to record the outcome if the constant cannot be represented. The literal is retained exactly as written: v2.1 introduces no alternative expression and no different test value.

```sql
WITH vectors (id, label, stored, expected_python, expected_vis_norm, expected_cell,
              expect_match, expect_supported_domain) AS (
  VALUES
    ( 1, 'NULL',                    NULL::text,             'public',  'public',  'visibility_null_profiles',  TRUE,  TRUE),
    ( 2, 'empty string',            ''::text,               'public',  'public',  'declared_public_profiles',  TRUE,  TRUE),
    ( 3, 'public',                  'public',               'public',  'public',  'declared_public_profiles',  TRUE,  TRUE),
    ( 4, 'private',                 'private',              'private', 'private', 'private_profiles',          TRUE,  TRUE),
    ( 5, 'space-wrapped',           ' private ',            'private', 'private', 'private_profiles',          TRUE,  TRUE),
    ( 6, 'PRIVATE',                 'PRIVATE',              'private', 'private', 'private_profiles',          TRUE,  TRUE),
    ( 7, 'Private',                 'Private',              'private', 'private', 'private_profiles',          TRUE,  TRUE),
    ( 8, 'tab-wrapped',             E'\tprivate\t',         'private', 'private', 'private_profiles',          TRUE,  TRUE),
    ( 9, 'newline-wrapped',         E'\nprivate\n',         'private', 'private', 'private_profiles',          TRUE,  TRUE),
    (10, 'CR-wrapped',              E'\rprivate\r',         'private', 'private', 'private_profiles',          TRUE,  TRUE),
    (11, 'mixed whitespace',        E' \t\r\nprivate\n\t ', 'private', 'private', 'private_profiles',          TRUE,  TRUE),
    (12, 'spaces only',             '   ',                  '',        '',        'visibility_other_profiles', TRUE,  TRUE),
    (13, 'tab only',                E'\t',                  '',        '',        'visibility_other_profiles', TRUE,  TRUE),
    (14, 'newline only',            E'\n',                  '',        '',        'visibility_other_profiles', TRUE,  TRUE),
    (15, 'unknown value',           'SECRET',               'secret',  'secret',  'visibility_other_profiles', TRUE,  TRUE),
    (16, 'NBSP-wrapped (outside domain)', U&'\00A0private\00A0',
                                                            'private', 'private', 'private_profiles',          FALSE, FALSE)
),
calc AS (
  -- Test-only stage: the candidate is applied to every vector so the expression
  -- itself can be tested. This is NOT how v1.3.16 evaluates it, and this CTE must
  -- never be transplanted into R16, whose candidate is reachable only through the
  -- domain gate (v1.3.16 scoped, lines 1383-1393).
  SELECT vectors.*,
         CASE WHEN stored IS NULL THEN TRUE
              ELSE octet_length(stored) = char_length(stored)
         END                                              AS ascii_ok,
         CASE WHEN stored IS NULL THEN TRUE
              ELSE translate(stored, E'\t\n\x0b\f\r', '') !~ '[[:cntrl:]]'
         END                                              AS control_ok,
         (current_setting('server_encoding', true) = 'UTF8') AS is_utf8,
         lower(btrim(coalesce(nullif(stored, ''), 'public'),
                     E' \t\n\r\f\x0b') COLLATE "C")       AS vis_norm_raw
  FROM vectors
),
detected AS (
  -- Clause order follows v1.3.16 detected (lines 1375-1380) exactly.
  SELECT calc.*,
         (NOT ascii_ok)                                   AS cat_non_ascii,
         (NOT control_ok)                                 AS cat_unsupported_control,
         CASE
           WHEN NOT control_ok      THEN 'unsupported'
           WHEN NOT ascii_ok        THEN 'unsupported'
           WHEN is_utf8 IS NOT TRUE THEN 'undetermined'
           ELSE                          'supported'
         END                                              AS domain_status
  FROM calc
),
scoped AS (
  -- Stage 2, faithful to v1.3.16 scoped (lines 1388-1392): candidate or NULL.
  SELECT detected.*,
         CASE WHEN domain_status = 'supported' THEN vis_norm_raw
              ELSE NULL
         END                                              AS vis_norm
  FROM detected
),
classified AS (
  -- Stage 3, faithful to v1.3.16 per_user (lines 1397-1403).
  SELECT scoped.*,
         CASE
           WHEN vis_norm IS NULL            THEN NULL
           WHEN stored IS NULL              THEN 'visibility_null_profiles'
           WHEN vis_norm = 'public'         THEN 'declared_public_profiles'
           WHEN vis_norm = 'private'        THEN 'private_profiles'
           ELSE                                  'visibility_other_profiles'
         END                                              AS cell,
         CASE WHEN vis_norm IS NULL            THEN NULL
              WHEN stored IS NULL              THEN 'visibility_null_profiles'
              WHEN vis_norm_raw = 'public'     THEN 'declared_public_profiles'
              WHEN vis_norm_raw = 'private'    THEN 'private_profiles'
              ELSE                                  'visibility_other_profiles'
         END                                              AS cell_if_domain_gate_were_open
  FROM scoped
)
SELECT id,
       label,
       expected_python,
       expected_vis_norm,
       vis_norm_raw,
       COALESCE(vis_norm_raw = expected_vis_norm, FALSE)              AS candidate_matches_route,
       expect_match,
       COALESCE(vis_norm_raw = expected_vis_norm, FALSE) = expect_match AS candidate_assertion_met,
       is_utf8,
       ascii_ok,
       control_ok,
       cat_non_ascii,
       cat_unsupported_control,
       domain_status,
       CASE WHEN expect_supported_domain
            THEN CASE WHEN is_utf8 IS TRUE THEN (domain_status = 'supported')
                      ELSE (domain_status = 'undetermined') END
            ELSE (domain_status <> 'supported')
       END                                                            AS domain_assertion_met,
       vis_norm,
       cell,
       expected_cell,
       CASE WHEN domain_status <> 'supported' THEN (cell IS NULL)
            ELSE (cell = expected_cell) END                           AS cell_assertion_met,
       cell_if_domain_gate_were_open,
       pg_collation_for(vis_norm_raw)                                  AS collation_derived_for_expression
FROM classified
ORDER BY id;
```

`pg_collation_for` requires PostgreSQL 9.5 or later. If it is unavailable, remove that one column and record the substitution; the run is then downgraded to **derived collation NOT RECORDED**, which Sections 7 and 10 treat as a limitation rather than a failure of the vectors.

## 5. Query B - R4b value-domain record (separate statement, reads `users`)

Execute **block 8 of v1.3.16, lines 1036-1197, unmodified**, in the same session, under its own explicit authorization. It is an aggregate-only read of the `users` table, it is not part of Query A, and it must not be edited. Its self-check remains commented out (block 8, lines 1164-1166); that is intentional in the source and is not a defect to be repaired here.

## 6. Row 16 - asserted, observed and unverified

Row 16's stored value is `U&'\00A0private\00A0'`: `U+00A0`, `private`, `U+00A0`.

**Established without a server, from the SQL text and from Python:**
1. Python's `.strip()` removes `U+00A0` (`'\u00a0private\u00a0'.strip() == 'private'`), so the route reads the value as `private`.
2. The candidate's trim set is the literal `E' \t\n\r\f\x0b'`, which does not contain `U+00A0`; therefore, **if the candidate is evaluated on that character string**, its result cannot equal `private`. This is a property of the literal, not of the encoding.
3. Given `ascii_ok`, `is_utf8` and `control_ok`, the `domain_status` outcome is fixed by the `CASE` copied from v1.3.16. That is a logical consequence of the SQL text, not an observation.

**Not established, and therefore recorded rather than assumed:**
- (a) whether the deployed server encoding can represent `U+00A0` at all;
- (b) the observed `octet_length` / `char_length` of the value there, and hence `ascii_ok`;
- (c) whether `[[:cntrl:]]` membership matches the documented set under the deployed `LC_CTYPE` (F-R16-05).

### 6.1 If the encoding cannot represent U+00A0

The `U&` constant is then not a valid string in the server encoding, and PostgreSQL raises an encoding error when the constant is parsed or coerced; the statement returns no rows. Record this as **ROW 16 NOT TESTABLE ON THIS INSTANCE** — an environment fact, not a vector failure — and record item 1 as **incomplete for this row**. Do not substitute a different character, a different literal form or a hand-derived expectation.

### 6.2 If it can be represented - branches on observed values only

No encoding name appears in this table. Every row is keyed on values Query A actually returns.

| Observed `ascii_ok` | Observed `is_utf8` | `domain_status` | `cell` | Excluded | Reading |
|---|---|---|---|---|---|
| FALSE | TRUE | `unsupported` | NULL | yes | The UTF8 case. In UTF-8, `U+00A0` is a two-byte sequence, so `octet_length > char_length` for any value containing it; that is a property of UTF-8 itself, not an assumption about a server. |
| FALSE | FALSE | `unsupported` | NULL | yes | Excluded by the byte-length test before the encoding test is reached. |
| TRUE | FALSE | `undetermined` | NULL | yes | `ascii_ok` being TRUE does **not** make the row supported: `is_utf8 IS NOT TRUE` places it outside the supported domain. This is the case D1 corrected. |
| TRUE | TRUE | `supported` | not NULL | **no** | **Cannot occur for this value on a genuine UTF8 server** (a value containing `U+00A0` is multibyte in UTF-8, so `ascii_ok` cannot be TRUE there). If it is observed, record **FAIL / UNEXPECTED**, stop, and investigate whether the literal is what this package assumes - do not accept the row as classified. |

In all three possible branches the row is excluded: `domain_status <> 'supported'`, `cell IS NULL`, it is counted in `unsupported_rows` or `domain_undetermined_rows`, and it is never `private_profiles`, never in a reachable cell, and never in exposure. `cell` is NULL because `scoped` nulls the candidate for a non-supported row and `per_user` maps a NULL `vis_norm` to a NULL cell - the two stages copied from v1.3.16, whose order is unchanged here.

### 6.3 Encoding names: what may and may not be said

**PostgreSQL-supported server encodings.** `server_encoding` takes values from PostgreSQL's supported set, and not every name PostgreSQL recognises can be a server encoding. `SJIS`, in particular, is **not a PostgreSQL server encoding** (it is a client-side encoding only), so it can never be the value of `server_encoding` and must never appear as a branch of this test. An earlier edition of this package listed it beside `EUC_JP`; that listing is a defect and is removed here.

**Encodings able to represent `U+00A0`.** Which supported encodings can represent `U+00A0`, and what `octet_length` / `char_length` they produce for it, is **not established by this package** and is not asserted. It is settled only by the run: either the constant is representable and Query A returns a row (Section 6.2), or it is not and Section 6.1 applies. No encoding is named as an example of either outcome.

**`SQL_ASCII` is not an ordinary single-byte character set.** Under `SQL_ASCII`, PostgreSQL performs **no character-set conversion and no validation** of non-ASCII data: bytes are stored and returned as they were supplied, multibyte characters are not recognised, and string functions operate on bytes rather than on decoded characters. Two consequences matter here. First, the byte-length non-ASCII test is structurally undecidable under `SQL_ASCII`, so a "supported" verdict there would rest on an absence the test cannot detect. Second, a `char_length` computed under `SQL_ASCII` is not an encoding-level statement about characters. This package therefore **asserts no `ascii_ok` value for `SQL_ASCII`**: whichever value is observed, `is_utf8` is FALSE and the row falls into one of the two excluded non-UTF8 branches of Section 6.2. A run on `SQL_ASCII` must additionally be recorded as **encoding unsupported for this test**, because the domain distinction that N-16.1 item 2 depends on cannot be established there.

**Unverified until executed.** Everything encoding-specific in this section - representability, observed byte and character lengths, and the resulting branch - is **unverified** until the authorized run on the target server. Nothing in this document reports a PostgreSQL result.

## 7. Preconditions and pass criteria

**P0 - Mandatory precondition: `standard_conforming_strings = on`.**
Row 16 is written with `U&` Unicode-escape string syntax, and this package will not depend on an unrecorded string-literal setting. `standard_conforming_strings_setting` from Query A2 must read **`on`**. Merely capturing the setting is not proof that it is `on`: the recorded value itself must be `on`. If it reads `off` (or is NULL/unavailable), the run is **BLOCKED - PRECONDITION FAILED**: no vector may be recorded PASS and the execution must be reported as incomplete. This is a conservative gate imposed by this package. It is **not** a claim that PostgreSQL rejects `U&` literals when the setting is `off`, and no such claim is made here.

With P0 satisfied, a run passes item 1 only if **all** of the following hold:

1. `candidate_assertion_met = TRUE` for rows 1-16, i.e. rows 1-15 match the tabulated values and row 16 does **not** match `'private'`.
2. `domain_assertion_met = TRUE` for rows 1-16: supported vectors are `supported` where `is_utf8` is TRUE and `undetermined` where it is not; row 16 is never `supported`.
3. `cell_assertion_met = TRUE` for rows 1-16: `cell` equals `expected_cell` where the domain gate is open, and `cell IS NULL` wherever it is closed.
4. Query A2 returned non-NULL `datcollate_authoritative` and `datctype_authoritative`, plus `version`, `server_encoding_setting`, `database_encoding`, `standard_conforming_strings_setting` and `pg_database_record`.
5. `collation_derived_for_expression` recorded for every row where it is non-NULL; if `pg_collation_for` was unavailable, the substitution is recorded and this criterion is reported as a limitation, not silently skipped.
6. `control_ok = TRUE` for rows 8-11, 13 and 14. A FALSE there means `[[:cntrl:]]` membership under the deployed `LC_CTYPE` differs from the documented set - an **F-R16-05 deployment finding**, not a vector error - and the run must record it as such.
7. Row 16 is either present in the result and satisfies criteria 2 and 3, or is recorded **NOT TESTABLE** under Section 6.1. In the latter case item 1 is **incomplete**, not passed.
8. Query B executed separately with its own authorization, and its counts agree with R16's domain columns per v1.3.16 line 1514.

Nothing in a passing run closes N-16.1 by itself: item 1 and item 2 must be recorded on the same instance and reviewed together.

## 8. Expression provenance (each expression vs. v1.3.16)

| Expression in this package | v1.3.16 source | Relationship |
|---|---|---|
| `lower(btrim(coalesce(nullif(..., ''), 'public'), E' \t\n\r\f\x0b') COLLATE "C")` | line 1290 (candidate), lines 1389-1390 (`scoped`) | copied character-for-character |
| `octet_length(...) = char_length(...)` | lines 1361-1364 (`base.ascii_ok`) | copied, `u.profile_visibility` -> `stored` |
| `translate(..., E'\t\n\x0b\f\r', '') !~ '[[:cntrl:]]'` | lines 1365-1368 (`base.control_ok`) | copied, same character set and same regex |
| `CASE WHEN NOT control_ok ... WHEN NOT ascii_ok ... WHEN is_utf8 IS NOT TRUE ... ELSE 'supported'` | lines 1375-1380 (`detected.domain_status`) | clause order and literals identical |
| `(NOT ascii_ok)` / `(NOT control_ok)` | lines 1373-1374 | same |
| `CASE WHEN domain_status = 'supported' THEN ... ELSE NULL` | lines 1388-1392 (`scoped`) | same gate |
| `CASE WHEN vis_norm IS NULL ... 'visibility_null_profiles' ... 'declared_public_profiles' ... 'private_profiles' ... ELSE 'visibility_other_profiles'` | lines 1397-1403 (`per_user`) | same order and literals |
| `current_setting('server_encoding', true) = 'UTF8'` | line 1056 (`enc.is_utf8`) | identical |
| `current_setting('lc_collate'/'lc_ctype', true)` | lines 1054-1055 | retained as secondary context only (D4) |

Only two expressions here are not copied from v1.3.16, and both are test scaffolding that touches no gate: `pg_collation_for(vis_norm_raw)` and `cell_if_domain_gate_were_open`. No `domain_status` clause was reordered or reworded, because no defect in it was demonstrated.

## 9. Execution checklist (authorized deployed run)

1. Authorization for Query A2 and Query A (read-only, no user data) and, separately, for Query B (aggregate read of `users`). Record instance name, environment and operator.
2. Read-only role; `SET default_transaction_read_only = on; SET statement_timeout = '30s';` record `SHOW standard_conforming_strings;`.
3. Run Query A2. **Gate P0:** if `standard_conforming_strings_setting` is not `on`, stop and record **BLOCKED - PRECONDITION FAILED**; do not run Query A. Fail the record if `datcollate_authoritative` or `datctype_authoritative` is NULL.
4. Run Query A. If it raises an encoding error on the row-16 constant, record **ROW 16 NOT TESTABLE** per Section 6.1, keep the rest of the result, and record the error text verbatim.
5. Capture the entire result set verbatim, text and CSV, with both file SHA-256 values recorded beside it.
6. Evaluate the preconditions and the eight criteria of Section 7 row by row; record any FALSE with the row id and the observed `ascii_ok` / `is_utf8` values.
7. Run Query B (block 8, unmodified) if separately authorized; capture verbatim; reconcile against R16's domain columns.
8. Record the observed encoding facts and which Section 6.2 branch applied; if the `TRUE`/`TRUE` branch appears, record **FAIL / UNEXPECTED**.
9. Do not edit any output. A failing row is recorded as a failure.
10. Do not close N-16.1 on item 1 alone.

## 10. Limitations and evidence boundaries

- **No PostgreSQL engine execution has been performed** for this package, at any version. No production or deployed database has been contacted.
- **Static SQL validation is not runtime validation.** Balanced parentheses and a structural reading of the `CASE` ordering do not establish that PostgreSQL will accept or correctly execute either query.
- **Encoding-specific outcomes remain unverified** until executed on the target server: whether `U+00A0` is representable, the observed `octet_length` / `char_length`, and the branch that follows. No encoding name carries an asserted Row 16 result.
- `pg_collation_for` availability and semantics are assumed, not proven (requirement: PostgreSQL 9.5+).
- `[[:cntrl:]]` membership under the deployed `LC_CTYPE` is exactly F-R16-05 and remains open; this package can surface it but cannot settle it.
- The `SQL_ASCII` case is recorded as **encoding unsupported for this test**; the package cannot distinguish domain membership there.
- The package does not close F-R16-04. It supplies the executable query the finding records as missing, in a separate file; whether the finding closes by accepting this external artifact or by embedding the query in a scoped revision is a document-owner decision.
- This is not an independent audit and does not satisfy G9. No finding, gate or status is changed by this document.
