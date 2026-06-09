#!/usr/bin/env python3
"""Build and optionally email a daily IEEE article digest.

The script intentionally sends links to original abstract pages instead of
copying complete abstracts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.message
import html
import json
import os
import smtplib
import ssl
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


CROSSREF_API = "https://api.crossref.org/journals/{issn}/works"
USER_AGENT = "daily-ieee-digest/1.0 (mailto:maplesoda251796@163.com)"


@dataclass(frozen=True)
class Candidate:
    title: str
    journal: str
    journal_key: str
    doi: str
    url: str
    published: str
    metrics: dict[str, Any]
    score: int


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_json(url: str, retries: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def first_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0]).strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def published_date(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            vals = [str(v) for v in parts[0]]
            while len(vals) < 3:
                vals.append("01")
            return "-".join(vals[:3])
    return "unknown"


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def topic_score(title: str, include: list[str], exclude: list[str]) -> int:
    normalized = normalize(title)
    if any(normalize(keyword) in normalized for keyword in exclude):
        return -100
    score = 0
    for keyword in include:
        if normalize(keyword) in normalized:
            score += 2
    return score


def crossref_url(issn: str, from_date: str, rows: int) -> str:
    params = {
        "filter": f"from-pub-date:{from_date},type:journal-article",
        "sort": "published",
        "order": "desc",
        "rows": str(rows),
        "select": "DOI,title,container-title,published,published-online,published-print,URL",
    }
    return f"{CROSSREF_API.format(issn=urllib.parse.quote(issn))}?{urllib.parse.urlencode(params)}"


def collect_candidates(config: dict[str, Any], days_back: int, rows_per_journal: int) -> list[Candidate]:
    from_date = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()
    include = config.get("include_keywords", [])
    exclude = config.get("exclude_keywords", [])
    candidates: list[Candidate] = []

    for journal in config["journals"]:
        issns = [journal.get("issn"), journal.get("eissn")]
        seen_dois: set[str] = set()
        for issn in [i for i in issns if i]:
            data = get_json(crossref_url(issn, from_date, rows_per_journal))
            for item in data.get("message", {}).get("items", []):
                title = first_text(item.get("title"))
                doi = str(item.get("DOI", "")).strip()
                if not title or not doi or doi.lower() in seen_dois:
                    continue
                seen_dois.add(doi.lower())
                journal_title = first_text(item.get("container-title")) or journal["title"]
                score = topic_score(title, include, exclude)
                if score < 1:
                    continue
                candidates.append(
                    Candidate(
                        title=title,
                        journal=journal_title,
                        journal_key=journal["key"],
                        doi=doi,
                        url=item.get("URL") or f"https://doi.org/{doi}",
                        published=published_date(item),
                        metrics=journal["metrics"],
                        score=score,
                    )
                )
    return sorted(candidates, key=lambda c: (c.published, c.score), reverse=True)


def select_articles(candidates: list[Candidate], limit: int) -> list[Candidate]:
    selected: list[Candidate] = []
    seen_titles: set[str] = set()
    for item in candidates:
        title_key = normalize(item.title)
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def render_text(articles: list[Candidate]) -> str:
    today = dt.date.today().isoformat()
    lines = [
        f"Daily IEEE Electronic and Communication Digest - {today}",
        "",
        "完整原文摘要不在邮件中复制；请打开每篇文章的 DOI / IEEE Xplore / 来源链接查看。",
        "",
    ]
    for idx, item in enumerate(articles, 1):
        metrics = item.metrics
        lines.extend(
            [
                f"{idx}. {item.title}",
                f"期刊: {item.journal} ({item.journal_key})",
                f"发表/在线日期: {item.published}",
                f"分区: {metrics['system']} {metrics['year']} {metrics['quartile']}",
                f"影响因子: {metrics['impact_factor']} ({metrics['source']})",
                f"影响因子/分区来源: {metrics['source_url']}",
                f"DOI: https://doi.org/{item.doi}",
                f"摘要/文章直达链接: {item.url}",
                "摘要说明: 因版权限制不复制完整原文摘要，请打开上方链接查看。",
                "",
            ]
        )
    if not articles:
        lines.append("未能找到满足条件且元数据可靠的文章。请检查网络或扩大检索范围。")
    return "\n".join(lines)


def render_html(articles: list[Candidate]) -> str:
    today = dt.date.today().isoformat()
    blocks = [
        f"<h2>Daily IEEE Electronic and Communication Digest - {html.escape(today)}</h2>",
        "<p>完整原文摘要不在邮件中复制；请打开每篇文章的 DOI / IEEE Xplore / 来源链接查看。</p>",
    ]
    for idx, item in enumerate(articles, 1):
        metrics = item.metrics
        blocks.append(
            textwrap.dedent(
                f"""
                <h3>{idx}. {html.escape(item.title)}</h3>
                <ul>
                  <li><b>期刊:</b> {html.escape(item.journal)} ({html.escape(item.journal_key)})</li>
                  <li><b>发表/在线日期:</b> {html.escape(item.published)}</li>
                  <li><b>分区:</b> {html.escape(metrics['system'])} {html.escape(str(metrics['year']))} {html.escape(metrics['quartile'])}</li>
                  <li><b>影响因子:</b> {html.escape(metrics['impact_factor'])} ({html.escape(metrics['source'])})</li>
                  <li><b>影响因子/分区来源:</b> <a href="{html.escape(metrics['source_url'])}">{html.escape(metrics['source_url'])}</a></li>
                  <li><b>DOI:</b> <a href="https://doi.org/{html.escape(item.doi)}">https://doi.org/{html.escape(item.doi)}</a></li>
                  <li><b>摘要/文章直达链接:</b> <a href="{html.escape(item.url)}">{html.escape(item.url)}</a></li>
                  <li><b>摘要说明:</b> 因版权限制不复制完整原文摘要，请打开上方链接查看。</li>
                </ul>
                """
            ).strip()
        )
    if not articles:
        blocks.append("<p>未能找到满足条件且元数据可靠的文章。请检查网络或扩大检索范围。</p>")
    return "\n".join(blocks)


def send_email(subject: str, text_body: str, html_body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    mail_to = os.environ["MAIL_TO"]
    mail_from = os.environ.get("MAIL_FROM") or user

    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if port in (465, 994):
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.send_message(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/journals.json")
    parser.add_argument("--send", action="store_true", help="Send email via SMTP.")
    parser.add_argument("--days-back", type=int, default=int(os.environ.get("DIGEST_DAYS_BACK", "1095")))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("DIGEST_MAX_ARTICLES", "2")))
    parser.add_argument("--rows-per-journal", type=int, default=30)
    args = parser.parse_args()

    config = load_config(args.config)
    candidates = collect_candidates(config, args.days_back, args.rows_per_journal)
    articles = select_articles(candidates, args.limit)
    text_body = render_text(articles)
    html_body = render_html(articles)

    print(text_body)
    if args.send:
        subject = f"IEEE电子通信论文摘要链接 - {dt.date.today().isoformat()}"
        send_email(subject, text_body, html_body)
        print("\nEmail sent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyError as exc:
        print(f"Missing required environment variable: {exc}", file=sys.stderr)
        raise SystemExit(2)
