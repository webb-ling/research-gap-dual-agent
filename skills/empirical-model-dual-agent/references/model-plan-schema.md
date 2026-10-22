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
  "model_formula": "logit P(Y=1)=α+β1 X+β2 Z+β3 X×Z+γC",
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

`profile_csv_variables(csv_path, columns, max_rows, missing_values)` 和 `count_group_cells(csv_path, columns, max_rows, missing_values)` 只读取 `RESEARCH_DATA_DIR` 已授权目录内的绝对 CSV 路径。`missing_values` 是列名到缺失码列表的映射，例如 `{"income": ["-9", "NA"]}`；空白始终视为缺失。`RESEARCH_MIN_CELL_COUNT` 默认 5，可设置为 2—100。若出现任何低频类别，工具不返回该列完整类别表；若出现低频组合，不返回组合计数表。检查 `truncated_by_row_limit`，它表示文件还有未读取行；即使未截断，计数也只是未加权描述统计。

