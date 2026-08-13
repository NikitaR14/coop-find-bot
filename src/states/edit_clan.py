from aiogram.fsm.state import State, StatesGroup


class EditClanForm(StatesGroup):
    choose_field = State()
    name = State()
    game = State()
    raven_cluster = State()
    raven_server = State()
    lineage_server = State()
    mmo_server = State()
    mmo_faction = State()
    description = State()
    demands = State()
    photo = State()
