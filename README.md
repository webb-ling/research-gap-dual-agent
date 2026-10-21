# 研究空白识别双 Agent Skill

这是一个可复用的 Codex Skill。输入任意学术研究方向后，主 Agent 会按本次题目和当前可用工具配置两个角色：文献检索 Agent 找相关研究，来源核验 Agent 独立检查论文和数据资料，最后由主 Agent 给出有证据边界的候选研究空白。

Skill 是工作流程说明，不是训练好的模型，也不会自动安装数据库或 MCP。它会优先使用当前环境已连接的学术检索工具和原始来源；没有专用 MCP 时，可使用可用的网页检索工具、DOI 页面、出版商页面和官方数据网站。实际使用的工具会写进本次结果。

## 安装

把本仓库整个文件夹放入 Codex 的个人 Skill 目录（通常为 `~/.codex/skills/research-gap-dual-agent`），然后重新打开会话。保留 `SKILL.md`、`agents/` 和 `references/` 的相对路径。

## 使用示例

```text
$research-gap-dual-agent
研究方向：城市绿地与居民健康的关系。
研究类型：使用公开数据的实证研究，不做问卷。
请找最接近的文献，核实数据来源，提出 1—2 个可检验的候选研究空白。
```

可按需要补充国家、时间范围、学科、方法、数据限制；无需预先编辑 Skill 中的提示词。检索结果是针对当次查询的候选结论，不能替代系统综述。

## 文件

- `SKILL.md`：主 Agent 的配置、分工、核验和交付规则。
- `references/agent-prompts.md`：两个子 Agent 的运行时提示词模板与回合控制。
- `agents/openai.yaml`：Codex 中显示的名称与说明。

## 许可

MIT License，见 `LICENSE`。
