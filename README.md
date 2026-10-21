# 实证研究模型建立与写作三环节 Skill

这是课程报告配套的开源仓库。仓库名沿用最初的第一环节项目名，现已扩展为一个总 Skill 和三个环节 Skill：文献检索与研究空白识别、回归模型建立与独立核验、模型建立部分写作与审阅。总 Skill 负责交接上一环节的证据与未确认事项；用户也可单独调用任一环节。

## 结构

| 路径 | 作用 |
| --- | --- |
| `skills/research-model-writing-pipeline/` | 总 Skill：三环节路由、输入输出交接及证据边界 |
| `skills/research-gap-dual-agent/` | 环节 1：文献检索 Agent 与独立来源核验 Agent |
| `skills/empirical-model-dual-agent/` | 环节 2：建模 Agent 与独立模型检验 Agent；含动态提示词与工具输入说明 |
| `skills/model-section-writing-review/` | 环节 3：写作、读者和编辑三种审阅角色 |
| `server/server.py` | 本地只读 MCP 服务器；提供书目检索、DOI 核对和模型准备检查 |
| `plugin.json`、`mcp.json` | 插件元数据及 stdio MCP 启动配置 |
| `tests/` | MCP 工具和数据整理的单元测试 |

两名或三名 Agent 是各 Skill 定义的运行时工作角色；本仓库没有训练或部署多个独立模型。是否并行创建子 Agent 取决于宿主环境；不支持时可按独立角色顺序运行。

## MCP 工具

| 环节 | 工具 | 用途与边界 |
| --- | --- | --- |
| 1 | `search_openalex`、`search_crossref`、`lookup_crossref_doi` | 检索书目元数据与核对 DOI；仍需查论文原文和出版商页面才能确认研究内容。 |
| 2 | `check_model_plan` | 检查结构化模型方案是否缺字段或有显见矛盾；不能证明统计模型正确。 |
| 2 | `profile_csv_variables`、`count_group_cells` | 仅在用户提供本地 CSV 时检查缺失、低类别变量和分组计数；不运行回归，也不返回个人记录。 |

六项工具均为只读。环节 2 的 CSV 计数是未加权描述统计，不能代替调查设计、正式模型估计或研究者对数据的解释。没有微观数据时，Skill 输出拟议模型和待核查清单，不会编造样本量、系数或显著性。

## 本地安装

1. 克隆仓库，准备 Python 3.11 或更新版本，在启动 MCP 的同一 Python 环境执行 `python -m pip install -r requirements.txt`。
2. 将仓库作为本地插件加入支持 Agent Plugins 的宿主。`plugin.json` 发现 `skills/`，`mcp.json` 使用 `python` 通过 stdio 启动 `server/server.py`。若宿主找不到该解释器，请把启动命令改为安装依赖的 Python 绝对路径。
3. 也可将所需 Skill 的文件夹复制到 Codex 的个人 Skills 目录单独使用。此时应另行连接 MCP，或使用当前环境可用的网页与文件工具；实际交付须记录使用了哪些工具。

OpenAlex 可以配置环境变量 `OPENALEX_API_KEY`，Crossref 可以配置 `CROSSREF_MAILTO`。不要将密钥写入仓库。

## 使用示例

```text
$research-model-writing-pipeline
我想用公开数据研究城市绿地与居民健康。请先寻找候选研究空白，再检查我提出的回归模型；第三环节等我写出方法初稿后再运行。
```

也可单独调用 `$research-gap-dual-agent`、`$empirical-model-dual-agent` 或 `$model-section-writing-review`。每环节都应保存原始输入、修改依据、实际使用工具和未解决的问题。

## 验证与资料来源

安装依赖后可运行 `python -m unittest discover -s tests`。测试覆盖书目元数据整理、DOI 核对、CSV 检查、模型方案字段检查与 MCP 工具注册。Crossref 检索和 DOI 查询曾完成真实 API 请求；OpenAlex 在当前执行环境出现 TLS 连接超时，因此其在线请求仍需在可访问的网络环境复核。

- [OpenAlex API 文档](https://help.openalex.org/api/)
- [Crossref REST API 文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- 本项目代码采用 [MIT License](LICENSE)。

