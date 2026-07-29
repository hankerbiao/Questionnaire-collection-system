from app.config import Settings


def test_settings_builds_replica_set_mongodb_uri() -> None:
    settings = Settings(
        mongodb_uri="",
        mongodb_hosts="10.17.159.232:27017,10.17.159.228:27017,10.17.158.254:27017",
        mongodb_username="dml_v4_survey_user",
        mongodb_password="W9=kfsGWp6a@IDQV(OKz",
        mongodb_database="dml_v4_survey",
        mongodb_auth_source="dml_v4_survey",
        mongodb_replica_set="rs0",
    )

    assert settings.mongodb_uri == (
        "mongodb://dml_v4_survey_user:W9%3DkfsGWp6a%40IDQV%28OKz@"
        "10.17.159.232:27017,10.17.159.228:27017,10.17.158.254:27017/"
        "dml_v4_survey?authSource=dml_v4_survey&replicaSet=rs0&w=1"
    )


def test_settings_preserves_explicit_mongodb_uri() -> None:
    settings = Settings(
        mongodb_uri="mongodb://example.mongodb.local:27017/custom",
        mongodb_hosts="10.17.159.232:27017",
        mongodb_username="ignored",
        mongodb_password="ignored",
    )

    assert settings.mongodb_uri == "mongodb://example.mongodb.local:27017/custom"
