"""B2/B3 — the local learning store (null default + native file-backed)."""

from tack.adapters.native import FileLearningStore
from tack.core.learning import LearningStore, NullLearningStore


def test_null_store_conforms_and_is_inert():
    s = NullLearningStore()
    assert isinstance(s, LearningStore)
    assert s.prior_knowledge() == ""
    s.record_success("x")  # no-ops, no error
    s.record_anti_pattern("a", "b")


def test_file_store_roundtrips_playbook_and_anti_patterns(tmp_path):
    s = FileLearningStore(root=str(tmp_path / "dev"))
    assert isinstance(s, LearningStore)
    assert s.prior_knowledge() == ""
    s.record_success("use uv for envs")
    s.record_anti_pattern("repeated action: bash:false", "looped on a failing cmd")
    pk = s.prior_knowledge()
    assert "use uv for envs" in pk
    assert "repeated action: bash:false" in pk
    assert "playbook" in pk.lower()
    assert "anti-pattern" in pk.lower()


def test_file_store_dedups(tmp_path):
    s = FileLearningStore(root=str(tmp_path / "dev"))
    s.record_success("same note")
    s.record_success("same note")
    assert s.prior_knowledge().count("same note") == 1


def test_file_store_honours_tack_home_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TACK_HOME", str(tmp_path / "home"))
    s = FileLearningStore()
    s.record_success("note")
    assert (tmp_path / "home" / "playbook.md").exists()
