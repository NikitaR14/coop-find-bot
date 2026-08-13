from aiogram.fsm.state import State, StatesGroup


class EditProfileForm(StatesGroup):
    choose_field = State()
    nickname = State()
    age = State()
    telegram_tag = State()
    gender = State()
    games = State()
    rank = State()
    aion_server = State()
    aion_faction = State()
    aion_rank = State()
    time = State()
    add_new_time = State()
    add_new_game = State()

    add_warcraft_mode = State()
    add_warcraft_rank = State()
    add_new_warcraft_rank = State()

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

    gallery = State()
    about = State()
    goal = State()
    add_new_goal = State()
    photo = State()
    is_active = State()
    clear = State()
    num_rank = State()
