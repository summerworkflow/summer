# 转换记录、效果回收和版本

## 制品关系

AI执行用例.md保存完整业务步骤、预期、参数来源和调用计划。conversion-record.json保存原检查点去向、脚本目录与绑定引用、准备状态和后续实际反馈，不重复维护整套用例正文。

以下为独立的虚构单目标示例，不能当成真实用例、脚本或执行事实；它不是格式示例中三目标原用例的完整转换。

~~~json
{
  "schema_version": "1.0",
  "skill_id": "system-ai-testcase-converter",
  "skill_version": "1.0.0",
  "conversion_id": "EXAMPLE-001",
  "revision": 1,
  "created_at": "2026-10-17T10:00:00+08:00",
  "counting_unit": "同粒度业务动作",
  "source_cases": [
    {
      "id": "MAN-01",
      "location": "虚构人工用例文档第1条",
      "version": "V1",
      "checkpoints": [{"id": "P1", "text": "改数量并保存后，人工运费不被覆盖"}],
      "disposition": "converted",
      "reason": "",
      "evidence": "",
      "excluded_checkpoints": []
    }
  ],
  "scripts": [],
  "cases": [
    {
      "id": "AI-MAN-01-01",
      "title": "改数量并保存后，人工运费保持",
      "source_checks": {"MAN-01": ["P1"]},
      "case_ref": "AI执行用例.md中的AI-MAN-01-01",
      "design_status": "complete",
      "basis_status": "confirmed",
      "basis": "虚构适用规则R-20",
      "route": "guided_once",
      "setup_required": true,
      "setup_reason": "需要独占的人工金额草稿",
      "bindings": [],
      "assertion_ids": ["A1", "A2", "A3"],
      "missing": ["尚未取得准备、页面改数量和保存回读的实际脚本"],
      "preflight": {"status": "unverified", "environment": null, "build": null, "evidence": []},
      "feedback": {"understood": null, "usable": null, "evidence": ""}
    }
  ],
  "attempts": [],
  "overall_feedback": [],
  "benefit_measurements": [],
  "improvement_proposals": []
}
~~~

### 映射与状态字段

- source_cases记录用户指定输入范围内的全部原用例。checkpoints逐项对应原检查内容；源文件可读时补充source_sha256，源ID缺失时保存逻辑编号及原位置。
- disposition为converted、deferred或excluded。converted的每个原检查点均须有case.source_checks去向或excluded_checkpoints中的排除依据；后两类须提供reason和evidence，不能静默省略。
- excluded_checkpoints的对象为id、reason、evidence，仅用于有依据地排除原检查点，不能为了脚本方便而排除。
- design_status为complete、rule_pending或detail_pending；basis_status为confirmed或pending。未明确的设计/业务预期必须route=blocked。
- route为script、guided_once、human或blocked，对应入口中的四条路线。
- bindings只引用实际登记的scripts；缺能力写missing，不能给不存在的入口取名冒充绑定。missing保留具体缺口，不用“待完善”代替。
- preflight.status为unverified、missing或ready。ready要求真实环境、部署及核对证据，必要脚本均在相同目标环境/部署有当前验证；这仍不表示本用例已执行。

### 脚本及调用引用

scripts中每个入口至少记录：

~~~json
{
  "id": "CAP-EXAMPLE",
  "path": "实际仓库/文件位置",
  "entry": "实际入口或已有CLI",
  "version": "实际提交/版本/哈希",
  "phases": ["prepare", "act", "check"],
  "disabled": false,
  "verification": {
    "status": "unverified",
    "environment": null,
    "build": null,
    "evidence": []
  }
}
~~~

verification.status为unverified、historical或current；后两类须有实际证据，current另需环境和部署。不能把示例CAP-EXAMPLE直接登记为实际可用。

每个binding为script_id、phases、call_ref；phases必须是该入口已说明的能力，call_ref定位到用例文档里实际的调用方式、参数/输出关系。一个入口可以覆盖多个环节。script路线要求act、check；setup_required=true时还要求prepare。无需准备时说明setup_reason，不创造空造数动作。

