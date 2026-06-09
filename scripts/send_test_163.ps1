param(
    [string]$SmtpHost = "smtp.163.com",
    [int]$SmtpPort = 465,
    [string]$MailTo = "maplesoda251796@163.com"
)

$ErrorActionPreference = "Stop"

$smtpUser = Read-Host "Enter your 163 sender email"
$smtpPassSecure = Read-Host "Enter your 163 SMTP authorization code" -AsSecureString
$smtpPassPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPassSecure)
)

try {
    $env:SMTP_HOST = $SmtpHost
    $env:SMTP_PORT = [string]$SmtpPort
    $env:SMTP_USER = $smtpUser
    $env:SMTP_PASS = $smtpPassPlain
    $env:MAIL_TO = $MailTo
    $env:MAIL_FROM = $smtpUser

    python scripts\daily_ieee_digest.py --config config\journals.json --send
}
finally {
    Remove-Item Env:\SMTP_HOST -ErrorAction SilentlyContinue
    Remove-Item Env:\SMTP_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\SMTP_USER -ErrorAction SilentlyContinue
    Remove-Item Env:\SMTP_PASS -ErrorAction SilentlyContinue
    Remove-Item Env:\MAIL_TO -ErrorAction SilentlyContinue
    Remove-Item Env:\MAIL_FROM -ErrorAction SilentlyContinue
    $smtpPassPlain = $null
}
