# 批次、两份文档与效果回收

## 目录与正文

用户目录优先，否则用项目下“测试用例/需求简称/批次ID/”。默认两份用例文档加一份索引反馈记录，模型/实际组合输出按需放支撑子目录。

~~~text
批次ID/
  全部测试用例.md
  不可替代的业务底线用例.md
  design-record.json
~~~

全量维护完整业务正文，第二份复制已核定及候选的同ID完整正文，补筛选理由。记录只存索引、三条件与反馈，不重复维护步骤。用户不要求落盘时遵从，说明跨会话回收需后续提供记录，不因此拒绝设计。

全量中标记独占一行，不影响阅读：

~~~markdown
<!-- SHARED PREP-01 BEGIN -->
## 共用前置PREP-01
写实际适用角色、合法准备链、数量和完成检查点。
<!-- SHARED PREP-01 END -->

<!-- CASE TC-001 BEGIN -->
### TC-001 条件、动作、主要目标
按用例契约完整写依据、风险、前置、数据、步骤、
A1/A2断言与取证、影响及设计/准备状态。
<!-- CASE TC-001 END -->
~~~

ID为1—64个字母、数字、点、下划线或连字符，首位字母或数字；同种块ID唯一，块不嵌套。cases.shared_refs声明共享块，shared_dependencies声明间接依赖。第二份复制依赖闭包，不能让读者回全量找必要前置。

正文块fingerprint：CRLF转LF → 去块首尾空白 → UTF-8 → SHA-256。全量sha256按实际文件字节算。可导入助手的fingerprint辅助计算。新建两份先写全量及记录，再调用build-bottomlines，最后check。

## 协议1.0

完整可运行的虚构记录构造见 tests/test_design_records.py 的 make_bundle；仅供本skill自测，不得把其来源、风险、反馈或执行当实际事实。正文示例见 worked-example.md。下表是记录字段的维护约定，不要求用户先填写，设计者按已有信息生成。

### 顶层字段

| 字段 | 内容 |
|---|---|
| schema_version | 1.0，表示记录协议 |
| skill_id / skill_version | system-testcase-design / 生成批次时的实际skill语义版本 |
| design_id / case_set_version | 唯一批次ID及这套用例版本，字符串 |
| previous_design_id | 关联前版，没有为null；助手不自动访问前版 |
| revision / created_at | 正整数；创建时间为带时区ISO时间 |
| requirement | 本批次需求名称和范围简称 |
| sources | id、path、version、read_status、sha256；read_status为read/partial/unread |
| documents | full为path与实际sha256；bottomline为path；路径相对记录目录且不能越出目录 |
| rules | id、basis_status、source_refs；basis_status为confirmed/pending/current_behavior，来源引用source_id与location |
| shared_dependencies | 共享块ID到依赖ID数组的映射，没有为{}，不得循环 |
| coverage | 每规则一项rule_id/status/case_ids/reason；status为covered/partial/pending/excluded |
| cases | 下表所列用例索引 |
| obligations | 下表所列BL三条件 |
| issues | id/title/status/case_ids，status为open/resolved，具体规则、数据、证据、风险或替代缺口 |
| feedback / outcomes / findings | 真实评价、执行及设计质量反馈；没有时分别为[] |
| benefit_measurements / improvement_proposals | 实际可比收益记录及改进提案；没有分别为[] |

本地可读来源记真实哈希。来源不可读或未取得时sha256可null并说明限制，不能用未读来源作为确认规则。助手只检查元数据，不访问source.path，不确认来源真实或适用。

### 每条cases

| 字段 | 内容 |
|---|---|
| id/title/case_ref | 稳定ID、标题、全量文档正文块定位 |
| fingerprint | 对应CASE块实际指纹 |
| priority | 项目适用优先级，不作为底线筛选开关 |
| rule_ids/assertion_ids/shared_refs | 对应规则、必要断言、共享块的ID数组；不能无规则或无断言 |
| design_status | complete/rule_pending/detail_pending |
| preparation | status为unverified/missing/ready，另有environment/build/evidence；ready须实际环境、构建与核对依据 |
| bottomline | classification、obligation_ids、reason；分类用底线筛选五类，reason写实际判断及替代位置 |

只有明确预期可记complete；pending规则不可当明确。准备就绪不等于执行通过，也不授权开始执行。参数行另计且正文保留稳定参数ID；case_count指原子目标数量，不用参数行或断言数冲高。

### 每条obligations

| 字段 | 内容 |
|---|---|
| id/text/condition/scope/consequence/rule_ids | BL编号、具体底线、触发条件、适用范围、直接后果、规则引用 |
| risk | status为confirmed/assessed/pending，basis为依据数组；confirmed需要适用政策/验收/业务决定 |
| gap | status为shown/not_shown/pending，reason、basis；near_cases为case_id/comparison数组，解释近似验证不足 |
| alternatives | inventory为complete/partial/unknown；scope、basis、conclusion、checks |
| proof | case_id、assertion_ids、adequacy、reason、evidence_plan；adequacy为sufficient/partial/unknown |

alternatives.conclusion为none_equivalent/equivalent_exists/pending。checks逐项为kind/ref/status/reason/evidence，status为effective/insufficient/unverified；有效或不足判断须有证据，未知如实保留。核定范围完整有依据才能inventory=complete；没有项目外清单不能默认已全盘点。用户限定只比较本套设计时把该决定写入scope和basis，不扩写全项目无替代。

