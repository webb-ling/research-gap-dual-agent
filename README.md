# 研究空白识别双 Agent 插件

本项目把一个可复用的 Codex Skill 和一个只读 MCP 工具服务器放在同一仓库。用户给出任意研究方向后，主 Agent 配置文献检索 Agent 与独立来源核验 Agent 的当次提示词；MCP 负责实际查询 OpenAlex、Crossref 和 DOI 元数据。主 Agent 根据核验意见安排补检，再输出有边界的候选研究空白。

这两个 Agent 是 Skill 指定的工作角色，由支持子 Agent 的宿主在运行时创建；本仓库没有训练两个独立模型。MCP 也不能自动判断论文结论是否正确，论文原文、出版商页面及官方数据文档仍需人工或 Agent 进一步核查。

## 仓库内容

| 路径 | 作用 |
| --- | --- |
| `skills/research-gap-dual-agent/SKILL.md` | 主 Agent 的任务分解、工具选择、双 Agent 协作及交付要求 |
| `skills/research-gap-dual-agent/references/agent-prompts.md` | 根据输入动态填充的两份角色提示词 |
| `server/server.py` | 本地只读 MCP 服务器：OpenAlex 检索、Crossref 检索、DOI 元数据核对 |
| `mcp.json`、`plugin.json` | 可移植插件清单及本地 MCP 启动配置 |
| `tests/` | 工具数据处理与 MCP 注册检查 |

## 本地安装

1. 克隆本仓库，准备 Python 3.11 或更新版本，并在用于启动 MCP 的同一 Python 环境执行 `python -m pip install -r requirements.txt`。
2. 将本仓库作为本地插件加入支持 Agent Plugins 的宿主；`plugin.json` 发现 `skills/`，`mcp.json` 以 stdio 启动 `server/server.py`。启动命令默认是 `python`；若宿主找不到该解释器，改成其绝对路径。
3. 若只想使用 Skill，可将 `skills/research-gap-dual-agent` 文件夹复制到 Codex 的个人 Skills 目录。此时需要自行连接学术检索 MCP，或让 Skill 使用可用的网页工具。

插件提供的三个 MCP 工具均只读：`search_openalex(query, limit)`、`search_crossref(query, limit)`、`lookup_crossref_doi(doi, expected_title)`。OpenAlex 匿名请求可用于少量测试；较多请求可自行申请密钥，并以环境变量 `OPENALEX_API_KEY` 传给 MCP 进程。Crossref 可选用 `CROSSREF_MAILTO` 环境变量。不要把密钥写入仓库。

## 使用示例

```text
$research-gap-dual-agent
研究方向：城市绿地与居民健康的关系。
研究类型：使用公开数据的实证研究，不做问卷。
请找最接近的文献，核实来源，并提出 1—2 个可检验的候选研究空白。
```

输出须列明当次实际调用的工具和检索日期。OpenAlex 与 Crossref 提供的是书目元数据；候选空白需要继续查重，不能把“本轮未见”写成“从未有人研究”。

## 验证

安装依赖后，在仓库根目录运行 `python -m unittest discover -s tests`。仓库包含 5 项测试，覆盖结果整理、DOI 核对和 MCP 工具注册。2026 年 10 月 21 日，本地测试全部通过，Crossref 的 DOI 查询和书目检索也经实际 API 请求验证。当前执行环境访问 OpenAlex 时发生 TLS 连接超时，因此 OpenAlex 工具通过模拟响应测试，尚未完成在线联调；使用前应在自己的网络环境运行一次实际检索。

## 数据来源与许可

- [OpenAlex API 文档](https://help.openalex.org/api/)：研究作品搜索与元数据。
- [Crossref REST API 文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)：作品检索与 DOI 注册元数据。
- 本项目代码采用 [MIT License](LICENSE)。

