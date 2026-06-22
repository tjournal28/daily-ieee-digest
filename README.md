# Daily IEEE Digest

## 2026-06-22 behavior update

Daily IEEE Digest 是一个基于 GitHub Actions 的论文邮件推送工具。它会在云端定时检索指定期刊的近年论文，按关键词筛选方向，生成摘要链接型邮件，并通过 SMTP 发送到指定邮箱。

这个仓库当前示例配置用于每天推送 IEEE 电子、通信方向论文，
比如我想要检索以下三种SCI一区期刊：
- IEEE Transactions on Wireless Communications (TWC)
- IEEE Transactions on Antennas and Propagation (TAP)
- IEEE Transactions on Microwave Theory and Techniques (TMTT)

邮件默认包含：

- 文章名
- 期刊名
- 发表或在线日期
- 分区和影响因子
- 分区和影响因子来源链接
- DOI 链接
- 摘要

## 使用方法

### 1. 前置条件

你需要准备：

- 一个 GitHub 仓库。
- GitHub Actions 已启用。
- 一个可用于发信的邮箱账号。
- 邮箱的 SMTP 服务已开启。
- 邮箱客户端授权码。不要使用邮箱登录密码。
- 授权码设置方法
- 163邮箱移动端
 打开网易-右下角 我-邮箱管理-点击自己的使用邮箱-第三方登录管理-设置通用授权码
<img width="1080" height="2400" alt="b1b37c7f3b178d4b7016c7dd65a46042" src="https://github.com/user-attachments/assets/8267e810-fffd-437a-ab19-92f770eeb9ce" />

- Python 3.11。本地测试时需要；GitHub Actions 会自动安装。

推荐先 fork 或复制本仓库，然后在自己的仓库中修改配置。

### 2. 修改检索的期刊和领域

核心配置文件是：

```text
config/journals.json
```

它包含三部分：

- `journals`：指定要检索的期刊。
- `include_keywords`：指定保留方向的关键词。
- `exclude_keywords`：指定排除方向的关键词。

#### 修改具体期刊

在 `journals` 数组中添加或修改期刊对象：

```json
{
  "key": "TWC",
  "title": "IEEE Transactions on Wireless Communications",
  "issn": "1536-1276",
  "eissn": "1558-2248",
  "preferred": true,
  "metrics": {
    "system": "JCR-JIF",
    "year": 2024,
    "impact_factor": "8.9",
    "quartile": "Q1",
    "source": "IEEE Title List August 2024",
    "source_url": "https://open.ieee.org/wp-content/uploads/IEEE-Title-List-August-2024.pdf"
  }
}
```

字段说明：

- `key`：简写名，用于邮件中显示。
- `title`：完整期刊名。
- `issn`：纸质版 ISSN。
- `eissn`：电子版 ISSN。
- `metrics.system`：分区或指标体系，例如 `JCR-JIF`、`CAS`。
- `metrics.year`：指标年份。
- `metrics.impact_factor`：影响因子。
- `metrics.quartile`：分区。
- `metrics.source`：数据来源名称。
- `metrics.source_url`：数据来源链接。

脚本通过 Crossref 的 journal works API 检索论文，所以 ISSN 或 EISSN 很关键。更换期刊时，建议先到 Crossref、IEEE Xplore、期刊官网或 Web of Science 信息页确认 ISSN。

#### 修改研究方向

`include_keywords` 决定保留哪些方向。例如当前配置偏电子、通信：

```json
"include_keywords": [
  "antenna",
  "beamforming",
  "communication",
  "mimo",
  "microwave",
  "radar",
  "wireless"
]
```

如果你想改成电力电子方向，可以改成类似：

```json
"include_keywords": [
  "converter",
  "inverter",
  "power electronics",
  "motor drive",
  "dc-dc",
  "grid-connected"
]
```

`exclude_keywords` 用于排除不想要的方向。例如当前配置排除明显偏材料、化学、生物材料的文章：

