from unittest import skip
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.constants import BUDGETS, GAME_LIST, FIELDS_LIST, GOALS_LIST, CONVENIENT_TIME
from utils.ranks import *
from models.profile import Game
from utils.raven import CLUSTERS, SERVERS, CLASSES
from utils.lineage import SERVER_TEXT, West, East, JP, RASES, CLASSES as LINEAGE_CLASSES

TEXT_BACK = "Назад"

async def get_skip_keyboard(with_back: bool = True, skip: bool = False) -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="Пропустить")]]
    
    if skip:
        buttons.append([KeyboardButton(text="Пропустить")])

    if with_back:
        buttons.append([KeyboardButton(text=TEXT_BACK)])
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=True
    )

async def get_back_kb(skip: bool = False) -> ReplyKeyboardMarkup:
    kb = [[KeyboardButton(text=TEXT_BACK)]]
    if skip:
        kb.insert(0, [KeyboardButton(text="Пропустить")])
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        one_time_keyboard=True
    )

async def get_gender_keyboard(with_back: bool = True) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Мужской", callback_data="gender_Мужской")],
        [InlineKeyboardButton(text="Женский", callback_data="gender_Женский")],
        [InlineKeyboardButton(text="Пропустить", callback_data="gender_skip")]
    ]
    if with_back:
        buttons.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"gender_back")])
        
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )
    return keyboard

async def get_game_kb(with_back: bool = True, n: int = 2, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for idx, game in enumerate(GAME_LIST):
        if idx < 18 * (page - 1) or idx >= 18 * page:
            continue
        builder.add(
            InlineKeyboardButton(text=GAME_LIST[game],
                                 callback_data=f"save_profile_game_{game}")
        )
    
    query_next = f"game_page_{page + 1}" if 18*page < len(GAME_LIST) else "blank"
    query_prev = f"game_page_{page - 1}" if page > 1 else "blank"
    if with_back:
        query_prev += "_back"
        query_next += "_back"

        
    btn_next = InlineKeyboardButton(text="Вперед ▶️", callback_data=query_next)
    btn_prev = InlineKeyboardButton(text="◀️ Назад", callback_data=query_prev)


    builder.adjust(n)
    builder.row(btn_prev, btn_next)
    builder.row(InlineKeyboardButton(text=f"{page}/{len(GAME_LIST) // 18 + 1}", callback_data="blank"))    

    
    if with_back:
        builder.row(InlineKeyboardButton(text="Назад", callback_data="back_from_games"))
    
    keyboard = builder.as_markup()
    return keyboard

async def get_photo_kb(with_back: bool = True) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="Фото с профиля")],
        [KeyboardButton(text="Пропустить")]
    ]
    
    if with_back:
        buttons.append([KeyboardButton(text=TEXT_BACK)])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

async def get_confirmation_kb(with_back: bool = True, skip: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Да", callback_data="confirm_Да")],
        [InlineKeyboardButton(text="Нет", callback_data="confirm_Нет")]
    ]

    if skip:
        buttons.append([InlineKeyboardButton(text="Пропустить", callback_data="confirm_skip")])
    
    if with_back:
        buttons.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"confirm_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def get_tag_kb(with_back: bool = True) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="Отправить данные")],
        [KeyboardButton(text="Пропустить")]
    ]
    
    if with_back:
        buttons.append([KeyboardButton(text=TEXT_BACK)])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

async def get_commit_profile_kb(with_back: bool = False):
    builder = InlineKeyboardBuilder()
    builder.button(text="Верно ✅", callback_data="profile_correct")
    builder.button(text="Неверно ❌", callback_data="profile_incorrect")
    if with_back:
        builder.button(text=TEXT_BACK, callback_data="back_from_check")
    builder.adjust(2)
    return builder.as_markup()

async def get_status_kb(with_back: bool = False):
    builder = InlineKeyboardBuilder()
    builder.button(text="Разрешить ✅", callback_data="status_true")
    builder.button(text="Запретить ❌", callback_data="status_false")
    if with_back:
        builder.button(text=TEXT_BACK, callback_data="back_from_status")
    builder.adjust(2)
    return builder.as_markup()

