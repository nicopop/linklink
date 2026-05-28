from ..Helpers import is_option_enabled, get_option_value, format_state_prog_items_key, ProgItemsCat, remove_specific_item, get_items_for_player
# Object classes from AP core, to represent an entire MultiWorld and this individual World that's part of it
from typing import TYPE_CHECKING, Iterator, cast, Any, Counter
from worlds.AutoWorld import World
from BaseClasses import MultiWorld, CollectionState, Item, ItemClassification, Location
from Options import OptionError
import logging
# Object classes from Manual -- extending AP core -- representing items and locations that are used in generation
from ..Items import ManualItem
from ..Locations import ManualLocation

if TYPE_CHECKING:
    from .. import ManualWorld

# Raw JSON data from the Manual apworld, respectively:
#          data/game.json, data/items.json, data/locations.json, data/regions.json
#
from ..Data import game_table, item_table, location_table, region_table
from .Data import MAX_PLAYERS
from .Options import Victims

# calling logging.info("message") anywhere below in this file will output the message to both console and log file
import logging, time

if TYPE_CHECKING:
    from .. import ManualWorld

########################################################################################
## Order of method calls when the world generates:
##    1. create_regions - Creates regions and locations
##    2. create_items - Creates the item pool
##    3. set_rules - Creates rules for accessing regions and locations
##    4. generate_basic - Runs any post item pool options, like place item/category
##    5. pre_fill - Creates the victory location
##
## The create_item method is used by plando and start_inventory settings to create an item from an item name.
## The fill_slot_data method will be used to send data to the Manual client for later use, like deathlink.
########################################################################################

# region Custom Client
from worlds.LauncherComponents import Component, SuffixIdentifier, components, Type, launch, icon_paths
from typing import Callable
def launch_client(*args):
    import CommonClient
    from ..ManualClient import launch as Main

    if CommonClient.gui_enabled:
        launch(Main, name="Manual client", args=args)
    else:
        Main(*args)

class VersionedComponent(Component):
    def __init__(self, display_name: str, script_name: str|None = None, func: Callable|None = None, version: int = 0, file_identifier: Callable[[str], bool]|None = None, icon: str = ""):
        super().__init__(display_name=display_name, script_name=script_name, func=func, component_type=Type.CLIENT, file_identifier=file_identifier, icon=icon)
        self.version = version

def add_client_to_launcher() -> None:
    import Utils
    version = 2026_04_13 # YYYYMMDD
    found = False

    if "manual" not in icon_paths:
        icon_paths["manual"] = Utils.user_path('data', 'manual.png')

    for c in components:
        if c.display_name == "Manual Client Nico's Experiment":
            found = True
            if getattr(c, "version", 0) < version:
                c.version = version # type: ignore
                c.func = launch_client
                c.icon = "manual"

    if not found:
        components.append(VersionedComponent("Manual Client Nico's Experiment", "ManualClient", func=launch_client, version=version, file_identifier=SuffixIdentifier('.apmanual'), icon="manual"))
add_client_to_launcher()
# endregion
# Use this function to change the valid filler items to be created to replace item links or starting items.
# Default value is the `filler_item_name` from game.json
def hook_get_filler_item_name(world: "ManualWorld", multiworld: MultiWorld, player: int) -> str | bool:
    return False

def before_generate_early(world: "ManualWorld", multiworld: MultiWorld, player: int) -> None:
    """
    This is the earliest hook called during generation, before anything else is done.
    Use it to check or modify incompatible options, or to set up variables for later use.
    """
# region UT stuff
    world.is_ut = hasattr(multiworld, "generation_is_fake") # type: ignore
    if world.is_ut and hasattr(multiworld, "re_gen_passthrough"):
        if world.game in multiworld.re_gen_passthrough: # type: ignore
            world.is_ut_regen = True # type: ignore
            slot_data = multiworld.re_gen_passthrough[world.game]["linklink"] # type: ignore
            world.linklink_locations = slot_data["filtered_locations"] # type: ignore
            world.linklink_locations_filtered_by_removed = slot_data["filtered_removed"] # type: ignore
            world.linklink_item_config = slot_data["key_counts"] # type: ignore
            world.linklink_active_victims_ids = slot_data["active_victims"] # type: ignore
            world.linklink_active_games = slot_data["active_games"] # type: ignore
    else:
        world.is_ut_regen = False # type: ignore