```json
"exclude_keywords": [
  "bio",
  "chemical",
  "materials",
  "polymer",
  "thin film"
]
```

如果你希望材料方向也进入推送，就删除或减少这些排除词。

### 3. 修改每天发送几篇、检索多长时间范围

这些参数在 GitHub Actions workflow 中配置：

```text
.github/workflows/daily-ieee-digest.yml
```

当前配置：

```yaml
DIGEST_DAYS_BACK: "1095"
DIGEST_MAX_ARTICLES: "2"
DIGEST_ROWS_PER_JOURNAL: "100"
```

含义：

- `DIGEST_DAYS_BACK`：向前检索多少天。`1095` 约等于近 3 年。
- `DIGEST_MAX_ARTICLES`：每封邮件最多发送几篇文章。
- `DIGEST_ROWS_PER_JOURNAL`：每个期刊从 Crossref 拉取多少条候选结果。

如果你想每天发 5 篇，改成：

```yaml
DIGEST_MAX_ARTICLES: "5"
```

### 4. 修改发送时间

GitHub Actions 的 `schedule.cron` 使用 UTC 时间，不是北京时间。

当前配置包含一个主触发和几个备份触发：

```yaml
on:
  schedule:
    # Primary 08:00 Beijing time (UTC+8).
    - cron: "0 0 * * *"
    # Backup wake-ups.
    - cron: "0 20 * * *"
    - cron: "0 21 * * *"
    - cron: "0 22 * * *"
    - cron: "0 23 * * *"
```

`0 0 * * *` 表示 UTC 00:00，也就是北京时间 08:00。

备份触发用于应对 GitHub Actions 定时任务可能延迟数小时的问题。脚本内部还设置了：

```yaml
DIGEST_TIMEZONE: "Asia/Shanghai"
DIGEST_NOT_BEFORE: "07:30"
```

并且运行命令带有：

```bash
--once-per-local-date
```

这意味着：

- 北京时间 07:30 前触发会自动跳过。
- 同一个北京时间日期只会发送一次。
- 后续备份触发不会重复发邮件。

如果你想改成北京时间每天 21:30 发送，可以设置：

```yaml
- cron: "30 13 * * *"
```

因为北京时间 21:30 = UTC 13:30。

同时建议把窗口改成：

```yaml
DIGEST_NOT_BEFORE: "21:00"
```

### 5. 指定收件邮箱和发件邮箱

邮箱参数不要写进代码或 README。请使用 GitHub Secrets。

进入你的 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

添加以下 Secrets：

```text
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=你的发件邮箱
SMTP_PASS=你的邮箱客户端授权码
MAIL_TO=你的收件邮箱
```

可选：

```text
MAIL_FROM=你的发件邮箱
```

如果不配置 `MAIL_FROM`，脚本默认使用 `SMTP_USER` 作为发件人。

#### 以 163 邮箱为例

1. 登录 163 邮箱网页版。
2. 进入设置，找到 `POP3/SMTP/IMAP` 或客户端授权相关设置。
3. 开启 `POP3/SMTP` 或 `IMAP/SMTP` 服务。
4. 按页面提示生成客户端授权码。
5. 把授权码填入 GitHub Secret `SMTP_PASS`。
6. 不要把授权码提交到仓库，也不要写进 README。

163 邮箱常用配置：

```text
SMTP_HOST=smtp.163.com
SMTP_PORT=465
```

如果你使用 QQ 邮箱、Gmail、Outlook 或企业邮箱，需要改成对应服务商的 SMTP 地址、端口和授权方式。

### 6. 手动测试

#### 在 GitHub 上测试

进入仓库：

```text
Actions -> Daily IEEE Digest -> Run workflow
```

运行完成后查看日志。成功时会出现：

```text
Email sent.
```

如果当天已经发送过，并且启用了 `--once-per-local-date`，日志会显示：

```text
Skip: digest already sent for YYYY-MM-DD.
```

#### 在本地只预览、不发邮件

