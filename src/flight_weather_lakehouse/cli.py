import argparse
import asyncio
import json

from .config import get_settings
from .demo import write_demo_data
from .lake import build_lake
from .logging import configure_logging
from .pipeline import Pipeline
from .warehouse import build_warehouse


def build_pipeline() -> Pipeline:
    settings = get_settings()
    configure_logging(settings.log_level)
    return Pipeline(settings, build_lake(settings), build_warehouse(settings.warehouse_provider, settings.duckdb_path, settings.bigquery_project, settings.bigquery_dataset))


def main() -> None:
    parser = argparse.ArgumentParser(description="Flight and weather lakehouse runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest")
    subparsers.add_parser("load")
    pipeline_parser = subparsers.add_parser("pipeline")
    pipeline_parser.add_argument("--once", action="store_true")
    subparsers.add_parser("bootstrap-demo")
    args = parser.parse_args()
    pipeline = build_pipeline()
    if args.command == "ingest":
        print(json.dumps(asyncio.run(pipeline.ingest())))
    elif args.command == "load":
        print(json.dumps(pipeline.load()))
    elif args.command == "bootstrap-demo":
        write_demo_data(pipeline.lake)
        print(json.dumps(pipeline.load()))
    elif args.once:
        print(json.dumps(asyncio.run(pipeline.run_once())))
    else:
        asyncio.run(pipeline.run_forever())


if __name__ == "__main__":
    main()

