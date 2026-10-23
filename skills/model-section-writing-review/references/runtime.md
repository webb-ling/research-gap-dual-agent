# Model setup Python 调度与规范加载

版本：v2

本 Skill 包含流程控制、角色规范、已有四份写作标准和离线测试。2026年10月23日已安装openai-codex 0.163.0，并从用户上传的新版Word提取素材，完成9轮真实SDK调用，首稿通过独立审核。实际角色为A、W1、5个W2、W3和R；没有补问，也未触发返修。因此本轮验证了正常通过路径，不声称已在线验证全部分支。Word解析和用户对话界面仍由宿主接入。

## 规范怎样进入角色上下文

1. scripts/workflow.py 的 SkillBundle 读取 agents/roles.json，检查入口、角色和引用文件均存在且位于本 Skill 目录内。
2. 每次调用注入 SKILL.md、工作安排、该角色说明及对应规范的完整正文，不只传路径或 Skill 名称。
3. 执行规范与待分析素材分开呈现。角色使用只读沙箱，返回 JSON；Python 校验后提交状态和文档。
4. 规则文件生成摘要，每轮记录实际加载文件及摘要。中途修改规则会停止旧后端；新建后端会读取新正文。恢复断点时也检查规则版本，不混用旧稿的通过结论。
5. 自动校验保证字段与流程约束，R 独立审核是否真正满足规范。提示词注入及摘要本身不证明模型遵从了全部要求。

角色需要什么文件，由 agents/roles.json 单一声明；角色说明与规范修改后，无须再手工复制进 Python 提示词。新增检查项或改变 JSON 字段仍需同步脚本的输出合约和验证逻辑，不能将任意接口变更视为自动兼容。

## 状态和会话

A检查素材，有缺口则等待用户；检查通过后依次由W1规划、W2分段写作、W3整合、R审核。写作问题回W修订，素材问题先回A核实，修改后再次审核当前版本。等待用户与完成状态不重复发起模型请求。

同一进程中，每个角色复用独立SDK会话，W2按段落编号区分会话。每次附上当前素材、稿件、版本和规则，旧会话不能替代当前输入。跨进程恢复使用保存的工作流状态和新的角色会话；SDK thread ID 的跨进程恢复尚未接入。本程序不控制当前桌面应用的已有聊天。

## 查看与验证

在 Skill 目录运行：

```bash
python scripts/workflow.py --describe
python scripts/workflow.py --explain-role A
python scripts/workflow.py --explain-role R
python tests/test_workflow.py
```

以上命令均不需要安装 SDK，也不发出模型推理请求。--explain-role 会显示实际路由到的文件及其摘要。

## SDK 接线示例

安装 openai-codex 并完成运行环境的Codex登录后，可以在 scripts 下创建宿主入口使用下列方式。source_text 必须是已规范化提取的用户素材文本，不是原始Word二进制。

本次实测发现两个运行环境前提：SDK宿主需要写入Codex的会话状态目录，Agent的只读沙箱并不限制宿主记录会话；系统若通过macOS本地代理联网，应将系统HTTP/HTTPS代理传给SDK子进程，否则可能直连超时。SQLite状态可用sqlite_home覆盖到任务目录。以下设置仅影响本次进程，不修改全局配置。

```python
from pathlib import Path
import json
import urllib.request
from openai_codex import Codex, CodexConfig
from workflow import CodexSDKBackend, Stage, WorkflowState, run_until_wait

skill_dir = Path(__file__).resolve().parents[1]
run_dir = Path("work/model-setup-run")
run_dir.mkdir(parents=True, exist_ok=True)
proxy_env = {k.upper() + "_PROXY": v for k, v in urllib.request.getproxies().items()
             if k in {"http", "https"}}
config = CodexConfig(
    cwd=str(run_dir.resolve()),
    env=proxy_env,
    config_overrides=("sqlite_home=" + json.dumps(str((run_dir / ".workflow/runtime").resolve())),),
)
state = WorkflowState(material=source_text)
with Codex(config) as client:
    backend = CodexSDKBackend(client, skill_dir)
    state = run_until_wait(state, backend, run_dir)

if state.stage == Stage.WAIT:
    # 展示 state.requests，收到真实用户回复后再恢复。
    pass
elif state.stage == Stage.DONE:
    print(state.draft)
# 其他状态表示本轮步数预算用尽，保留状态继续，不能当作通过。
```

使用 load_checkpoint(run_dir)恢复状态，使用provide_user_reply(state, user_reply)输入用户答案。规则版本改变时，应明确重新执行素材检查，不直接沿用旧规则下的进度或通过状态。

## 文件和权限

Agent只返回内容，Python统一提交material.md和result.md。内部.workflow/state.json保存检查、段落规划、规范加载凭据、审核和用户回复记录，作为断点恢复依据。同一运行目录只允许一个调度进程写入。

两份正文视图可以从机器状态重建；完整的可读记录区、请求稳定编号去重、历史版本视图仍待宿主接入。不要将内部记录混入最终model setup正文。

## 验证边界

离线测试使用模拟SDK客户端检查真实出站提示词，验证角色确实收到所需文件正文、只读沙箱被设置、同角色复用会话且更新当前素材、规范缺失或改动停止调用、跨目录引用被拒绝、规则摘要进入检查记录。另有流程测试覆盖等待用户、修改后复核和不合格不能通过。

本次在线运行已验证安装、登录、真实返回、正常路径和当前稿件审核通过。素材补问与返修分支、异常恢复以及通用宿主对话和Word解析入口仍需独立在线验证。SDK返回中断或失败状态时，适配器拒绝将部分JSON提交为成功结果。

接口依据：[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)、[Codex App Server](https://learn.chatgpt.com/docs/app-server)。
