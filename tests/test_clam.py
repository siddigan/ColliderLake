import shutil

from src.acquire.clam import (
    HeaderDiagnosis,
    _aria2c_command,
    download_file,
    resolve_target,
)


def test_resolve_registered_2012_target():
    target = resolve_target("run2012bc_doublemuparked", "Run2012BC_DoubleMuParked_Muons.root")
    assert target.expected_size == 2244449133
    assert target.url.endswith("/Run2012BC_DoubleMuParked_Muons.root")
    assert target.xrootd_url.startswith("root://eospublic.cern.ch/")
    assert target.output_path.as_posix().endswith(
        "data/raw/run2012bc_doublemuparked/Run2012BC_DoubleMuParked_Muons.root"
    )


def test_aria2c_command_is_resume_safe():
    target = resolve_target("run2012bc_doublemuparked", "Run2012BC_DoubleMuParked_Muons.root")
    command = _aria2c_command(target)
    assert "-c" in command
    assert "--max-tries=0" in command
    assert "-x" in command and "4" in command
    assert "--file-allocation=none" in command


def test_auto_download_falls_back_to_native_when_aria2_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    shutil.copytree("configs", tmp_path / "configs")
    calls = []

    monkeypatch.setattr("src.acquire.clam.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "src.acquire.clam.diagnose_url",
        lambda url: HeaderDiagnosis(url, url, True, 10, None),
    )
    monkeypatch.setattr("src.acquire.clam.native_download", lambda target, **kwargs: calls.append(target.name))
    monkeypatch.setattr("src.acquire.clam.verify_target", lambda target: None)
    monkeypatch.setattr("src.acquire.clam.acquire_dataset", lambda dataset_id: None)

    output = download_file("run2012bc_doublemuparked", "Run2012BC_DoubleMuParked_Muons.root")

    assert calls == ["Run2012BC_DoubleMuParked_Muons.root"]
    assert output.as_posix().endswith("Run2012BC_DoubleMuParked_Muons.root")
