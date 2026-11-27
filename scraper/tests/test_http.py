"""No real network and no real sleeping: httpx.MockTransport plus a fake clock."""

import httpx
import pytest

from vpo.core.http import USER_AGENT, HttpClient, _parse_robots
from vpo.sources.base import DeadlineExceeded, FetchError, HttpStatusError, RobotsDisallowed

BASE = "https://example.org"
URL = f"{BASE}/pagina"
ROBOTS_URL = f"{BASE}/robots.txt"
MODIFIED = "Tue, 24 Nov 2026 10:00:00 GMT"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.sleeps.append(seconds)
        self.now += seconds


class Server:
    """Routes by full URL. A list is consumed one reply at a time; its last item repeats."""

    def __init__(self, clock: FakeClock, routes: dict) -> None:
        self.clock = clock
        self.routes = routes
        self.requests: list[httpx.Request] = []
        self.times: list[float] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.times.append(self.clock.now)
        url = str(request.url)
        reply = self.routes.get(url)
        if reply is None:
            return httpx.Response(404 if url.endswith("/robots.txt") else 200, content=b"ok")
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if callable(reply):
            reply = reply(request)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]

    @property
    def gaps(self) -> list[float]:
        return [b - a for a, b in zip(self.times, self.times[1:])]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make(clock: FakeClock, routes: dict | None = None, **kwargs) -> tuple[HttpClient, Server]:
    server = Server(clock, routes or {})
    client = HttpClient(transport=httpx.MockTransport(server), sleep=clock.sleep, clock=clock, **kwargs)
    return client, server


def robots(text: str) -> httpx.Response:
    return httpx.Response(200, text=text)


def ok(body: bytes = b"cuerpo", **headers: str) -> httpx.Response:
    return httpx.Response(200, content=body, headers={k.replace("_", "-"): v for k, v in headers.items()})


def redirect(location: str, status: int = 302) -> httpx.Response:
    return httpx.Response(status, headers={"location": location})


# -- basics ------------------------------------------------------------------------------------


def test_response_user_agent_and_log(clock):
    page = ok("año".encode("latin-1"), content_type="text/html; charset=ISO-8859-1")
    client, server = make(clock, {URL: page})
    with client:
        response = client.get(URL + "#promo-2")
    assert (response.status, response.text, response.from_cache) == (200, "año", False)
    assert response.url == URL
    assert response.requested_url == URL + "#promo-2"
    assert client.log == [response]  # robots.txt is not logged
    assert server.urls == [ROBOTS_URL, URL]
    assert all(r.headers["user-agent"] == USER_AGENT for r in server.requests)


@pytest.mark.parametrize("url", ["ftp://example.org/x", "/relativa", "no es una url", "mailto:a@example.org"])
def test_invalid_url(clock, url):
    client, server = make(clock)
    with pytest.raises(FetchError):
        client.get(url)
    assert server.requests == []


@pytest.mark.parametrize("status", [401, 403, 404, 410, 304, 302])
def test_other_statuses_fail_at_once(clock, status):
    client, server = make(clock, {URL: httpx.Response(status)})
    with pytest.raises(HttpStatusError) as error:
        client.get(URL)
    assert (error.value.status, error.value.url) == (status, URL)
    assert len(server.requests) == 2
    assert client.log == []


# -- rate limit --------------------------------------------------------------------------------


def test_rate_limit_per_host(clock):
    client, server = make(clock)
    client.get(f"{BASE}/a")
    client.get(f"{BASE}/b")
    client.get("https://otro.example.org/a")
    # robots, a, b at 3 s intervals; the other host does not wait for the first one.
    assert server.times == [1000.0, 1003.0, 1006.0, 1006.0, 1009.0]


def test_elapsed_time_counts_towards_the_interval(clock):
    client, _ = make(clock)
    client.get(f"{BASE}/a")
    clock.now += 2.0
    clock.sleeps.clear()
    client.get(f"{BASE}/b")
    assert clock.sleeps == [1.0]


@pytest.mark.parametrize(("min_interval", "gap"), [(3.0, 10.0), (15.0, 15.0)])
def test_crawl_delay(clock, min_interval, gap):
    routes = {ROBOTS_URL: robots("User-agent: *\nCrawl-delay: 10\n")}
    client, server = make(clock, routes, min_interval_s=min_interval)
    client.get(f"{BASE}/a")
    client.get(f"{BASE}/b")
    assert server.gaps == [gap, gap]


# -- robots ------------------------------------------------------------------------------------

