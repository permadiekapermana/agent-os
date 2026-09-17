#!/usr/bin/env python3
"""Direct HTTP request — meta-skill entrypoint.

Writes the response body to stdout. Non-2xx HTTP responses exit 1
with the status code on stderr; network failures exit 2.

Used by meta-skills to skip a full sub-Agent loop just to GET/POST a
URL. Not a crawler, not a browser — single request, single body.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from typing import TextIO


def _emit(text: str, stream: TextIO = sys.stdout) -> None:
    """Write text to stream safely across non-UTF-8 console code pages.

    The binary buffer is the primary path: it keeps UTF-8 content intact even
    when the stream's own encoding cannot represent it. A stream without a
    usable ``buffer`` still gets the text, escaped rather than raising
    ``UnicodeEncodeError``.
    """
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        try:
            buffer.write(text.encode("utf-8"))
            buffer.flush()
            return
        except (AttributeError, OSError, ValueError):
            pass

    encoding = getattr(stream, "encoding", None) or "utf-8"
    stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))
    stream.flush()


def _fetch(
    url: str,
    method: str,
    body: bytes,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, str]:
    """Return ``(status, body_bytes, reason)``. Raises on network errors."""
    req = urllib.request.Request(  # noqa: S310 — URL is operator-supplied per turn
        url,
        data=body if body else None,
        headers=headers or {},
        method=method,
    )
    if not body:
        # Strip Content-Length urllib auto-adds when data=b"" — some servers
        # reject it on GET.
        req.headers.pop("Content-length", None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read(), resp.reason or ""
    except urllib.error.HTTPError as exc:
        # Non-2xx: still return the body so callers can inspect.
        return exc.code, (exc.read() if hasattr(exc, "read") else b""), exc.reason or ""


def _read_stdin_body() -> bytes:
    """Read binary body from stdin if piped/available, or return empty bytes."""
    try:
        if sys.stdin.isatty():
            return b""
    except (AttributeError, OSError, ValueError):
        return b""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        try:
            return buffer.read()
        except (AttributeError, OSError, ValueError):
            return b""
    try:
        text = sys.stdin.read()
        return text.encode("utf-8")
    except (AttributeError, OSError, ValueError):
        return b""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--method", default="GET")
    parser.add_argument(
        "--header",
        "-H",
        action="append",
        default=[],
        help="Extra request header as 'Key: value'. Repeatable.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    args = parser.parse_args(argv)

    method = (args.method or "GET").upper()
    valid_methods = {"GET", "POST", "PUT", "DELETE", "HEAD", "PATCH"}
    if method not in valid_methods:
        print(
            f"unsupported method {method!r}; valid: {sorted(valid_methods)!r}",
            file=sys.stderr,
        )
        return 2

    url = args.url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        print(
            f"invalid url {url!r}: must start with http:// or https://",
            file=sys.stderr,
        )
        return 2

    headers: dict[str, str] = {}
    for raw_header in args.header:
        key, sep, val = raw_header.partition(":")
        if not sep or not key.strip():
            print(
                f"invalid header format {raw_header!r}: expected 'Key: value'",
                file=sys.stderr,
            )
            return 2
        headers[key.strip()] = val.strip()

    # Body comes from stdin (per the SKILL.md entrypoint contract).
    body = _read_stdin_body()

    try:
        status, raw, reason = _fetch(url, method, body, args.timeout, headers=headers)
    except urllib.error.URLError as exc:
        print(f"URLError: {exc.reason}", file=sys.stderr)
        return 2
    except TimeoutError:
        print(f"timeout after {args.timeout}s", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface, don't crash
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if len(raw) > args.max_bytes:
        raw = raw[: args.max_bytes - 1] + b"\xe2\x80\xa6"  # … (truncation marker)

    # Lossy decode — meta-skill DAGs need string output for templating.
    text = raw.decode("utf-8", errors="replace")
    _emit(text, sys.stdout)

    if not (200 <= status < 300):
        preview = text[:200].replace("\n", " ")
        status_msg = (
            f"HTTP {status}: {reason}: {preview}" if reason else f"HTTP {status}: {preview}"
        )
        print(status_msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
