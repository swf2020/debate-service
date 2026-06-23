## ADDED Requirements

### Requirement: SSEHistoryReplay includes verdict
The `SSEHistoryReplay` SSE event SHALL optionally carry the judge's verdict and winner fields for completed debates.

#### Scenario: Finished debate replay includes verdict
- **WHEN** a client reconnects to an SSE stream for a debate with `status == "finished"`
- **THEN** the `SSEHistoryReplay` event SHALL include `verdict` (full verdict dict) and `winner` (string: "pro" | "con" | "draw")

#### Scenario: Running debate replay omits verdict
- **WHEN** a client reconnects to an SSE stream for a debate with `status != "finished"`
- **THEN** the `SSEHistoryReplay` event SHALL omit `verdict` and `winner` fields (both `None`)

#### Scenario: Forward compatibility
- **WHEN** an older client receives an `SSEHistoryReplay` event with `verdict` and `winner` fields
- **THEN** the client SHALL ignore unknown fields without error

### Requirement: Verdict replay renders immediately
The frontend SHALL render the judge verdict upon receiving `history_replay` event without requiring an additional REST API call.

#### Scenario: Render verdict from history_replay
- **WHEN** frontend receives `history_replay` event with `status === "finished"` and valid `verdict`
- **THEN** frontend SHALL call `showVerdict(verdict, winner)` immediately

#### Scenario: Skip verdict render for running debate
- **WHEN** frontend receives `history_replay` event with `status !== "finished"` or missing `verdict`
- **THEN** frontend SHALL NOT attempt to render verdict

### Requirement: REST endpoint reads verdict from cache
The `GET /api/debate/{debate_id}` endpoint SHALL prefer Redis cache for verdict retrieval, falling back to SQLite on cache miss.

#### Scenario: Cache hit on REST endpoint
- **WHEN** `GET /api/debate/{id}` is called and verdict is cached in Redis
- **THEN** the response SHALL include the cached verdict without querying SQLite for verdict

#### Scenario: Cache miss falls back to SQLite
- **WHEN** `GET /api/debate/{id}` is called and verdict is NOT cached in Redis
- **THEN** the endpoint SHALL read verdict from SQLite via `get_debate()` and backfill Redis cache
