# 测试 skills

本目录保存显示名以“测试：”开头的本地已安装技能快照，最近更新日期：2026-10-18。

| 名称 | 版本 | 技能目录 | 职责 |
|---|---|---|---|
| 测试：需求分析 | 1.0.0 | [system-requirement-analysis](system-requirement-analysis/SKILL.md) | 分析需求、输出待确认清单，回收并查看分析效果 |
| 测试：风险分析 | 1.0.0 | [system-risk-analysis](system-risk-analysis/SKILL.md) | 分析业务失败场景、后果、防护与验证优先级，生成独立风险分析并回收查看实际效果 |
| 测试：用例设计 | 2.0.0 | [system-testcase-design](system-testcase-design/SKILL.md) | 设计全部用例和不可替代业务底线用例，回收并查看设计效果 |
| 测试：AI用例转换器 | 1.0.0 | [system-ai-testcase-converter](system-ai-testcase-converter/SKILL.md) | 将已有人工用例转换为 AI 执行说明，查看转换效果 |
| 测试：生成skills | 1.0.0 | [system-skill-generator](system-skill-generator/SKILL.md) | 创建或修订原子化、版本化、可读且可回收效果的测试 skill |
| 测试：用例转XMind | 1.0.0 | [system-testcase-xmind](system-testcase-xmind/SKILL.md) | 将已有用例转为审阅索引与完整详情两页 XMind，核对保真并查看审阅反馈 |

## 使用

每个技能文件夹包含 SKILL.md、agents/openai.yaml、CHANGELOG.md 以及配套参考、脚本和自测。将所需文件夹完整放到 Codex 的用户 skills 目录后，在新会话中按显示名或调用名使用。

例如：使用 $system-testcase-design 根据给定需求设计全部用例和不可替代的业务底线用例。

## 版本和效果查看

版本变更见各技能的 CHANGELOG.md；效果记录协议和查看命令见对应 SKILL.md、references 及 scripts。上传完成、结构自测和真实使用效果分别记录，实际收益须由后续使用反馈证明。

[manifest.json](manifest.json) 列出本次 54 个技能文件的字节数、SHA-256 和 Git blob SHA，便于核对快照完整性。