# endregion
# region validate victims
    option_victims = cast(Victims, world.options.victims) # type: ignore
    victims = option_victims.value
    victims_ids: set[int] = set()
    filtered_victims_ids: set[int]
    active_games: set[str] = set()
    if world.is_ut:
        if world.is_ut_regen:
            victims_ids = cast(set[int], world.linklink_active_victims_ids)
            active_games = cast(set[str], world.linklink_active_games)
            filtered_victims_ids = victims_ids
    else:
        if len(victims) == 0:
            victims_ids = set(range(1, multiworld.players + 1))
        else:
            missing: list[str] = []
            id_for_names = {w.player_name: i for i, w in multiworld.worlds.items()}
            for name in victims:
                if name not in id_for_names.keys():
                    missing.append(name)
                    continue
                victims_ids.add(id_for_names[name])
            if missing:
                raise OptionError(f"The following victims could not be found in the multiworld, there could be some typos or their yaml failed to load.\
                    \n - missing: {', '.join(missing)}")

        if player in victims_ids:
            victims_ids.remove(player)

        filtered_victims_ids = victims_ids.copy()
        games = get_linklink_games(world)
        for victim in set(victims_ids):
            game = multiworld.worlds[victim].game
            if game not in games:
                filtered_victims_ids.remove(victim)
            else:
                active_games.add(game)

    world.linklink_victims_ids = victims_ids # type: ignore
    world.linklink_active_victims_ids = filtered_victims_ids # type: ignore
    world.linklink_active_games = active_games # type: ignore
# endregion
    world.linklink_helpers_disabled_location = 0  # type: ignore
    def create_filler() -> Item:
        filler = replace_nothings(world, multiworld, player, 1)[0]
        logging.debug(f"create_filler() was called and it made an item for player {filler.player}")
        return filler
    setattr(world, "create_filler", create_filler)
# region Custom funcs
def get_linklink_games(world: "ManualWorld") -> set[str]:
    if hasattr(world, "linklink_games"):
        return world.linklink_games
    games: set[str] = set()
    for item_data in item_table:
        if 'linklink' not in item_data:
            continue
        for game in item_data['linklink'].keys():
            games.add(game)
    world.linklink_games = games # type: ignore
    return games

def get_victims(world: "ManualWorld", filter: bool = False) -> set[int]:
    linklink_victims_ids = cast(set[int], world.linklink_victims_ids) # type: ignore
    linklink_active_victims_ids = cast(set[int], world.linklink_active_victims_ids) # type: ignore
    return linklink_active_victims_ids if filter else linklink_victims_ids

def place_locked_item(location: Location, item: Item) -> Item | None:
    old_item = None
    if location.item:
        old_item = location.item
        old_item.location = None
    location.item = item
    item.location = location
    location.locked = True
    return old_item
# endregion
# Called before regions and locations are created. Not clear why you'd want this, but it's here. Victory location is included, but Victory event is not placed yet.
def before_create_regions(world: "ManualWorld", multiworld: MultiWorld, player: int):
    pass

# Called after regions and locations are created, in case you want to see or modify that information. Victory location is included.
def after_create_regions(world: "ManualWorld", multiworld: MultiWorld, player: int):
    if world.is_ut_regen:
        # ? maybe move this to helper hooks
        filter = world.linklink_locations
        players_digits = len(str(MAX_PLAYERS))
        events_name_to_remove: set[str] = set()
        locations_to_remove: list[Location] = []
        # world.linklink_locations_filtered_by_removed = if the filter contains all the removed location (true) vs contains all the enabled location (false)
        for location in multiworld.get_locations(player):
            if location.address is not None and (location.address in filter and world.linklink_locations_filtered_by_removed):
                player1 = f" Player {str(1).zfill(players_digits)}"
                if location.name.endswith(player1):
                    event_name = location.name.removesuffix(player1)
                    events_name_to_remove.add(event_name + " Event")
                locations_to_remove.append(location)
            elif location.address is None and location.name in events_name_to_remove:
                locations_to_remove.append(location)

        for location in locations_to_remove:
            if location.parent_region is not None:
                location.parent_region.locations.remove(location)
    pass

# This hook allows you to access the item names & counts before the items are created. Use this to increase/decrease the amount of a specific item in the pool
# Valid item_config key/values:
# {"Item Name": 5} <- This will create qty 5 items using all the default settings
# {"Item Name": {"useful": 7}} <- This will create qty 7 items and force them to be classified as useful
# {"Item Name": {"progression": 2, "useful": 1}} <- This will create 3 items, with 2 classified as progression and 1 as useful
# {"Item Name": {0b0110: 5}} <- If you know the special flag for the item classes, you can also define non-standard options. This setup
#       will create 5 items that are the "useful trap" class
# {"Item Name": {ItemClassification.useful: 5}} <- You can also use the classification directly
def before_create_items_all(item_config: dict[str, int|dict[Any, int]], world: "ManualWorld", multiworld: MultiWorld, player: int) -> dict[str, int|dict]:
    if not world.is_ut:
        for name, config in item_config.copy().items():
            if config:
                item_data = world.item_name_to_item[name]
                item_config[name] = item_data['count'] + item_data["extra"]
    elif world.is_ut_regen:
        if linklink_item_config := cast(Counter[str], getattr(world, "linklink_item_config", {})):
            for item_name in dict(item_config).keys():
                item_config[item_name] = linklink_item_config[item_name]
    return item_config

