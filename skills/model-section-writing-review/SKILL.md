---
name: model-section-writing-review
description: 将用户确定的模型草稿组织为 model setup 章节，通过素材检查、最小补充请求、分段写作和独立审核循环完成文稿。用于模型部分的撰写或修订；不代替作者决定模型，不默认展开数据处理或实际结果。
---

# 模型章节写作与审核

输入为用户确认的模型建立草稿，输出为完整、准确、简洁的 model setup 正文。原稿可以是公式和说明，无须已有论文措辞。保留作者的模型选择及解释边界。

## 共同约定

- 按[工作安排](references/agent-work-plan.md)划分 A、W、R 及写作子角色。宿主调度流程，不新增模型决策权。
- 运行中维护素材文档和结果文档；原稿及用户原始回复保留，内部机器状态可以单独持久化。
- 素材缺失、含糊或冲突回 A；素材充分但文稿表达有问题回 W；R 复核修改后才判定通过。
- 具体数据处理和实际结果暂不展开。必要的模型定义、范围、取值、参照组、尺度和数学变换仍需表达。
- 公式唯一确定的数学含义可据此解释。实质性设定、作者动机或解释范围不能靠写作补出。
- Markdown 文件中的数学使用美元分隔符。面向用户的聊天沿用用户指定的公式显示方式。

## 根据当前任务加载角色资料

每个角色均阅读本入口及[工作安排](references/agent-work-plan.md)，再加载下表对应的角色说明与规范。完整规范保留在引用文件中；不用把所有角色说明一起加载。

| 角色 | 角色说明 | 需要加载的规范 |
| --- | --- | --- |
| A 素材检查 | [material-checker](references/roles/material-checker.md) | [信息检查表](references/information-checklist.md)、[素材请求格式](references/material-request-format.md) |
| W1 段落规划 | [paragraph-planner](references/roles/paragraph-planner.md) | 信息检查表、[文稿框架](references/writing-framework.md) |
| W2 要素写作 | [section-writer](references/roles/section-writer.md) | 信息检查表、文稿框架 |
| W3 全文衔接 | [coherence-editor](references/roles/coherence-editor.md) | 信息检查表、文稿框架 |
| W 修订负责人 | [lead-writer](references/roles/lead-writer.md) | 信息检查表、文稿框架、[审核标准](references/review-criteria.md) |
| R 独立审核 | [reviewer](references/roles/reviewer.md) | 信息检查表、文稿框架、审核标准 |

SDK 的机器路由在 [agents/roles.json](agents/roles.json)。当前角色、当前素材及稿件版本必须随每次调用传入；不能用会话中的旧版本替代。

普通 Skill 调用时，以自然语言展示检查、素材请求和最终文稿，不要求用户处理内部 JSON。由 SDK 调度角色时，才按 Python 随本轮任务提供的 JSON 输出合约返回；具体字段由 scripts/workflow.py 中的当前阶段定义，不能仅凭角色说明猜测字段。

## 调度流程

1. A 按信息检查表检查完整素材。按需询问用户并等待真实回答，必需信息齐备后再交写作。
2. W1 建立信息与段落对应，W2 按分配任务撰写，W3 整合衔接。简单模型允许由写作负责人兼任子任务。
3. R 独立对照当前素材审核成稿，意见包含位置、依据、影响和修改方向。
4. 写作问题由 W 修订；素材问题先回 A 核实再决定是否询问用户。每次修改后回 R 复核。
5. 仅在当前版本无阻止通过的问题时交付正文。纯措辞偏好可以作为非阻止性建议，不以轮数耗尽冒充通过。

## 运行脚本

[scripts/workflow.py](scripts/workflow.py)实现状态机和 Codex Python SDK 适配。

- SDK 入口不依赖自动发现本 Skill。适配器直接将本入口、当前角色说明及路由规范的全文注入每次请求，作为执行规则；用户素材另作待分析数据。
- 规范缺失、路由越出 Skill 目录或规则版本改变时拒绝继续混用。每步记录所用规则摘要，方便定位本次运行采用的规范。
- Agent 以只读沙箱返回结构化结果，由 Python 校验和提交。结构校验只能保证约定字段与状态约束；内容质量仍由 R 审核。
- 查看加载关系：`python scripts/workflow.py --explain-role A`。
- 查看流程而不调用模型：`python scripts/workflow.py --describe`。
- SDK 接线、安装前提、断点恢复和已知未接入项见[运行说明](references/runtime.md)。此说明供宿主开发或运行流程时阅读，不默认注入写作角色。

当前文件既是普通 Skill 调用入口，也是 SDK 直接加载的共同规则。不要仅发送 Skill 名称就假定引用文件已进入 Agent 上下文。