# Остальные клавиатуры остаются без изменений
async def get_game_inline_kb(page: int = 1, with_back: bool = False) -> InlineKeyboardMarkup:
    """Inline клавиатура для выбора игр"""
    builder = InlineKeyboardBuilder()
    
    for idx, game in enumerate(GAME_LIST):
        if idx < 18 * (page - 1) or idx >= 18 * page:
            continue
        builder.add(InlineKeyboardButton(
            text=GAME_LIST[game],
            callback_data=f"get_profiles_by_{game}"
        ))

    builder.adjust(2)
    
    
    query_next = f"game_inline_page_{page + 1}" if 18*page < len(GAME_LIST) else "blank"
    query_prev = f"game_inline_page_{page - 1}" if page > 1 else "blank"
    
    if with_back:
        query_prev += "_back"
        query_next += "_back"

    btn_next = InlineKeyboardButton(text="Вперед ▶️", callback_data=query_next)
    btn_prev = InlineKeyboardButton(text="◀️ Назад", callback_data=query_prev)
    builder.row(btn_prev, btn_next)
    builder.row(InlineKeyboardButton(text=f"{page}/{len(GAME_LIST) // 18 + 1}", callback_data="blank"))    



    if with_back:
        builder.row(InlineKeyboardButton(text="Назад", callback_data="get_profiles_by_back"))
    return builder.as_markup()

async def get_profile_kb(user_id: int) -> InlineKeyboardBuilder:
    buttons = [
        InlineKeyboardButton(text="Создать анкету", callback_data="create_profile"),
        InlineKeyboardButton(text="Показать профиль", callback_data=f"read_profile_self_{user_id}"),
        InlineKeyboardButton(text="Изменить анкету📝", callback_data="edit_profile"),
        InlineKeyboardButton(text="Удалить анкету❌", callback_data="delete_profile"),
        InlineKeyboardButton(text="Снять анкету ⏸️", callback_data="deactivate_profile"),
        InlineKeyboardButton(text="Разместить анкету 📢", callback_data="activate_profile"),
        InlineKeyboardButton(text="Назад", callback_data="menu")
    ]

    builder = InlineKeyboardBuilder()

    for button in buttons:
        builder.add(button)

    builder.adjust(1)

    return builder

async def get_interaction_kb(profile_id: int, game: str, need_filter: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text="Галерея",
            callback_data=f"show_gallery_profile_{profile_id}_{game}" if not need_filter else f"show_gallery_profilefilter_{profile_id}_{game}"
        )],
        [InlineKeyboardButton(
            text="Написать сообщение",
            callback_data=f"send_message_to_profile_{profile_id}"
        )],
        [InlineKeyboardButton(
            text="Пригласить в игру",
            callback_data=f"invite_profile_{game}_{profile_id}"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="back_to_profiles" if not need_filter else "profile_by_filters"
        )]
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    return keyboard

async def get_gallery_kb(user_id: int, game: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text="Назад",
            callback_data=f"read_profile_self_{user_id}_{game}"
        )]
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    return keyboard

async def get_edit_fields_kb():
    keyboard = [
        [
            InlineKeyboardButton(text="Никнейм", callback_data="edit_nickname"),
        ],
        [
            InlineKeyboardButton(text="Возраст", callback_data="edit_age"),
        ],
        [
            InlineKeyboardButton(text="Тег Telegram", callback_data="edit_telegram_tag"),
        ],
        [
            InlineKeyboardButton(text="Пол", callback_data="edit_gender"),
        ],
        [  
            InlineKeyboardButton(text="Игры", callback_data="edit_games"),
        ],
        [  
            InlineKeyboardButton(text="Удобное время", callback_data="edit_time"),
        ],
        [
            InlineKeyboardButton(text="О себе", callback_data="edit_about"),
        ],
        [
            InlineKeyboardButton(text="Цели", callback_data="edit_goal"),
        ],
        [
           InlineKeyboardButton(text="Фото", callback_data="edit_photo")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="profile"),
        ]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_back_to_check_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Вернуться к проверке", callback_data="back_to_profile_check")
    return builder.as_markup()

