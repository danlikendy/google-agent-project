"""Build the public development tasks from GitHub pull requests.

The instance list is the published index of the Gemma 4 development set.
Issue text and the reference diff come from the public pull request, not from
the competition archive.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "gemma4_tasks_index.json"
OUT = ROOT / "data" / "gemma4_tasks.jsonl"
UA = {"User-Agent": "editslice-devset"}
FIX = re.compile(r"(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.I)


def get(url: str) -> str:
    last = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 + attempt * 3)
    raise RuntimeError(url) from last


def plain(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def first_comment(page: str) -> str:
    marker = 'class="comment-body markdown-body'
    start = page.find(marker)
    if start < 0:
        return ""
    div_start = page.rfind("<div", 0, start)
    depth = 0
    i = div_start
    end = div_start
    while i < len(page):
        if page.startswith("<div", i):
            depth += 1
            i = page.find(">", i)
            if i < 0:
                break
            i += 1
            continue
        if page.startswith("</div>", i):
            depth -= 1
            i += len("</div>")
            if depth == 0:
                end = i
                break
            continue
        i += 1
    inner_from = page.find(">", div_start) + 1
    return plain(page[inner_from:end])


def title_of(page: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, re.S)
    if not match:
        return ""
    title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return re.split(r"\s+by\s+|\s+·\s+", title)[0].strip()


def statement(owner: str, repo: str, number: str, seen: set[str]) -> str:
    key = f"{owner}/{repo}#{number}"
    if key in seen:
        return ""
    seen.add(key)
    page = get(f"https://github.com/{owner}/{repo}/pull/{number}")
    if "comment-body markdown-body" not in page:
        page = get(f"https://github.com/{owner}/{repo}/issues/{number}")
    body = first_comment(page)
    title = title_of(page)
    text = f"{title}\n\n{body}".strip()
    extra = []
    for linked in FIX.findall(text)[:2]:
        if linked == number:
            continue
        extra.append(statement(owner, repo, linked, seen))
    return "\n\n".join(part for part in [text, *extra] if part)


def main() -> int:
    if not INDEX.exists():
        INDEX.write_text(
            get(
                "https://huggingface.co/datasets/HIMANSHUKUMARJHA/"
                "gemma4-graph-retrieval-benchmark/resolve/main/results/tasks_index.json"
            ),
            encoding="utf-8",
        )
    rows = json.loads(INDEX.read_text(encoding="utf-8"))
    done = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("problem_statement") and row.get("patch"):
                    done[row["instance_id"]] = row
    with OUT.open("a", encoding="utf-8") as handle:
        for index, row in enumerate(rows, start=1):
            if row["instance_id"] in done:
                continue
            number = row["instance_id"].rsplit("_", 1)[1]
            owner, repo = row["repo"].split("/")
            patch = get(f"https://patch-diff.githubusercontent.com/raw/{owner}/{repo}/pull/{number}.diff")
            text = statement(owner, repo, number, set())
            item = {
                "instance_id": row["instance_id"],
                "repo": row["repo"],
                "base_commit": row["base_commit"],
                "problem_statement": text,
                "patch": patch,
            }
            handle.write(json.dumps(item) + "\n")
            handle.flush()
            print(f"[{index}/{len(rows)}] {row['instance_id']}  text={len(text)}  patch={len(patch)}", flush=True)
            time.sleep(0.2)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