ROBOTS = """
# comment
Sitemap: https://example.org/sitemap.xml
User-agent: *
Allow: /misc/*.css$
Disallow: /misc/
Disallow: /_layouts/
Disallow: /*?buscar=
Disallow: /exacto$
Disallow: /empate
Allow: /empate
Disallow: /privado%7e/
Disallow: /año/
Disallow:
"""


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/", True),
        ("/misc/estilo.css", True),
        ("/misc/sub/estilo.css", True),
        ("/misc/estilo.css?v=1", False),
        ("/misc/script.js", False),
        ("/_layouts/15/x.aspx", False),
        ("/_Layouts/x", True),
        ("/lista?buscar=1", False),
        ("/lista?pagina=1", True),
        ("/exacto", False),
        ("/exacto/mas", True),
        ("/empate/x", True),
        ("/privado~/x", False),
        ("/a%C3%B1o/x", False),
        ("/a%c3%b1o/x", False),
        ("/robots.txt", True),
    ],
)
def test_robots_matching(path, allowed):
    assert _parse_robots(ROBOTS).allows(path) is allowed


def test_robots_group_for_our_token_wins():
    text = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: otro\nUser-Agent: VPO-Madrid-Bot\nDisallow: /no\nCrawl-delay: 7\n"
    )
    rules = _parse_robots(text)
    assert rules.allows("/si") and not rules.allows("/no")
    assert rules.crawl_delay == 7.0


def test_robots_ignores_other_agents():
    rules = _parse_robots("User-agent: vpo\nDisallow: /\nCrawl-delay: 99\n\nUser-agent: *\nCrawl-delay: x\n")
    assert rules.allows("/a") and rules.crawl_delay == 0.0


def test_disallowed_and_fetched_once(clock):
    client, server = make(clock, {ROBOTS_URL: robots("User-agent: *\nDisallow: /no")})
    client.get(f"{BASE}/a")
    with pytest.raises(RobotsDisallowed):
        client.get(f"{BASE}/no/x")
    client.get(f"{BASE}/b")
    assert server.urls == [ROBOTS_URL, f"{BASE}/a", f"{BASE}/b"]


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_robots_4xx_allows_everything(clock, status):
    client, _ = make(clock, {ROBOTS_URL: httpx.Response(status)})
    assert client.get(URL).status == 200


@pytest.mark.parametrize("reply", [httpx.Response(500), httpx.Response(429), httpx.ConnectError("caído")])
def test_robots_failure_is_conservative_and_remembered(clock, reply):
    client, server = make(clock, {ROBOTS_URL: reply}, max_retries=2)
    for _ in range(2):
        with pytest.raises(FetchError) as error:
            client.get(URL)
        assert not isinstance(error.value, (HttpStatusError, RobotsDisallowed))
    assert server.urls == [ROBOTS_URL] * 3
    assert all(gap >= 3.0 for gap in server.gaps)


def test_robots_redirect_is_followed(clock):
    routes = {
        ROBOTS_URL: redirect("/robots-real.txt", 301),
        f"{BASE}/robots-real.txt": robots("User-agent: *\nDisallow: /pagina"),
    }
    client, _ = make(clock, routes)
    with pytest.raises(RobotsDisallowed):
        client.get(URL)


# -- redirects ---------------------------------------------------------------------------------


def test_redirect_with_explicit_port(clock):
    routes = {f"{BASE}/viejo": redirect("https://www.example.org:443/nuevo", 301)}
    client, server = make(clock, routes)
    response = client.get(f"{BASE}/viejo")
    assert response.url == "https://www.example.org/nuevo"
    assert response.requested_url == f"{BASE}/viejo"
    assert server.urls == [
        ROBOTS_URL,
        f"{BASE}/viejo",
        "https://www.example.org/robots.txt",
        "https://www.example.org/nuevo",
    ]
    assert len(client.log) == 1


def test_redirect_hop_obeys_robots_and_rate_limit(clock):
    routes = {
        ROBOTS_URL: robots("User-agent: *\nDisallow: /_layouts/"),
        f"{BASE}/a": redirect("b"),
        f"{BASE}/b": redirect("/_layouts/c", 307),
    }
    client, server = make(clock, routes)
    with pytest.raises(RobotsDisallowed):
        client.get(f"{BASE}/a")
    assert server.urls[1:] == [f"{BASE}/a", f"{BASE}/b"]
    assert server.gaps == [3.0, 3.0]


def test_redirect_loop_is_bounded(clock):
    client, server = make(clock, {URL: redirect(URL)})
    with pytest.raises(FetchError, match="redirecciones"):
        client.get(URL)
    assert len(server.requests) == 12  # robots + first request + 10 redirects


# -- retries -----------------------------------------------------------------------------------


@pytest.mark.parametrize("reply", [httpx.Response(500), httpx.Response(429), httpx.ReadTimeout("lento")])
def test_retry_then_success(clock, reply):
    client, server = make(clock, {URL: [reply, reply, ok()]})
    assert client.get(URL).content == b"cuerpo"
    assert server.gaps[1:] == [3.0, 4.0]  # backoff 2 s is below the 3 s rate limit, then 4 s
    assert len(client.log) == 1


@pytest.mark.parametrize(
    ("reply", "expected"),
    [(httpx.Response(503), HttpStatusError), (httpx.ConnectError("caído"), FetchError)],
)
def test_retries_exhausted(clock, reply, expected):
    client, server = make(clock, {URL: reply})
    with pytest.raises(expected):
        client.get(URL)
    assert server.urls.count(URL) == 4
    assert server.gaps[1:] == [3.0, 4.0, 8.0]


