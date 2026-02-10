# v1.3 Agent + Skill 运维框架

基于 **Agent + Skill** 的 Python 项目，集成 **MCP（Model Context Protocol）+ RAG 知识库**，通过**命令行**与 **Web API** 进行运维管理，支持 **Docker** 与 **exe** 封装，可在 **Windows** 与 **Linux** 下运行。

## 特性

- **AI Agent**：大模型对话、多轮工具调用、流式输出
- **MCP 工具**：Chroma、知识库检索、Git、SSH、Shell、MySQL、SQLite 等，按需加载
- **RAG 知识库**：基于 Chroma 的运维文档检索，支持自动/按需注入上下文
- **命令行**：`chat.py` 交互式或单次提问
- **Web API**：FastAPI 提供 `/health`、`POST /api/chat`（流式/非流式）
- **跨平台**：Windows / Linux，Docker 与 PyInstaller 打包

## 快速开始

### 环境

- Python 3.11+
- 可选：Chroma 服务（RAG）、MySQL（mysql MCP）、GitLab + git.yaml（git MCP）

### 安装依赖

```bash
cd v1.3
pip install -r requirements.txt
```

### 配置

1. 复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`（或其它 AI 提供商密钥）。
2. 按需修改 `config.yaml`（默认 AI provider、MCP 路径、知识库、认证等）；**多模型配置**在 `ai.yaml`（可对接多个大模型，便于扩展多个 aiagent 实例）。
3. **Git MCP**：在项目根目录配置 `git.yaml`（GitLab 地址与仓库 project_id 等）；**token 放在 `.env`**（如 `GIT_TOKEN_LUBANLOU`），勿写入 git.yaml。
4. **SSH MCP**：通过对话中的 `ssh_add_host` 添加主机，或后续扩展为配置文件。

### 命令行运行

```bash
# 交互式对话
python chat.py

# 单次提问
python chat.py -p "如何检查服务状态"

# 静默模式（仅输出回答）
python chat.py -p "简述运维流程" -q

# 禁用打字机效果 / 禁用预处理
python chat.py --no-typewriter --no-preprocess
```

### Web API 运行

```bash
python app.py
# 或
uvicorn app:app --host 0.0.0.0 --port 8000
```

- **健康检查**：`GET /health`
- **对话**：`POST /api/chat`，Body：`{"prompt": "你的问题", "stream": true, "preprocess": true}`

## MCP 服务说明

| 服务 | 说明 | 依赖/配置 |
|------|------|-----------|
| **chroma** | Chroma 集合的 ping、创建、列表、添加、查询 | Chroma 服务地址（config.yaml / 环境变量） |
| **knowledge** | RAG 知识库检索 `knowledge_retrieve`，优先查文档再执行操作 | Chroma + config 中 `knowledge_base` |
| **git** | GitLab issues、commits、项目、分支、搜索 | `git.yaml`（结构）+ `.env`（token，如 GIT_TOKEN_*） |
| **ssh** | 远程主机列表、添加/移除、执行命令、系统信息与指标 | `module/ssh_manager` + paramiko，运行时添加主机 |
| **shell** | 本地命令/脚本执行，危险命令过滤，`rm` 需确认 | 无 |
| **mysql** | 连接、查询、执行、库表列表、服务器信息 | mysql-connector-python，运行时 `mysql_connect` |
| **sqlite** | 按文件路径查询/执行、表列表、表结构 | 无（标准库 sqlite3） |

未配置或未使用的 MCP 不影响启动；Agent 只会调用已加载且配置正确的工具。

## 配置文件说明

| 文件 | 作用 |
|------|------|
| **config.yaml** | 主配置：默认 AI provider（`ai.provider`）、MCP 路径、知识库、认证等；通过 `ai.config_file` 引用 ai.yaml。 |
| **ai.yaml** | 多模型定义：`providers` 下列出可对接的大模型（base_url、model、api_key 等），`default` 为默认 provider。 |
| **git.yaml** | GitLab 仓库列表与 project_id；各仓库 token 放在 `.env`（如 `GIT_TOKEN_LUBANLOU`）。 |

切换 AI 模型：在 **config.yaml** 中修改 `ai.provider` 为 ai.yaml 里某 provider 的键名（如 `siliconflow`）；新增模型则在 **ai.yaml** 的 `providers` 下添加一项并设置对应环境变量。

## 打包

### Docker

```bash
# Windows
build_docker.bat

# Linux/Mac
chmod +x build_docker.sh && ./build_docker.sh
```

运行容器（传入 API 密钥或挂载配置）：

```bash
docker run -p 8000:8000 -e DEEPSEEK_API_KEY=你的密钥 fastapi-ai-cli:v1.3
# 挂载配置与数据（含 ai.yaml）
docker run -p 8000:8000 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/ai.yaml:/app/ai.yaml \
  -v $(pwd)/data:/app/data \
  -e DEEPSEEK_API_KEY=xxx \
  fastapi-ai-cli:v1.3
```

### exe（PyInstaller）

```bash
# Windows
build_exe.bat

# Linux/Mac
chmod +x build_exe.sh && ./build_exe.sh
```

产物在 `dist/chat` 与 `dist/app`。运行时需将 `config.yaml`、`ai.yaml`、`mcp/`、`module/` 与可执行文件放在同一目录；使用 Git MCP 时同目录需有 `git.yaml`。

## 目录结构

```
v1.3/
├── app.py              # FastAPI 入口
├── chat.py             # CLI 入口
├── config.yaml         # 主配置（默认 provider、MCP、知识库、认证等）
├── ai.yaml             # 多模型 AI 配置（providers 列表，供多 aiagent 实例）
├── git.yaml            # GitLab 配置（可选，git MCP 使用）
├── requirements.txt
├── .env.example        # 环境变量示例（复制为 .env 并填写）
├── module/             # 核心模块
│   ├── aiagent.py      # AI Agent + 工具调用 + RAG
│   ├── mcpserver.py    # MCP 服务管理
│   ├── config_manager.py
│   ├── auth.py
│   ├── markdown.py
│   ├── router.py
│   └── ssh_manager.py  # SSH 连接管理（ssh MCP 使用）
├── mcp/                # MCP 服务
│   ├── chroma.py       # Chroma 集合操作
│   ├── knowledge.py    # 知识库检索 (RAG)
│   ├── git.py          # GitLab API
│   ├── ssh.py          # SSH 远程执行与系统信息
│   ├── shell.py        # 本地 Shell 命令执行
│   ├── mysql.py        # MySQL 连接、查询、执行、库表
│   └── sqlite.py       # SQLite 按路径查询/执行、表结构
├── Dockerfile
├── docker-compose.yml
├── build_docker.bat / .sh
├── build_exe.bat / .sh
├── chat.spec / app.spec
├── requirements.md     # 需求说明
└── README.md
```

## 环境变量示例

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `SILICONFLOW_API_KEY` | SiliconFlow API 密钥（可选） |
| `CHROMA_BASE_URL` | Chroma 服务地址（默认 `http://127.0.0.1:8000`） |
| `GITLAB_SERVER` / `GITLAB_PORT` | GitLab 地址与端口（git MCP） |
| `GIT_TOKEN_*` | 各仓库 token（如 `GIT_TOKEN_LUBANLOU`），与 git.yaml 中 repository 键名对应 |
| `CONFIG_PATH` | 配置文件路径（默认 `config.yaml`） |
| `HOST` / `PORT` | Web 服务监听地址与端口（默认 `0.0.0.0:8000`） |

## 需求说明

详见 [requirements.md](requirements.md)。
