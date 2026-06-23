#!/usr/bin/env python3
"""Build and optionally email a daily IEEE article digest."""

from __future__ import annotations

import argparse
import datetime as dt
import email.message
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
import sys
import textwrap
import time
from html.parser import HTMLParser
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo


CROSSREF_API = "https://api.crossref.org/journals/{issn}/works"
OPENALEX_WORKS_API = "https://api.openalex.org/works/{work_id}"
USER_AGENT = "daily-ieee-digest/1.0 (mailto:maplesoda251796@163.com)"
NON_ARTICLE_TITLE_PATTERNS = (
    "publication information",
    "information for authors",
    "for authors",
    "call for papers",
    "editorial",
    "guest editorial",
    "erratum",
    "correction to",
    "corrections to",
    "table of contents",
    "about this issue",
    "preface",
)


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
    authors: str
    abstract: str


class MetaTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_tags: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        normalized: dict[str, str] = {}
        for key, value in attrs:
            if key and value is not None:
                normalized[key.lower()] = value
        if normalized:
            self.meta_tags.append(normalized)


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"sent": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("sent"), list):
        raise ValueError(f"Invalid history file: {path}")
    return data


def history_dois(history: dict[str, Any]) -> set[str]:
    return {
        str(item.get("doi", "")).lower()
        for item in history.get("sent", [])
        if isinstance(item, dict) and item.get("doi")
    }


def history_digest_dates(history: dict[str, Any]) -> set[str]:
    digest_dates = {
        str(item.get("date", ""))
        for item in history.get("digests", [])
        if isinstance(item, dict) and item.get("date")
    }
    sent_dates = {
        str(item.get("date", ""))
        for item in history.get("sent", [])
        if isinstance(item, dict) and item.get("date")
    }
    return digest_dates | sent_dates


def local_now(timezone_name: str) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(timezone_name))


def should_skip_for_daily_window(
    history: dict[str, Any],
    timezone_name: str,
    not_before: str,
    once_per_date: bool,
) -> str | None:
    now = local_now(timezone_name)
    hour, minute = [int(part) for part in not_before.split(":", 1)]
    earliest = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < earliest:
        return f"Skip: local time {now:%Y-%m-%d %H:%M} is before {not_before} {timezone_name}."
    if once_per_date and now.date().isoformat() in history_digest_dates(history):
        return f"Skip: digest already sent for {now.date().isoformat()}."
    return None


def update_history(path: str, history: dict[str, Any], articles: list["Candidate"], timezone_name: str) -> None:
    sent = history.setdefault("sent", [])
    digests = history.setdefault("digests", [])
    existing = history_dois(history)
    now = local_now(timezone_name)
    today = now.date().isoformat()
    for article in articles:
        doi_key = article.doi.lower()
        if doi_key in existing:
            continue
        sent.append(
            {
                "date": today,
                "doi": article.doi,
                "title": article.title,
                "journal": article.journal,
                "url": article.url,
            }
        )
        existing.add(doi_key)
    if today not in history_digest_dates(history):
        digests.append({"date": today, "sent_at": now.isoformat(timespec="seconds")})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")


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


def get_text(url: str, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
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
            values = [str(v) for v in parts[0]]
            while len(values) < 3:
                values.append("01")
            return "-".join(values[:3])
    return "unknown"


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def is_likely_non_article_title(title: str) -> bool:
    normalized = normalize(title)
    return any(pattern in normalized for pattern in NON_ARTICLE_TITLE_PATTERNS)


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
        "select": "DOI,title,container-title,published,published-online,published-print,URL,author,abstract",
    }
    return f"{CROSSREF_API.format(issn=urllib.parse.quote(issn))}?{urllib.parse.urlencode(params)}"


def openalex_url(doi: str) -> str:
    work_id = urllib.parse.quote(f"https://doi.org/{doi}", safe="")
    return OPENALEX_WORKS_API.format(work_id=work_id)


def extract_authors(item: dict[str, Any]) -> str:
    authors: list[str] = []
    for author in item.get("author", []):
        if not isinstance(author, dict):
            continue
        given = str(author.get("given", "")).strip()
        family = str(author.get("family", "")).strip()
        name = str(author.get("name", "")).strip()
        full_name = " ".join(part for part in (given, family) if part).strip()
        if full_name:
            authors.append(full_name)
        elif name:
            authors.append(name)
        elif family:
            authors.append(family)
    return ", ".join(authors)


