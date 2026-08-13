from aiogram.fsm.state import State, StatesGroup


class SendMessageForm(StatesGroup):
    message = State()
    message_without_game = State()


class GameForm(StatesGroup):
    search_type = State()
    game = State()


class SearchForm(StatesGroup):
    game = State()
    warcraft_mode = State()
    warcraft_rank = State()
    mode = State()
    rank = State()

    # AION 2
    aion_server = State()
    aion_faction = State()
    aion_rank = State()

    # RAVEN
    raven_cluster = State()
    raven_server = State()
    raven_class = State()
    raven_level = State()
    raven_stats = State()

    # LINEAGE
    lineage_server = State()
    lineage_rasa = State()
    lineage_class = State()
    lineage_level = State()
    lineage_stats = State()

    donate = State()
    budget = State()
    transfer = State()

    goal = State()
    num_rank = State()


class ClanForm(StatesGroup):
    message = State()


class ClanFilterForm(StatesGroup):
    server = State()
    faction = State()
