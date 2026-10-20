"""Syncing the data folder between computers through a git remote (FR-82).

The data folder is plain text written in a stable order, so git merges it
cleanly. ``.state/`` (the running timer, the lock, the session key) belongs to
one machine and is never committed. The model is one computer at a time:
sync when you are done, sync again before you start on the other one.
"""

from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime

from cubit.core.errors import CubitError
from cubit.core.storage import Storage

REMOTE = "origin"
GIT_TIMEOUT = 120


@dataclass(frozen=True)
class SyncReport:
    """What one ``cubit sync`` did."""

    committed: bool
    pulled: int
    pushed: bool


@dataclass(frozen=True)
class SetupReport:
    """What ``cubit sync setup`` did."""

    cloned: bool
    initialised: bool
    pushed: bool


def _git(storage: Storage, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git in the data folder; failures become ordinary cubit errors."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=storage.data_dir,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env=env,
        )
    except FileNotFoundError:
        raise CubitError("git is not installed.", hint="Install git and try again.") from None
    except subprocess.TimeoutExpired:
        raise CubitError(
            f"git {args[0]} took longer than {GIT_TIMEOUT} seconds.",
            hint="Check the network and the remote, then try again.",
        ) from None
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
        raise CubitError(f"git {args[0]} failed: {detail}")
    return result


def is_repository(storage: Storage) -> bool:
    return (storage.data_dir / ".git").exists()


def remote_url(storage: Storage) -> str | None:
    result = _git(storage, "remote", "get-url", REMOTE, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _branch(storage: Storage) -> str:
    return _git(storage, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _has_commits(storage: Storage) -> bool:
    return _git(storage, "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def _remote_has_data(storage: Storage, remote: str) -> bool:
    """True if the remote already holds a ``main`` branch."""
    found = _git(storage, "ls-remote", "--exit-code", "--heads", remote, "main", check=False)
    return found.returncode == 0


def _unfinished_git_work(storage: Storage) -> bool:
    """A merge or rebase somebody started by hand and never finished."""
    git_dir = storage.data_dir / ".git"
    return any((git_dir / name).exists() for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD"))


def _commit_all(storage: Storage, message: str) -> bool:
    """Commit every change; False if there was nothing to commit."""
    _git(storage, "add", "--all")
    if not _git(storage, "status", "--porcelain").stdout.strip():
        return False
    _git(storage, "commit", "--message", message)
    return True


def _default_message() -> str:
    return f"Sync from {socket.gethostname()} at {datetime.now():%Y-%m-%d %H:%M}"


def setup_sync(storage: Storage, remote: str | None = None) -> SetupReport:
    """Turn the data folder into a git repository that syncs to ``remote``.

    On a computer with no data folder yet, a remote that already holds the data
    is cloned into place. Safe to run again.
    """
    cloned = False
    if not storage.data_dir.exists():
        if remote is None:
            raise CubitError(
                f"No cubit data folder at {storage.data_dir}.",
                hint="Pass the remote to clone it from, or create one with 'cubit init'.",
            )
        storage.data_dir.parent.mkdir(parents=True, exist_ok=True)
        clone = subprocess.run(
            ["git", "clone", remote, str(storage.data_dir)],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if clone.returncode != 0:
            raise CubitError(f"git clone failed: {clone.stderr.strip()}")
        cloned = True

    initialised = not is_repository(storage)
    if initialised:
        _git(storage, "init", "--initial-branch", "main")

    storage.init()

    if remote is not None and remote_url(storage) is None and _remote_has_data(storage, remote):
        # The remote already holds the data, so this folder must not start a second history.
        if _has_commits(storage) or not storage.is_starter:
            raise CubitError(
                f"{remote} already holds cubit data, and so does {storage.data_dir}.",
                hint=(
                    "Move this folder aside (mv ~/cubit-data ~/cubit-data-old) and run "
                    "'cubit sync setup' again to fetch the remote's data."
                ),
            )
        _git(storage, "remote", "add", REMOTE, remote)
        _git(storage, "fetch", REMOTE, "main")
        _git(storage, "checkout", "--force", "-B", "main", f"{REMOTE}/main")
        storage.ensure_gitignore()
        return SetupReport(cloned=True, initialised=initialised, pushed=False)

    storage.ensure_gitignore()

    if remote is not None:
        existing = remote_url(storage)
        if existing is None:
            _git(storage, "remote", "add", REMOTE, remote)
        elif existing != remote:
            raise CubitError(
                f"This folder already syncs to {existing}.",
                hint="Change it with: git -C <data folder> remote set-url origin <url>",
            )

    _commit_all(storage, "Start syncing cubit data")

    pushed = False
    if remote_url(storage) is not None and _has_commits(storage):
        _git(storage, "push", "--set-upstream", REMOTE, _branch(storage))
        pushed = True
    return SetupReport(cloned=cloned, initialised=initialised, pushed=pushed)


def run_sync(storage: Storage, message: str | None = None) -> SyncReport:
    """Commit local changes, bring in the other computer's, and push (FR-82)."""
    if not is_repository(storage) or remote_url(storage) is None:
        raise CubitError(
            "This data folder is not set up for syncing.",
            hint="Run 'cubit sync setup <git-url>' first.",
        )
    if _unfinished_git_work(storage) or _branch(storage) == "HEAD":
        raise CubitError(
            f"A git merge or rebase in {storage.data_dir} was never finished.",
            hint="Finish it, or undo it with 'git rebase --abort', then run 'cubit sync' again.",
        )
    timer = storage.read_timer()
    if timer is not None:
        raise CubitError(
            f"A timer is running for {timer.project_id!r}, and a timer does not sync.",
            hint="Stop it with 'cubit stop', or drop it with 'cubit cancel', then sync.",
        )

    with storage.lock():
        storage.ensure_gitignore()
        _git(storage, "rm", "-r", "--cached", "--ignore-unmatch", "--quiet", ".DS_Store")
        committed = _commit_all(storage, message or _default_message())

        branch = _branch(storage)
        remote_has_branch = (
            _git(
                storage, "ls-remote", "--exit-code", "--heads", REMOTE, branch, check=False
            ).returncode
            == 0
        )

        pulled = 0
        if remote_has_branch:
            _git(storage, "fetch", REMOTE, branch)
            counted = _git(storage, "rev-list", "--count", "HEAD..FETCH_HEAD").stdout.strip()
            pulled = int(counted or 0)
            if pulled and _git(storage, "rebase", "FETCH_HEAD", check=False).returncode != 0:
                _git(storage, "rebase", "--abort", check=False)
                raise CubitError(
                    "Both computers changed the same lines, so git could not merge them.",
                    hint=(
                        f"Nothing was lost. Resolve it in {storage.data_dir} with "
                        f"'git pull --rebase {REMOTE} {branch}', then run 'cubit sync' again."
                    ),
                )

        pushed = _push_needed(storage, branch, remote_has_branch)
        if pushed:
            _git(storage, "push", "--set-upstream", REMOTE, branch)
    return SyncReport(committed=committed, pulled=pulled, pushed=pushed)


def _push_needed(storage: Storage, branch: str, remote_has_branch: bool) -> bool:
    if not remote_has_branch:
        return True
    ahead = _git(storage, "rev-list", "--count", f"{REMOTE}/{branch}..HEAD", check=False)
    return ahead.returncode != 0 or int(ahead.stdout.strip() or 0) > 0
