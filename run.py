import argparse

from agri_vision.api import serve
from agri_vision.config import Settings, validate_runtime_security
from agri_vision.inference import HttpInferenceEngine


def main() -> None:
    settings = Settings.from_environment()
    parser = argparse.ArgumentParser(description="Agri Vision MVP")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--database", default=settings.database)
    parser.add_argument("--media-dir", default=settings.media_dir)
    args = parser.parse_args()
    try:
        validate_runtime_security(args.host, settings.api_key)
    except ValueError as error:
        parser.error(str(error))
    engine = HttpInferenceEngine(settings.inference_url, settings.inference_model_version, settings.inference_api_key, settings.inference_timeout) if settings.inference_url else None
    serve(args.host, args.port, args.database, args.media_dir, settings.api_key, engine)


if __name__ == "__main__":
    main()
