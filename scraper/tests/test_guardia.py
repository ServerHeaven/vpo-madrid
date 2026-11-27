import subprocess

import pytest

from vpo.guardia import BOT, en_rango, main, prohibidos, sin_commit


def git(repo, *args, author="Persona"):
    config = ["-c", f"user.name={author}", "-c", "user.email=dev@example.invalid", "-c", "commit.gpgsign=false"]
    done = subprocess.run(["git", *config, *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def write(repo, path, text="{}\n"):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def commit(repo, *paths, author="Persona", text="x\n"):
    for path in paths:
        write(repo, path, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "cambio", author=author)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    commit(tmp_path, "data/overrides.json", "data/state.json", "data/promociones.json", text="{}\n")
    return tmp_path


def test_only_the_generated_files_are_allowed():
    allowed = ["data/promociones.json", "data/state.json", "data/sources/emvs-madrid.json", "web/x.ts"]
    forbidden = [
        "data/overrides.json",
        "data/iprem.json",
        "data/programas.json",
        "data/fuentes.json",
        "data/municipios.json",
        "data/schema/state.schema.json",
        "data/sources/sub/x.json",
        "data/sources/x.py",
    ]
    assert prohibidos(allowed) == []
    assert prohibidos(allowed + forbidden) == sorted(forbidden)


def test_a_clean_tree_with_generated_changes_passes(repo):
    write(repo, "data/state.json", "nuevo\n")
    write(repo, "data/sources/nueva.json")
    assert sin_commit(repo) == []
    assert main(["trabajo"], repo) == 0


@pytest.mark.parametrize("path", ["data/overrides.json", "data/nuevo.json"])
def test_uncommitted_changes_to_manual_files_are_caught(repo, path):
    write(repo, path, "otro\n")
    assert sin_commit(repo) == [path]
    assert main(["trabajo"], repo) == 1


def test_a_deleted_manual_file_is_caught(repo):
    (repo / "data" / "overrides.json").unlink()
    assert sin_commit(repo) == ["data/overrides.json"]


def test_a_person_may_change_manual_files(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "data/overrides.json", text="corregido\n")
    assert en_rango(repo, base, head) == []


def test_a_bot_commit_in_the_middle_of_the_range_is_caught(repo):
    base = git(repo, "rev-parse", "HEAD")
    bad = commit(repo, "data/iprem.json", "data/state.json", author=BOT)
    head = commit(repo, "web/x.ts")
    assert en_rango(repo, base, head) == [(bad, "data/iprem.json")]
    assert main(["rango", base, head], repo) == 1


def test_a_bot_commit_before_the_range_is_not_checked_again(repo):
    base = commit(repo, "data/iprem.json", author=BOT)
    head = commit(repo, "web/x.ts")
    assert en_rango(repo, base, head) == []


@pytest.mark.parametrize("base", ["0" * 40, "f" * 40, ""])
def test_without_a_usable_base_the_whole_history_is_checked(repo, base):
    bad = commit(repo, "data/fuentes.json", author=BOT)
    head = commit(repo, "web/x.ts")
    assert en_rango(repo, base, head) == [(bad, "data/fuentes.json")]


def test_renaming_a_manual_file_is_caught(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "data/overrides.json", "data/sources.json")
    git(repo, "commit", "-q", "-m", "mover", author=BOT)
    head = git(repo, "rev-parse", "HEAD")
    assert {path for _, path in en_rango(repo, base, head)} == {"data/overrides.json", "data/sources.json"}


def test_wrong_usage(repo):
    assert main(["otra"], repo) == 2
