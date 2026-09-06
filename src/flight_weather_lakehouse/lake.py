import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .config import Settings


class Lake(Protocol):
    def put(self, source: str, entity: str, payload: dict[str, Any], observed_at: datetime) -> str: ...
    def list_objects(self) -> list[str]: ...
    def get(self, object_key: str) -> dict[str, Any]: ...


def object_key(source: str, entity: str, observed_at: datetime) -> str:
    observed_at = observed_at.astimezone(UTC)
    return (
        f"raw/source={source}/entity={entity}/dt={observed_at:%Y-%m-%d}/"
        f"hour={observed_at:%H}/{observed_at:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex}.json"
    )


class LocalLake:
    def __init__(self, root: Path):
        self.root = root

    def put(self, source: str, entity: str, payload: dict[str, Any], observed_at: datetime) -> str:
        key = object_key(source, entity, observed_at)
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        return key

    def list_objects(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*.json"))

    def get(self, object_key: str) -> dict[str, Any]:
        return json.loads((self.root / object_key).read_text(encoding="utf-8"))


class S3Lake:
    def __init__(self, bucket: str, region: str):
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    def put(self, source: str, entity: str, payload: dict[str, Any], observed_at: datetime) -> str:
        key = object_key(source, entity, observed_at)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=json.dumps(payload).encode(), ContentType="application/json")
        return key

    def list_objects(self) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        return sorted(item["Key"] for page in paginator.paginate(Bucket=self.bucket, Prefix="raw/") for item in page.get("Contents", []))

    def get(self, object_key: str) -> dict[str, Any]:
        body = self.client.get_object(Bucket=self.bucket, Key=object_key)["Body"].read()
        return json.loads(body)


def build_lake(settings: Settings) -> Lake:
    if settings.lake_provider == "s3":
        if not settings.aws_s3_bucket:
            raise ValueError("AWS_S3_BUCKET is required for LAKE_PROVIDER=s3")
        return S3Lake(settings.aws_s3_bucket, settings.aws_region)
    return LocalLake(settings.local_lake_path)

