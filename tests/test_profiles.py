from pathlib import Path

from engine.profile_loader import load_all_profiles

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


def test_all_profiles_load():
    profiles = load_all_profiles(PROFILES_DIR)
    assert len(profiles) == len(list(PROFILES_DIR.glob("*.yaml")))
