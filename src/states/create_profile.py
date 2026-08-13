from aiogram.fsm.state import State, StatesGroup


### ФОРМА ДЛЯ АНКЕТЫ
class ProfileForm(StatesGroup):
    nickname = State()
    age = State()
    telegram_tag = State()
    gender = State()
    game = State()

    rank = State()

    # AION 2
    aion_server = State()
    aion_faction = State()
    aion_rank = State()

    # WOR | RSL
    num_rank = State()

    # WARCRAFT
    add_warcraft_mode = State()
    add_warcraft_rank = State()

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

    gallery = State()
    add_new_game = State()

    time = State()
    add_new_time = State()
    about = State()
    goal = State()
    add_new_goal = State()

    donate = State()
    budget = State()
    transfer = State()

    photo = State()
    check_profile = State()
    is_active = State()
