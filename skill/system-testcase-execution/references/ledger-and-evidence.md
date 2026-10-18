# 执行台账、证据与只读检查

## 人工可读记录

用例执行记录.md写run_id/revision、skill版本、源用例与规则指纹/版本、部署/环境、身份数据范围、授权、所选及排除用例/分支、证据层和实际时间。逐分支写DATA/CAP、实际对象关系、输入、步骤、预期来源、断言实际值、证据、结果、副作用、首轮及后续attempt和残余验证。

每个结论需能定位对象、时间、动作、独立预期和实际观察；截图需要身份/上下文与目标值，无法同屏时用关联图片。高风险状态/金额写入核对动作前、输入/动作、即时结果和刷新/重入；持久性只有在必要且可观察时才断言，不冒充数据库证明。只读检查或非持久化校验按实际声明检查点并说明理由，不能为易通过删必要证据。

不可见证据保留缺口。预期依据分为已确认业务规范、实现事实、实际观察和挑战策略；后3类不能自行升级为正向业务预期。敏感令牌、密码、完整请求头不进入报告；必要脱敏不应失去对象关联或金额判断能力。

## execution-ledger.json 协议1.0

UTF-8 JSON。已有项目协议不变，必要时另建本协议映射；核对原用例到映射的一致性和哈希。检查器不解析原始Word/XMind/用例文档，也不验证实际证据内容。

| 顶层字段 | 约定 |
|---|---|
| schema_version | "1.0" |
| run_id / revision | 稳定运行编号、正整数；技能版本另记录在人工报告 |
| baseline | 非空字符串字段cases_ref、environment、build、role_scope、authorization_ref；未知事实如实写未知及影响，不是已核实 |
| selected_case_ids | 非空、无重复的选定用例ID；须与cases中ID集合一致 |
| cases | 所选用例目录；每个为id和非空branches；每分支为id、非空assertions、非空required_checkpoints |
| attempts | 按记录顺序追加的尝试；未执行可为空 |
| regression_scope_note | 适用固定回归和动态风险复查的范围依据；无项说明原因 |
| regressions | 回归任务数组，无项为[] |
| blocker_reviews | 初始存在blocked断言的分支复查数组，无项为[] |

分支assertions每项为id及basis_ref（可null表示未裁定）。断言编号在本分支唯一；basis_ref非空方可报passed/failed。required_checkpoints是本分支必要证据标签的无重复字符串列表，如identity、before、action、after、persistence。所选分支必须保留来源中全部适用的必要断言；未选/缩范围放人工报告及来源映射，不暗删隐藏层断言。

### attempt

字段：id（运行内唯一）、case_id、branch_id、phase（first/retry/regression）、at（含时区ISO时间）、context_verified、preconditions_verified（真实布尔）、context_evidence（引用字符串数组）、checkpoint_evidence（标签到非空引用数组的字典）、results（数组）。

- 每分支首次记录必须first，最多一个first；后续retry/regression必须prior_attempt_id指向该分支最近一次attempt，时间不能倒退，reason说明新尝试依据。
- results每项为assertion_id、status、actual、evidence、reason；不认识或重复的断言报错。缺失必要断言按not_run处理，不默认通过。
- status为passed/failed/blocked/inconclusive/not_run。passed/failed需非空actual、非空evidence，以及本attempt的身份/前置核实为true且context_evidence非空。其业务语义和证据充分性仍须人工判断。
- blocked/inconclusive/not_run需非空reason，actual可null、evidence可[]；不得用空话代替实际缺口。
- 分支必要断言全passed但缺required_checkpoints时，检查器判inconclusive并列缺口，不照抄通过。failed保留反例，即使其他断言未执行；缺失项仍使记录未收口。
- 同分支最新attempt整体作为当前结果，不拼接不同attempt的通过项。首轮及所有历史failed单列，不被后续passed覆盖。

### 回归与阻塞复查

regressions每项有id、kind（fixed/dynamic）、case_id、branch_id、reason及status：

- pending：尚未处置，记录不收口。
- done：attempt_id指向本分支phase=regression且必要断言完整处置、结果passed/failed的真实尝试；失败也是已执行，不能当通过。
- blocked：reason及evidence明确未能执行/判断的原因；有实际attempt时附attempt_id并保持其blocked/inconclusive结果。
- waived：waiver_ref指向明确人类授权及范围，保留reason，不记通过。

初始存在blocked断言的每个分支必须有一条blocker_reviews：case_id、branch_id、resolution、reason。

- resolution=retried：attempt_id指向本分支phase=retry且必要断言已完整处置的后续尝试。
- resolution=still_blocked：evidence非空，保存复查事实；若当前分支已passed，不能仍标still_blocked。
- resolution=waived：waiver_ref指向明确人类授权，不删除首轮阻塞。

这些引用只能证明记录有定位，检查器不判断授权或证据真伪。首轮失败中夹带blocked断言同样要复查；没有blocked的分支不能虚造复查项。用户中途缩范围保留旧run，再建新选择范围及授权理由，不从原run移除失败/阻塞项。

## 计算规则和完成边界

断言与分支聚合优先次序为failed → not_run → inconclusive → blocked → passed。分支缺必要检查点且全断言passed时改为inconclusive；用例按所有选定分支聚合。各分支必须独立判断，一方通过不抵消另一方失败。

completion_gate是**台账收口**：首轮每个选定分支有记录且必要断言均已处置（没有缺失/not_run）；最新attempt亦已完整处置；无pending回归；所有初始blocked分支有有效复查记录。失败、阻塞及未决可以收口，必须保留其结论和后续影响。输入中的手填完成标记不起作用。

输出同时列首轮与当前用例计数、分支结果、历史失败attempt、待回归项和未复查阻塞。无统计分母时不算通过率；如需比例，明确对象/观察层及原始分子分母，把阻塞、未决、未执行单列，不把重试次数当新增用例。

检查器只做声明范围的结构/一致性检查，不能证明实际完成了原始用例、识别所有动态回归或据此作发布决策。退出0=结构可分析；退出2=输入/结构错误。缺Python时人工依本协议核对并记未运行助手，不凭缺工具判业务失败。

## 最小结构示例（虚构、未执行）

~~~json
{
  "schema_version": "1.0", "run_id": "DEMO-PLAN", "revision": 1,
  "baseline": {"cases_ref": "DEMO-cases-v1", "environment": "未知", "build": "未知", "role_scope": "未知", "authorization_ref": "仅规划"},
  "selected_case_ids": ["TC-1"],
  "cases": [{"id": "TC-1", "branches": [{"id": "main", "assertions": [{"id": "A1", "basis_ref": "DEMO-R1"}], "required_checkpoints": ["identity", "result"]}]}],
  "attempts": [], "regression_scope_note": "演练尚未安排回归，不能代表项目无适用项",
  "regressions": [], "blocker_reviews": []
}
~~~

示例可被分析，但completion_gate=false，当前TC-1=not_run。完整可运行的虚构attempt例子见 [隔离测试](../tests/test_review_execution.py)，不是实际环境记录。
