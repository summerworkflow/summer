# 转换效果回收与查看

每次转换在新输出目录保存 xmind-review-record.json。skill 版本、输入协议版本、批次和反馈 revision 分开；运行记录不放安装包。build 只登记实际机械回读，默认客户端未检查、审阅未评价，feedback 为 []。

## 本次记录

记录包含 run_id、revision、created_at、skill、source_input（路径及指纹）、scope、counts、missing_fields、case_mapping、checks、artifacts、feedback。case_mapping 对应原编号/导入编号、来源、分组、索引 topic ID 及详情 topic ID。

checks.integrity 为归一化 JSON 到 XMind 的回读结果。checks.source_review、desktop_open、readability 均含 status 和 evidence 数组：

- source_review：not_checked/pass/fail；依据是实际对原文逐编号、数量及抽取异常的核对。
- desktop_open：not_checked/pass/fail；证据含实际客户端版本、观察与定位。
- readability：not_evaluated/pass/fail；依据实际审阅反馈，不把作者结构检查写成接收者评价。

人工补记检查时保留本次原意和证据。更新前核对当前记录及导图指纹，先将旧记录另存为 xmind-review-record-r1.json 等对应修订快照，再增加 revision。实际评价追加 feedback，不删除旧反证；检查状态变化的旧值和依据可通过旧修订快照再次查看。人为编辑导图或变更输入后新建批次并重新核对，不能沿用旧指纹的通过。

## 实际反馈事件

~~~json
{
  "id": "FB-001",
  "at": "2026-10-17T15:00:00+08:00",
  "artifact_sha256": "本批次导图的实际SHA-256",
  "kind": "readability",
  "value": false,
  "comment": "审阅者实际原话，说明哪个编号的哪一处难读",
  "evidence": ["实际反馈来源定位"]
}
~~~

上例为协议示意，不可登记为真实评价。kind 为 openability/readability/omission/mapping/other，value 为真实 true/false 或未判定 null。评价正向含义为“该维度满足审阅需要”；omission 为“没有遗漏”、mapping 为“对应正确”，comment 保留具体事实。整份“好用”只记 other，不摊成所有维度通过。

review 输出每个维度当前最后一条评价和历史事件数，显式 null 撤回当前判定。反馈必须绑定该批次导图指纹；旧版或别的导图不混算。缺反馈写未评价，null 不计为通过/失败，不伪造百分比。

## 查看入口

~~~powershell
python -X utf8 -B scripts/xmind_review.py review --record "本批次/xmind-review-record.json"
python -X utf8 -B scripts/xmind_review.py review --record "本批次/xmind-review-record.json" --format json
~~~

只读指定记录，不联网、不执行用例、不访问记录里的文件引用、不写回。先列缺失字段、未核实或失败检查及实际负面反馈，再列数量、版本及当前评价。它汇总已记录证据，不能代替重新读取客户端或原文。

真实使用可回收：打开是否成功、是否漏内容、定位是否方便、步骤预期是否对得上、底线标记是否误导、具体需改位置。没有可比前后基线不报告节约时间。要改 skill 时根据实际反馈小步修订并升版，不自动改变源业务用例或旧导图。
