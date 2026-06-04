from optcg_card_bot.interactions import (
    CardSelectView,
    build_choice_options,
    create_bot,
)
from optcg_card_bot.search import CardChoice


def test_choice_options_include_card_number_and_name() -> None:
    choices = (
        CardChoice(
            card_number="OP01-001",
            name="Roronoa Zoro",
            set_code="OP01",
            card_type="Leader",
            color=("Red",),
        ),
    )

    options = build_choice_options(choices)

    assert options[0].label == "Roronoa Zoro"
    assert options[0].value == "OP01-001"
    assert options[0].description == "OP01 • Leader • Red"


def test_select_view_tracks_owner_and_query() -> None:
    view = CardSelectView(
        owner_id=123,
        source_query="luffy",
        action="card",
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
    )

    assert view.owner_id == 123
    assert view.source_query == "luffy"
    assert view.action == "card"
    assert view.timeout == 180


def test_create_bot_registers_expected_commands() -> None:
    bot = create_bot(command_service=None)

    names = {command.name for command in bot.tree.get_commands()}

    assert {"card", "search", "random", "faq", "help"} <= names
