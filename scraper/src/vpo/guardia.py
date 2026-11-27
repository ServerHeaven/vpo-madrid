"""File ownership guard (ARCHITECTURE.md §2 and §4.3): what the bot may change inside data/.

    python -m vpo.guardia trabajo           uncommitted files, before the bot commits
    python -m vpo.guardia rango BASE HEAD   bot commits of a push or pull request

Only the standard library and git are needed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

BOT = "github-actions[bot]"
GENERADOS = ("data/promociones.json", "data/state.json")
_FUENTE = re.compile(r"data/sources/[^/]+\.json")
_SIN_BASE = re.compile(r"0*")


def prohibidos(paths: Iterable[str]) -> list[str]:
    """The paths under data/ that only a person may change."""
    return sorted(
        {p for p in paths if p.startswith("data/") and p not in GENERADOS and not _FUENTE.fullmatch(p)}
    )


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return done.stdout


def _nombres(output: str) -> list[str]:
    return [name for name in output.split("\0") if name]


def sin_commit(repo: Path) -> list[str]:
    """Forbidden files that are modified, deleted, staged or untracked."""
    repo = Path(_git(repo, "rev-parse", "--show-toplevel").strip())  # pathspecs are relative to cwd
    changed = _nombres(_git(repo, "diff", "--name-only", "--no-renames", "-z", "HEAD", "--", "data"))
    untracked = _nombres(_git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", "data"))
    return prohibidos(changed + untracked)


def _existe(repo: Path, revision: str) -> bool:
    try:
        _git(repo, "cat-file", "-e", f"{revision}^{{commit}}")
    except subprocess.CalledProcessError:
        return False
    return True


def en_rango(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    """(commit, path) for each forbidden file touched by a commit of the bot in base..head.

    Without a usable base (new branch or rewritten history) the whole history of head is checked.
    """
    known = not _SIN_BASE.fullmatch(base) and _existe(repo, base)
    commits = _git(repo, "rev-list", f"{base}..{head}" if known else head).split()
    found: list[tuple[str, str]] = []
    for commit in commits:
        who = _git(repo, "show", "-s", "--format=%an%x00%cn", commit).strip().split("\0")
        if BOT not in who:
            continue
        # -m: a merge commit is compared with each parent. --no-renames: a moved file shows both names.
        output = _git(
            repo, "diff-tree", "-r", "-m", "--root", "--no-commit-id", "--no-renames", "--name-only", "-z", commit
        )
        found += [(commit, path) for path in prohibidos(_nombres(output))]
    return found


def main(argv: list[str] | None = None, repo: Path | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    repo = repo or Path.cwd()
    if args == ["trabajo"]:
        errors = [f"{path}: modificado por el proceso automático" for path in sin_commit(repo)]
    elif len(args) == 3 and args[0] == "rango":
        errors = [
            f"{path}: modificado por {BOT} en {commit[:10]}" for commit, path in en_rango(repo, *args[1:])
        ]
    else:
        print("uso: python -m vpo.guardia trabajo | rango BASE HEAD", file=sys.stderr)
        return 2
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    if errors:
        print("Solo promociones.json, state.json y sources/*.json los puede escribir el bot.", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
