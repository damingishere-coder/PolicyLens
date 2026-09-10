import pytest

from policylens_api.backup import BackupError
from policylens_api.household import HouseholdService
from policylens_api.household_domain import PolicyInput
from policylens_api.runtime_gate import RuntimeGate
from policylens_api.service import ConflictError


@pytest.mark.parametrize("failure", ["wrap_before_switch", "reload_after_switch"])
def test_restore_keeps_original_directories_and_cipher_when_key_operations_fail(
    service, tmp_path, monkeypatch, failure
):
    family = HouseholdService(service)
    family.save_policy(PolicyInput(name="SYNTHETIC in backup"))
    backup = tmp_path / "restore-safety.plbackup"
    service.create_backup("SYNTHETIC-safe-restore", backup)
    survivor = family.save_policy(PolicyInput(name="SYNTHETIC must survive failed restore"))
    expected = [p.model_dump(mode="json") for p in family.list_policies()]
    preview = service.preview_restore("SYNTHETIC-safe-restore", backup)

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC injected key failure")

    if failure == "wrap_before_switch":
        monkeypatch.setattr(service.key_manager.protector, "protect", fail)
    else:
        monkeypatch.setattr(service.key_manager, "load_or_create", fail)
    with pytest.raises(BackupError):
        service.commit_restore(preview["restore_token"])
    assert [p.model_dump(mode="json") for p in family.list_policies()] == expected
    assert family.policy(survivor.id).name == "SYNTHETIC must survive failed restore"
    assert (service.data_dir / "keys/dek.dpapi.json").exists()
    assert list((service.data_dir / "backups").glob("pre-restore-*.pllocal"))


def test_restore_gate_excludes_inflight_requests_and_all_external_work():
    gate = RuntimeGate()
    with gate.request(), pytest.raises(ConflictError), gate.request(restoring=True):
        pytest.fail("restore must not enter with an active request")
    with gate.external():
        with gate.request():
            pass  # Progress and cancellation stay readable.
        with pytest.raises(ConflictError), gate.external():
            pytest.fail("second external operation must not run")
        with pytest.raises(ConflictError), gate.request(restoring=True):
            pytest.fail("restore must not enter with background research")
    with gate.request(restoring=True):
        with pytest.raises(ConflictError), gate.request():
            pytest.fail("requests must not observe a partially switched database")
        with pytest.raises(ConflictError), gate.external():
            pytest.fail("external work must not start during restore")
    with gate.request():
        pass
