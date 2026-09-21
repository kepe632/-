# A股科技长期主义观察池 · 投研 Agent

面向「中国科技长期主义」A 股观察池的投研工具，按 **事实(Fact)+逻辑(Logic)+预期(Expectation)** 产出可追溯报告。

> 本版本**不含定时推送**：所有报告由你手动运行命令生成。完整用法见 [使用说明.md](使用说明.md)。

## 能生成的报告（Word 版，按日期+星期归档）

| 命令 | 报告 | 内容 |
|---|---|---|
| `python agent.py morning` | 每日早间市场与行业要闻 | 全球/中国主要指数 + 全球/中国/行业要闻分类 + DeepSeek 专家解读 |
| `python agent.py daily` | 每日舆情雷达 | 每只股：量价 + 主力资金 + 估值位置(52周分位) + 基本面 + 公告 + 组合点评 |
| `python agent.py weekly` | 本周板块复盘 | 东财行业 Top10 + 涨跌幅条形图 + 概率化归因 + 下周前瞻 |
| `python agent.py biweekly` | 双周投研备忘录 | 消息面·技术面·估值水位·买卖建议 四维表格 |

每份报告末尾固定带合规声明。LLM 输出强制「概率思维、假设句式、禁止绝对化」。

## 快速开始

```powershell
# 1) 安装依赖（需联网；如在国内可自行配置代理）
pip install -r requirements.txt

# 2) 离线跑通（不依赖 akshare / 网络）
python agent.py selftest
python agent.py daily --demo

# 3) 手动生成报告
python agent.py morning
python agent.py daily
python agent.py biweekly
python agent.py weekly
```

## 配置你的观察池

编辑 `config.json` 的 `watchlist`，`code` 为 6 位股票代码，`name` 为名称。默认给的 10 只是
占位样例（AI 算力/半导体/机器人/消费电子主线），**请替换成你自己的长期主义名单**。

## 接入 LLM（可选增强）

未配置时报告输出数据驱动模板；配置后会自动补充「专家解读 / 组合点评」：

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"   # 默认值，可省
$env:DEEPSEEK_MODEL = "deepseek-chat"
```

或复制 `.env.example` 为 `.env` 填写（`.env` 已 gitignore）。

## 输出位置

所有报告生成在 `reports/<日期_星期>/` 子目录（如 `reports/2026-09-21_周一/`），
同时输出 **.docx(Word)** 与 **.md**。

## 数据来源

- 行情：腾讯行情 `qt.gtimg.cn`
- 主力资金 / 52周极值 / 行业板块：东方财富 `push2delay.eastmoney.com`
- 财务数据：东方财富 `datacenter.eastmoney.com`
- 新闻：东方财富 / 财联社 / 新浪
- 专家解读：DeepSeek

## 几点说明（刻意从简）

- **记忆层**用本地 `data/*.json` 逐日快照，双周任务直接读近 14 天文件召回。若日后需要**语义检索**再升级为向量库。
- **北向逐日净流向**自 2024-08 起不再实时披露，脚本以**主力净流入**作代理并明确标注。
- **卖方覆盖**未自动抓券商研报库，仅按新闻关键词粗分类；严谨起见建议人工核验或补数据源。
- **估值分位**用 52 周区间近似。
- **定时推送已移除**：Windows 计划任务已删除，`install_scheduler.ps1` 不再包含在仓库。

> 本内容基于公开信息整理，不构成任何投资建议，股市有风险，入市需谨慎。