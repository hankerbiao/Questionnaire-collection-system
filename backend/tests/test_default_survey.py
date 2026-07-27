from app.default_survey import default_survey


def test_default_catalog_covers_live_dml_navigation() -> None:
    survey = default_survey("published", 1)
    names = {page.name for page in survey.pages}
    assert {"首页", "测试需求", "测试用例", "测试计划管理", "Excel测试计划管理"} <= names
    assert len([page for page in survey.pages if page.enabled]) >= 3
    assert all(any(feature.enabled for feature in page.features) for page in survey.pages if page.enabled)
    restricted = next(page for page in survey.pages if page.name == "Tx XH测试用例")
    assert restricted.enabled is False


def test_publish_validation_rejects_enabled_page_without_feature() -> None:
    survey = default_survey("draft", 0)
    survey.pages[0].features = []
    try:
        survey.validate_for_publish()
    except ValueError as error:
        assert "至少需要一个启用功能点" in str(error)
    else:
        raise AssertionError("publish validation should fail")


def test_default_survey_returns_independent_copies() -> None:
    first = default_survey("draft", 0)
    first.pages.clear()

    second = default_survey("draft", 0)

    assert second.pages
