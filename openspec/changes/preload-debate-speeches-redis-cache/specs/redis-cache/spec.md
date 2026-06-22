## ADDED Requirements

### Requirement: Redis 连接管理

系统 SHALL 在应用启动时建立 Redis 连接池，在应用关闭时释放连接。

#### Scenario: 正常连接
- **WHEN** 应用启动且 `REDIS_URL` 环境变量已配置
- **THEN** 系统建立到 Redis 的连接池（max_connections=10），并可通过 `get_redis()` 获取客户端实例

#### Scenario: Redis 不可用
- **WHEN** 应用启动但 Redis 服务不可达
- **THEN** 系统记录警告日志并继续启动，所有缓存操作静默回退到 SQLite

#### Scenario: 未配置 Redis
- **WHEN** `REDIS_URL` 环境变量为空
- **THEN** 系统跳过 Redis 初始化，所有操作直接使用 SQLite

### Requirement: 演讲缓存写入

系统 SHALL 在辩论结束时将 speeches 写入 Redis 缓存。

#### Scenario: 辩论正常结束
- **WHEN** 辩论流程执行完毕（status 变为 finished）
- **THEN** 系统异步将完整 speeches 数组写入 `debate:{id}:speeches` key 和摘要写入 `debate:{id}:summary` key，均设置 TTL 86400 秒

#### Scenario: 辩论异常终止
- **WHEN** 辩论因异常终止
- **THEN** 系统在 finally 块中尝试写入缓存，写入失败仅记录日志不影响主流程

#### Scenario: 空 speeches
- **WHEN** 辩论无任何演讲记录
- **THEN** 系统不写入 Redis 缓存

### Requirement: 演讲缓存读取

系统 SHALL 在读取辩论 speeches 时优先从 Redis 获取。

#### Scenario: 缓存命中
- **WHEN** 请求 `debate:{id}:speeches` 且 Redis 中存在该 key
- **THEN** 系统直接返回缓存的 speeches 数组，不查询 SQLite

#### Scenario: 缓存未命中
- **WHEN** 请求 `debate:{id}:speeches` 且 Redis 中不存在该 key
- **THEN** 系统从 SQLite 查询 speeches，返回结果，并异步回填 Redis 缓存

#### Scenario: Redis 异常
- **WHEN** 读取 Redis 时发生连接异常
- **THEN** 系统捕获异常，回退到 SQLite 查询，记录警告日志

### Requirement: 缓存失效

系统 SHALL 在辩论删除时同步清除对应的 Redis 缓存。

#### Scenario: 删除辩论
- **WHEN** 通过 `DELETE /api/debate/{id}` 删除辩论
- **THEN** 系统删除 `debate:{id}:speeches` 和 `debate:{id}:summary` 两个 Redis key

#### Scenario: TTL 自动过期
- **WHEN** 缓存 key 超过 86400 秒未被访问
- **THEN** Redis 自动删除该 key，下次读取时从 SQLite 回填

### Requirement: 批量演讲摘要查询

系统 SHALL 提供批量获取多个辩论 speeches 摘要的接口。

#### Scenario: 批量查询
- **WHEN** 请求 `GET /api/debate/speeches/batch?ids=id1,id2,id3`
- **THEN** 系统返回 `{speeches: {id1: [...], id2: [...], id3: [...]}}`，每个 debate_id 对应其 speeches 摘要数组（不含 thinking 字段）

#### Scenario: 部分缓存命中
- **WHEN** 请求的 debates 中部分在 Redis 命中、部分未命中
- **THEN** 命中的从 Redis 返回，未命中的从 SQLite 查询并回填缓存

#### Scenario: 空 id 列表
- **WHEN** 请求 `ids` 参数为空
- **THEN** 系统返回 `{speeches: {}}`
