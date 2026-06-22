## ADDED Requirements

### Requirement: Redis verdict cache storage
The system SHALL store the judge verdict in Redis under the key `debate:{debate_id}:verdict` as a JSON string with a TTL of 86400 seconds (24 hours), consistent with speech cache TTL.

#### Scenario: Cache verdict on debate finish
- **WHEN** `cache_verdict(debate_id, verdict, winner)` is called after debate finishes
- **THEN** the verdict JSON (containing `winner`, `scores`, `summary` fields) SHALL be stored under `debate:{debate_id}:verdict` with 24h TTL

#### Scenario: Cache miss returns None
- **WHEN** `get_verdict(debate_id)` is called for a debate not in cache
- **THEN** the method SHALL return `None`

#### Scenario: Cache hit returns parsed dict
- **WHEN** `get_verdict(debate_id)` is called for a cached debate
- **THEN** the method SHALL return the verdict dict with `winner` and `scores` keys

#### Scenario: Redis unavailable degrades gracefully
- **WHEN** Redis connection is unavailable during `cache_verdict` or `get_verdict` calls
- **THEN** the method SHALL log a warning and return normally (no-op for write, `None` for read)

### Requirement: Verdict cache invalidation
The system SHALL delete the verdict cache key when a debate is deleted.

#### Scenario: Invalidate removes verdict key
- **WHEN** `invalidate_debate(debate_id)` is called
- **THEN** the `debate:{debate_id}:verdict` key SHALL be deleted alongside speeches and summary keys

### Requirement: Batch verdict retrieval
The system SHALL support batch retrieval of verdicts for multiple debate IDs.

#### Scenario: Batch get returns partial results
- **WHEN** `get_batch_verdicts(debate_ids)` is called with a list of debate IDs
- **THEN** the method SHALL return a dict `{debate_id: verdict}` for all cached debates, omitting misses
- **THEN** the method SHALL return `None` when all keys miss
