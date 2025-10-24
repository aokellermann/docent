# Docent Query Language (DQL)

Docent Query Language is a read-only SQL subset that supports ad-hoc exploration in Docent.

## Overview

- DQL accepts a **single `SELECT` statement**. The validator rejects data-changing commands, multi-statement batches, and unsupported syntax.
- Queries can only run over a single collection by design (if you need multi-collection support, please reach out to us!)

## Available Tables and Columns

| Table | Description |
| --- | --- |
| `agent_runs` | Information about each agent run in a collection. |
| `transcripts` | Individual transcripts tied to an agent run; stores serialized messages and per-transcript metadata. |
| `transcript_groups` | Hierarchical groupings of transcripts for runs. |
| `judge_results` | Scored rubric outputs keyed by agent run and rubric version. |

### `agent_runs`

| Column | Description |
| --- | --- |
| `id` | Agent run identifier (UUID). |
| `collection_id` | Collection that owns the run; DQL enforces equality with the active collection. |
| `name` | Optional user-provided display name. |
| `description` | Optional description supplied at ingest time. |
| `metadata_json` | User suplied metadata, stored as JSON.  |
| `created_at` | When the run was recorded in Docent. |
| `text_for_search` | Preprocessed text blob used by full-text search. |

### `transcripts`

| Column | Description |
| --- | --- |
| `id` | Transcript identifier (UUID). |
| `collection_id` | Collection that owns the transcript. |
| `agent_run_id` | Parent run identifier; joins back to `agent_runs.id`. |
| `name` | Optional transcript title. |
| `description` | Optional description. |
| `transcript_group_id` | Optional grouping identifier. |
| `messages` | Binary-encoded JSON payload of message turns. |
| `metadata_json` | Binary-encoded metadata describing the transcript. |
| `created_at` | Timestamp recorded during ingest. |

### `transcript_groups`

| Column | Description |
| --- | --- |
| `id` | Transcript group identifier. |
| `collection_id` | Owning collection. |
| `agent_run_id` | Parent run identifier. |
| `name` | Optional name for the group. |
| `description` | Optional descriptive text. |
| `parent_transcript_group_id` | Identifier of the parent group (for hierarchical groupings). |
| `metadata_json` | JSONB metadata payload for the group. |
| `created_at` | Timestamp recorded during ingest. |

### `judge_results`

| Column | Description |
| --- | --- |
| `id` | Judge result identifier. |
| `agent_run_id` | Run scored by the rubric. |
| `rubric_id` | Rubric identifier. |
| `rubric_version` | Version of the rubric used when scoring. |
| `output` | JSON representation of rubric outputs. |
| `result_metadata` | Optional JSON metadata attached to the result. |
| `result_type` | Enum describing the rubric output type. |
| `value` | Deprecated string value retained for back-compat. |

### JSON Metadata Paths

Docent stores user-supplied metadata as JSON, and can be access in Postgres style. Here are some examples:

#### Access Patterns
```sql
-- Filter agent runs by a metadata attribute
SELECT id, name
FROM agent_runs
WHERE metadata_json->>'environment' = 'staging';
```
```sql
-- Retrieve nested transcript metadata
SELECT
  id,
  metadata_json->'conversation'->>'speaker' AS speaker,
  metadata_json->'conversation'->>'topic' AS topic
FROM transcripts
WHERE metadata_json->>'status' = 'flagged';
```
```sql
-- Cast numeric metadata for aggregation
SELECT
  AVG(CAST(metadata_json->>'latency_ms' AS DOUBLE PRECISION)) AS avg_latency_ms
FROM agent_runs
WHERE metadata_json ? 'latency_ms';
```
When querying JSON fields, comparisons default to string semantics. Cast values when you need numeric ordering or aggregation.


## Allowed Syntax

DQL supported keywords:

| Feature | Notes / References |
| --- | --- |
| `SELECT`, `DISTINCT`, `FROM`, `WHERE` | Standard projections and filters. |
| `JOIN`, `LEFT JOIN`, `RIGHT JOIN`, `FULL JOIN` | Explicit joins across tables. |
| `WITH ...` (CTEs) | Common table expressions are supported; each body is validated and collection-scoped. |
| `GROUP BY`, `HAVING` | Aggregations. |
| `ORDER BY`, `LIMIT`, `OFFSET` | Limits are capped by the service (default 500 rows). |
| `CASE ... WHEN ... THEN ... END` | Conditional projections. |
| `COUNT()` | Row counts without needing `*`. |
| Boolean logic (`AND`, `OR`, `NOT`) | Nested expressions are permitted. |
| Comparison operators (`=`, `!=`, `<`, `<=`, `>`, `>=`, `IS`, `IS NOT`) | Includes `IN`, `BETWEEN`, `LIKE`, `ILIKE`, `EXISTS`. |
| Arithmetic (`+`, `-`, `*`, `/`) | Limited to expression contexts supported by `sqlglot`. |
| JSON operators | `metadata_json` paths compile to PostgreSQL JSON operators (`->`, `->>`, etc.). |

Unsupported constructs include `*`, user-defined functions, and any DDL or DML commands.

## Examples

### Recent Runs

```sql
SELECT
  id,
  name,
  metadata_json->'model'->>'name' AS model_name,
  created_at
FROM agent_runs
WHERE metadata_json->>'status' = 'completed'
ORDER BY created_at DESC
LIMIT 10;
```

### Transcript Counts per Group

```sql
SELECT
  tg.id AS group_id,
  tg.name AS group_name,
  COUNT(t.id) AS transcript_count
FROM transcript_groups tg
JOIN transcripts t ON t.transcript_group_id = tg.id
GROUP BY tg.id, tg.name
HAVING COUNT(t.id) > 1
ORDER BY transcript_count DESC;
```

### Flagged Judge Results

```sql
SELECT
  jr.agent_run_id,
  jr.rubric_id,
  jr.result_metadata->>'label' AS label,
  jr.output->>'score' AS score
FROM judge_results jr
WHERE jr.result_metadata->>'severity' = 'high'
  AND EXISTS (
    SELECT 1
    FROM agent_runs ar
    WHERE ar.id = jr.agent_run_id
      AND ar.metadata_json->>'environment' = 'prod'
  )
ORDER BY score DESC
LIMIT 25;
```

## Restrictions and Best Practices

- **Read-only**: Only `SELECT`-style queries are permitted. Use bulk exports or ingestion utilities to modify data outside of DQL.
- **Single statement**: Batches or multiple statements are rejected to avoid mixed workloads.
- **Explicit projection**: Wildcard projections (`*`) are disallowed. List the columns you need so downstream tooling (schema builders, type generation) stays predictable.
- **Collection scoping**: A single query can only access data within a single collection.
- **Limit enforcement**: Every query is capped at 10,000 rows by the server. If you omit `LIMIT` or request more, Docent automatically applies the cap—use pagination (`OFFSET`/`LIMIT`) or offline exports for larger result sets.
- **JSON performance**: Metadata fields are stored as JSON; heavy traversal across large collections can be slower than filtering on indexed scalar columns. Prefer top-level fields when available.
- **Type awareness**: The registry tracks datatypes for JSON metadata paths. When a path supports multiple types Docent may fall back to string comparisons, so cast where precision matters (e.g., `CAST(metadata_json->>'duration_ms' AS BIGINT)`).
