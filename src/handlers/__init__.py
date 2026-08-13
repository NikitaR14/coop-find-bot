from handlers.start import router as start_router
from handlers.profile.create_profile import router as create_profile_router
from handlers.menu import router as menu_router
from handlers.profile.profile import router as profile_router
from handlers.search.search import router as search_profile
from handlers.estimate import router as estimate_router
from handlers.clan.create_clan import router as create_clan_router
from handlers.clan.clan import router as clan_router
from handlers.clan.edit_clan import router as edit_clan_router
from handlers.profile.edit_profile import router as edit_profile_router
from handlers.profile.games_handlers.raven import router as raven_router
from handlers.profile.games_handlers.donate import router as donate_router
from handlers.profile.games_handlers.lineage import router as lineage_router
from handlers.profile.games_handlers.edit.raven import router as edit_raven_router
from handlers.profile.games_handlers.edit.donate import router as edit_donate_router
from handlers.profile.games_handlers.edit.lineage import router as edit_lineage_router
from handlers.search.search_donate import router as search_donate_router
from handlers.search.search_raven import router as search_raven_router
from handlers.search.search_lineage import router as search_lineage_router
from handlers.clan.games.raven import router as raven_clan_router
from handlers.clan.games.lineage import router as lineage_clan_router
from handlers.autofit import router as autofit_router
from handlers.shared_contacts import router as shared_contacts_router


routers = [
            start_router,
            create_clan_router, raven_clan_router,
            create_profile_router, raven_router,
            lineage_router,
            lineage_clan_router,
            edit_raven_router,
            edit_lineage_router,
            edit_donate_router,
            donate_router, menu_router,
            profile_router,
            autofit_router,
            search_donate_router, 
            search_raven_router, 
            search_lineage_router,
            search_profile, estimate_router,
            shared_contacts_router,
            clan_router, edit_profile_router,
            edit_clan_router,
            ]
