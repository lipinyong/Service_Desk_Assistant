# 项目需求说明（v1.3）

## 项目定位

基于 **Agent + Skill** 的 Python 框架，通过 **MCP（Model Context Protocol）+ RAG 知识库** 实现运维管理能力，以**命令行**为主要交互方式，支持 **Docker** 与 **exe** 封装，可在 **Windows** 与 **Linux** 下运行。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **Agent** | 大模型驱动的智能体，支持多轮对话、工具调用与迭代推理 |
| **Skill** | 可插拔技能模块（如认证、Markdown、AI Agent 等），通过配置启用 |
| **MCP** | 集成 MCP 服务（如 Chroma、Git、SSH、知识库等），为 Agent 提供工具 |
| **RAG 知识库** | 基于 Chroma 的运维文档检索，支持自动/按需注入上下文 |
| **命令行运维** | CLI 交互（如 `chat.py`）进行问答、周报、文档检索等运维操作 |
| **Web API** | FastAPI 服务（如 `app.py`）提供 HTTP 接口，可选认证 |

---

## 运行与交付

- **运行方式**：本地 Python 运行、Docker 容器、exe 可执行文件
- **平台**：Windows、Linux（Mac 可沿用 Linux 脚本）
- **封装**：
  - **Docker**：`Dockerfile` + `docker-compose.yml`，支持健康检查与挂载配置
  - **exe**：PyInstaller（`chat.spec` / `app.spec`），需与 `config.yaml`、`mcp/`、`module/` 等同目录

---

## 技术栈与依赖

- **语言**：Python 3.11+
- **AI**：OpenAI 兼容 API（如 DeepSeek、SiliconFlow），AsyncOpenAI
- **配置**：YAML（`config.yaml`），支持环境变量占位符 `${VAR}`
- **MCP**：自管 MCP 服务目录（`mcp/`），动态发现与加载
- **RAG**：Chroma HTTP API，知识库集合可配置（如 `ops_docs`）

---

## 非功能需求

- **跨平台**：同一套代码与配置在 Windows/Linux 下均可运行
- **可配置**：AI 提供商、MCP 路径、知识库、认证等均通过配置与环境变量控制
- **可扩展**：通过新增 MCP 工具与 Skill 模块扩展能力，无需改核心逻辑

---

## 与 v1.2 的延续关系

v1.3 在架构上延续 v1.2 的：

- Agent（`module/aiagent.py`）+ MCP 管理（`module/mcpserver.py`）
- 命令行入口 `chat.py`、Web 入口 `app.py`
- 配置结构（`config.yaml`：ai、mcp、chroma、knowledge_base 等）
- 打包与运行方式（Docker、exe、BUILD.md 说明）

后续可在 v1.3 中迭代需求（如新 Skill、新 MCP 工具、RAG 策略优化等）并在此文档中补充。