async def get_back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="profile")]])

async def get_back_to_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu")]])

async def get_back_to_main_menu_from_invite(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(
                                                    text="Ответить",
                                                    callback_data=f"message_without_game_{user_id}"
                                                )]          
                                                  ])

async def get_goals_kb(with_back: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    for i in range(len(GOALS_LIST) // 2):
        keyboard.append([InlineKeyboardButton(text=GOALS_LIST[i*2], callback_data=f"goal_{GOALS_LIST[i*2]}"),
                         InlineKeyboardButton(text=GOALS_LIST[i*2+1], callback_data=f"goal_{GOALS_LIST[i*2+1]}"),
                         ])
        
    if len(GOALS_LIST) % 2 == 1:
        keyboard.append([InlineKeyboardButton(text=GOALS_LIST[-1], callback_data=f"goal_{GOALS_LIST[-1]}")])


    if with_back:
        keyboard.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"goals_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)



async def get_ranks_kb(game: str, with_back: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    if game in GAMES_RANKS:
        ranks = GAMES_RANKS[game]
        for i in range(len(ranks) // 2):
            keyboard.append([InlineKeyboardButton(text=ranks[i*2], callback_data=f"rank_{ranks[i*2]}"),
                             InlineKeyboardButton(text=ranks[i*2+1], callback_data=f"rank_{ranks[i*2+1]}")
                             ])
    
        if len(ranks) % 2 == 1:
            keyboard.append([InlineKeyboardButton(text=ranks[-1], callback_data=f"rank_{ranks[-1]}")])

    keyboard.append([InlineKeyboardButton(text="Пропустить", callback_data=f"rank_skip")])

    if with_back:
        keyboard.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"rank_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
        

async def get_marvel_ranks(with_back: bool = False) -> InlineKeyboardMarkup:
    btns = []
    titles = ["Бронза (Bronze)", "Серебро (Silver)", "Золото (Gold)", "Платина (Platinum)", "Алмаз (Diamond)", "Грандмастер (Grandmaster)", "Целестиал (Celestial)"]

    for title in titles:
        btns.append([InlineKeyboardButton(text=title, callback_data="blank")])
        
        first = title.split()[0]

        btns.append([InlineKeyboardButton(text=first + " I", callback_data="rank_" + first + " I"),
                     InlineKeyboardButton(text=first + " II", callback_data="rank_" + first + " II")])
        
        btns.append([InlineKeyboardButton(text=first + " III", callback_data="rank_" + first + " III")])

    btns.append([InlineKeyboardButton(text="Вечность", callback_data="rank_Вечность")])

    btns.append([InlineKeyboardButton(text="Один над всеми", callback_data="rank_Один над всеми")])
    
    btns.append([InlineKeyboardButton(text="Пропустить", callback_data=f"rank_skip")])
    
    if with_back:
        btns.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"rank_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=btns)

async def get_standoff_ranks(with_back: bool = False) -> InlineKeyboardMarkup:
    btns = []
    titles = ["Silver", "Gold", "Master"]

    for title in titles:
        btns.append([InlineKeyboardButton(text=title, callback_data="blank")])

        btns.append([InlineKeyboardButton(text=title + " I", callback_data="rank_" + title + " I"),
                     InlineKeyboardButton(text=title + " II", callback_data="rank_" + title + " II")])
        
        btns.append([InlineKeyboardButton(text=title + " III", callback_data="rank_" + title + " III"),
                     InlineKeyboardButton(text=title + " IV", callback_data="rank_" + title + " IV")])

    btns.append([InlineKeyboardButton(text="Champion", callback_data="blank")])
    btns.append([InlineKeyboardButton(text="Champion", callback_data="rank_Champion")])

    btns.append([InlineKeyboardButton(text="Пропустить", callback_data=f"rank_skip")])
    
    if with_back:
        btns.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"rank_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=btns)


async def get_warcraft_modes_kb(with_back: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    for mode in WARCRAFT_MODES:
        keyboard.append([InlineKeyboardButton(text=mode, callback_data=f"mode_{mode}")])
    
    keyboard.append([InlineKeyboardButton(text="Пропустить", callback_data="mode_skip")])

    if with_back:
        keyboard.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"mode_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_warcraft_ranks_kb(is_pve: bool = False, page=0, per_page=18):
    """Клавиатура для отображения списка кланов"""
    builder = InlineKeyboardBuilder()
    ranks = WARCRAFT_PvE if is_pve else WARCRAFT
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    ranks_page = ranks[start_idx:end_idx]
    
    for rank in ranks_page:
        rank_index = ranks.index(rank)
        builder.add(
            InlineKeyboardButton(text=rank, callback_data=f"add_warcraft_rank/{rank_index}/{is_pve}")
        )

    builder.adjust(2)
    
    navigation_buttons = []
    
    if page > 0:
        navigation_buttons.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"ranks_page_nopve_{page - 1}" if not is_pve else f"ranks_page_pve_{page - 1}"
            )
        )

    total_pages = (len(ranks) - 1) // per_page + 1 if ranks else 1
    navigation_buttons.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="current_page"
        )
    )
    
    if end_idx < len(ranks):
        navigation_buttons.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=f"ranks_page_nopve_{page + 1}" if not is_pve else f"ranks_page_pve_{page + 1}"
            )
        )
    
    if navigation_buttons:
        builder.row(*navigation_buttons)
    
    builder.row(
        InlineKeyboardButton(
            text="Назад",
            callback_data=f"back_from_warcraft_ranks"
        )
    )

    return builder.as_markup()


