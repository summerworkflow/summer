# 分析记录、效果回收与版本

## 保存什么

清单供人阅读；analysis-record.json 供续接、回收和只读汇总。每次分析对应一个需求与材料基线，后续答复更新该记录的 revision。不同需求或不同基线不混成一个运行。

以下为虚构结构示例，不能直接作为实际反馈或分析事实。实际交付填入真实来源、时间与内容；没有反馈时保留 null 和空数组。

~~~json
{
  "schema_version": "1.0",
  "skill_id": "system-requirement-analysis",
  "skill_version": "1.0.0",
  "run_id": "REQ-EXAMPLE-001",
  "requirement": "示例需求",
  "revision": 1,
  "created_at": "2026-10-16T15:00:00+08:00",
  "sources": [
    {"id": "S1", "path": "需求文件位置", "version": "V1", "read_status": "read", "sha256": null}
  ],
  "coverage": [
    {"area": "保存与付款", "status": "partial", "note": "已读失败流程；最终字段表未读"}
  ],
  "questions": [
    {
      "id": "Q001",
      "kind": "rule_missing",
      "title": "委托保存后付款申请失败，用户怎样继续？",
      "scenario": "假设例子：委托保存成功，付款页面未打开，用户再次点击。",
      "uncertainty": "已读材料只描述成功流程，未说明本例的继续入口。",
      "question": "再次操作是否使用原委托？用户从哪里继续申请？",
      "owner_role": "产品负责人和开发",
      "recommendation": "建议保留已保存委托并提供继续入口，尚未确认。",
      "impact": "影响失败重试分支，不阻塞普通保存用例设计。",
      "source_refs": [{"source_id": "S1", "location": "保存并申请付款章节"}],
      "status": "open",
      "resolution": {"answer": "", "evidence": "", "applied_to": [], "reason": ""},
      "feedback": {"understood": null, "answerable": null, "useful": null, "evidence": ""},
      "history": []
    }
  ],
  "overall_feedback": [],
  "benefit_measurements": [],
  "improvement_proposals": []
}
~~~

字段约定：

- kind：rule_conflict / rule_missing / material_needed / existing_rule_needed / configuration_needed，对应入口的五类。
- source_refs 引用 sources 中的真实来源；位置至少具体到旁注、章节、表格单元格或可定位答复。未读材料的引用只能支撑“待取资料”，不能支撑该材料中的业务结论。
- coverage.status：reviewed / partial / not_reviewed；只说明材料分析覆盖，不表示设计或测试完成。
- 每个问题的 history 追加对象，字段为 at（带时区的时间）、event（变化）、evidence（依据）；回答修改、撤销、延期均保留缘由。只有实际发生才追加，不能预填用户答复或虚构人名、日期。

## 状态表示什么

| status | 人能看懂的含义 | 所需依据 |
| --- | --- | --- |
| open | 等答案 | 当前具体问题及材料依据 |
| waiting_material | 等资料 | 缺哪份资料、为何影响本题 |
| answered | 已取得适用答案 | resolution.answer 和 evidence |
| applied | 答案已经写进相应文档/用例 | 以上内容，加 applied_to 的可定位制品 |
| not_issue | 这项无需再问，例如已有明确规定或重复 | resolution.reason 和 evidence；不抹掉原问题 |
| deferred | 暂缓 | 原因和实际延期决定来源；不能编造恢复时间 |
| out_of_scope | 本期不处理 | 原因和范围依据 |

answered 不等于文档已改，applied 不等于业务已实现或测试通过。不得因为旧规则待查已经问了开发，就记成已取得答案。

## 收到反馈时怎样回收

只使用用户实际提供或授权读取的答复、评审记录、修订文件及后续反馈；不主动给他人发问卷、外发资料或跨项目收集信息。

1. 对应稳定 Q 编号，记录实际答案及来源，核对适用版本和影响分支。
2. 查相应文档是否确实更新；没有查看到更新证据时保持 answered，不自动升为 applied。
3. understood 表示接收方反馈“不需要再翻译就能看懂”；answerable 表示“能直接回答，不用再次拆题”；useful 表示“对确认、设计或实施有帮助”。只接受实际 true/false 反馈，未评价为 null。任一评价必须有 feedback.evidence。
   用户只评价“整份清单看不懂/挺有用”时，在 overall_feedback 记录 comment 原意及 evidence；不要求用户逐题打分，也不把整体评价自动填成每题评价。汇总原样展示整体反馈，不算入逐题百分比。
4. 记录误报、重复提问、漏项和措辞问题。没有可读性反馈时只报告“未评价”，不能由自己的阅读感受补成 true。
5. 输出“还没解决的具体问题 → 已有答案但未更新文档 → 处理进展 → 有反馈部分的表达效果 → 改进提案”。用户只要短版时保留前两项和证据限制。

## 只读汇总

在本 skill 目录中，使用已知 Python 环境运行；下面的记录位置先替换为实际绝对路径。脚本位于本 skill 的 scripts/review_outcomes.py。

~~~powershell
python -X utf8 scripts/review_outcomes.py "项目输出目录/analysis-record.json"
python -X utf8 scripts/review_outcomes.py "需求A/analysis-record.json" "需求B/analysis-record.json" --format json
~~~

脚本只读明确传入的文件，不联网、不写回、不扫描其他目录。不同 skill_version 分组展示；发现重复 run_id 不重复计算，直接报错。查看目录内多份记录时，先明确选择要汇总的文件。

汇总口径：

- “已取得答案”只计 answered、applied。分母为问题总数减 not_issue、out_of_scope；deferred 仍是未取得答案。这个比例是处理进展，不能称为 skill 有效率。
- “文档已更新”只计 applied；展示原始数量，不称为测试通过率。
- 三项表达反馈分别以该项非 null 的条数为分母，同时显示未评价数。没有反馈显示 N/A，不能显示 0% 或 100%。
- not_issue 单列为“无需再问”，不会记成成功解答。coverage 未读/部分覆盖保持可见。
- 跨需求汇总保留需求名称、run_id 与版本，不把多份记录当同一需求的重复闭环。

## 节省时间或减少返工的证据

仅有关闭率、生成用例数量、脚本成功或口头“挺好”，不能推出省时百分比。

确有可比的前后记录时，benefit_measurements 可放：

~~~json
{
  "metric": "澄清耗时",
  "before": 40,
  "after": 25,
  "unit": "分钟",
  "scope": "相同需求范围、计时起止方式和参与人员条件",
  "evidence": "两次计时记录的位置与日期"
}
~~~

示例数字为虚构。script 只列出带依据的 before/after，不评价可比性、不自动计算“提升效果”。人工确认 scope 确实可比后，才可另算差值并解释限制。

没有前后记录时写“目前只能查看问题处理和表达反馈，节省时间/减少返工尚不能判断”。

## 版本与改进

- skill_version 是本 skill 的语义版本，analysis-record 的 revision 是需求记录修订次数，两者分开。
- 补充不改变行为的说明或修复脚本错误：PATCH；增加兼容能力：MINOR；改变职责、必需记录结构或不兼容行为：MAJOR。
- 每次升版同时更新 SKILL.md 的 metadata.version、正文版本和 CHANGELOG.md；记录日期、原因、影响和验证。schema_version 仅在记录协议变化时变更。
- improvement_proposals 记录“具体反馈 → 受影响问题 → 建议修改 → 拟验证场景 → proposed/applied/rejected 及依据”。用户明确授权应用后才修改 skill；应用记录写入新版本号，不改旧运行的 skill_version。
- 本版本不附带远端遥测或后台回访；查看与更新由用户本次请求触发。
