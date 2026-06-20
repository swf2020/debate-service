# ECS 自动部署方案

## Context

当前 debate-service 是本地开发的 Python FastAPI 工程，代码托管在 GitHub，需要推送到阿里云 ECS 并实现：本地 push 代码 → ECS 自动检测版本变化 → 自动重启服务。

## 推荐方案：git 轮询 + systemd 管理（最简单、零外部依赖）

不需要暴露额外端口，不需要 GitHub Actions 或 webhook 基础设施。ECS 上通过 systemd timer 每分钟 `git fetch` 检查新提交，有变化就 pull + 重启。

## 实施步骤

### 步骤 1：ECS 环境初始化

在 ECS 上安装依赖：

```bash
# Python 3.11+
sudo yum install -y python3 python3-pip git nginx

# 克隆项目
cd /opt
sudo git clone https://github.com/swf2020/debate-service.git
cd debate-service

# 创建 venv 并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 步骤 2：创建环境变量文件（不提交到 git）

```bash
sudo vim /etc/default/debate-env
```

内容：

```
DEEPSEEK_API_KEY=sk-你的真实key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
ADMIN_USERS=admin
DEBATE_DB_PATH=/opt/debate-service/debate.db
```

权限收紧：

```bash
sudo chmod 600 /etc/default/debate-env
```

### 步骤 3：创建 systemd 服务

文件 `/etc/systemd/system/debate.service`：

```ini
[Unit]
Description=Debate Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/debate-service
EnvironmentFile=/etc/default/debate-env
ExecStart=/opt/debate-service/.venv/bin/python /opt/debate-service/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 步骤 4：创建自动部署脚本

文件 `/opt/debate-service/deploy.sh`：

```bash
#!/bin/bash
cd /opt/debate-service

# Fetch latest from remote
git fetch origin

# Check if local is behind remote
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] New commits detected. Deploying..."
    git pull origin master
    source .venv/bin/activate
    pip install -r requirements.txt --quiet
    sudo systemctl restart debate.service
    echo "[$(date)] Deploy complete."
else
    echo "[$(date)] No new commits."
fi
```

### 步骤 5：创建 systemd timer（每分钟检查）

文件 `/etc/systemd/system/debate-deploy.timer`：

```ini
[Unit]
Description=Debate Service auto-deploy timer

[Timer]
OnCalendar=*-*-* *:*:00
Persistent=true

[Install]
WantedBy=timers.target
```

文件 `/etc/systemd/system/debate-deploy.service`：

```ini
[Unit]
Description=Debate Service auto-deploy check

[Service]
Type=oneshot
ExecStart=/bin/bash /opt/debate-service/deploy.sh
```

启用 timer：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now debate-deploy.timer
sudo systemctl enable --now debate.service
```

### 步骤 6：本地推送流程

```bash
# 正常开发提交
git add -A
git commit -m "feat: xxx"
git push origin master

# 最多 1 分钟后 ECS 自动拉取并重启
# 查看 ECS 状态：sudo systemctl status debate.service
# 查看部署日志：sudo journalctl -u debate-deploy.service -f
```

## 备选方案对比

| 方案 | 延迟 | 复杂度 | 额外依赖 |
|------|------|--------|----------|
| **git 轮询 + systemd timer**（推荐） | ≤1 分钟 | 低 | 无 |
| GitHub Actions SSH 部署 | 即时 | 中 | GitHub Secrets 存 SSH key |
| Webhook 服务器 | 即时 | 中 | 需暴露公网端口 |

## 可选增强

- **Nginx 反代**：如果 ECS 需要域名访问，加一个 nginx 配置反代到 `localhost:8080`
- **HTTPS**：搭配 certbot 自动续签 SSL 证书
- **健康检查**：deploy.sh 里加 `curl localhost:8080/api/debate/active` 验证服务启动成功
- **回滚**：deploy.sh 里记录上一次成功的 commit，失败时自动 `git reset --hard $LAST_GOOD`

## 验证

1. `sudo systemctl status debate.service` — 确认服务 running
2. `curl http://localhost:8080/api/debate/active` — 确认 API 响应
3. 本地 push 一个空 commit：`git commit --allow-empty -m "test deploy" && git push`
4. 等待 1 分钟后 `sudo journalctl -u debate-deploy.service --since "1 min ago"` — 确认检测到变化并重启
