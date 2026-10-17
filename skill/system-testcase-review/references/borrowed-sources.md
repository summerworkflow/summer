# 检索来源与方法取舍

核对日期：2026-10-18。GitHub星数来自仓库API，属于整个仓库；安装量来自 skills@1.7.2 的 find 命令，属于对应skill且为显示值。二者都不是实际评审质量证明。

本技能以本机 enterprise-testcase-review 的业务流程及现有设计/底线约定为基础独立编写。下列公开资料用于研究比较或提炼适用检查角度，不复制第三方技能、脚本和模板，不形成运行依赖。

| 来源 | 仓库星数 | 适配与处理 |
|---|---:|---|
| [softaworks/agent-toolkit：qa-test-planner](https://github.com/softaworks/agent-toolkit/blob/3027f20f3181758385a1bb8c022d4041dfb4de84/skills/qa-test-planner/SKILL.md) | 2,559 | MIT；参考清楚前置、数据、可观察预期和追溯的检查角度。其通用90%通过率、固定时间和Figma流程不作为本项目要求 |
| [fugazi：静态评审](https://github.com/fugazi/test-automation-skills-agents/blob/65a72d5e74def3c23143bef8757e72cb68e91032/skills/qa-manual-istqb/references/static-testing.md) | 252 | MIT；参考静态检查与问题跟踪思路。不继承整套QA流程、Node/Playwright依赖或成本比例 |
| [petrkindlmann：ai-qa-review](https://github.com/petrkindlmann/qa-skills/blob/b3bb61bd268b147476252c6ed5a0440c87b97441/skills/ai-qa-review/SKILL.md) | 189 | MIT；参考断言有效性及结合上下文判断问题。主要审测试代码，其反复运行、变异测试和CI门禁不进入本技能 |
| [alirezarezvani：senior-qa](https://github.com/alirezarezvani/claude-skills/blob/19392f7a08264ed00486a251f5b2098321771f94/engineering-team/skills/senior-qa/SKILL.md) | 28,315 | MIT；已比较，主要为React/Next.js自动化，未作为业务用例评审模板 |
| [VoltAgent：qa-expert](https://github.com/VoltAgent/awesome-claude-code-subagents/blob/408d3c9eee2d0c75c12a3abb5de29e53c2ca6b9e/categories/04-quality-security/qa-expert.md) | 25,787 | MIT；已比较，属于广泛QA代理，未继承其覆盖率/自动化比例及代理协作要求 |
| [naodeng：test-case-reviewer-plus](https://github.com/naodeng/awesome-qa-skills/blob/c341df697dda7b0f67a4cae0263595934ef5367a/skills/zh/testing-types/test-case-reviewer-plus/SKILL.md) | 265 | 任务相关；其[LICENSE](https://github.com/naodeng/awesome-qa-skills/blob/c341df697dda7b0f67a4cae0263595934ef5367a/LICENSE)为PolyForm Noncommercial 1.0.0，仅作比较，不复用正文、脚本或派生模板 |
| [fishzjp：test-case-review](https://github.com/fishzjp/qa-skills/blob/ff6957f44190e63ec46dcb1a513d196a0b062bd4/skills/test-case-review/SKILL.md) | 46 | MIT；已比较。其代码优先裁决与直接改源默认不匹配本项目，未采用 |

find 命令检索到 [qa-test-planner](https://skills.sh/softaworks/agent-toolkit/qa-test-planner) 显示4.3K安装；[test-case-reviewer](https://skills.sh/naodeng/awesome-qa-skills/test-case-reviewer)为195，[plus](https://skills.sh/naodeng/awesome-qa-skills/test-case-reviewer-plus)为109。安装量不改变内容和许可适配判断。

发现流程参考 [find-skills](https://github.com/vercel-labs/skills/blob/main/skills/find-skills/SKILL.md)，实际使用 npx skills@1.7.2 find 关键词查询；先发现，再读源码、核对星数与适配，未安装第三方候选。CLI日志及来源清单保存在维护项目的 releases/research-20261018，不随运行包交付。

## 本项目保留的独立要求

业务预期有适用依据，前置可达与本轮样本就绪分开；检查交易身份、状态、金额、来源副本及证据上限；复核不可替代底线三条件和两份正文；保留稳定编号、真实反馈及反证。不从外部模板擅自增加审批、数字门槛或真实执行。
