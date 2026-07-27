from app.default_survey import default_survey
from scripts.publish_default_survey import default_draft_update, published_summary


def test_default_publish_helpers_use_page_catalog_structure() -> None:
    update = default_draft_update(7)
    assert update.revision == 7
    assert len(update.pages) >= 3
    assert all(page.features for page in update.pages if page.enabled)

    published = default_survey("published", 1).model_dump(mode="python")
    published.update({"_id": "version-id", "version": 4})
    summary = published_summary(published)
    assert summary["version"] == 4
    assert summary["versionId"] == "version-id"
    assert len(summary["pageIds"]) == 21
    assert summary["enabledFeatureCount"] == 72