## 收到运行结果时记录什么

转换器不主动运行。用户提供或授权读取实际执行结果后，在attempts追加本次尝试：

~~~json
{
  "id": "ATTEMPT-EXAMPLE-01",
  "case_id": "AI-MAN-01-01",
  "environment": "实际目标环境",
  "build": "实际部署版本",
  "result": "pass",
  "preflight_evidence": ["本次环境、角色、对象及初始状态核对记录"],
  "assertions": [
    {"id": "A1", "status": "pass", "actual": "实际观察值", "evidence": ["实际证据位置"]}
  ],
  "evidence": ["本次执行记录位置"],
  "script_steps": 0,
  "exploration_steps": 0,
  "human_interventions": 0
}
~~~

这只是字段说明，不能作为通过记录。本例若要求A1/A2/A3，只记录A1就不能result=pass。

- result为pass、setup_failed、script_failed、assertion_failed或blocked。pass须全部必要断言有实际值及证据；assertion_failed至少有一条实际不符断言。证据不足不算通过。
- 原始首次与重跑按实际发生顺序追加，分别保留id及证据；汇总的“首次”按记录顺序判断，顺序不明时先核实，不能擅自倒排。后一次通过不覆盖首次失败；不同部署分开列，不能混称当前版本通过。
- 计数依据来自执行记录。script_steps和exploration_steps按counting_unit中同一约定粒度计数，不能把整个大脚本记1步、把每次探索点击各记1步来美化比例。human_interventions只记真实人工接管。
- 本轮还没执行时attempts必须为空；不能把准备练习、历史其他场景成功或计划步骤填作本例试跑。
- 修改用例逻辑、原检查点映射或脚本版本时另建conversion_id，保留previous_conversion_id及旧记录；只回填准备证据、执行与反馈时增加revision，保留历史。旧结果不迁移成新批次结果。

## 查看效果

使用本skill目录中的脚本，路径替换为实际记录：

~~~powershell
python -X utf8 scripts/review_conversion.py "项目输出目录/conversion-record.json"
python -X utf8 scripts/review_conversion.py "转换A/conversion-record.json" "转换B/conversion-record.json" --format json
~~~

只读指定文件，不联网、不执行登记的脚本、不写回。重复conversion_id报错，避免同一批次重复累计；不同skill版本和计数粒度分别汇总。

输出先列每条缺口与待核实准备，再展示：

- 原用例/检查点是否登记了去向：这是映射核对，不是业务覆盖已审完。
- 脚本方案已绑定数、首次需走通数、人工协助数、阻塞数，以及有核实记录的准备情况。
- 实际尝试的各类结果、首次尝试与后续尝试，按环境/部署分别列；未试跑显示“尚未试跑”。
- 有记录的脚本动作、临时探索和人工接管，注明计数粒度；没有动作记录显示N/A。
- 每例understood和usable只接受实际true/false反馈并附evidence；未评价为null。整体反馈放overall_feedback（comment、evidence），不自动摊到每例。
- benefit_measurements记录metric、before、after、unit、scope、evidence。没有同条件前后基线，只展示现有记录，不计算“省时/减少探索百分比”。

案例转换数不是AI自动执行成功数，脚本步骤占比不是测试通过率。准备失败不记确认产品Bug；真实断言不符也需继续核实。

## 回收后的改进与版本

improvement_proposals记录proposal、evidence、status（proposed/applied/rejected）；已应用另写applied_version。先形成具体改进提案，用户明确要求应用后再改skill。

补充说明或修复错误升PATCH；增加兼容能力升MINOR；改变职责或不兼容记录协议升MAJOR。同时更新SKILL.md元数据、正文版本和CHANGELOG.md，保留变更原因及验证。

schema_version描述记录协议；skill_version描述生成本批次的skill版本，revision描述记录更新次数，三者不混用。无真实使用证据时，不能用自测通过宣称skill有效。

在本skill目录运行汇总器自测：

~~~powershell
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
~~~

测试仅使用虚构记录，不访问实际业务环境、不执行登记的业务脚本。格式示例中的语义验收场景另作逐项审阅。
