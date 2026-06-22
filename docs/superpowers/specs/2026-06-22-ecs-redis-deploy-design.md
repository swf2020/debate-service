# ECS Redis 缓存部署方案

**日期**: 2026-06-22
**状态**: 设计完成
**分支**: feat/debater-status-refresh

## 背景

代码仓已完整集成 Redis 缓存层（`redis_cache.py`），用于缓存辩论演讲数据，减少 SQLite 查询压力。`deploy/setup.sh` 已有 Redis 安装步骤（`yum install redis` + `systemctl enable/start`），但缺少缓存专用配置（内存限制、淘汰策略、持久化关闭）。

## 部署模式

- **同机部署**：Redis 与 debate-service 在同一台 ECS 上运行
- **通信方式**：`redis://localhost:6379/0`，仅绑定 127.0.0.1
- **安全策略**：仅 localhost 监听，无密码，外部不可达
- **持久化**：关闭（纯缓存，数据由 SQLite 兜底）
- **配置方式**：追加配置到 `/etc/redis.conf` 末尾

## Redis 配置（追加到 /etc/redis.conf）

```conf
# === debate-service 缓存专用配置 ===
# 仅监听本地，防止外部访问
bind 127.0.0.1

# 关闭 RDB 快照（纯缓存模式，无需持久化）
save ""

# 关闭 AOF 日志
appendonly no

# 内存淘汰策略：LRU 淘汰所有 key
maxmemory-policy allkeys-lru

# 内存上限（256MB，ECS 通常内存为 4-8GB）
maxmemory 256mb
```

**为什么 256MB？** 每条演讲数据约 2-10KB，24h TTL 自动过期，256MB 可容纳约 2-10 万条演讲缓存，足够覆盖数千场辩论。

**为什么 `allkeys-lru`？** 所有 key 都有 SQLite 兜底，可安全淘汰。LRU 确保热点数据留存在内存中。

## 改动点

### 1. `deploy/setup.sh` — 首次部署脚本

在安装 Redis 后增加配置步骤。当前：

```bash
yum install -y python3 python3-pip git nginx redis
echo "=== Enabling and starting Redis ==="
systemctl enable redis
systemctl start redis
```

改为：

```bash
yum install -y python3 python3-pip git nginx redis

echo "=== Configuring Redis cache ==="
cat >> /etc/redis.conf <<'REDIS_EOF'

# === debate-service cache config ===
bind 127.0.0.1
save ""
appendonly no
maxmemory-policy allkeys-lru
maxmemory 256mb
REDIS_EOF

echo "=== Enabling and starting Redis ==="
systemctl enable redis
systemctl restart redis
```

### 2. `deploy/deploy.sh` — 自动部署健康检查

当前已有 app 健康检查。可选增加 Redis 连通性检查：

```bash
# 现有：curl -sf http://localhost:8080/api/debate/active
# 可选增加一行：
redis-cli ping > /dev/null 2>&1 || echo "Warning: Redis not responding"
```

此项为**可选**，不阻塞部署流程。

### 3. 无需代码改动

`redis_cache.py` 已处理 Redis 不可用的优雅降级（返回 None，自动回退 SQLite）。`REDIS_URL=redis://localhost:6379/0` 已在 `/etc/default/debate-env` 中配置。

## 验证方法

### 1. 配置验证

```bash
# SSH 到 ECS
redis-cli CONFIG GET bind          # 应返回 127.0.0.1
redis-cli CONFIG GET save          # 应返回空
redis-cli CONFIG GET maxmemory     # 应返回 268435456
redis-cli CONFIG GET maxmemory-policy  # 应返回 allkeys-lru
```

### 2. 连通性验证

```bash
redis-cli ping  # 应返回 PONG
```

### 3. 缓存读写验证

```bash
# 启动一场辩论，等待结束后
redis-cli KEYS "debate:*"  # 应有 debate:{id}:speeches 和 debate:{id}:summary
redis-cli TTL "debate:{id}:speeches"  # 应返回 ≤ 86400

# 访问辩论详情 API，验证优先走 Redis
curl -H "Authorization: Bearer <token>" http://localhost:8080/api/debate/{id} | jq '.speeches'
```

### 4. 模拟 Redis 不可用

```bash
systemctl stop redis
# 辩论详情 API 应正常返回（从 SQLite 读取）
curl -H "Authorization: Bearer <token>" http://localhost:8080/api/debate/{id}
systemctl start redis
```

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| Redis OOM | 旧缓存被 LRU 淘汰 | 所有数据有 SQLite 兜底，无业务影响 |
| Redis 进程 crash | 缓存不可用 | `debate.service` 有 `Wants=redis.service`，systemd 自动重启 Redis；app 层降级到 SQLite |
| 内存不足（ECS 规格过低） | 无法分配 256MB | 可调低 `maxmemory` 到 128mb 或 64mb |

## 环境变量

无需新增。已有：

```
REDIS_URL=redis://localhost:6379/0
```

已在 `deploy/setup.sh` 写入 `/etc/default/debate-env`，`debate.service` 通过 `EnvironmentFile` 加载。
