# Source.Python imports
from commands.typed import TypedServerCommand
from core import echo_console
from engines.server import engine_server
from events import Event
from events.manager import event_manager
from loggers import LogManager
from messages import SayText2
from players.entity import Player
from filters.players import PlayerIter,parse_filter

# Python 3 std lib
import collections
import copy
from enum import Enum
import random


PLAYER_POOL = None
GAME_STATE = None
EVENT_HANDLER = None


class IntConVarMock(object):
    def __init__(self, num):
        self.num = num

    def get_int(self):
        return self.num


pypug_log = LogManager('PyPUG', IntConVarMock(4), IntConVarMock(8),
                       filepath='pypug.log')


def log(text):
    pypug_log.log_debug(text)
    echo_console(text)


def load():
    global PLAYER_POOL
    global GAME_STATE
    global EVENT_HANDLER
    PLAYER_POOL = PlayerPool()
    GAME_STATE = GameState(PLAYER_POOL)
    EVENT_HANDLER = PyPugEventHandler(
        (PLAYER_POOL, GAME_STATE), # NOTE: Order is important here.
        ('player_connect', 'player_connect_full', 'player_disconnect',
         'player_say')
    )
    log('PyPUG Loaded.')


def unload():
    global EVENT_HANDLER
    del EVENT_HANDLER
    EVENT_HANDLER = None

    global PLAYER_POOL
    del PLAYER_POOL
    PLAYER_POOL = None

    global GAME_STATE
    del GAME_STATE
    GAME_STATE = None

    log('PyPUG Unloaded.')


@TypedServerCommand('pypug_player_list')
def on_player_list(command_info):
    log("PyPUG Player List:")
    for userid in PLAYER_POOL.all_players():
        log(str(userid))


@TypedServerCommand('pypug_player_iter')
def on_player_iter(command_info):
    log("PyPUG Player List (Iterator):")
    player_iter = PlayerIter.iterator()
    while True:
        try:
            p = player_iter.next()
            log(str(p))
        except Exception as e:
            return


@TypedServerCommand('pypug_goto')
def on_goto(command_info, state:str):
    global GAME_STATE

    if state not in [n for n,m in GAME_STATE.States.__members__.items()]:
        log('State \'%s\' not recognized.' % state)
        return

    log('Trying to jump to \'%s\' state.' % state)

    if state == 'warm_up':
        GAME_STATE.enter_warm_up_state()
    elif state == 'match_setup':
        GAME_STATE.enter_match_setup_state()
    elif state == 'map_vote':
        GAME_STATE.enter_map_vote_state()

    log('PyPUG goto done.')


@TypedServerCommand('pypug_force_ready')
def on_force_ready(command_info):
    global PLAYER_POOL
    for userid in PLAYER_POOL.all_players():
        Player.from_userid(userid).say('.ready')
        log('Force readied %s' % userid)


def dump_event(event, event_name):
    log(event_name)
    log(str([v for v in event.variables]))
    for v in event.variables:
        log("%s: %s" % (v, event[v]))


def generate_handler(event_name, listeners):
    def pypug_event_handler(event):
        dump_event(event, event_name)
        for listener in listeners:
            ear = getattr(listener, 'eh_%s' % (event_name,), None)
            if ear is not None:
                ear(event)
    return pypug_event_handler


class PyPugEventHandler(object):
    def __init__(self, listeners, event_names):
        self._handlers = {}

        for name in event_names:
            eh = generate_handler(name, listeners)
            self._handlers[name] = eh
            event_manager.register_for_event(name, eh)

    def __del__(self):
        for name, func in self._handlers.items():
            event_manager.unregister_for_event(name, func)


class PlayerPool(object):
    def __init__(self):
        self.networkid_to_userid = {}
        self.human_players = set()
        self.readied_players = set()
        self.bots = set()

    def all_players(self):
        return self.human_players.union(self.bots)

    def eh_player_connect(self, pc_event):
        if pc_event['networkid'] == 'BOT':
            self.bots.add(pc_event['userid'])
            return

        self.networkid_to_userid[pc_event['networkid']] = pc_event['userid']

    def ready_player(self, userid):
        self.readied_players.add(userid)

    def unready_all(self):
        self.readied_players = set()

    def eh_player_connect_full(self, pcf_event):
        self.human_players.add(pcf_event['userid'])

    def eh_player_disconnect(self, pd_event):
        if pd_event['networkid'] == 'BOT':
            self.bots.remove(pd_event['userid'])

        self.networkid_to_userid.pop(pd_event['networkid'])
        self.human_players.remove(pd_event['userid'])


def tell_user(userid, text):
    log("tell_user: Implement me!")
    pass


class GameState(object):
    States = Enum(
        'States',
        ' '.join(['warm_up', 'match_setup', 'map_vote', 'captain_vote',
                  'team_pick', 'prematch', 'first_half', 'halftime',
                  'second_half', 'match_end'])
    )

    WARM_UP_MAPS = ('de_vertigo', 'de_aztec', 'cs_militia')
    PUG_MAPS = ('de_dust2', 'de_mirage', 'de_nuke')

    def __init__(self, player_pool):
        self.player_pool = player_pool
        self.teams = [set(), set()]
        self.enter_warm_up_state()

    def enter_warm_up_state(self):
        self.state = self.States.warm_up
        self.player_pool.unready_all()
        warm_up_map = random.choice(self.WARM_UP_MAPS)
        engine_server.server_command('changelevel %s;' % warm_up_map)

    def enter_match_setup_state(self):
        self.state = self.States.match_setup
        # TODO Is there anything to do before proceeding to a map vote?
        self.enter_map_vote_state()

    def enter_map_vote_state(self):
        # TODO
        # 1 Initialize vote object.
        pass

    def end_map_vote(self, winner):
        self.selected_map = winner
        self.enter_captain_vote_state()

    def handle_ready(self, userid):
        if self.state in (self.States['warm_up'], self.States['halftime']):
            self.player_pool.ready_player(userid)
            log("Player %d readied up." % userid)
            if len(self.player_pool.readied_players) == 10:
                log("10 Players readied. Entering match setup state.")
                self.enter_match_setup_state()
            return

        # Otherwise no need to ready now.
        tell_user(userid, "No need to ready now.")

    def handle_unready(self, userid):
        if userid in self.player_pool.readied_players:
            pass
        pass

    def eh_player_connect(self, pc_event):
        pass

    def eh_player_disconnect(self, pd_event):
        pass

    def eh_player_say(self, ps_event):
        if 'text' not in ps_event.variables:
            return

        if ps_event['text'] == '.ready':
            return self.handle_ready(ps_event['userid'])
        elif ps_event['text'] == '.unready':
            return self.handle_unready(ps_event['userid'])
