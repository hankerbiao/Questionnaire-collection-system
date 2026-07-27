import argparse
import asyncio
import json

from pymongo import AsyncMongoClient

from app.config import get_settings
from app.default_survey import default_survey
from app.repository import SubmissionRepository
from app.survey_models import SurveyDraftUpdate


def default_draft_update(current_revision: int) -> SurveyDraftUpdate:
    template = default_survey("draft", 0)
    return SurveyDraftUpdate(
        revision=current_revision,
        title=template.title,
        description=template.description,
        roles=template.roles,
        pages=template.pages,
    )


def published_summary(published: dict) -> dict:
    enabled_pages = [page for page in published["pages"] if page.get("enabled", True)]
    return {
        "version": published["version"],
        "versionId": str(published["_id"]),
        "pageIds": [page["id"] for page in enabled_pages],
        "enabledFeatureCount": sum(
            1
            for page in enabled_pages
            for feature in page.get("features", [])
            if feature.get("enabled", True)
        ),
    }


async def publish_default_survey(confirm: bool) -> None:
    if not confirm:
        raise SystemExit("Pass --confirm to replace the current draft and publish the template.")

    settings = get_settings()
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
    )
    repository = SubmissionRepository(client, settings.mongodb_database)
    try:
        await repository.ping()
        await repository.ensure_indexes()

        current_draft = await repository.get_survey_draft("dml-v4")
        if current_draft is None:
            raise RuntimeError("Current DML survey draft does not exist.")

        update = default_draft_update(current_draft["revision"])
        refreshed_draft = await repository.save_survey_draft("dml-v4", update)
        if refreshed_draft is None:
            raise RuntimeError("Draft changed concurrently; no data was published.")

        published = await repository.publish_survey_draft(
            "dml-v4",
            expected_revision=refreshed_draft["revision"],
        )
        if published is None:
            raise RuntimeError("Draft changed before publication; publication was cancelled.")

        print(json.dumps(published_summary(published), ensure_ascii=False))
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace the DML survey draft with the code template and publish it.",
    )
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    asyncio.run(publish_default_survey(args.confirm))


if __name__ == "__main__":
    main()
