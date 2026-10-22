# 模型方案与 MCP 输入

`check_model_plan(plan_json)` 接受 JSON 字符串，检查必填字段和少量显见矛盾，不验证数据、拟合、统计显著性或因果识别。变量名和理由需按具体研究填写。例如：

```json
{
  "research_question": "X 与 Y 的关联是否因 Z 而不同？",
  "data_source": "官方数据集名称、版本与年份",
  "sample": "分析单位、纳入排除和跳题规则",
  "outcome": {"name": "Y", "type": "binary", "encoding": "是=1，否=0"},
  "exposure": "X",
  "exposure_encoding": "X 的测量与参照组",
  "moderator": "Z",
  "interaction": true,
  "model_family": "binary Logit",
  "model_formula": "Y ~ X * Z + C",
  "controls": [{"name": "C", "rationale": "具体的混杂控制理由"}],
  "fixed_effects": [{"name": "地区", "rationale": "控制地区共有差异"}],
  "estimand": "在指定协变量分布下的调整后预测概率差",
  "interpretation_plan": "报告四组预测概率与差异；不把交互系数当成概率差",
  "missing_data_plan": "检查缺失机制并报告完整案例与替代处理",
  "standard_errors": {"method": "survey_design"},
  "sampling_design": {
    "kind": "complex_survey",
    "weight_plan": "根据官方文档使用抽样权重",
    "variance_plan": "按官方可用设计变量或明确的替代方法估计方差"
  },
  "causal_claim": false,
  "robustness_plan": "更换样本限制和变量口径，检查方向与不确定性"
}
```

`controls`、`fixed_effects` 可为 `[]`，但应在报告中解释为何无需纳入。`standard_errors.method` 可用 `iid`、`heteroskedastic_robust`、`clustered`、`survey_design`、`other`；选 `clustered` 时提供 `cluster_level`。`sampling_design.kind` 可用 `complex_survey`、`simple_random`、`administrative`、`convenience`、`other`。若 `causal_claim=true`，还须填写 `identification_assumptions`。工具不能判断这些理由是否正确。

检查器对简单 R/Python 公式（如 `Y ~ X * Z + C` 或 `Y ~ X + Z + X:Z + C`）核对因变量、核心自变量、交互项及其余变量是否在 `controls` / `fixed_effects` 中定义。变量名请使用公式中的实际标识符，详细含义写在编码或理由字段；若使用别名、函数、变换或数学公式（如 `logit P(Y=1)=...`），返回 `requires_manual_review`，由检验 Agent 核对。简单公式的明确缺项返回 `needs_revision`。数学公式只做有限的变量与显式交互检查，仍须人工审查。

支持的 Probit 名称包括 `binary probit`、`ordered/ordinal probit` 和 `multinomial probit`，分别对应二元、有序和无序多类别结局。声明 `complex_survey` 时，若标准误方法不是 `survey_design`，须给出 `standard_errors.design_compatibility_rationale`，然后由独立检验 Agent 判断是否合理；填写理由并不代表设计相容性得到证明。`check_model_plan` 的 `ready_for_data_validation`、`requires_manual_review`、`needs_revision` 只反映静态方案审查，不是模型估计结果。

`profile_csv_variables(csv_path, columns, max_rows, missing_values)` 和 `count_group_cells(csv_path, columns, max_rows, missing_values)` 只读取 `RESEARCH_DATA_DIR` 已授权目录内的绝对 CSV 路径。`missing_values` 是列名到缺失码列表的映射，例如 `{"income": ["-9", "NA"]}`；空白始终视为缺失。`RESEARCH_MIN_CELL_COUNT` 默认 5，可设置为 2—100。若出现任何低频类别，工具不返回该列完整类别表；若出现低频组合，不返回组合计数表。检查 `truncated_by_row_limit`，它表示文件还有未读取行；即使未截断，计数也只是未加权描述统计。

