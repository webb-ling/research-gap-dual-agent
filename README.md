# Research Model Writing Pipeline

**实证研究模型建立与论文写作：一个总 Skill、三个环节 Skill、一组只读 MCP 工具。**

从[总 Skill](SKILL.md)开始，也可分别使用[环节 1：研究空白识别](skills/research-gap-dual-agent/SKILL.md)、[环节 2：模型建立与核验](skills/empirical-model-dual-agent/SKILL.md)、[环节 3：模型部分写作与审阅](skills/model-section-writing-review/SKILL.md)。插件发现的总 Skill 位于 `skills/research-model-writing-pipeline/`；根目录 `SKILL.md` 是仓库阅读入口。三个环节的角色是运行时任务分工，并非分别训练的模型。宿主不支持子 Agent 时可依次运行并保留独立记录。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `SKILL.md`、`skills/research-model-writing-pipeline/` | 三环节路由与交接 |
| `skills/research-gap-dual-agent/` | 检索 Agent、来源核验 Agent、研究空白交接记录 |
| `skills/empirical-model-dual-agent/` | 建模 Agent、模型检验 Agent、结构化方案输入 |
| `skills/model-section-writing-review/` | 写作、读者、编辑三种审阅角色 |
| `server/core.py`、`server/server.py` | 纯逻辑与 stdio MCP 包装 |
| `plugin.json`、`mcp.json` | 插件元数据和 MCP 启动配置 |
| `tests/`、`.github/workflows/tests.yml` | 单元、权限边界和 MCP stdio 测试及 CI |

## MCP 的八项只读工具

| 工具 | 功能 | 主要边界 |
| --- | --- | --- |
| `search_openalex`、`search_crossref` | 分页查询书目元数据 | 单次仅返回指定页，按需调整检索式与翻页 |
| `search_literature` | 查询上述两库并对本次返回的结果按 DOI、题名与年份谨慎去重 | 不跨不同调用自动累计或证明检索穷尽；歧义记录保留待核验 |
| `lookup_crossref_doi` | 核对 DOI 书目元数据，可对比预期题名 | 不验证论文方法与结论；题名相似度只是提醒 |
| `check_gap_evidence` | 检查研究空白交接记录的必要字段 | 不核实链接或创新性 |
| `check_model_plan` | 检查方案字段、变量类型与少量显见矛盾 | 不运行回归，也不证明模型有效 |
| `profile_csv_variables`、`count_group_cells` | 对授权 CSV 的选定列做缺失和分组计数 | 未加权，不返回个体记录；稀疏类别/单元格抑制 |

检索工具返回查询日期、页码、数据库命中数及是否可能有下一页。`search_literature.status=both_sources_succeeded` 只表示两次接口请求成功，`coverage_status=requested_page_only` 表示本次只覆盖指定页，并不表示检索完成。数据库命中数不是已筛读数；检索 Agent 应记录自己实际筛读的数量，跨查询与跨页再去重。若同题同年有多个不同 DOI，无 DOI 记录会保留并标记歧义，不自动并入第一篇。作者列表不截断；Crossref 缺少发表年份时返回空值并提示核验，不用元数据创建年份冒充发表年份。两库书目必须再与出版商页面或论文原文对照。参见[环节 1 交接结构](skills/research-gap-dual-agent/references/gap-evidence-schema.md)。

`check_model_plan` 对常见简单公式核对变量和交互项；复杂公式、别名和复杂抽样下替代标准误方法返回 `requires_manual_review`，明确的缺项返回 `needs_revision`。`ready_for_data_validation` 仅表示静态方案可继续核查，且始终标注 `data_validation_status=not_run`、`statistical_validity_status=not_assessed`。真正的回归估计、调查加权方差、模型诊断和独立结果复核需要数据及另外的统计软件，本仓库 MCP 尚未实现这些步骤。没有数据时只交付拟议模型，不编造样本量、系数或显著性。参见[环节 2 方案结构](skills/empirical-model-dual-agent/references/model-plan-schema.md)。

## 安装与数据授权

1. 准备 Python 3.11 或更新版本，在用于启动 MCP 的同一环境运行 `python -m pip install -r requirements.txt`。
2. 将仓库作为本地插件加入支持 Agent Plugins 的宿主。`plugin.json` 发现 `skills/`；`mcp.json` 通过 stdio 运行 `server/server.py`。若 `python` 不是已安装依赖的解释器，改用其绝对路径。
3. 可单独复制 Skill 文件夹到 Codex 个人 Skills 目录，但此时须另行连接 MCP 或使用实际可用的网页/文件工具，并如实报告工具使用情况。

需要 CSV 工具时，由使用者在启动 MCP **之前**设置 `RESEARCH_DATA_DIR` 为明确授权的数据目录；工具拒绝目录外文件和经符号链接跳出目录的路径。可设置 `RESEARCH_MIN_CELL_COUNT`（默认 5，范围 2—100）控制低频结果抑制。调用时只指定必要列，并依代码本传入逐列缺失码。输出的计数只用于建模前诊断；不要把它当作正式统计结果。未经授权目录配置，CSV 工具直接拒绝访问。

可选环境变量：`OPENALEX_API_KEY`、`CROSSREF_MAILTO`。不要将密钥或受限制微观数据提交到仓库。

## 使用与验证

```text
$research-model-writing-pipeline
我想用公开数据研究城市绿地与居民健康。请先找候选研究空白，
再检查我的回归初稿；论文模型部分等我写出初稿后再运行。
```

每环节保留原始输入、具体修改依据、实际工具、无法确认的事项与下一环节交接。运行测试：

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

测试包含书目整理、分页参数、去重、DOI 题名提示、CSV 目录限制与稀疏计数、方案检查，以及通过 `mcp.json` 启动并调用 stdio MCP 的集成用例。在线检索 API 是否可达取决于运行环境；本地单元测试用模拟响应，不证明网络检索在每个环境都成功。

API 依据：[OpenAlex 分页](https://help.openalex.org/api/paging/)、[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)。代码采用 [MIT License](LICENSE)。

