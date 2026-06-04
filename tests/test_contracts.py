from optcg_card_bot.contracts import (
    load_poneglyph_openapi,
    require_card_detail_schema,
    require_endpoint,
    require_search_parameters,
)


def test_vendored_openapi_contains_mvp_endpoints() -> None:
    contract = load_poneglyph_openapi()

    for path in ["/v1/search", "/v1/cards/{card_number}", "/v1/random"]:
        require_endpoint(contract, path)


def test_vendored_openapi_contains_required_search_parameters() -> None:
    contract = load_poneglyph_openapi()

    assert require_search_parameters(contract) == {
        "q",
        "page",
        "limit",
        "sort",
        "order",
        "collapse",
        "lang",
    }


def test_vendored_openapi_contains_card_detail_shape() -> None:
    contract = load_poneglyph_openapi()

    required = require_card_detail_schema(contract)

    assert {"card_number", "name", "variants", "official_faq"} <= required
