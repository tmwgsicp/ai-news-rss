# Docker 环境变量配置说明

本项目已针对 Docker 环境优化了环境变量读取逻辑，避免了常见的 Docker 无法读取 `.env` 文件的问题。

## 问题背景

在之前的 wechat 开源版中，Docker 容器无法正确读取 `.env` 文件中的环境变量，导致配置失效。

## 解决方案

### 1. 配置文件优化

`backend/core/config.py` 中的环境变量读取逻辑：

```python
# 仅在 .env 文件存在时加载（本地开发）
env_file = self.base_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)

# 优先使用环境变量（Docker 传入的）
self.glm_api_key = os.getenv("GLM_API_KEY", "")
```

**工作原理**：
- **本地开发**：从 `.env` 文件加载环境变量
- **Docker 容器**：直接使用 Docker 传入的环境变量（不依赖文件）

### 2. docker-compose.yml 配置

```yaml
services:
  app:
    environment:
      # 从宿主机的 .env 文件读取，传入容器
      - GLM_API_KEY=${GLM_API_KEY}
      - MINIMAX_API_KEY=${MINIMAX_API_KEY:-}
```

**工作原理**：
- Docker Compose 自动读取项目根目录的 `.env` 文件
- 通过 `${VAR}` 语法将环境变量传入容器
- 容器内的应用通过 `os.getenv()` 直接读取

### 3. 数据持久化改进

```yaml
volumes:
  # 挂载整个 data 目录，而不是单独挂载文件
  - ./data:/app/data
```

**优势**：
- 数据库、音频、运行时配置统一管理
- 避免单文件挂载的权限问题
- 更符合 Docker 最佳实践

## 使用方法

### 方式 1: docker-compose（推荐）

```bash
# 1. 配置 .env
cp .env.example .env
vim .env  # 填入 GLM_API_KEY

# 2. 启动（自动读取 .env）
docker-compose up -d
```

### 方式 2: docker run + env-file

```bash
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ai-news-rss:latest
```

### 方式 3: docker run + 手动传入

```bash
docker run -d \
  -p 8000:8000 \
  -e GLM_API_KEY="xxx" \
  -e MINIMAX_API_KEY="yyy" \
  -v $(pwd)/data:/app/data \
  ai-news-rss:latest
```

## 验证环境变量

### 检查容器内的环境变量

```bash
# 进入容器
docker exec -it ai-news-rss bash

# 查看环境变量
echo $GLM_API_KEY
env | grep GLM

# 测试 Python 读取
python3 -c "import os; print('GLM_API_KEY:', os.getenv('GLM_API_KEY'))"
```

### 检查应用日志

```bash
docker logs ai-news-rss 2>&1 | grep -i "api key"
docker logs ai-news-rss 2>&1 | grep -i "配置"
```

正常情况应该看到：
```
当前配置:
   - GLM API Key: 已配置
```

## 常见问题

### Q1: 环境变量未生效

**现象**：日志显示 `GLM API Key: 未配置`

**排查步骤**：
```bash
# 1. 检查 .env 文件是否存在
ls -la .env

# 2. 检查 .env 内容
cat .env | grep GLM_API_KEY

# 3. 检查 docker-compose 是否读取
docker-compose config | grep GLM_API_KEY

# 4. 检查容器内环境变量
docker exec ai-news-rss env | grep GLM_API_KEY
```

**解决方法**：
- 确保 `.env` 文件在 `docker-compose.yml` 同目录
- 确保 `.env` 格式正确（无空格、无引号）
- 重启容器：`docker-compose restart`

### Q2: 数据库无法写入

**现象**：容器日志显示 `Permission denied: news.db`

**原因**：使用了单文件挂载，容器内权限不足

**解决方法**：
```yaml
# 错误写法
volumes:
  - ./news.db:/app/news.db  # 不推荐

# 正确写法
volumes:
  - ./data:/app/data  # 推荐
```

### Q3: .env 文件格式错误

**正确格式**：
```bash
# 正确
GLM_API_KEY=your_api_key_here
MINIMAX_API_KEY=your_minimax_key

# 错误（不要加引号）
GLM_API_KEY="your_api_key_here"

# 错误（不要加空格）
GLM_API_KEY = your_api_key_here

# 错误（不要用 export）
export GLM_API_KEY=your_api_key_here
```

## 与 wechat 开源版的区别

| 项目 | wechat 开源版（旧） | ai-news-rss（新） |
|------|---------------------|-------------------|
| 环境变量读取 | 强依赖 .env 文件 | 优先使用 Docker 环境变量 |
| 数据持久化 | 单文件挂载 | 目录挂载 |
| 配置验证 | 无 | 启动时自动验证 |
| 健康检查 | 无 | 内置 healthcheck |

## 总结

本项目通过以下优化避免了 Docker 环境变量问题：

1. **双重读取机制**：本地开发用 `.env` 文件，Docker 用环境变量
2. **docker-compose 自动传递**：无需手动配置，自动读取 `.env`
3. **目录挂载替代文件挂载**：避免权限问题
4. **启动验证**：自动检查必需配置
5. **详细日志**：配置状态一目了然

**推荐做法**：使用 `docker-compose up -d`，最简单可靠！
