# 模型方案与 MCP 输入

`check_model_plan(plan_json)` 接受 JSON 字符串，检查必要字段和显见矛盾，不判断模型的因果识别或统计正确性。以下仅示范字段结构，变量名需按当次研究填写：

```json
{
  "research_question": "X 与 Y 的关联是否因 Z 而不同？",
  "data_source": "官方数据集和年份",
  "sample": "符合条件的观察单位及筛选规则",
  "outcome": {"name": "Y", "type": "binary"},
  "exposure": "X",
  "moderator": "Z",
  "interaction": true,
  "model_family": "binary Logit",
  "estimand": "给定协变量分布下的条件关联",
  "interpretation_plan": "报告调整后的预测概率及组间差异"
}
```

`profile_csv_variables(csv_path, columns, max_rows)` 读取明确提供的本地 CSV，返回所选列的缺失数、非缺失数和低类别变量的计数；不返回个人记录。`count_group_cells(csv_path, columns, max_rows)` 对 2—3 列做未加权完整观测组合计数，用于发现空组和极小组。路径须为绝对路径，列名须来自实际 CSV。计数不等于调查加权估计，达到行数上限时应扩大检查范围或用合适统计软件复核。