# The item pool before place_item(_category) are processed, in case you want to see the raw item pool at that stage
def before_create_items_place_items(item_pool: list, world: "ManualWorld", multiworld: MultiWorld, player: int) -> list:
    return item_pool

# The item pool before starting items are processed, in case you want to see the raw item pool at that stage
def before_create_items_starting(item_pool: list, world: "ManualWorld", multiworld: MultiWorld, player: int) -> list:
    return item_pool

# The item pool after starting items are processed but before filler is added, in case you want to see the raw item pool at that stage
def before_create_items_filler(item_pool: list, world: "ManualWorld", multiworld: MultiWorld, player: int) -> list:
    return item_pool


# The complete item pool prior to being set for generation is provided here, in case you want to make changes to it
def after_create_items(item_pool: list[Item], world: "ManualWorld", multiworld: MultiWorld, player: int) -> list:
    unplaced_nothing = [i for i in item_pool if i.name == world.filler_item_name]
    ll_locations = [l for l in world.get_locations() if world.location_name_to_location.get(l.name, {}).get("linklink", None) is not None]

    # Doing the placing on locked items here since its faster than Manual's place_item
    for location in ll_locations:
        if len(unplaced_nothing) > 0:
            item = unplaced_nothing.pop()
            try_remove_specific_item(item_pool, item)
        else:
            item = world.create_item(world.filler_item_name)
        location.place_locked_item(item)
# region magic time
    # ? maybe add support for executing linklink_magic here, that would be the most "correct" time to do it
    #  if player > max(get_victims(world, True)):
    #     print("we could do the magic here maybe :D")
# endregion
    return item_pool

def try_remove_specific_item(items: list[Item], item: Item):
    try:
        remove_specific_item(items, item)
    except ValueError:
        # At this point if the modified item is not in the original list we can just remove a unmodified version instead
        # since the original list copy of the item will not be modified at all
        logging.error(f"linklink failed to cleanly remove item '{item.name}'")
        items.remove(item)

def remove_location(world: "ManualWorld", location: Location):
    if location.parent_region is not None:
        location.parent_region.locations.remove(location)
        if location.address is not None: #Which it should never unless we have events
            world.linklink_removed_location.append(location.address)

def replace_nothings(world: "ManualWorld", multiworld: MultiWorld, player: int, unplaced_nothing: int | None = None):
    # Remove "Nothing" items and replace them with filler items from other players
    if unplaced_nothing is not None:
        item_count = unplaced_nothing
    else:
        item_pool = [i for i in multiworld.itempool if i.player == player and i.name == world.filler_item_name]
        item_count = len(item_pool)

    filler_blacklist: list[str] = [] # ["SMZ3", "Links Awakening DX"]  # These games don't have filler items or don't implement them correctly
    victims = list(get_victims(world))
    victims = [v for v in victims if v != player and multiworld.worlds[v].game not in filler_blacklist \
                and "linklink" not in multiworld.worlds[v].game.lower()]  # Only include players with filler items
    replacements: list[Item] = []
    queue: Iterator = iter([])  # for type checking reason
    other_player = None
    while item_count > 0:
        if other_player is None:
            world.random.shuffle(victims)
            queue = iter(v for v in victims)
            other_player = next(queue)
        jworld = multiworld.worlds[other_player]
        filler = try_create_filter(jworld)
        if filler is not None:
            replacements.append(filler)
            item_count -= 1
        else:
            victims.remove(other_player)
            if not victims:
                break
            world.random.shuffle(victims)
            queue = iter(v for v in victims)
        other_player = next(queue, None)
    return replacements

# Called before rules for accessing regions and locations are created. Not clear why you'd want this, but it's here.
def before_set_rules(world: "ManualWorld", multiworld: MultiWorld, player: int):
    pass

# Called after rules for accessing regions and locations are created, in case you want to see or modify that information.
def after_set_rules(world: "ManualWorld", multiworld: MultiWorld, player: int):
    # Use this hook to modify the access rules for a given location

    def Example_Rule(state: CollectionState) -> bool:
        # Calculated rules take a CollectionState object and return a boolean
        # True if the player can access the location
        # CollectionState is defined in BaseClasses
        return True

    ## Common functions:
    # location = world.get_location(location_name, player)
    # location.access_rule = Example_Rule

    ## Combine rules:
    # old_rule = location.access_rule
    # location.access_rule = lambda state: old_rule(state) and Example_Rule(state)
    # OR
    # location.access_rule = lambda state: old_rule(state) or Example_Rule(state)

# The item name to create is provided before the item is created, in case you want to make changes to it
def before_create_item(item_name: str, world: "ManualWorld", multiworld: MultiWorld, player: int) -> str:
    return item_name

