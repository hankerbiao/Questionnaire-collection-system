import argparse
import asyncio
import json

from pymongo import AsyncMongoClient

from app.config import get_settings
from app.default_survey import default_survey
from app.repository import SubmissionRepository


async def purge_development_data(confirm: bool) -> None:
    if not confirm:
        raise SystemExit("Pass --confirm to purge all development survey data.")
    settings = get_settings()
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
    )
    database = client[settings.mongodb_database]
    collections = [
        "submissions",
        "survey_versions",
        "survey_attachments.files",
        "survey_attachments.chunks",
        "admin_audit_events",
    ]
    try:
        await client.admin.command("ping")
        before = {name: await database[name].count_documents({}) for name in collections}
        for name in collections:
            await database.drop_collection(name)

        repository = SubmissionRepository(client, settings.mongodb_database)
        await repository.ensure_indexes()
        await repository.ensure_default_survey(
            default_survey("published", 1),
            default_survey("draft", 0),
        )
        published = await repository.get_current_survey()
        draft = await repository.get_survey_draft("dml-v4")
        print(json.dumps({
            "deleted": before,
            "created": {
                "publishedVersion": published["version"] if published else None,
                "publishedVersionId": str(published["_id"]) if published else None,
                "draftId": str(draft["_id"]) if draft else None,
            },
        }, ensure_ascii=False))
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete and recreate all development survey data.")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    asyncio.run(purge_development_data(args.confirm))


if __name__ == "__main__":
    main()
