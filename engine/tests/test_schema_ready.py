import supabase_client as db


def test_schema_ready_true_when_version_met(monkeypatch):
    monkeypatch.setattr(db, "select", lambda t, p=None: [{"version": 2}])
    assert db.schema_ready(2) is True


def test_schema_ready_false_when_older_or_empty(monkeypatch):
    monkeypatch.setattr(db, "select", lambda t, p=None: [{"version": 1}])
    assert db.schema_ready(2) is False
    monkeypatch.setattr(db, "select", lambda t, p=None: [])
    assert db.schema_ready(2) is False


def test_schema_ready_false_when_table_missing(monkeypatch):
    def boom(t, p=None):
        raise RuntimeError("Supabase select failed [404]: relation does not exist")
    monkeypatch.setattr(db, "select", boom)
    assert db.schema_ready(2) is False
