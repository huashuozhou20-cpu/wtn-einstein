from einstein_wtn import i18n


def test_translations_cover_keys():
    required = [
        "window_title",
        "game_group",
        "move_log",
        "dice_group",
        "status_ready",
    ]
    for lang in i18n.available_langs():
        for key in required:
            assert key in i18n._LANG_MAP[lang]  # type: ignore[attr-defined]
            assert isinstance(i18n.t(key, lang), str)


def test_missing_key_raises():
    try:
        i18n.t("missing-key", "zh")
    except ValueError:
        return
    assert False, "Expected ValueError for missing key"


def test_language_key_sets_match():
    zh_keys = set(i18n.LANG_ZH.keys())
    en_keys = set(i18n.LANG_EN.keys())
    assert zh_keys == en_keys
