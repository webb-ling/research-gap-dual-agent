# 研究空白交接记录

`check_gap_evidence(gap_json)` 接受 JSON 字符串，只检查字段、基本 URL 格式和状态一致性，不访问链接，也不验证论文或创新性。交给第二环节时保留以下字段；`screened_count` 是研究者实际看过的条目数，不能填数据库命中总数，且不能超过本次 `returned_count`。

```json
{
  "candidate_gap": "限定对象、变量和问题的候选空白",
  "existing_coverage": "最接近研究已经回答了什么",
  "unresolved_part": "本轮尚未见直接回答的具体问题",
  "data_feasibility": "官方数据、变量、覆盖和限制",
  "evidence_boundary": "检索数据库、日期、语言、全文可得性和未核验事项",
  "verification_status": "needs_revision",
  "search_log": [
    {
      "database": "OpenAlex",
      "query": "实际查询式",
      "searched_at_utc": "2026-10-22",
      "page": 1,
      "returned_count": 10,
      "screened_count": 10
    }
  ],
  "closest_studies": [
    {
      "title": "论文完整题名",
      "original_url": "https://doi.org/10.xxxx/example",
      "covered_question": "该研究已回答的问题",
      "remaining_difference": "与候选问题的具体差别",
      "verification_status": "unconfirmed"
    }
  ]
}
```

`search_log` 的 `searched_at_utc` 使用 `YYYY-MM-DD` 日期；`page` 必须是正整数，`returned_count` 和 `screened_count` 必须是非负整数。`original_url` 必须是带主机名的 `http(s)` URL。`verification_status` 可填 `passed`、`needs_revision` 或 `unconfirmed`；总体标为 `passed` 时，所有最接近研究都须标为 `passed`，否则返回一致性问题。只有核验 Agent 实际打开并核对原始材料后，才可将该研究标为 `passed`。工具返回 `required_fields_present` 仅代表结构完整，绝不代表证据已通过核验。