正式入选至少有一项本例BL：风险已确认、删除空白有依据、替代清单在声明范围完整、无有效或未知替代、证据设计足够、业务规则已确认、设计明确。候选缺什么写入reason/issues，不能为了数量填空的“已确认”。

proof充分只指设计方案足以证明目标，实际能力未核实保持准备未核实；页面不能证明服务端幂等时方案不得写sufficient。助手能拒绝缺字段的正式项，不能证明填写的业务判断真实或充分。

规则/底线在正文中有完整可定位含义，JSON只是简短索引。修订理由、旧ID映射和范围决定保留在全量；可添加history等字段，但助手未校验的附加字段不能宣称已验证。

## 真实反馈怎样回收

只使用用户提供或获准读取的评审、准备、后续执行记录，不主动发问卷、联网、联系他人或创建定时回访。更新前读最新指纹，发现并发变化先合并，不能覆盖他人反馈。

feedback追加事件：id、scope（case/suite）、at（带时区）、comment（接收者实际原意）、evidence（来源）；逐例另有case_id和case_fingerprint。ratings对象可包含readable/preparable/assertable/useful，值只能是真实true/false或未评价null，分别表示看得懂、能按方案准备、能独立判定、对工作有帮助。

整份评价用scope=suite，原样保留，不摊给每例。逐例按本批次每维度最后事件值计分，分母仅有该项真实评价者，未评价单列；显式null可撤销该维度当前评价，旧事件仍保留。作者自审不能冒充接收者反馈。

findings字段为id/kind/description/case_ids/status/evidence。status为reported/confirmed/rejected；可记录冗余、误判底线、漏掉底线、不可准备、预期不独立或表达不清。用户报告、确认的设计问题与产品Bug分开，缺准备不能记产品Bug。

## 后续执行证据

本skill不开始执行。用户提供或授权读取实际结果后，在outcomes追加：

- id、case_id、case_fingerprint、at、environment、build、result、evidence。
- preflight_evidence：本次真实环境、角色、对象、初始状态核对依据。
- assertions：每条id、status（pass/fail/not_observed）、actual、evidence。

result为pass/fail/blocked/inconclusive。pass须预期明确、全部必要断言有实际值和证据、本次前置有核对依据；只观察A1而缺A2不能整体pass。fail至少一条实际不符；blocked/inconclusive附reason。实际0和false是有效观察，不得按空值抹去。

保留首次与重跑事件；查看按批次、环境、构建分列每例最新结果，原始事件不删。旧指纹不能套新用例，历史通过不能冒充当前部署通过。缺证据保持不确定，不直接称确认Bug。

## 查看命令和分母

在当前skill实际目录运行，记录换成本次真实路径：

~~~powershell
python -X utf8 scripts/design_records.py build-bottomlines "项目输出目录/design-record.json"
python -X utf8 scripts/design_records.py check "项目输出目录/design-record.json"
python -X utf8 scripts/design_records.py review "项目输出目录/design-record.json"
python -X utf8 scripts/design_records.py review "批次A/design-record.json" "批次B/design-record.json" --format json
~~~

build只创建/复用相同第二份本地文档，不写JSON，不覆盖不同旧文档。check核对结构、引用、指纹与两份一致。review先做相同检查，再只读汇总；不扫描磁盘、不访问来源、不运行登记的业务动作或采集新反馈。退出0只表示记录一致，错误退出2。

多文件先选定批次；同design_id多revision直接报错防重复统计。不同版本、需求、环境/构建分列，无混合“总通过率”。

查看顺序：未关闭问题和待核定底线 → 设计/准备分类 → 实际逐例反馈分母和未评价数 → 整份原话 → 实际执行 → 质量发现 → 收益原始记录及提案。没有反馈显示未评价，没有执行显示未执行，不用0%/100%美化。

benefit_measurements记录metric/before/after/unit/scope/evidence，只有实际可比较前后基线才登记；助手只列原值，不计算收益百分比或替代人工可比性判断。无基线写尚不能判断，不以用例数、P0占比、候选确认率或业务通过率当skill效果。

improvement_proposals记录id/proposal/evidence/status（proposed/applied/rejected），应用另记applied_version。实际反馈先形成改进提案，用户要求应用才修改skill；项目规则或一次Bug不自动变成通用规范。

## 版本与升级

skill_version是生成批次的skill；case_set_version是用例版本；schema_version是记录协议；revision只表示反馈和准备记录更新，四者分开。

步骤、预期、依据、底线判断或材料基线变了，新建design_id与输出目录，关联previous_design_id、旧ID映射和理由；不把旧执行或评价迁成新版结果。仅追加反馈时同批次增revision并保留事件。

说明/缺陷修正升PATCH，兼容增强升MINOR，不兼容职责/交付/协议升MAJOR；同步SKILL元数据、正文版本、CHANGELOG与版本包。已发布标签和包不覆盖。

在skill目录运行自测：

~~~powershell
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
~~~

自测使用隔离虚构记录，验证复制、候选不冒充正式、弱证据不能通过、反馈分母及版本隔离；再按 acceptance-scenarios.md 检查语义。自测不等于真实用户效果或真实业务执行。
