"""daikin_filter.py

mitmproxy addon script that filters, pretty-prints, and logs all
HTTPS traffic to Daikin cloud hosts.

Usage:
    mitmweb --mode wireguard --ssl-insecure -s tools/daikin_filter.py

Output:
    - Stdout: human-readable request/response summary (tokens redacted)
    - daikin_api.log: full timestamped log of every captured call
    - daikin_capture.json: append-mode JSON array for post-processing
"""

import json
import logging
import os
import re
from datetime import datetime
from mitmproxy import http

DAIKIN_HOSTS = [
    "scr.daikincloud.net",
    "daikinskyport.com",
    "daikincloud.net",
    "daikincomfort.com",
    "daikin.com",
]

SECRET_HEADERS = {"authorization", "authentication", "x-daikin-uid"}
OUTPUT_LOG  = "daikin_api.log"
OUTPUT_JSON = "daikin_capture.json"

logging.basicConfig(
    filename=OUTPUT_LOG,
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger("daikin_capture")

if not os.path.exists(OUTPUT_JSON):
    with open(OUTPUT_JSON, "w") as f:
        f.write("[]\n")


def _try_decode(data: bytes) -> object:
    """Decode bytes as JSON, URL-encoded form, or UTF-8 string."""
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        pass
    try:
        text = data.decode("utf-8", errors="replace")
        if "=" in text and "&" in text:
            from urllib.parse import parse_qs
            return parse_qs(text)
        return text.strip() or None
    except Exception:
        return data.hex()


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def response(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    if not any(h in host for h in DAIKIN_HOSTS):
        return

    req_body  = _try_decode(flow.request.content)
    resp_body = _try_decode(flow.response.content)

    entry = {
        "timestamp":        datetime.utcnow().isoformat() + "Z",
        "method":           flow.request.method,
        "url":              flow.request.pretty_url,
        "request_headers":  dict(flow.request.headers),
        "request_body":     req_body,
        "status":           flow.response.status_code,
        "response_headers": dict(flow.response.headers),
        "response_body":    resp_body,
    }

    # Full log including real tokens - keep this file private / gitignored
    log.info(json.dumps(entry))

    # Append to structured JSON capture file
    try:
        with open(OUTPUT_JSON, "r+") as f:
            data = json.load(f)
            data.append(entry)
            f.seek(0)
            json.dump(data, f, indent=2)
    except Exception:
        pass

    # Stdout summary with tokens redacted
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  {entry['method']}  {entry['url']}  ->  {entry['status']}")
    print(f"  Time: {entry['timestamp']}")

    hdrs = flow.request.headers
    if "x-daikin-uid" in hdrs:
        print(f"  x-daikin-uid   : {hdrs['x-daikin-uid']}")
    if "authentication" in hdrs:
        token = hdrs["authentication"]
        print(f"  authentication : {token[:40]}... [{len(token)} chars]")

    if req_body:
        body_str = json.dumps(req_body, indent=2)
        body_str = re.sub(r'"password":\s*"[^"]+"', '"password": "<redacted>"', body_str)
        print(f"  REQUEST BODY:\n{_indent(body_str[:800])}")

    if resp_body:
        body_str = json.dumps(resp_body, indent=2)
        # Redact tokens in response body too
        body_str = re.sub(r'"(access_token|refresh_token)":\s*"[^"]+"',
                          r'"\1": "<redacted>"', body_str)
        print(f"  RESPONSE BODY:\n{_indent(body_str[:1200])}")

    print(sep)