def clean_abstract(raw_abstract: Any) -> str:
    if not isinstance(raw_abstract, str):
        return ""
    text = html.unescape(raw_abstract)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def extract_abstract_from_html(page_text: str) -> str:
    parser = MetaTagParser()
    parser.feed(page_text)
    preferred_keys = (
        ("name", "citation_abstract"),
        ("property", "citation_abstract"),
        ("name", "dc.description"),
        ("property", "og:description"),
        ("name", "description"),
    )
    for attr_name, attr_value in preferred_keys:
        for meta in parser.meta_tags:
            if meta.get(attr_name, "").lower() == attr_value:
                content = meta.get("content", "").strip()
                if content:
                    return clean_abstract(content)
    return ""


def fetch_landing_page_abstract(url: str) -> str:
    try:
        return extract_abstract_from_html(get_text(url))
    except RuntimeError:
        return ""


def abstract_from_inverted_index(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    max_position = max(
        (position for positions in inverted_index.values() if isinstance(positions, list) for position in positions),
        default=-1,
    )
    if max_position < 0:
        return ""
    words: list[str] = [""] * (max_position + 1)
    for word, positions in inverted_index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and 0 <= position <= max_position:
                words[position] = word
    return clean_abstract(" ".join(word for word in words if word))


def fetch_openalex_abstract(doi: str) -> str:
    try:
        data = get_json(openalex_url(doi))
    except RuntimeError:
        return ""
    return abstract_from_inverted_index(data.get("abstract_inverted_index"))


def resolve_abstract(item: dict[str, Any], url: str, doi: str) -> str:
    abstract = clean_abstract(item.get("abstract"))
    if abstract:
        return abstract
    abstract = fetch_landing_page_abstract(url)
    if abstract:
        return abstract
    return fetch_openalex_abstract(doi)


def select_daily_journal(journals: list[dict[str, Any]], run_date: dt.date) -> dict[str, Any]:
    if not journals:
        raise ValueError("At least one journal is required.")
    day_key = run_date.isoformat().encode("utf-8")
    digest = hashlib.sha256(day_key).digest()
    index = int.from_bytes(digest[:8], "big") % len(journals)
    return journals[index]


def collect_candidates(
    config: dict[str, Any],
    days_back: int,
    rows_per_journal: int,
    resolve_abstracts: bool = True,
    selected_journal_keys: set[str] | None = None,
) -> list[Candidate]:
    from_date = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()
    include = config.get("include_keywords", [])
    exclude = config.get("exclude_keywords", [])
    candidates: list[Candidate] = []

    for journal in config["journals"]:
        if selected_journal_keys is not None and journal["key"] not in selected_journal_keys:
            continue
        issns = [journal.get("issn"), journal.get("eissn")]
        seen_dois: set[str] = set()
        for issn in [value for value in issns if value]:
            data = get_json(crossref_url(issn, from_date, rows_per_journal))
            for item in data.get("message", {}).get("items", []):
                title = first_text(item.get("title"))
                doi = str(item.get("DOI", "")).strip()
                if not title or not doi or doi.lower() in seen_dois:
                    continue
                seen_dois.add(doi.lower())
                authors = extract_authors(item)
                if not authors or is_likely_non_article_title(title):
                    continue
                score = topic_score(title, include, exclude)
                if score < 1:
                    continue
                journal_title = first_text(item.get("container-title")) or journal["title"]
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
                        authors=authors,
                        abstract=(
                            resolve_abstract(item, item.get("URL") or f"https://doi.org/{doi}", doi)
                            if resolve_abstracts
                            else ""
                        ),
                    )
                )
    return sorted(candidates, key=lambda c: (c.published, c.score), reverse=True)


def enrich_candidates_with_abstracts(candidates: list[Candidate]) -> list[Candidate]:
    enriched: list[Candidate] = []
    for candidate in candidates:
        abstract = candidate.abstract or resolve_abstract({}, candidate.url, candidate.doi)
        enriched.append(
            Candidate(
                title=candidate.title,
                journal=candidate.journal,
                journal_key=candidate.journal_key,
                doi=candidate.doi,
                url=candidate.url,
                published=candidate.published,
                metrics=candidate.metrics,
                score=candidate.score,
                authors=candidate.authors,
                abstract=abstract,
            )
        )
    return enriched