# The item that was created is provided after creation, in case you want to modify the item
def after_create_item(item: ManualItem, world: "ManualWorld", multiworld: MultiWorld, player: int) -> ManualItem:
    return item

def linklink_magic(world: "ManualWorld", in_pre_fill = False):
    multiworld = world.multiworld
    player = world.player
    from operator import indexOf
    world.linklink_removed_location = [] # type: ignore
    start_time = time.perf_counter()
    victims = get_victims(world, True)

    logging.info(f"{multiworld.player_name[player]} is casting some {world.game}{' black' if in_pre_fill else ''} magic with {', '.join([multiworld.player_name[p] for p in victims]) if len(world.options.victims.value) > 0 else f'{len(victims)} players'}") # type: ignore

    # region handle Items
    from Options import LocalItems, PlandoItems, ItemLinks, StartInventoryPool
    usable_items_for_player: dict[int, list[Item]] = {}
    unplaced_nothing: list[Item] = []
    for victim in victims:
        usable_items_for_player[victim] = []
    usable_items_for_player[player] = []
    nothing_source: Counter[str] = Counter()

    for item in multiworld.itempool:
        if item.player == player:
            if item.name == world.filler_item_name:
                # * should never find any logically since we preplace all the nothing in create_items
                unplaced_nothing.append(item)
                nothing_source["free"] += 1
            else:
                usable_items_for_player[player].append(item)
        elif item.player in victims and item.location is None:
            usable_items_for_player[item.player].append(item)


    for _player, items in usable_items_for_player.copy().items():
        _world: World = multiworld.worlds[_player]
        options = _world.options
        count_to_remove: Counter[str] = Counter()
        remove_all: set[str] = set()

        # Remove local_items and item_links always, even in pre_fill
        local_items = cast(LocalItems, getattr(options, "local_items", LocalItems([])))
        remove_all |= local_items.value
        # region hdl item_links
        item_links = cast(ItemLinks, getattr(options, "item_links", ItemLinks([])))
        for item_link in item_links.value:
            _pool: set[str] = set(item_link.get("item_pool", []))
            _local: set[str] = set(item_link.get("local_items", []))
            _non_local: set[str] = set(item_link.get("non_local_items", []))
            remove_all |= _pool | _local | _non_local
        # endregion

        if not in_pre_fill:
            # in pre_fill plando and StartInventoryPool should already be processed by AP
            # region hdl plando
            plando = cast(PlandoItems, getattr(options, "plando_items", PlandoItems([])))
            for plando_item in plando.value:
                if not plando_item.from_pool or not plando_item.percentage or plando_item.force != True:
                    continue
                plando_max: int | bool
                if isinstance(plando_item.count, dict):
                    plando_max = plando_item.count.get("max", False)
                else:
                    plando_max = plando_item.count
                if type(plando_max) is bool:
                    plando_max = 99999999

                # sadly locations groups are not converted to "real" locations for plando like items groups so we cant know how many there are
                if plando_item.locations and set(plando_item.locations).isdisjoint(set(["early_locations", "non_early_locations", "Everywhere"])):
                    plando_max = min(plando_max, len(plando_item.locations))

                if isinstance(plando_item.items, list):
                    for item_name in plando_item.items:
                        if item_name in remove_all:
                            continue
                        if plando_max == 99999999:
                            remove_all.add(item_name)
                        else:
                            count_to_remove[item_name] += plando_max
                else:
                    for item_name, count in plando_item.items.items():
                        if item_name in remove_all:
                            continue
                        if type(count) is int:
                            count_to_remove[item_name] += min(count, plando_max)
                        elif type(count) is bool and count:
                            if plando_max == 99999999:
                                remove_all.add(item_name)
                            else:
                                count_to_remove[item_name] += plando_max
            # endregion
            start_inv_pool = cast(StartInventoryPool, getattr(options, "start_inventory_from_pool", StartInventoryPool({})))
            count_to_remove += Counter(start_inv_pool.value)
        # ? potentially check for special trigger to exclude items from linklink

        if count_to_remove or remove_all:
            processed_items: Counter[str] = Counter()
            for item in items.copy():
                if item.name in remove_all:
                    remove_specific_item(usable_items_for_player[_player], item)
                elif item.name in count_to_remove.keys() and processed_items[item.name] < count_to_remove[item.name]:
                    remove_specific_item(usable_items_for_player[_player], item)
                else:
                    continue
                processed_items[item.name] += 1

        if not usable_items_for_player[_player]:
            victims.remove(_player)

    for game_name in world.linklink_active_games.copy():
        players = set(multiworld.get_game_players(game_name))
        if victims.isdisjoint(players):
            world.linklink_active_games.remove(game_name)
    # endregion

    item_create_filler: set[int] = set()
    # * a set of item mem Addresses (id(Item)) of items that create fillers when placed in a linklink spot

    filler_to_make: int = 0
    filler_made: int = 0
    filler_items: list[Item] = []
    extras: int = 0

    players_digits = len(str(MAX_PLAYERS))
    linklink_items = usable_items_for_player[player]
    unique_linklink_items = list(dict.fromkeys(linklink_items))

    key_count = 0
    for key in unique_linklink_items:
        # items variables
        item_name = key.name
        item_data: dict[str, Any] = world.item_name_to_item[item_name]
        linklink: dict[str, list[str]] = item_data['linklink']
        item_count: int = item_data['count']
        item_extras: int = item_data['extra']
        digit = len(str(item_count + 1))

        # counters and cache variables
        filler_to_make_for_player: Counter[int] = Counter()
        item_cache: dict[int, list[Item]] = {}
        highest_placed_count = 0
        spot_filled = 0

        # region Item_groups
        if not item_data.get("linklink_item_name_groups_done"):
            for game_name, ll_data in linklink.items():
                if game_name not in world.linklink_active_games:
                    continue
                _world = next(iter(multiworld.worlds[w] for w in victims if multiworld.worlds[w].game == game_name))
                item_name_groups: dict[str, set[str]] = getattr(_world, "item_name_groups", dict[str, set[str]]())
                if item_name_groups:
                    for name in ll_data:
                        if name in item_name_groups.keys():
                            index = ll_data.index(name)
                            ll_data.remove(name)
                            for ll_element in reversed([lli for lli in _world.item_name_groups[name]]):
                                ll_data.insert(index, ll_element)
                pass
            item_data["linklink_item_name_groups_done"] = True
        # endregion

        for i in range(1, item_count + 1):
            n = 1
            for victim_id in victims: # victim_id was j
                victim_items: list[Item] = usable_items_for_player[victim_id]
                victim_world: World = multiworld.worlds[victim_id]
                game = victim_world.game

                if game not in linklink:
                    continue

                location_name = f"{item_name} {str(i).zfill(digit)} Player {str(n).zfill(players_digits)}"
                location = multiworld.get_location(location_name, player)

                # region Item Cache
                if item_cache.get(victim_id, None) is None:
                    shuffle = "$Shuffle" in linklink[game]
                    items = [item for item in victim_items if item.name in linklink[game]]

                    for item in items:
                        item_create_filler.add(id(item))

                    items.sort(key=lambda x: linklink[game].index(x.name))
                    items_name = [item.name for item in items]

                    buffer_index = 0
                    last_index = -1

                    for ll_item_name in linklink[game]:
                        if not ll_item_name.startswith("$") and ll_item_name in items:
                            # Find the last instance of item to insert buffer after
                            buffer_index = len(items) - indexOf(reversed(items_name), ll_item_name) - 1
                        # elif ll_item_name == "$Shuffle":
                        #     if last_index != -1:
                        #         # ? maybe shuffle everything BEFORE the shuffle instead of just if shuffle is present
                        #         pass
                        elif ll_item_name.startswith("$Buffer_"):
                            buffer_to_make = min(int(ll_item_name.removeprefix("$Buffer_")), max(0, item_count - len(items)))
                            if buffer_to_make:
                                failed = False
                                buffers: list[Item] = []
                                while buffer_to_make > 0 and not failed:
                                    filler = try_create_filter(victim_world)
                                    if filler is not None:
                                        buffers.append(filler)
                                        buffer_to_make -= 1
                                    else:
                                        failed = True
                                if failed:
                                    buffers.extend(replace_nothings(world, multiworld, player, buffer_to_make))

                                for item in buffers:
                                    if id(item) in item_create_filler:
                                        item_create_filler.discard(id(item))

                                multiworld.itempool.extend(buffers)
                                victim_items.extend(buffers)
                                for buffer_item in buffers:
                                    items.insert(buffer_index + 1, buffer_item)

                                # update the name list to include buffers
                                items_name = [item.name for item in items]

                        last_index += 1

                    if shuffle and len(items) > 1: victim_world.random.shuffle(items)
                    item_cache[victim_id] = items
                    if i == 1 and len(items) == 0:
                        logging.debug(f"linklink: No options for {item_name} {str(i).zfill(digit)} for {multiworld.player_name[victim_id]} ({game})")
                        continue
                # endregion

                nullable_item: Item|None = next(iter(item_cache[victim_id]), None)
                if nullable_item is not None:
                    item = nullable_item # to make mypy happy
                    item_cache[victim_id].remove(item)
                    old_item = place_locked_item(location, item)
                    if old_item is not None:
                        multiworld.itempool.append(old_item)
                        unplaced_nothing.append(old_item)
                        nothing_source[item_name] += 1
                    victim_items.remove(item)
                    try_remove_specific_item(multiworld.itempool, item)
                    if id(item) in item_create_filler:
                        filler_to_make_for_player[victim_id] += 1
                    else:
                        try_remove_specific_item(multiworld.itempool, unplaced_nothing.pop())
                        nothing_source[item_name] -= 1
                    n += 1
                    spot_filled += 1
                    highest_placed_count = max(highest_placed_count, i)

        # region extra keys rem
        extras += item_extras
        ll_keys = [item for item in linklink_items if item.name == item_name]
        if ll_keys: # to protect from divided by 0
            extra_percent = (highest_placed_count / item_count)
            extra_to_keep = int(item_extras * extra_percent)
            to_keep = highest_placed_count + (extra_to_keep)
            copies_to_remove = item_count + item_extras - to_keep
            if copies_to_remove:
                logging.debug(f'Removing surplus {item_name}')
            if copies_to_remove < 0:
                logging.error(f"we got a problem for {item_name}")
            iterable = iter(ll_keys)
            for _ in range(copies_to_remove):
                nullable_item = next(iterable, None)
                if nullable_item is None:
                    break
                    # We are out of items to remove anyway
                item = nullable_item

                try_remove_specific_item(multiworld.itempool, item)
                linklink_items.remove(item)
            if item_extras and extra_percent < 1:
                extras -= (item_extras - extra_to_keep)
        # endregion

        # region main filler gen
        filler_to_make_for_player = +filler_to_make_for_player
        if filler_to_make_for_player.values():
            available_spots = spot_filled - highest_placed_count
            extra_to_remove = min(available_spots, extras)
            item_count = highest_placed_count + extra_to_remove
            extras -= extra_to_remove

            # if we have keys and extras keys (but less than total available spots) remove them randomly from the amount of filler we have to make later
            filler_to_make_for_player = +filler_to_make_for_player
            players_ids: list[int] = list(filler_to_make_for_player.keys())
            for i in range(item_count):
                if not players_ids:
                    filler_to_make -= (item_count - i)
                    break
                player_id: int = world.random.choice(players_ids)
                filler_to_make_for_player[player_id] -= 1
                if not filler_to_make_for_player[player_id]:
                    players_ids.remove(player_id)

            # Generate filler for every player that needs it
            filler_to_make_for_player = +filler_to_make_for_player
            # ? maybe add option to skip this block and make filler all random
            for player_id, count in filler_to_make_for_player.copy().items():
                for _ in range(count):
                    player_world: World = multiworld.worlds[player_id]
                    filler = try_create_filter(player_world)
                    if filler is not None:
                        filler_made += 1
                        multiworld.itempool.append(filler)
                        filler_items.append(filler)
                        if unplaced_nothing is not None and len(unplaced_nothing) > 0:
                            try_remove_specific_item(multiworld.itempool, unplaced_nothing.pop())
                            nothing_source[item_name] -= 1
                        filler_to_make_for_player[player_id] -= 1
                        if filler_to_make_for_player[player_id] == 0:
                            filler_to_make_for_player.pop(player_id)
                    else:
                        # if creating filler fail skip the rest of this players attempt
                        break
            filler_to_make += filler_to_make_for_player.total()
        # endregion
        # region location rem

        events_name_to_remove: set[str] = set()
        filled_locations = [l for l in multiworld.get_filled_locations(player) if l.name.startswith(f"{item_name} ") ]
        players_digits = len(str(MAX_PLAYERS))
        for location in filled_locations:
            if location.item is not None:
                if location.item.name == world.filler_item_name:
                    player1 = f" Player {str(1).zfill(players_digits)}"
                    if location.name.endswith(player1):
                        event_name = location.name.removesuffix(player1)
                        events_name_to_remove.add(event_name + " Event")
                    remove_location(world, location)
                elif location.item.code is None:
                    if location.name in events_name_to_remove:
                        events_name_to_remove.remove(location.name)
                        remove_location(world, location)
        # endregion
        key_count += highest_placed_count


    if extras > 0:
        logging.debug(f"Failed to fit {extras} extra keys in the item pool, randomly picked items from the generated fillers will be removed to avoid creating too many items")
        for _ in range(extras):
            if filler_to_make > 0:
                filler_to_make -= 1
                extras -= 1
            elif filler_items:
                sacrifice = world.random.choice(filler_items)
                try_remove_specific_item(multiworld.itempool, sacrifice)
                filler_items.remove(sacrifice)
                extras -= 1
            else:
                break
        if extras > 0:
            logging.debug(f"Failed to remove {extras} extra keys, you might see a message later talking about too many items.")

    precollected_items = list(multiworld.precollected_items.get(player, []))

    # Filter Precollected items for those not in logic aka created by start_inventory(_from_pool)
    precollected_exceptions = world.options.start_inventory.value
    if not in_pre_fill: # outside of pre_fill the items are still in the main item pool
        precollected_exceptions += world.options.start_inventory_from_pool.value # type: ignore

    for item_name, count in precollected_exceptions.items():
        items_iter = iter([i for i in precollected_items if i.name == item_name])
        for _ in range(count):
            precollected_items.remove(next(items_iter))

    nothing_total = filler_to_make + len(multiworld.get_unfilled_locations(player))
    nothing_to_make = nothing_total - len(unplaced_nothing) - extras

    failed_to_remove = 0
    if nothing_to_make < 0:
        for _ in range(abs(nothing_to_make)):
            if len(unplaced_nothing) > 0:
                try_remove_specific_item(multiworld.itempool, unplaced_nothing.pop())
            else:
                failed_to_remove += 1

    elif nothing_to_make > 0:
        replacements = replace_nothings(world, multiworld, player, nothing_to_make)
        multiworld.itempool.extend(replacements)

    if failed_to_remove:
        logging.warning(f"{multiworld.player_name[player]} failed to remove {failed_to_remove} items you will see in the logs that there are more items than locations")
    # ? maybe add emergency extra removal here or something
    if unplaced_nothing:
        replacements = replace_nothings(world, multiworld, player, len(unplaced_nothing))
        for nothing in unplaced_nothing:
            multiworld.itempool.remove(nothing)
        multiworld.itempool.extend(replacements)

    # Update item counts for potential rules usage
    pool = [item for item in get_items_for_player(multiworld, player, False)]
    real_pool = pool + precollected_items
    world.item_counts[player] = world.get_item_counts(pool=real_pool)
    world.item_counts_progression[player] = world.get_item_counts(pool=real_pool, only_progression=True)

    link_count = len([location for location in multiworld.get_filled_locations(player) if not location.is_event and world.location_name_to_location[location.name].get("linklink") is not None]) - 1 # victory removed
    elapsed_time = time.perf_counter() - start_time
    logging.info(f"{multiworld.player_name[player]} took {elapsed_time:.4f} seconds to do the linklink magic")
    logging.info(f"{multiworld.player_name[player]} Has {key_count} keys and {link_count} links")

