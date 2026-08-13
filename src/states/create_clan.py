from aiogram.fsm.state import State, StatesGroup


class ClanForm(StatesGroup):
    name = State()
    game = State()

    # RAVEN
    raven_cluster = State()
    raven_server = State()

    # LINEAGE
    lineage_server = State()

    # AION 2
    aion_server = State()
    aion_faction = State()
    mmo_server = State()
    mmo_faction = State()

    description = State()
    demands = State()
    photo = State()
    check = State()