```bash
python scripts/daily_ieee_digest.py --config config/journals.json
```

#### 在本地通过 SMTP 发邮件测试

PowerShell 示例：

```powershell
$env:SMTP_HOST="smtp.163.com"
$env:SMTP_PORT="465"
$env:SMTP_USER="your_sender@163.com"
$env:SMTP_PASS="your_smtp_authorization_code"
$env:MAIL_TO="your_receiver@example.com"
python scripts\daily_ieee_digest.py --config config\journals.json --send
```

也可以使用交互式测试脚本，授权码只在当前进程临时使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\send_test_163.ps1
```

### 7. 去重机制

脚本会把已发送论文 DOI 写入：

```text
data/sent_history.json
```

后续运行会跳过已经发送过的 DOI，避免每天重复推同一篇文章。

GitHub Actions 成功发邮件后，会自动提交这个历史文件：

```yaml
- name: Commit sent history
```

因此 workflow 需要：

```yaml
permissions:
  contents: write
```

如果你不希望自动写回仓库，可以去掉 `--update-history` 和 `Commit sent history` 步骤，但这样会失去跨天去重能力。

## 示例

### 示例 1：当前仓库配置

当前仓库用于推送 IEEE 电子、通信方向论文：

```text
期刊：TWC / TAP / TMTT
方向：antenna, beamforming, communication, mimo, microwave, radar, wireless 等
时间：北京时间每天 08:00 附近
每次：2 篇
邮箱：通过 GitHub Secrets 中的 163 SMTP 配置发送
```

当前 GitHub Actions 关键配置：

```yaml
on:
  schedule:
    - cron: "0 0 * * *"
    - cron: "0 20 * * *"
    - cron: "0 21 * * *"
    - cron: "0 22 * * *"
    - cron: "0 23 * * *"

env:
  DIGEST_DAYS_BACK: "1095"
  DIGEST_MAX_ARTICLES: "2"
  DIGEST_ROWS_PER_JOURNAL: "100"
  DIGEST_TIMEZONE: "Asia/Shanghai"
  DIGEST_NOT_BEFORE: "07:30"
```

### 示例 2：改成每天晚上 21:30 发送

修改 `.github/workflows/daily-ieee-digest.yml`：

```yaml
on:
  schedule:
    - cron: "30 13 * * *"
```

并设置：

```yaml
DIGEST_NOT_BEFORE: "21:00"
```

### 示例 3：改成每天发送 5 篇

修改：

```yaml
DIGEST_MAX_ARTICLES: "5"
```

如果候选论文不够，可以适当提高：

```yaml
DIGEST_ROWS_PER_JOURNAL: "200"
```

### 示例 4：改成其他期刊

在 `config/journals.json` 中替换 `journals`：

```json
{
  "key": "TVT",
  "title": "IEEE Transactions on Vehicular Technology",
  "issn": "0018-9545",
  "eissn": "1939-9359",
  "preferred": true,
  "metrics": {
    "system": "JCR-JIF",
    "year": 2024,
    "impact_factor": "请自行填写",
    "quartile": "请自行填写",
    "source": "请自行填写来源",
    "source_url": "请自行填写来源链接"
  }
}
```

同时调整关键词：

```json
"include_keywords": [
  "vehicular",
  "v2x",
  "wireless",
  "communication",
  "network"
]
```

## 常见问题

### 为什么不是严格准点发送？

GitHub Actions 的 `schedule` 不是实时闹钟，可能延迟。仓库当前通过多个备份 cron 加脚本内每日去重，尽量提高在目标时间附近发送的概率。

### 为什么需要写回 `sent_history.json`？

因为 GitHub Actions 每次运行都是新的云端环境。如果不把已发送 DOI 保存回仓库，下一次运行无法知道哪些论文已经发过。

### 授权码泄露了怎么办？

立即到邮箱后台删除或重新生成授权码，然后更新 GitHub Secret `SMTP_PASS`。