# This method is run towards the end of pre-generation, before the place_item options have been handled and before AP generation occurs
def before_generate_basic(world: "ManualWorld", multiworld: MultiWorld, player: int):

    if not world.is_ut:
        if world.options.magic_in_pre_fill.value: # type: ignore
            def pre_fill():
                linklink_magic(world, in_pre_fill=True)
            setattr(world, "pre_fill", pre_fill)
        else:
            linklink_magic(world)

def get_filler_item_name(self: World) -> str:
        multiworld = self.multiworld
        player = self.player
        if hasattr(self, "linklink_filler_names"):
            items = self.linklink_filler_names
        else:
            items = {i.name for i in get_items_for_player(multiworld, player, True) if i.classification == ItemClassification.filler and i.name.lower() != "nothing"}
            self.linklink_filler_names = items  # type: ignore

        if items:
            return self.random.choice(list(items))
        else:
            return "Nothing"

def try_create_filter(world: World) -> Item|None:
    player = world.player
    player_name = world.multiworld.player_name[player]
    def recursion(tries: int = 0) -> Item|None:
        if tries > 10:
            world.linklink_custom_filler = False # type: ignore
            return None
        if hasattr(world, "linklink_custom_filler"):
            if not world.linklink_custom_filler:
                return None
        if type(world).get_filler_item_name == World.get_filler_item_name and type(world).create_filler == World.create_filler:
            # When this is the case the default implementation just pick a random item from the entire itempool of that world
            # progression items included, lets not do that
            type(world).get_filler_item_name = get_filler_item_name  # type: ignore
            type(world).linklink_custom_filler = True  # type: ignore
            logging.debug(f"linklink: replaced '{world.game}''s default unimplemented get_filler_item_name with my custom function")
        try:
            filler = world.create_filler()
            if filler is None:
                raise Exception(f"{str(type(world))}'s create_filler returned None instead of a filler item.")
            if filler.name == "Nothing":
                return recursion(tries + 1) #might be a bad luck so reroll
            return filler
        except Exception as e:
            logging.error(f"linklink: Error creating filler for {player_name}: {e}")
            if hasattr(world, "linklink_custom_filler"):
                type(world).get_filler_item_name = World.get_filler_item_name # type: ignore
                logging.debug(f"linklink: custom get_filler_item_name for {world.game} didn't work, reverting to default")
            type(world).linklink_custom_filler = False  # type: ignore
            return None

    return recursion()