async def get_time_kb(with_back: bool = False) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text=time, callback_data=f"time_{time}")] for time in CONVENIENT_TIME]

    if with_back:
        kb.append([InlineKeyboardButton(text=TEXT_BACK, callback_data=f"time_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def get_edit_games_kb(games: list[Game], process: str = "", new_game: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for game in games:
        builder.add(InlineKeyboardButton(
            text=f"{game.name}",
            callback_data=f"update_game_{game.name}"
        ))
    
    if new_game:
        builder.add(
            InlineKeyboardButton(
                text="Добавить игру",
                callback_data="add_new_game"
            )
        )

    if process != "creating_profile":
        builder.add(
            InlineKeyboardButton(
                text="Назад",
                callback_data="edit_profile"
            )
        )
    else:
        builder.add(
            InlineKeyboardButton(
                text="Назад",
                callback_data="get_back_from_games_to_creating_profile"
            )
        )


    builder.adjust(1)

    return builder.as_markup()

async def get_read_game_kb(game: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Ранг", callback_data=f"edit_rank_{game}")
    )

    builder.add(
        InlineKeyboardButton(text="Галерея", callback_data=f"edit_gallery_{game}")
    )

    builder.add(
        InlineKeyboardButton(text="Удалить", callback_data=f"delete_game_{game}")
    )

    builder.add(
        InlineKeyboardButton(text="Назад", callback_data=f"update_games")
    )

    builder.adjust(1)

    return builder.as_markup()

async def get_delete_confirm_kb() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Да ✅", callback_data="delete_confirm_yes"),
         InlineKeyboardButton(text="Нет ❌", callback_data="delete_confirm_no"),]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def get_raven_clusters_kb(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cluster in CLUSTERS:
        builder.add(InlineKeyboardButton(
            text=cluster,
            callback_data=f"raven_cluster_{cluster}"
        ))
    builder.adjust(2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="raven_cluster_skip"
        ))
        
    if with_back:
        builder.row(InlineKeyboardButton(
            text=TEXT_BACK,
            callback_data="raven_cluster_back"
        ))

    return builder.as_markup()

async def get_raven_servers_kb(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for server in SERVERS:
        builder.add(InlineKeyboardButton(
            text=server,
            callback_data=f"raven_server_{server}"
        ))
    builder.adjust(2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="raven_server_skip"
        ))

    if with_back:
        builder.row(InlineKeyboardButton(
            text=TEXT_BACK,
            callback_data="raven_server_back"
        ))

    return builder.as_markup()

async def get_raven_classes_kb(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cls in CLASSES:
        builder.add(InlineKeyboardButton(
            text=cls,
            callback_data=f"raven_class_{cls}"
        ))
    builder.adjust(2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="raven_cluster_skip"
        ))

    if with_back:
        builder.row(InlineKeyboardButton(
            text=TEXT_BACK,
            callback_data="raven_class_back"
        ))

    return builder.as_markup()

async def get_raven_budgets_kb(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for budget in BUDGETS:
        builder.add(InlineKeyboardButton(
            text=budget,
            callback_data=f"budget_{budget}"
        ))
    builder.adjust(2)
    
    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="raven_cluster_skip"
        ))

    if with_back:
        builder.row(InlineKeyboardButton(
            text=TEXT_BACK,
            callback_data="budget_back"
        ))

    return builder.as_markup()


async def get_lineage_servers_pt_1(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="RU/EU East",
        callback_data="blank"
    ))

    for server in East:
        builder.add(InlineKeyboardButton(
            text=server,
            callback_data=f"lineage_server_{server}"
        ))


    builder.row(InlineKeyboardButton(
        text="NA/EU West",
        callback_data="blank"
    ))

    for server in West:
        builder.add(InlineKeyboardButton(
            text=server,
            callback_data=f"lineage_server_{server}"
        ))

    
    builder.row(InlineKeyboardButton(
        text="1/2",
        callback_data="blank"
    ))

    builder.add(InlineKeyboardButton(
            text="Назад",
            callback_data=f"blank"
        ))

    builder.add(InlineKeyboardButton(
            text="Вперед",
            callback_data=f"get_lineage_servers_pt_2"
        ))

    builder.adjust(1, 2, 2, 1, 2, 2, 1, 2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="lineage_server_skip"
        ))

    if with_back:
        builder.row(InlineKeyboardButton(
            text="Обратно",
            callback_data="lineage_server_back"
        ))


    return builder.as_markup()

