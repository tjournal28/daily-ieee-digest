# Daily IEEE Digest

这个仓库用于云端定时推送 IEEE 电子、通信方向论文信息到邮箱。默认每天北京时间 08:00 运行一次，不依赖本机 Codex 是否在线。

## 推送内容

每天筛选 2 篇近 3 年内的 IEEE 期刊文章，优先：

- IEEE Transactions on Wireless Communications (TWC)
- IEEE Transactions on Antennas and Propagation (TAP)
- IEEE Transactions on Microwave Theory and Techniques (TMTT)

邮件包含：

- 文章名
- 期刊名
- 发表/在线日期
- JCR 分区和影响因子
- 影响因子/分区来源链接
- DOI 链接
- 摘要/文章直达链接

邮件不会复制完整英文摘要。请打开 DOI、IEEE Xplore 或来源链接查看原文摘要。

## GitHub Secrets

在 GitHub 仓库进入 `Settings` -> `Secrets and variables` -> `Actions`，添加：

```text
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=你的163发件邮箱
SMTP_PASS=你的163邮箱客户端授权码
MAIL_TO=maplesoda251796@163.com
```

可选：

```text
MAIL_FROM=你的163发件邮箱
```

`SMTP_PASS` 必须使用 163 邮箱的客户端授权码，不要使用邮箱登录密码。

## 开启 163 SMTP

1. 登录 163 邮箱网页版。
2. 进入设置，找到 `POP3/SMTP/IMAP` 或客户端授权相关设置。
3. 开启 SMTP 服务。
4. 生成客户端授权码。
5. 将授权码填入 GitHub Secret `SMTP_PASS`。

## 手动测试

上传到 GitHub 后，进入 `Actions` -> `Daily IEEE Digest` -> `Run workflow`，可以立即手动运行一次。

本地只预览、不发邮件：

```bash
python scripts/daily_ieee_digest.py --config config/journals.json
```

本地发邮件测试需要先设置环境变量：

```powershell
$env:SMTP_HOST="smtp.163.com"
$env:SMTP_PORT="465"
$env:SMTP_USER="你的163发件邮箱"
$env:SMTP_PASS="你的163邮箱客户端授权码"
$env:MAIL_TO="maplesoda251796@163.com"
python scripts/daily_ieee_digest.py --config config/journals.json --send
```

也可以使用交互式 163 邮箱测试脚本，授权码只在当前进程临时使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\send_test_163.ps1
```

## 修改时间

`.github/workflows/daily-ieee-digest.yml` 中：

```yaml
cron: "0 0 * * *"
```

表示 UTC 00:00，也就是北京时间 08:00。