# This method is run every time an item is added to the state, can be used to modify the value of an item.
# IMPORTANT! Any changes made in this hook must be cancelled/undone in after_remove_item
def after_collect_item(world: "ManualWorld", state: CollectionState, Changed: bool, item: Item):
    # the following let you add to the Potato Item Value count
    # if item.name == "Cooked Potato":
    #     state.prog_items[item.player][format_state_prog_items_key(ProgItemsCat.VALUE, "Potato")] += 1
    pass

# This method is run every time an item is removed from the state, can be used to modify the value of an item.
# IMPORTANT! Any changes made in this hook must be first done in after_collect_item
def after_remove_item(world: "ManualWorld", state: CollectionState, Changed: bool, item: Item):
    # the following let you undo the addition to the Potato Item Value count
    # if item.name == "Cooked Potato":
    #     state.prog_items[item.player][format_state_prog_items_key(ProgItemsCat.VALUE, "Potato")] -= 1
    pass


# This is called before slot data is set and provides an empty dict ({}), in case you want to modify it before Manual does
def before_fill_slot_data(slot_data: dict, world: "ManualWorld", multiworld: MultiWorld, player: int) -> dict:
    slot_data["linklink"] = {}
    slot_data["linklink"]["key_counts"] = world.item_counts_progression[player]
    slot_data["linklink"]["active_victims"] = world.linklink_active_victims_ids
    slot_data["linklink"]["active_games"] = world.linklink_active_games


    locations_ids = [l.address for l in world.get_locations() if l.address is not None]
    removed_smaller = len(world.linklink_removed_location) < len(locations_ids)
    # To send as little ids as possible pick the one with less locs in the list
    slot_data["linklink"]["filtered_removed"] = removed_smaller
    slot_data["linklink"]["filtered_locations"] = world.linklink_removed_location if removed_smaller else locations_ids
    return slot_data