async def get_lineage_servers_pt_2(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="JP",
        callback_data="blank"
    ))

    for server in JP:
        builder.add(InlineKeyboardButton(
            text=server,
            callback_data=f"lineage_server_{server}"
        ))


    builder.row(InlineKeyboardButton(
        text="2/2",
        callback_data="blank"
    ))

    builder.add(InlineKeyboardButton(
            text="Назад",
            callback_data=f"get_lineage_servers_pt_1"
        ))

    builder.add(InlineKeyboardButton(
            text="Вперед",
            callback_data=f"blank"
        ))

    builder.adjust(1, 2, 2, 2, 2, 2, 1, 2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="lineage_server_skip"
        ))


    if with_back:
        builder.row(InlineKeyboardButton(
            text="Обратно",
            callback_data="lineage_server_back"
        ))
    

    return builder.as_markup()


async def get_lineage_rases_kb(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for rase in RASES:
        builder.add(InlineKeyboardButton(
            text=rase,
            callback_data=f"lineage_rase_{rase}"
        ))

    builder.adjust(2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="lineage_rase_skip"
        ))

    if with_back:
        builder.row(InlineKeyboardButton(
            text=TEXT_BACK,
            callback_data="lineage_rase_back"
        ))

    return builder.as_markup()

async def get_lineage_classes_kb(with_back: bool = False, skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cls in LINEAGE_CLASSES:
        builder.add(InlineKeyboardButton(
            text=cls,
            callback_data=f"lineage_class_{cls}"
        ))
    builder.adjust(2)

    if skip:
        builder.row(InlineKeyboardButton(
            text="Пропустить",
            callback_data="lineage_class_skip"
        ))

    if with_back:
        builder.row(InlineKeyboardButton(
            text=TEXT_BACK,
            callback_data="lineage_class_back"
        ))

    return builder.as_markup()
