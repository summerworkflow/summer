# 生成记录与效果查看

## 保存位置与对象

每次生成一个目标skill对应一个run_id。skill-generation-record.json保存在项目/批次输出目录，不装入目标skill包。目标skill自己的业务反馈记录另存；本记录只引用用户提供或授权读取的实际结果，不扫描外部环境或执行生成物。

生成器质量与生成物任务效果分开。例如“技能包结构通过”不是“需求分析好用”，更不是“业务测试通过”。不要把创建新生成器的过程伪记成这个新生成器已经被用户实际使用。

## 协议1.0字段

| 字段 | 内容 |
|---|---|
| schema_version | 1.0；协议版本 |
| run_id / revision / created_at | 唯一生成批次、正整数修订次数、带时区ISO时间 |
| generator | id、version；实际创作器未提供版本可null，不捏造版本 |
| request | summary、evidence：本次请求及来源 |
| generated_skill | id、display_name、version：实际目标skill及语义版本 |
| requirements | id、text、origin、status、reason、evidence数组 |
| checks | id、kind、status、reason、evidence数组 |
| artifacts | id、kind、ref、sha256；文件真实指纹，目录为null并引用清单证据 |
| issues | id、description、status、evidence数组；open/resolved |
| feedback | 实际评价事件，没有为[] |
| usage | 实际使用事件，没有为[] |
| benefit_measurements | 实际可比前后记录，没有为[] |
| improvement_proposals | 改进提案，没有为[] |

requirements.origin为explicit/convention/task_specific/inferred，对应明确要求、实现惯例、专属规则和未确认推断。status为met/partial/unmet/unverified/not_applicable；met需要可定位产物或检查依据，不把作者自审当用户评价。不适用也须说明原因。

checks.kind说明实际做的结构、链接、脚本自测、行为审阅或包副本比对；status为pass/fail/not_run。有实际结果须evidence，未做写reason。脚本退出0只支持对应检查，不升级为实际效果。

artifacts.kind为source/archive/installed；ref是实际位置。查看助手不读取该位置，不执行其中内容，只展示已记录指纹；生成时源/包/副本是否一致另由实际比对证据证明。

## 实际评价事件

feedback每条为id、subject、subject_version、at、comment、evidence和ratings。

- subject为generator或generated_skill，版本须对应本批次实际对象。目标旧版评价放旧批次，不借给新版。生成器未提供版本时subject_version可null，查看明确版本未提供。
- comment保存实际原意，evidence是实际答复/记录位置，不可由作者代填。
- ratings为atomic/readable/usable/reviewable中有关维度，实际true/false，未评价null；原子职责清楚、能看懂、能用于目标任务、效果入口能查看。
- 用户仅评价整份好用时只保留comment，ratings可{}。不把整体评价自动分配到每项requirement或每条目标业务用例。
- 同一subject、同一维度按时间最后事件值展示，缺字段不改变旧值，显式null撤回当前评价；所有旧事件保留。

只根据明确提供或获准读取的实际反馈追加，不外发、不发问卷、不联系他人、不设定时回访。

## 实际使用事件

usage每条为id、subject、subject_version、at、scope、result、evidence数组。

result为pass/fail/blocked/inconclusive，scope写实际使用目标和观察范围。真实来源中的准备失败、操作问题、未知结果和确认不符分别保留，不自动当产品Bug或整个skill无效。必要目标未验证的结果保持inconclusive，不以命令退出码代替。

本助手只汇总这些实际记录，不重新核验目标业务的全部断言；目标已有专用记录/报告时引用其真实定位及限制。自测、样例和本次作者审阅放checks，不填usage，更不填feedback。

改目标逻辑/版本或生成规则基线时新建run_id和记录，旧记录保留；只追加反馈增加revision。更新前核对当前文件指纹，遇到并发变化先合并，不覆盖旧评价与反证。

## 查看

路径替换为实际本skill脚本位置及指定记录：

~~~powershell
python -X utf8 scripts/review_generation.py "批次/skill-generation-record.json"
python -X utf8 scripts/review_generation.py "批次A/skill-generation-record.json" "批次B/skill-generation-record.json" --format json
~~~

脚本只读这些JSON，不联网、不扫描目录、不读引用路径、不写回、不执行生成物。同一run_id不同revision不能同时累计，重复直接报错；不同版本分别输出，不算混合效果总分。

先列未满足/未核实要求、失败或未做检查、未关闭问题，再列规则去向、产物、按两个subject分列的实际评价和使用结果、收益原值与改进。

每维度分母只包含本对象真实非null评价；没有为未评价，不虚造0%/100%。没有使用记录为尚无使用记录，不据此推断从未发生。多个批次分别展示，不把同一生成物的重复观察累计成多个成功技能。

benefit_measurements为subject、metric、before、after、unit、scope、evidence；须实际可比的前后基线。脚本只展示原值，不计算“效率提升”或判可比性；没有基线写尚不能判断。

improvement_proposals为id、proposal、evidence、status（proposed/applied/rejected），应用另记applied_version。先记录具体反馈及建议验证场景；当前请求已授权修订时落实，否则不自动改技能或升版。

## 自测边界

可运行：

~~~powershell
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
~~~

tests/test_review_generation.py中make_record是完整可运行的虚构示例。仅验证结构、版本隔离、反馈分母、未评价和只读行为，不代表新skill曾被真实用户使用。实际创作记录必须用本轮真实请求、版本、产物和证据；空反馈/空使用保持空。
