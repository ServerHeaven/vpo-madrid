"""Polite HTTP client: User-Agent, per-host rate limit, robots.txt, ETag, retries."""

from __future__ import annotations

import codecs
import hashlib
import json
import math
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from ..sources.base import DeadlineExceeded, FetchError, HttpStatusError, Response, RobotsDisallowed

USER_AGENT = "vpo-madrid-bot/1.0 (+https://serverheaven.github.io/vpo-madrid/metodologia)"
ROBOTS_TOKEN = "vpo-madrid-bot"

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 10
_MAX_ROBOTS_REDIRECTS = 5
_MAX_ROBOTS_BYTES = 500 * 1024
_BACKOFF_BASE_S = 2.0
_MAX_RETRY_AFTER_S = 120.0


# -- robots.txt (RFC 9309) ---------------------------------------------------------------------
# urllib.robotparser is not usable here: it ignores "*" and "$" and applies the first match.

_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")


def _normalize_path(path: str) -> str:
    """Make percent-encoding comparable between robots patterns and request paths."""

    def canonical(match: re.Match[str]) -> str:
        char = chr(int(match[1], 16))
        return char if char in _UNRESERVED else match[0].upper()

    return _PERCENT.sub(canonical, quote(path, safe="!#$%&'()*+,/:;=?@[]"))


def _pattern_matches(pattern: str, path: str) -> bool:
    """Prefix match where "*" is any sequence and a final "$" anchors the end (no backtracking)."""
    anchored = pattern.endswith("$")
    parts = (pattern[:-1] if anchored else pattern).split("*")
    if not path.startswith(parts[0]):
        return False
    pos = len(parts[0])
    if len(parts) == 1:
        return not anchored or pos == len(path)
    for part in parts[1:-1]:
        index = path.find(part, pos)
        if index < 0:
            return False
        pos = index + len(part)
    last = parts[-1]
    if anchored:
        return path.endswith(last) and len(path) - len(last) >= pos
    return path.find(last, pos) >= 0


@dataclass(frozen=True)
class _RobotsRules:
    rules: tuple[tuple[bool, str], ...] = ()  # (allow, pattern)
    crawl_delay: float = 0.0

    def allows(self, path: str) -> bool:
        """The longest matching pattern wins; on a tie, allow."""
        path = _normalize_path(path)
        if path == "/robots.txt":
            return True
        matches = [(len(pattern), allow) for allow, pattern in self.rules if _pattern_matches(pattern, path)]
        return max(matches)[1] if matches else True


def _parse_robots(text: str) -> _RobotsRules:
    """Keep the groups naming our token or, if there are none, the "*" groups."""
    groups: list[tuple[set[str], list[tuple[str, str]]]] = []
    in_agent_lines = False
    for line in text.lstrip("﻿").splitlines():
        key, colon, value = line.partition("#")[0].partition(":")
        if not colon:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not in_agent_lines:
                groups.append((set(), []))
                in_agent_lines = True
            groups[-1][0].add(value.split("/")[0].strip().lower())
        elif key in ("allow", "disallow", "crawl-delay"):
            in_agent_lines = False
            if groups:
                groups[-1][1].append((key, value))

    selected = [lines for agents, lines in groups if ROBOTS_TOKEN in agents]
    if not selected:
        selected = [lines for agents, lines in groups if "*" in agents]

    rules: list[tuple[bool, str]] = []
    crawl_delay = 0.0
    for key, value in (entry for lines in selected for entry in lines):
        if key == "crawl-delay":
            try:
                delay = float(value)
            except ValueError:
                continue
            if math.isfinite(delay):
                crawl_delay = max(crawl_delay, delay)
        elif value:  # an empty "Disallow:" forbids nothing
            rules.append((key == "allow", _normalize_path(value)))
    return _RobotsRules(tuple(rules), crawl_delay)


# -- response helpers --------------------------------------------------------------------------


def _retry_after_s(response: httpx.Response) -> float:
    """Seconds asked by Retry-After (number or HTTP date), capped. 0 when absent or unreadable."""
    value = response.headers.get("retry-after", "").strip()
    if not value:
        return 0.0
    if value.isascii() and value.isdigit():
        seconds = float(value)
    else:
        try:
            until = parsedate_to_datetime(value)
            # Prefer the server's own Date header, so a skewed local clock does not matter.
            sent = response.headers.get("date")
            now = parsedate_to_datetime(sent) if sent else datetime.now(UTC)
            seconds = (until - now).total_seconds()
        except (TypeError, ValueError):
            return 0.0
    return min(max(seconds, 0.0), _MAX_RETRY_AFTER_S)