def select_articles(candidates: list[Candidate], limit: int, excluded_dois: set[str] | None = None) -> list[Candidate]:
    selected: list[Candidate] = []
    seen_titles: set[str] = set()
    excluded = excluded_dois or set()
    for item in candidates:
        if item.doi.lower() in excluded:
            continue
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
    ]
    for idx, item in enumerate(articles, 1):
        metrics = item.metrics
        abstract = item.abstract or "Abstract unavailable from metadata source."
        lines.extend(
            [
                f"{idx}. {item.title}",
                f"Journal: {item.journal} ({item.journal_key})",
                f"Authors: {item.authors}",
                f"Published: {item.published}",
                f"Quartile: {metrics['system']} {metrics['year']} {metrics['quartile']}",
                f"Impact Factor: {metrics['impact_factor']} ({metrics['source']})",
                f"Metrics Source: {metrics['source_url']}",
                f"DOI: https://doi.org/{item.doi}",
                f"Article Link: {item.url}",
                f"Abstract: {abstract}",
                "",
            ]
        )
    if not articles:
        lines.append("No qualifying papers were found from the current metadata sources.")
    return "\n".join(lines)


def render_html(articles: list[Candidate]) -> str:
    today = dt.date.today().isoformat()
    blocks = [
        f"<h2>Daily IEEE Electronic and Communication Digest - {html.escape(today)}</h2>",
    ]
    for idx, item in enumerate(articles, 1):
        metrics = item.metrics
        abstract = item.abstract or "Abstract unavailable from metadata source."
        blocks.append(
            textwrap.dedent(
                f"""
                <h3>{idx}. {html.escape(item.title)}</h3>
                <ul>
                  <li><b>Journal:</b> {html.escape(item.journal)} ({html.escape(item.journal_key)})</li>
                  <li><b>Authors:</b> {html.escape(item.authors)}</li>
                  <li><b>Published:</b> {html.escape(item.published)}</li>
                  <li><b>Quartile:</b> {html.escape(metrics['system'])} {html.escape(str(metrics['year']))} {html.escape(metrics['quartile'])}</li>
                  <li><b>Impact Factor:</b> {html.escape(metrics['impact_factor'])} ({html.escape(metrics['source'])})</li>
                  <li><b>Metrics Source:</b> <a href="{html.escape(metrics['source_url'])}">{html.escape(metrics['source_url'])}</a></li>
                  <li><b>DOI:</b> <a href="https://doi.org/{html.escape(item.doi)}">https://doi.org/{html.escape(item.doi)}</a></li>
                  <li><b>Article Link:</b> <a href="{html.escape(item.url)}">{html.escape(item.url)}</a></li>
                  <li><b>Abstract:</b> {html.escape(abstract)}</li>
                </ul>
                """
            ).strip()
        )
    if not articles:
        blocks.append("<p>No qualifying papers were found from the current metadata sources.</p>")
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
    parser.add_argument("--rows-per-journal", type=int, default=int(os.environ.get("DIGEST_ROWS_PER_JOURNAL", "100")))
    parser.add_argument("--history", default="data/sent_history.json")
    parser.add_argument("--update-history", action="store_true", help="Record successfully emailed DOIs.")
    parser.add_argument("--timezone", default=os.environ.get("DIGEST_TIMEZONE", "Asia/Shanghai"))
    parser.add_argument("--not-before", default=os.environ.get("DIGEST_NOT_BEFORE", "07:30"))
    parser.add_argument("--once-per-local-date", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    history = load_history(args.history)
    if args.once_per_local_date:
        skip_reason = should_skip_for_daily_window(
            history,
            args.timezone,
            args.not_before,
            once_per_date=True,
        )
        if skip_reason:
            print(skip_reason)
            return 0
    journals = [journal for journal in config["journals"] if journal.get("preferred", True)]
    selected_journal = select_daily_journal(journals, local_now(args.timezone).date())
    candidates = collect_candidates(
        config,
        args.days_back,
        args.rows_per_journal,
        resolve_abstracts=False,
        selected_journal_keys={selected_journal["key"]},
    )
    articles = select_articles(candidates, args.limit, history_dois(history))
    articles = enrich_candidates_with_abstracts(articles)
    text_body = render_text(articles)
    html_body = render_html(articles)

    print(text_body)
    if args.send:
        subject = f"IEEE电子通信论文摘要 - {local_now(args.timezone).date().isoformat()}"
        send_email(subject, text_body, html_body)
        if args.update_history:
            update_history(args.history, history, articles, args.timezone)
        print("\nEmail sent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyError as exc:
        print(f"Missing required environment variable: {exc}", file=sys.stderr)
        raise SystemExit(2)
