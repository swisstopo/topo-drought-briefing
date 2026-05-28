# tests/test_i18n.py
from config.settings import BERNE_REGION_NAMES_FR, CDI_LABELS_FR


def test_fr_region_names_has_all_berne_regions():
    from config.settings import BERNE_REGION_IDS
    assert set(BERNE_REGION_NAMES_FR.keys()) == BERNE_REGION_IDS


def test_fr_cdi_labels_has_all_levels():
    assert set(CDI_LABELS_FR.keys()) == set(range(6))


def test_fr_region_34_is_mittelland():
    assert BERNE_REGION_NAMES_FR[34] == "Mittelland bernois"


def test_fr_cdi_label_0_is_no_drought():
    assert CDI_LABELS_FR[0] == "Pas de sécheresse"