# This is called after slot data is set and provides the slot data at the time, in case you want to check and modify it after Manual is done with it
def after_fill_slot_data(slot_data: dict, world: "ManualWorld", multiworld: MultiWorld, player: int) -> dict:
    from .Options import VictoryPercent
    from math import ceil
    keys_required = cast(VictoryPercent, getattr(world.options, "keys_required", VictoryPercent(VictoryPercent.default)))
    percent = keys_required.value / 100
    keys_count = ceil(world.item_counts_progression[player]["ll_collected"] * percent)

    victory_name: str = world.victory_names[0]
    Manual_victory = world.location_name_to_location[victory_name]
    if "location_id_to_alias" not in slot_data.keys():
        slot_data["location_id_to_alias"] = {}
    slot_data["location_id_to_alias"][Manual_victory["id"]] = f"{keys_count} keys required"
    return slot_data

# This is called right at the end, in case you want to write stuff to the spoiler log
def before_write_spoiler(world: "ManualWorld", multiworld: MultiWorld, spoiler_handle) -> None:
    pass

# This is called when you want to add information to the hint text
def before_extend_hint_information(hint_data: dict[int, dict[int, str]], world: "ManualWorld", multiworld: MultiWorld, player: int) -> None:
    from itertools import groupby
    items = [loc.item for loc in multiworld.get_filled_locations() if loc.item is not None and loc.item.player == player]
    items.extend(multiworld.precollected_items.get(player, []))
    items = [i for i in items if i.advancement]

    groups: dict[str,list] = {}
    keyfunc = lambda i: i.name
    data = sorted(items, key=keyfunc)
    for k, g in groupby(data, keyfunc):
        if k not in groups.keys():
            groups[k] = list(g)

    if player not in hint_data:
        hint_data[player] = {}

    iterators: dict[str, dict[str,Iterator]] = {}
    next_item: dict[str, dict[str,Item|None]] = {}
    # hintsdone: dict[str, list[str]] = {}
    for location in multiworld.get_locations(player):
        if not location.address or location.item is None:
            continue
        elif world.location_name_to_location.get(location.name, {}).get("linklink", None) is None:
            continue

        item_name= cast(str, world.location_name_to_location[location.name]["linklink"])
        p_num = str(location.item.player)
        if p_num not in iterators.keys():
            iterators[p_num] = {}
            next_item[p_num] = {}
            # hintsdone[p_num] = []

        if next_item[p_num].get(item_name, None) is None or item_name not in iterators[p_num].keys():
            ll_keys = list(groups.get(item_name, []))
            world.random.shuffle(ll_keys)

            iterators[p_num][item_name] = iter(ll_keys)
            next_item[p_num][item_name] = next(iterators[p_num][item_name], None)

        current_item = next_item[p_num][item_name]
        if current_item is not None:
            if current_item.location is not None:
                hint_data[player][location.address] = f"{str(current_item.location)}"
            else:
                hint_data[player][location.address] = f"In {world.player_name}'s start inventory"
            pass
        # hintsdone[p_num].append(f"{item_name}: {hint_data[player][location.address]}")
        next_item[p_num][item_name] = next(iterators[p_num][item_name], None)
    pass

def after_extend_hint_information(hint_data: dict[int, dict[int, str]], world: "ManualWorld", multiworld: MultiWorld, player: int) -> None:
    pass

def hook_interpret_slot_data(world: "ManualWorld", player: int, slot_data: dict[str, Any]) -> dict[str, Any]:
    """
        Called when Universal Tracker wants to perform a fake generation
        Use this if you want to use or modify the slot_data for passed into re_gen_passthrough
    """
    return slot_data
