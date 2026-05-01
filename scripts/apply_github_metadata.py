from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META_FILE = ROOT / '.github' / 'repository-metadata.json'


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def get_repo_slug() -> str:
    origin = subprocess.check_output(
        ['git', '-C', str(ROOT), 'remote', 'get-url', 'origin'],
        text=True,
    ).strip()
    m = re.search(r'github\.com[:/](.+?)(?:\.git)?$', origin)
    if not m:
        fail(f'cannot parse GitHub repo from origin: {origin}')
    return m.group(1)


def api_request(url: str, method: str, token: str, payload: dict) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method=method,
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': 'android-reverse-mcp-metadata-updater',
        },
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status >= 300:
            fail(f'GitHub API request failed: {resp.status}')


def main() -> None:
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        fail('GITHUB_TOKEN is required')
    meta = json.loads(META_FILE.read_text())
    slug = get_repo_slug()
    base = f'https://api.github.com/repos/{slug}'
    api_request(
        base,
        'PATCH',
        token,
        {
            'description': meta['description'],
            'homepage': meta['homepage'],
        },
    )
    api_request(
        f'{base}/topics',
        'PUT',
        token,
        {
            'names': meta['topics'],
        },
    )
    print(f'updated GitHub metadata for {slug}')


if __name__ == '__main__':
    main()
