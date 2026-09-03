# A股科技长期主义观察池 · 投研 Agent

面向「中国科技长期主义」A 股观察池的定时投研工具，按 **事实(Fact)+逻辑(Logic)+预期(Expectation)** 产出可追溯报告。

## 生成的报告（Word 版，按日期+星期归档）

| 任务 | 触发时刻 | 产物 |
|---|---|---|
| 早间市场与行业要闻 | 每工作日 07:00 | 全球/中国主要指数 + 全球/中国/行业要闻分类 |
| 每日舆情雷达 | 每工作日 20:00 | 量价异动 / 公告速递 / 行业催化剂 / 卖方覆盖 |
| 双周投研备忘录 | 每月 1、16 日 20:00 | 消息面·技术面·估值水位·买卖建议 四维表格 |
| 本周板块归因复盘 | 每周五 16:00 | Top3 板块 + 归因 + 抽血/共振 + 下周前瞻 |

每份报告末尾固定带合规声明。LLM 输出强制「概率思维、假设句式、禁止绝对化」。

## 快速开始

```powershell
# 1) 安装依赖（需联网，可走代理 127.0.0.1:7890）
pip install -r requirements.txt

# 2) 离线跑通（不依赖 akshare / 网络）
python agent.py selftest
python agent.py daily --demo

# 3) 实盘跑（需已装 akshare 且有网）
python agent.py morning
python agent.py daily
python agent.py biweekly
python agent.py weekly
```

## 配置你的观察池

编辑 `config.json` 的 `watchlist`，`code` 为 6 位股票代码，`name` 为名称。默认给的 10 只是
占位样例（AI 算力/半导体/机器人/消费电子主线），**请替换成你自己的长期主义名单**。

## 接入 LLM（可选增强）

未配置时报告输出数据驱动模板；配置后会自动补充「综合研判」：

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"   # 默认值，可省
$env:DEEPSEEK_MODEL = "deepseek-chat"
```

## 定时调度（Windows 任务计划程序）

```powershell
powershell -ExecutionPolicy Bypass -File install_scheduler.ps1
```

会注册 `AshareMorning`(工作日07:00)、`AshareDaily`(工作日20:00)、`AshareBiweekly1/16`(每月1/16日20:00)、`AshareWeeklyFri`(周五16:00)。
若改用 Linux，可在 crontab 写入：`0 7 * * 1-5`、`0 20 * * 1-5`、`0 20 1,16 * *`、`0 16 * * 5`。

## 几点说明（刻意从简）

- **记忆层**用本地 `data/*.json` 逐日快照，双周任务直接读近 14 天文件召回。若日后需要**语义检索**再升级为向量库，
  当前场景用文件读取就够。 `ponytail: 文件记忆；若需跨时间语义召回再上 chromadb/sentence-transformers。`
- **北向逐日净流向**自 2024-08 起不再实时披露，脚本以**主力净流入**作代理并明确标注。
- **卖方覆盖**未自动抓券商研报库，仅按新闻关键词粗分类；严谨起见建议人工核验或补数据源。
- **估值分位**当前用 PE 阈值近似，真实近 3 年分位需拉序列，接口做好后替换 `biweekly_memo` 中的 `band`。
- **行情兜底**：akshare 取东财实时行情优先；若 egress 被限制则自动切换腾讯行情 qt.gtimg.cn（--noproxy 直连）。腾讯源不含量比与主力净流入，这两项显示 N/A；在本机正常终端里 akshare 可补齐。

- **输出落盘**：所有报告生成在 `reports/<日期_星期>/` 子文件夹，同时输出 **.docx(Word)** 与 `.md`；早间 07:00 为市场/行业要闻，晚间 20:00 为个股舆情报告。

> 本内容基于公开信息整理，不构成任何投资建议，股市有风险，入市需谨慎。