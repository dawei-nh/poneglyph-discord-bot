import json
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = PROJECT_ROOT / "contracts" / "poneglyph" / "openapi.json"

JsonObject = dict[str, Any]

REQUIRED_SEARCH_PARAMETERS = {
    "q",
    "page",
    "limit",
    "sort",
    "order",
    "collapse",
    "lang",
}


def json_member(data: JsonObject, key: str) -> object:
    return data.get(key)


def json_string_member(data: object, key: str) -> str | None:
    if not isinstance(data, dict):
        return None

    value = json_member(cast(JsonObject, data), key)
    if not isinstance(value, str):
        return None

    return value


def load_json_file(path: Path) -> JsonObject:
    with path.open(encoding="utf-8") as file:
        data: object = json.load(file)

    if not isinstance(data, dict):
        raise AssertionError(f"{path} must contain a JSON object")

    return cast(JsonObject, data)


def load_poneglyph_openapi() -> JsonObject:
    return load_json_file(OPENAPI_PATH)


def require_endpoint(contract: JsonObject, path: str) -> JsonObject:
    paths = json_member(contract, "paths")
    if not isinstance(paths, dict):
        raise AssertionError("OpenAPI contract is missing object 'paths'")
    paths_object = cast(JsonObject, paths)

    endpoint = json_member(paths_object, path)
    if not isinstance(endpoint, dict):
        raise AssertionError(f"OpenAPI contract is missing object endpoint {path}")

    return cast(JsonObject, endpoint)


def require_search_parameters(contract: JsonObject) -> set[str]:
    endpoint = require_endpoint(contract, "/v1/search")
    operation = json_member(endpoint, "get")
    if not isinstance(operation, dict):
        raise AssertionError("OpenAPI endpoint /v1/search is missing GET operation")
    operation_object = cast(JsonObject, operation)

    parameters = json_member(operation_object, "parameters")
    if not isinstance(parameters, list):
        raise AssertionError("OpenAPI GET /v1/search is missing parameter list")
    parameter_items = cast(list[Any], parameters)

    names = {
        name
        for parameter in parameter_items
        if (name := json_string_member(parameter, "name")) is not None
    }
    missing = REQUIRED_SEARCH_PARAMETERS - names
    if missing:
        missing_parameters = ", ".join(sorted(missing))
        raise AssertionError(
            f"OpenAPI GET /v1/search is missing parameters: {missing_parameters}"
        )

    return set(REQUIRED_SEARCH_PARAMETERS)


def require_card_detail_schema(contract: JsonObject) -> set[str]:
    endpoint = require_endpoint(contract, "/v1/cards/{card_number}")
    operation = json_member(endpoint, "get")
    if not isinstance(operation, dict):
        raise AssertionError(
            "OpenAPI endpoint /v1/cards/{card_number} is missing GET operation"
        )
    operation_object = cast(JsonObject, operation)

    responses = json_member(operation_object, "responses")
    if not isinstance(responses, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing responses object"
        )

    response_200 = json_member(cast(JsonObject, responses), "200")
    if not isinstance(response_200, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing 200 response object"
        )

    content = json_member(cast(JsonObject, response_200), "content")
    if not isinstance(content, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing 200 content object"
        )

    media_type = json_member(cast(JsonObject, content), "application/json")
    if not isinstance(media_type, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing application/json"
        )

    schema = json_member(cast(JsonObject, media_type), "schema")
    if not isinstance(schema, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing 200 JSON schema"
        )

    properties = json_member(cast(JsonObject, schema), "properties")
    if not isinstance(properties, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing schema properties"
        )

    data_schema = json_member(cast(JsonObject, properties), "data")
    if not isinstance(data_schema, dict):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} is missing data schema"
        )

    required = json_member(cast(JsonObject, data_schema), "required")
    if not isinstance(required, list):
        raise AssertionError(
            "OpenAPI GET /v1/cards/{card_number} data schema is missing required list"
        )

    return {field for field in cast(list[Any], required) if isinstance(field, str)}
