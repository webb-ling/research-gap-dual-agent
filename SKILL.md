---
name: research-model-writing-pipeline
description: 将公开数据实证研究的文献检索与研究空白识别、回归模型建立与检验、模型建立部分写作连接为可追溯的三环节工作流。适用于需要从选题推进到论文方法写作的任务；只执行使用者当前要求的环节。
---

# 实证研究模型与写作三环节 Skill

本 Skill 是总入口。保留使用者的研究选择和已完成成果；按照请求执行一个环节或依次运行三个环节，不擅自把候选研究空白当作已经证明的创新点，也不把概念模型当作已经估计的结果。

## 路由与交接

1. **识别研究空白**：阅读 [research-gap-dual-agent](skills/research-gap-dual-agent/SKILL.md)。输入研究方向和约束；交接经过来源核验的候选空白、最接近文献、数据线索及未确认事项。
2. **建立并检验模型**：阅读 [empirical-model-dual-agent](skills/empirical-model-dual-agent/SKILL.md)。输入研究问题、候选空白、原始数据文档和使用者的初步模型；交接修订模型、变量定义、分析样本、估计目标、识别与解释限制、待数据检查项。
3. **写作模型建立部分**：阅读 [model-section-writing-review](skills/model-section-writing-review/SKILL.md)。输入已确认的模型和使用者初稿；交接修订文字、读者与编辑意见及尚需证据的表述。

若从中途开始，先检查前一环节的必要输入；缺失时列出具体缺口，可继续处理不依赖该缺口的部分。每次交接标明哪些事实来自论文或官方数据文档，哪些是建模选择，哪些仍是待验证设想。

## 工具与诚实记录

仓库的 [mcp.json](mcp.json) 可启动只读的 `research-workflow-tools` 服务，供第一、二环节使用。实际运行时先确认工具是否连接，再选择所需工具；若未连接，用当前可用的网页、文件或统计工具，并在交付中记录。MCP 的书目元数据、CSV 计数和模型字段检查只提供辅助证据，不能代替原文核验、统计估计或研究者决策。

插件发现的总 Skill 位于 [skills/research-model-writing-pipeline/SKILL.md](skills/research-model-writing-pipeline/SKILL.md)；本文件是仓库根目录的同内容入口。