def _charset(response: httpx.Response) -> str | None:
    name = response.charset_encoding
    if name is None:
        return None
    try:
        codecs.lookup(name)
    except LookupError:
        return None
    return name


def _parse_url(url: str, base: httpx.URL | None = None) -> httpx.URL:
    """Absolute http(s) URL without fragment, resolved against ``base`` if given."""
    try:
        parsed = base.join(url) if base is not None else httpx.URL(url)
    except (httpx.InvalidURL, TypeError, ValueError) as exc:
        raise FetchError(f"URL no válida: {url}") from exc
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise FetchError(f"URL no válida: {url}")
    return parsed.copy_with(fragment=None) if parsed.fragment else parsed


# -- cache -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _CacheEntry:
    content: bytes
    encoding: str | None
    etag: str | None
    last_modified: str | None

    def conditional_headers(self) -> dict[str, str]:
        headers = {}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers


class _Cache:
    """One file per URL: a JSON header line followed by the raw body.

    A single file replaced atomically means validators and body cannot get out of step.
    The cache is optional by nature, so I/O errors are never propagated.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self, url: str) -> Path:
        return self.directory / f"{hashlib.sha256(url.encode()).hexdigest()}.cache"

    def load(self, url: str) -> _CacheEntry | None:
        try:
            header, newline, content = self._path(url).read_bytes().partition(b"\n")
            meta = json.loads(header)
            if not newline or meta["url"] != url or meta["sha256"] != hashlib.sha256(content).hexdigest():
                return None
            values = [meta[key] for key in ("encoding", "etag", "last_modified")]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not all(value is None or isinstance(value, str) for value in values):
            return None
        entry = _CacheEntry(content, *values)
        return entry if entry.conditional_headers() else None

    def store(self, url: str, entry: _CacheEntry) -> None:
        """Save the entry, or drop the old one when the response has no validators."""
        path = self._path(url)
        temporary: str | None = None
        try:
            if not entry.conditional_headers():
                path.unlink(missing_ok=True)
                return
            meta = {
                "url": url,
                "sha256": hashlib.sha256(entry.content).hexdigest(),
                "encoding": entry.encoding,
                "etag": entry.etag,
                "last_modified": entry.last_modified,
            }
            self.directory.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            with os.fdopen(handle, "wb") as file:
                file.write(json.dumps(meta).encode() + b"\n" + entry.content)
            os.replace(temporary, path)
            temporary = None
        except OSError:
            pass
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)


# -- client ------------------------------------------------------------------------------------


class HttpClient:
    """Implements sources.base.Fetcher. Usable as a context manager."""

    log: list[Response]  # every successful response, in order

    def __init__(
        self,
        *,
        min_interval_s: float = 3.0,
        deadline: float | None = None,  # value of clock() after which DeadlineExceeded is raised
        cache_dir: Path | None = None,  # enables conditional requests
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 3,
        timeout_s: float = 30.0,
    ) -> None:
        self.log = []
        self._min_interval_s = min_interval_s
        self._deadline = deadline
        self._cache = _Cache(cache_dir) if cache_dir is not None else None
        self._sleep = sleep
        self._clock = clock
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._client = httpx.Client(
            transport=transport, headers={"User-Agent": USER_AGENT}, follow_redirects=False
        )
        self._last_request: dict[str, float] = {}  # host -> clock() when the request ended
        self._crawl_delay: dict[str, float] = {}  # host -> seconds
        # (scheme, host, port) -> rules, or the error that made robots.txt unreadable
        self._robots: dict[tuple[str, str, int | None], _RobotsRules | FetchError] = {}

    def get(self, url: str) -> Response:
        current = _parse_url(url)
        for _ in range(_MAX_REDIRECTS + 1):
            self._check_robots(current)
            key = str(current)
            cached = self._cache.load(key) if self._cache else None
            response = self._send(current, cached.conditional_headers() if cached else {})
            status = response.status_code

            if status in _REDIRECT_STATUSES and "location" in response.headers:
                current = _parse_url(response.headers["location"], base=current)
                continue
            if status == 304 and cached:
                entry = _CacheEntry(
                    cached.content,
                    cached.encoding,
                    response.headers.get("etag", cached.etag),
                    response.headers.get("last-modified", cached.last_modified),
                )
                return self._succeed(url, key, 200, entry, from_cache=True)
            if response.is_success:
                entry = _CacheEntry(
                    response.content,
                    _charset(response),
                    response.headers.get("etag"),
                    response.headers.get("last-modified"),
                )
                if self._cache and status == 200:
                    self._cache.store(key, entry)
                return self._succeed(url, key, status, entry)
            raise HttpStatusError(key, status)
        raise FetchError(f"Demasiadas redirecciones desde {url}")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _succeed(
        self, requested_url: str, url: str, status: int, entry: _CacheEntry, *, from_cache: bool = False
    ) -> Response:
        result = Response(
            url=url,
            requested_url=requested_url,
            status=status,
            content=entry.content,
            encoding=entry.encoding,
            etag=entry.etag,
            last_modified=entry.last_modified,
            from_cache=from_cache,
        )
        self.log.append(result)
        return result

    # -- timing --------------------------------------------------------------------------------

    def _pause(self, seconds: float, url: httpx.URL) -> None:
        if self._deadline is not None and self._clock() + seconds >= self._deadline:
            raise DeadlineExceeded(f"Tiempo agotado para la fuente antes de pedir {url}")
        self._sleep(seconds)

    def _wait_for_host(self, url: httpx.URL) -> None:
        last = self._last_request.get(url.host)
        if last is None:
            return
        interval = max(self._min_interval_s, self._crawl_delay.get(url.host, 0.0))
        wait = last + interval - self._clock()
        if wait > 0:
            self._pause(wait, url)

    def _request_timeout(self, url: httpx.URL) -> float:
        if self._deadline is None:
            return self._timeout_s
        remaining = self._deadline - self._clock()
        if remaining <= 0:
            raise DeadlineExceeded(f"Tiempo agotado para la fuente antes de pedir {url}")
        return min(self._timeout_s, remaining)

    # -- requests ------------------------------------------------------------------------------

    def _send(self, url: httpx.URL, headers: dict[str, str]) -> httpx.Response:
        """One hop with rate limit and retries. Returns any response that is not 429/5xx."""
        attempt = 0
        while True:
            self._wait_for_host(url)
            timeout = self._request_timeout(url)
            retry_after = 0.0
            failure: FetchError
            try:
                response = self._client.get(url, headers=headers, timeout=timeout)
            except httpx.TransportError as exc:
                # The timeout may have been cut short by the deadline.
                if self._deadline is not None and self._clock() >= self._deadline:
                    raise DeadlineExceeded(f"Tiempo agotado para la fuente al pedir {url}") from exc
                failure = FetchError(f"Error de red en {url}: {type(exc).__name__}: {exc}")
                failure.__cause__ = exc
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                raise FetchError(f"Respuesta no válida de {url}: {exc}") from exc
            else:
                status = response.status_code
                if status != 429 and not 500 <= status < 600:
                    return response
                failure = HttpStatusError(str(url), status)
                retry_after = _retry_after_s(response)
            finally:
                self._last_request[url.host] = self._clock()

            if attempt >= self._max_retries:
                raise failure
            self._pause(max(_BACKOFF_BASE_S * 2**attempt, retry_after), url)
            attempt += 1

    # -- robots --------------------------------------------------------------------------------

    def _check_robots(self, url: httpx.URL) -> None:
        origin = (url.scheme, url.host, url.port)
        rules = self._robots.get(origin)
        if rules is None:
            try:
                rules = self._fetch_robots(url.join("/robots.txt"))
            except FetchError as exc:
                rules = exc  # remembered, so a failing server is not asked again for every page
            self._robots[origin] = rules
            if isinstance(rules, _RobotsRules):
                self._crawl_delay[url.host] = max(self._crawl_delay.get(url.host, 0.0), rules.crawl_delay)
        if isinstance(rules, FetchError):
            raise FetchError(f"No se pudo obtener robots.txt de {url.host}: {rules}") from rules
        if not rules.allows(url.raw_path.decode("ascii")):
            raise RobotsDisallowed(f"robots.txt no permite {url}")

    def _fetch_robots(self, url: httpx.URL) -> _RobotsRules:
        for _ in range(_MAX_ROBOTS_REDIRECTS + 1):
            response = self._send(url, {})
            status = response.status_code
            if status in _REDIRECT_STATUSES and "location" in response.headers:
                url = _parse_url(response.headers["location"], base=url)
                continue
            if response.is_success:
                return _parse_robots(response.content[:_MAX_ROBOTS_BYTES].decode("utf-8", errors="replace"))
            if 400 <= status < 500:
                return _RobotsRules()
            raise HttpStatusError(str(url), status)
        raise FetchError(f"Demasiadas redirecciones en {url}")
