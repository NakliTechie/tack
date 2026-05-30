"""A8 + A9 — verification discovery/running, and the safety/economics guards."""

from tack.adapters.native import NativeExecFS
from tack.core.safety import DoomLoopDetector, GitStepper, is_dangerous
from tack.core.verify import discover_verify_command, run_verification


# --- A8 verification ------------------------------------------------------
def test_discover_explicit_wins(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    assert discover_verify_command(fs, explicit="make check") == "make check"


def test_discover_reads_tack_verify_file(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write(".tack/verify", "pytest -q -k foo\n")
    assert discover_verify_command(fs) == "pytest -q -k foo"


def test_discover_infers_pytest(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("test_x.py", "def test_x():\n    assert True\n")
    assert discover_verify_command(fs) == "pytest -q"


def test_discover_none_when_no_markers(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    assert discover_verify_command(fs) is None


def test_run_verification_pass_and_fail(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    assert run_verification(fs, "true").passed
    out = run_verification(fs, "echo boom 1>&2; false")
    assert not out.passed
    assert "FAILED" in out.feedback
    assert "boom" in out.feedback


# --- A9 dangerous-command detection --------------------------------------
def test_is_dangerous_matches_destructive():
    assert is_dangerous("rm -rf /")
    assert is_dangerous("rm -fr build")
    assert is_dangerous(":(){ :|:& };:")
    assert is_dangerous("dd if=/dev/zero of=/dev/sda")
    assert is_dangerous("mkfs.ext4 /dev/sdb")


def test_is_dangerous_allows_benign():
    assert is_dangerous("echo hi") is None
    assert is_dangerous("pytest -q") is None
    assert is_dangerous("rm build/tmp.o") is None


# --- A9 doom-loop detection ----------------------------------------------
def test_doom_same_action_n_times():
    d = DoomLoopDetector(window=3)
    d.record("bash:false", False, "err")
    d.record("bash:false", False, "err")
    assert not d.is_doomed()
    d.record("bash:false", False, "err")
    assert d.is_doomed()


def test_doom_same_error_different_actions():
    d = DoomLoopDetector(window=3)
    d.record("edit:a", False, "ImportError: x")
    d.record("edit:b", False, "ImportError: x")
    d.record("edit:c", False, "ImportError: x")
    assert d.is_doomed()


def test_doom_quiet_on_progress():
    d = DoomLoopDetector(window=3)
    d.record("read:a", True)
    d.record("edit:b", True)
    d.record("bash:pytest", True)
    assert not d.is_doomed()


# --- A9 git-per-step ------------------------------------------------------
def test_git_stepper_commits_each_step_and_reverts(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    g = GitStepper(fs)
    g.ensure_repo()
    fs.write("a.txt", "one")
    h1 = g.commit("step 1")
    fs.write("a.txt", "two")
    h2 = g.commit("step 2")
    assert h1 and h2 and h1 != h2
    assert fs.read("a.txt") == "two"
    g.revert_to(h1)
    assert fs.read("a.txt") == "one"


def test_git_stepper_skips_empty_step(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    g = GitStepper(fs)
    g.ensure_repo()
    fs.write("a.txt", "one")
    h1 = g.commit("step 1")
    h2 = g.commit("no-op step")  # nothing changed
    assert h1 == h2
