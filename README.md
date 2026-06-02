<div align="center">

# AI News RSS

### 开源 AI 新闻聚合系统

**完全开源 | 免费使用 | AI 智能评分 | 每日精选日报 | RSS 订阅**

[![GitHub stars](https://img.shields.io/github/stars/tmwgsicp/ai-news-rss?style=for-the-badge&logo=github)](https://github.com/tmwgsicp/ai-news-rss/stargazers)
[![License](https://img.shields.io/badge/License-AGPL%203.0-blue?style=for-the-badge)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/tmwgsicp/ai-news-rss?style=for-the-badge&logo=docker&logoColor=white)](https://hub.docker.com/r/tmwgsicp/ai-news-rss)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

> **100% 开源，100% 免费。** 代码完全公开，私有化部署无任何限制，不搞"开源"之名行收费之实。

</div>

---

## 功能特性

- **AI 智能分析** — 使用智谱 GLM 模型自动评分，过滤低质量内容
- **多源聚合** — 支持 arXiv、GitHub、HackerNews、Reddit、RSS 等多个信息源
- **智能分类** — 自动分类到五大主题（每日速览、工具雷达、行业脉搏、深度阅读、社区声音）
- **智能去重** — 基于 URL、标题、语义相似度的三重去重机制
- **语音播报** — 支持 MiniMax TTS，生成专业播报音频（可选）
- **RSS 订阅** — 标准 RSS 2.0 格式输出

---

## Docker 部署（推荐）

**最快速的部署方式**，无需配置 Python 环境，一键启动：

```bash
# 方式一：使用 docker-compose（推荐）
git clone https://github.com/tmwgsicp/ai-news-rss.git
cd ai-news-rss
cp .env.example .env
# 编辑 .env，至少填入 GLM_API_KEY
docker-compose up -d

# 方式二：直接运行
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --name ai-news-rss \
  ghcr.io/tmwgsicp/ai-news-rss:latest
```

服务启动后访问 `http://localhost:8000` 即可使用。

**重要说明**：
- Docker Compose 会自动从 `.env` 文件读取环境变量
- 数据持久化到 `./data` 目录（数据库和音频文件）
- 首次启动需要几分钟初始化和抓取数据

---

## 配置说明

### 必需配置

| 配置项 | 说明 | 获取地址 |
|--------|------|----------|
| `GLM_API_KEY` | 智谱 AI API 密钥（用于内容分析） | https://open.bigmodel.cn/ |

### 可选配置

| 配置项 | 说明 | 获取地址 |
|--------|------|----------|
| `MINIMAX_API_KEY` | MiniMax API 密钥（用于语音播报） | https://platform.minimaxi.com/ |

---

## 功能说明

| 页面/接口 | 说明 |
|-----------|------|
| `/` | 今日日报 — 查看当日 AI 资讯精选，支持音频播放 |
| `/rss.html` | RSS 订阅 — 订阅说明和 RSS 源地址 |
| `/api/news/latest` | API — 获取最新新闻 |
| `/api/daily/latest` | API — 获取最新日报 |
| `/api/rss/feed.xml` | RSS 订阅源 |

---

## 自定义配置

编辑 `backend/config/sources.json` 调整：
- 新闻源配置
- 抓取时间窗口（默认 24 小时）
- AI 评分阈值（默认 7.0）

---

## 项目结构

```
ai-news-rss/
├── backend/           # 后端代码
│   ├── core/         # 核心功能（爬虫、AI、聚合）
│   ├── models/       # 数据模型
│   ├── routes/       # API 路由
│   └── config/       # 配置文件
├── static/           # 前端页面
├── app.py            # 应用入口
└── requirements.txt  # Python 依赖
```

---

## 常见问题

<details>
<summary><b>启动后没有数据？</b></summary>

首次运行需要几分钟抓取数据，可查看日志：`docker logs -f ai-news-rss`
</details>

<details>
<summary><b>RSS 订阅没有内容？</b></summary>

RSS 源更新频率较低，24 小时内可能没有新内容，这是正常现象
</details>

<details>
<summary><b>音频生成失败？</b></summary>

需要配置 `MINIMAX_API_KEY`。如不需要语音功能，可忽略此错误
</details>

<details>
<summary><b>AI 评分太严格？</b></summary>

在 `backend/config/sources.json` 中降低 `base_threshold` 值（默认 7.0，可调整为 6.5）
</details>

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **Web 框架** | FastAPI |
| **ASGI 服务器** | Uvicorn |
| **数据库** | SQLite |
| **AI 模型** | 智谱 GLM |
| **语音合成** | MiniMax TTS |
| **运行环境** | Python 3.10+ |

---

## 开源协议

本项目采用 **AGPL 3.0** 协议开源，**所有功能代码完整公开，私有化部署完全免费**。

| 使用场景 | 是否允许 |
|---------|---------|
| 个人学习和研究 | 允许，免费使用 |
| 企业内部使用 | 允许，免费使用 |
| 私有化部署 | 允许，免费使用 |
| 修改后对外提供网络服务 | 需开源修改后的代码 |

详见 [LICENSE](LICENSE) 文件。

### 免责声明

- 本软件按"原样"提供，不提供任何形式的担保
- 本项目仅供学习和研究目的
- 使用者对自己的操作承担全部责任
- 因使用本软件导致的任何损失，开发者不承担责任

---

## 参与贡献

由于个人精力有限，目前**暂不接受 PR**，但非常欢迎：

- **提交 Issue** — 报告 Bug、提出功能建议
- **Fork 项目** — 自由修改和定制
- **Star 支持** — 给项目点 Star，让更多人看到

---

## 联系方式

<table>
  <tr>
    <td align="center">
      <img src="assets/qrcode/wechat.jpg" width="200"><br>
      <b>个人微信</b><br>
      <em>技术交流 / 商务合作</em>
    </td>
    <td align="center">
      <img src="assets/qrcode/sponsor.jpg" width="200"><br>
      <b>赞赏支持</b><br>
      <em>开源不易，感谢支持</em>
    </td>
  </tr>
</table>

- **GitHub Issues**: [提交问题](https://github.com/tmwgsicp/ai-news-rss/issues)
- **邮箱**: creator@waytomaster.com

---

## 致谢

- [FastAPI](https://fastapi.tiangolo.com/) — 高性能 Python Web 框架
- [智谱 AI](https://open.bigmodel.cn/) — GLM 大语言模型
- [MiniMax](https://platform.minimaxi.com/) — 语音合成服务

---

<div align="center">

**如果觉得项目有用，请给个 Star 支持一下！**

[![Star History Chart](https://api.star-history.com/svg?repos=tmwgsicp/ai-news-rss&type=Date)](https://star-history.com/#tmwgsicp/ai-news-rss&Date)

Made with love by [tmwgsicp](https://github.com/tmwgsicp)

</div>