@pytest.mark.parametrize(
    ("headers", "gap"),
    [
        ({"retry-after": "30"}, 30.0),
        ({"retry-after": "999999"}, 120.0),
        ({"retry-after": "pronto"}, 3.0),
        ({"date": "Fri, 27 Nov 2026 10:00:00 GMT", "retry-after": "Fri, 27 Nov 2026 10:00:45 GMT"}, 45.0),
    ],
)
def test_retry_after(clock, headers, gap):
    client, server = make(clock, {URL: [httpx.Response(429, headers=headers), ok()]})
    client.get(URL)
    assert server.gaps[1] == gap


# -- deadline ----------------------------------------------------------------------------------


def test_deadline_already_passed(clock):
    client, server = make(clock, deadline=999.0)
    for _ in range(2):  # not remembered as a robots.txt failure
        with pytest.raises(DeadlineExceeded):
            client.get(URL)
    assert server.requests == []


def test_deadline_prevents_sleeping_past_it(clock):
    client, server = make(clock, deadline=1002.0)
    with pytest.raises(DeadlineExceeded):
        client.get(URL)  # robots.txt goes out, the page would have to wait 3 s
    assert len(server.requests) == 1
    assert clock.sleeps == []


def test_deadline_stops_retries(clock):
    reply = httpx.Response(429, headers={"retry-after": "60"})
    client, server = make(clock, {URL: reply}, deadline=1030.0)
    with pytest.raises(DeadlineExceeded):
        client.get(URL)
    assert server.urls.count(URL) == 1


def test_deadline_caps_request_timeout(clock):
    client, server = make(clock, deadline=1010.0)
    client.get(URL)
    assert [r.extensions["timeout"]["read"] for r in server.requests] == [10.0, 7.0]


def test_timeout_caused_by_deadline(clock):
    def slow(request: httpx.Request) -> Exception:
        clock.now += request.extensions["timeout"]["read"]
        return httpx.ReadTimeout("lento")

    client, _ = make(clock, {URL: slow}, deadline=1010.0)
    with pytest.raises(DeadlineExceeded):
        client.get(URL)


# -- cache -------------------------------------------------------------------------------------


def conditional(request: httpx.Request) -> httpx.Response:
    if request.headers.get("if-none-match") == '"v1"':
        return httpx.Response(304)
    return ok(content_type="text/html; charset=utf-8", etag='"v1"', last_modified=MODIFIED)


def test_conditional_request_across_clients(clock, tmp_path):
    first, _ = make(clock, {URL: conditional}, cache_dir=tmp_path / "cache")
    first.get(URL)
    second, server = make(clock, {URL: conditional}, cache_dir=tmp_path / "cache")
    response = second.get(URL)
    sent = server.requests[-1].headers
    assert (sent["if-none-match"], sent["if-modified-since"]) == ('"v1"', MODIFIED)
    assert "if-none-match" not in server.requests[0].headers  # robots.txt
    assert (response.status, response.from_cache, response.content) == (200, True, b"cuerpo")
    assert (response.encoding, response.etag, response.last_modified) == ("utf-8", '"v1"', MODIFIED)
    assert second.log == [response]
    assert [p.suffix for p in (tmp_path / "cache").iterdir()] == [".cache"]


@pytest.mark.parametrize(
    "damage",
    [
        lambda data: b"",
        lambda data: b"\xff\x00 basura",
        lambda data: data[:-1],
        lambda data: b"[]\n" + data.partition(b"\n")[2],
        lambda data: data.replace(b'"utf-8"', b"7"),
    ],
)
def test_corrupt_cache_degrades_to_unconditional(clock, tmp_path, damage):
    client, server = make(clock, {URL: conditional}, cache_dir=tmp_path)
    client.get(URL)
    [path] = tmp_path.iterdir()
    path.write_bytes(damage(path.read_bytes()))
    response = client.get(URL)
    assert "if-none-match" not in server.requests[-1].headers
    assert (response.from_cache, response.content) == (False, b"cuerpo")


def test_unwritable_cache_does_not_fail(clock, tmp_path):
    blocker = tmp_path / "archivo"
    blocker.write_text("x")
    client, _ = make(clock, {URL: conditional}, cache_dir=blocker)
    assert client.get(URL).content == b"cuerpo"


def test_entry_dropped_when_validators_disappear(clock, tmp_path):
    client, server = make(clock, {URL: [ok(etag='"v1"'), ok(b"nuevo")]}, cache_dir=tmp_path)
    client.get(URL)
    client.get(URL)
    assert list(tmp_path.iterdir()) == []
    client.get(URL)
    assert "if-none-match" not in server.requests[-1].headers


def test_no_cache_dir_means_no_conditional_requests(clock):
    client, server = make(clock, {URL: conditional})
    client.get(URL)
    client.get(URL)
    assert "if-none-match" not in server.requests[-1].headers
