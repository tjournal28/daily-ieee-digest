# Daily IEEE Digest

`Daily IEEE Digest` 是一个基于 GitHub Actions 的论文邮件推送工具。

我做这个项目的目的很简单：每天自动筛选几篇我关心方向的新论文，整理成一封短邮件发到邮箱里，这样不用反复手动刷 IEEE Xplore、Crossref 或期刊主页。

当前仓库的默认配置，面向 IEEE 电子与通信相关方向，固定跟踪下面 3 本期刊：

- IEEE Transactions on Wireless Communications (`TWC`)
- IEEE Transactions on Antennas and Propagation (`TAP`)
- IEEE Transactions on Microwave Theory and Techniques (`TMTT`)

脚本会从这些期刊里检索候选论文，再按关键词筛选，最后每天发送少量结果到邮箱。

## What The Email Contains

默认每封邮件包含：

- 论文标题
- 作者
- 摘要
- DOI 链接
- 期刊名
- 发表日期
- 分区和影响因子信息

为了避免误发无关内容，脚本还会自动过滤：

- `Publication Information`
- `Information for Authors`
- `editorial`
- `erratum`
- 其他明显不是论文正文的 front matter 页面

同时，系统会记录已经发送过的 DOI，避免后续重复发同一篇文章。

## Default Behavior

当前仓库默认行为如下：

- 每天发送 `2` 篇论文
- 关注电子、通信、天线、微波、雷达等方向
- 默认运行在 GitHub Actions 上
- 自动去重
- 自动补摘要

摘要获取顺序是：

1. Crossref
2. DOI / 落地页元数据
3. OpenAlex

也就是说，如果某个来源没有摘要，脚本会继续尝试后面的来源，而不是直接留空。

## If You Want To Use It

如果你也想把这个仓库跑起来，最少只需要做下面几步。

### 1. Fork 本仓库

点击 GitHub 右上角 `Fork`，复制到你自己的仓库。

### 2. 先配置邮箱

下面以 `163 邮箱` 为例说明。

如果你使用 163 邮箱，这几步是必须先做的：

1. 登录 163 邮箱网页版
2. 打开 `设置`
3. 找到 `POP3/SMTP/IMAP`
4. 开启 `SMTP`
5. 生成客户端授权码
6. 记下这个授权码，后面填 `SMTP_PASS` 时要用

### 3. 配置 GitHub Secrets

进入你的仓库：

`Settings -> Secrets and variables -> Actions -> New repository secret`

添加下面 5 个值：

```text
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=your_163_email@163.com
SMTP_PASS=your_163_smtp_authorization_code
MAIL_TO=your_receiver@example.com
```

可选：

```text
MAIL_FROM=your_163_email@163.com
```

如果不填，默认使用 `SMTP_USER` 作为发件人。

### 4. 手动运行一次

进入：

`Actions -> Daily IEEE Digest -> Run workflow`

如果日志里出现：

```text
Email sent.
```

说明已经配置成功。

## What You Usually Need To Modify

大多数人真正需要改的，通常只有 1 个文件：

`config/journals.json`

通常只看这 3 项：

- `journals`
- `include_keywords`
- `exclude_keywords`

### Change The Research Direction

如果你不想改期刊，只想改关键词方向，通常只需要改：

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

以及：

```json
"exclude_keywords": [
  "bio",
  "chemical",
  "materials",
  "polymer",
  "thin film"
]
```

## Local Preview

如果你想先在本地只预览、不发邮件：

```bash
python scripts/daily_ieee_digest.py --config config/journals.json
```

如果你想在本地直接测试 SMTP：

```powershell
$env:SMTP_HOST="smtp.163.com"
$env:SMTP_PORT="465"
$env:SMTP_USER="your_163_email@163.com"
$env:SMTP_PASS="your_163_smtp_authorization_code"
$env:MAIL_TO="your_receiver@example.com"
python scripts\daily_ieee_digest.py --config config\journals.json --send
```

也可以用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\send_test_163.ps1
```

## Advanced Configuration

如果你只是想“先跑起来”，这一节可以先跳过。

### Change Send Count

修改 `.github/workflows/daily-ieee-digest.yml` 里的：

```yaml
DIGEST_MAX_ARTICLES: "2"
```

例如改成每天 5 篇：

```yaml
DIGEST_MAX_ARTICLES: "5"
```

### Change Send Time

默认是北京时间早上 8 点附近。

如果你想改成北京时间 21:30，可以把 cron 改成：

```yaml
- cron: "30 13 * * *"
```

并建议同时把：

```yaml
DIGEST_NOT_BEFORE: "21:00"
```

### Change Search Range

默认配置：

```yaml
DIGEST_DAYS_BACK: "1095"
DIGEST_ROWS_PER_JOURNAL: "100"
```

含义：

- `DIGEST_DAYS_BACK`：向前检索多少天
- `DIGEST_ROWS_PER_JOURNAL`：每个期刊从 Crossref 拉多少候选记录

## FAQ

### 为什么不是严格整点发送？

GitHub Actions 的定时触发可能有延迟，所以 workflow 里用了主触发加备份触发，再结合本地日期去重，尽量保证每天只发一次。

### 为什么有时摘要来源不一样？

不同论文在不同元数据源上的完整度不一样。脚本会优先使用更直接的来源，如果拿不到，再自动回退到其他公开学术元数据源。

### 为什么不会重复发同一篇论文？

已经发送过的 DOI 会写入：

`data/sent_history.json`

后续运行时会自动跳过这些 DOI。

### 如果邮箱授权码泄露了怎么办？

去邮箱后台立即停用或重新生成授权码，然后更新仓库里的 `SMTP_PASS` secret。
