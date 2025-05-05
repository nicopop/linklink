# Object classes from AP core, to represent an entire MultiWorld and this individual World that's part of it
import logging
from worlds.AutoWorld import World
from BaseClasses import MultiWorld, CollectionState, Item, ItemClassification, Location
from typing import TYPE_CHECKING, Iterator, cast, Any

# Object classes from Manual -- extending AP core -- representing items and locations that are used in generation
from ..Items import ManualItem
from ..Locations import ManualLocation
from ..Helpers import get_items_for_player
# Raw JSON data from the Manual apworld, respectively:
#          data/game.json, data/items.json, data/locations.json, data/regions.json
#
from ..Data import game_table, item_table, location_table, region_table
from .Data import MAX_PLAYERS

# These helper methods allow you to determine if an option has been set, or what its value is, for any player in the multiworld
from ..Helpers import is_option_enabled, get_option_value, format_state_prog_items_key, ProgItemsCat

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



# Use this function to change the valid filler items to be created to replace item links or starting items.
# Default value is the `filler_item_name` from game.json
def hook_get_filler_item_name(world: World, multiworld: MultiWorld, player: int) -> str | bool:
    return False

# Called before regions and locations are created. Not clear why you'd want this, but it's here. Victory location is included, but Victory event is not placed yet.
def before_create_regions(world: World, multiworld: MultiWorld, player: int):
    pass

# Called after regions and locations are created, in case you want to see or modify that information. Victory location is included.
def after_create_regions(world: World, multiworld: MultiWorld, player: int):
    pass

# This hook allows you to access the item names & counts before the items are created. Use this to increase/decrease the amount of a specific item in the pool
# Valid item_config key/values:
# {"Item Name": 5} <- This will create qty 5 items using all the default settings
# {"Item Name": {"useful": 7}} <- This will create qty 7 items and force them to be classified as useful
# {"Item Name": {"progression": 2, "useful": 1}} <- This will create 3 items, with 2 classified as progression and 1 as useful
# {"Item Name": {0b0110: 5}} <- If you know the special flag for the item classes, you can also define non-standard options. This setup
#       will create 5 items that are the "useful trap" class
# {"Item Name": {ItemClassification.useful: 5}} <- You can also use the classification directly
def before_create_items_all(item_config: dict[str, int|dict], world: World, multiworld: MultiWorld, player: int) -> dict[str, int|dict]:
    for item_data in item_table:
        item_data = cast(dict[str, Any], item_data)
        if item_config.get(item_data['name']) and 'linklink' in item_data:
            classification = ItemClassification.filler

            if item_data.get("trap"):
                classification |= ItemClassification.trap

            if item_data.get("useful"):
                classification |= ItemClassification.useful

            if item_data.get("progression_skip_balancing"):
                classification |= ItemClassification.progression_skip_balancing
            elif item_data.get("progression"):
                classification |= ItemClassification.progression

            if item_data['extra']:
                extra_classification = ItemClassification(classification)
                if ItemClassification.progression in classification and ItemClassification.useful not in classification:
                    extra_classification |= ItemClassification.useful
                extra_classification &= ~ItemClassification.progression_skip_balancing

                item_config[item_data['name']] = {classification: item_data['count'] - item_data['extra'], extra_classification: item_data['extra']}

    return item_config

# The item pool before starting items are processed, in case you want to see the raw item pool at that stage
def before_create_items_starting(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    return item_pool

# The item pool after starting items are processed but before filler is added, in case you want to see the raw item pool at that stage
def before_create_items_filler(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    # To get the total of non-filler items without counting later.
    world.linklink_keys = len(item_pool)
    return item_pool


# The complete item pool prior to being set for generation is provided here, in case you want to make changes to it
def after_create_items(item_pool: list[Item], world: World, multiworld: MultiWorld, player: int) -> list:
    fillers = len(item_pool) - int(world.linklink_keys)
    locations: dict[str, Location] = {n:l for n, l in world.location_name_to_location.items() if not (l.get('victory') or [world.filler_item_name] != l.get("place_item", []) or l.get("place_item_category")) }
    todo = len(locations) - fillers
    if todo > 0:
        for _ in range(todo):
            item_pool.append(world.create_filler())
    return item_pool



def replace_nothings(world: World, multiworld: MultiWorld, player: int, unplaced_nothing: int | None = None):
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
def before_set_rules(world: World, multiworld: MultiWorld, player: int):
    pass

# Called after rules for accessing regions and locations are created, in case you want to see or modify that information.
def after_set_rules(world: World, multiworld: MultiWorld, player: int):
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
def before_create_item(item_name: str, world: World, multiworld: MultiWorld, player: int) -> str:
    return item_name

# The item that was created is provided after creation, in case you want to modify the item
def after_create_item(item: ManualItem, world: World, multiworld: MultiWorld, player: int) -> ManualItem:
    return item

# This method is run towards the end of pre-generation, before the place_item options have been handled and before AP generation occurs
def before_generate_basic(world: World, multiworld: MultiWorld, player: int):
    pass

# This method is run at the very end of pre-generation, once the place_item options have been handled and before AP generation occurs
def after_generate_basic(world: World, multiworld: MultiWorld, player: int):
    def linklink_magic(count_precollected_items = True):
        start_time = time.time()
        victims = get_victims(world, True)

        unplaced_items = [i for i in multiworld.itempool if i.location is None]
        unplaced_nothing = [i for i in unplaced_items if i.name == world.filler_item_name and i.player == player]

        filler_to_make: int = 0
        filler_made: int = 0
        filler_keys: int = 0
        extras: int = 0

        players_digits = len(str(MAX_PLAYERS))
        def place_locked_item(location: Location, item: Item):
            if location.item:
                old_item = location.item
                old_item.location = None
                multiworld.itempool.append(old_item)
                unplaced_items.append(old_item)
                unplaced_nothing.append(old_item)
            location.item = item
            item.location = location
            location.locked = True

        logging.info(f"{multiworld.player_name[player]} is casting some linklink{' black' if count_precollected_items else ''} magic with {', '.join([multiworld.player_name[p] for p in victims]) if len(world.options.victims.value) > 0 else 'everyone'}") # type: ignore
        for item_data in item_table:
            if 'linklink' in item_data:
                # logging.debug(repr(linklink))
                linklink: dict[str, list[str]] = item_data['linklink']
                item_count: int = item_data['count'] - item_data['extra']
                extras += item_data['extra']
                item_name: str = item_data['name']
                filler_to_make_for_player: dict[int, int] = {}
                item_cache: dict[int, list[Item]] = {}
                digit = len(str(item_count + 1))
                any_victim = False
                highest_placed_count = 0
                spot_filled = 0
                for i in range(1, item_count + 1):
                    any_placed = False
                    n = 1
                    for j in range(1, multiworld.players + 1):
                        if j == player or j not in victims:
                            continue
                        jworld: World = multiworld.worlds[j]
                        game = jworld.game
                        if game not in linklink:
                            logging.debug(f"Game {game} not in linklink for {item_name}")
                            continue

                        if filler_to_make_for_player.get(j, None) is None:
                            filler_to_make_for_player[j] = 0

                        location = multiworld.get_location(f"{item_name} l$l {str(i).zfill(digit)} Player {str(n).zfill(players_digits)}", player)
                        if location is None:
                            continue

                        if hasattr(jworld, "item_name_groups") and "$item_name_groups" not in linklink[game]:
                            for name in list(linklink[game]):
                                if name in jworld.item_name_groups.keys():
                                    linklink[game].remove(name)
                                    linklink[game].extend([lli for lli in jworld.item_name_groups[name]])
                            linklink[game].append("$item_name_groups")

                        if item_cache.get(j, None) is None:
                            shuffle = "$Shuffle" in linklink[game]
                            options = [item for item in unplaced_items if item.name in linklink[game] and item.player == j]
                            for item in options:
                                item.LINKLINK_create_filler = True
                            options.sort(key=lambda x: linklink[game].index(x.name))
                            options_index = 0
                            last_index = -1
                            for ll_item in linklink[game]:
                                if not ll_item.startswith("$"):
                                    buffer_index = -1
                                    for buffer_item in options:
                                        buffer_index += 1
                                        if buffer_item.name == ll_item:
                                            options_index = buffer_index
                                            break
                                elif ll_item == "$Shuffle":
                                    if last_index != -1:
                                        # TODO shuffle everything BEFORE the shuffle instead of just if shuffle is present
                                        pass
                                elif ll_item.startswith("$Buffer_"):
                                    buffer_to_make = min(int(ll_item.removeprefix("$Buffer_")), max(0, item_count - len(options)))
                                    if try_create_filter(jworld) is not None: # If current jworld can create filler use those
                                        failed = False
                                        buffers: list[Item] = []
                                        buffer_count = buffer_to_make
                                        while buffer_count > 0 and not failed:
                                            filler = try_create_filter(jworld)
                                            if filler is not None:
                                                buffers.append(filler)
                                                buffer_count -= 1
                                            else:
                                                failed = True
                                    else: # if not go ahead and use the default any victims randomly picked fillers
                                        buffers = replace_nothings(world, multiworld, player, buffer_to_make)
                                    for item in buffers:
                                        item.LINKLINK_create_filler = False
                                    multiworld.itempool.extend(buffers)
                                    unplaced_items.extend(buffers)
                                    for buffer_item in buffers:
                                        options.insert(options_index + 1, buffer_item)
                                last_index += 1

                            if shuffle and len(options) > 1: jworld.random.shuffle(options)
                            item_cache[j] = options
                            if i == 1 and len(options) == 0:
                                logging.debug(f"linklink: No options for {item_name} {str(i).zfill(digit)} for {multiworld.player_name[j]} ({game})")
                                continue

                        item: Item|None = next(iter(item_cache[j]), None)
                        if item is not None:
                            item_cache[j].remove(item)
                            place_locked_item(location, item)
                            unplaced_items.remove(item)
                            multiworld.itempool.remove(item)
                            if item.LINKLINK_create_filler:
                                filler_to_make_for_player[j] += 1
                            else:
                                multiworld.itempool.remove(unplaced_nothing.pop())
                            n += 1
                            spot_filled += 1
                            any_placed = True
                            any_victim = True
                            highest_placed_count = max(highest_placed_count, i)

                    if not any_placed:
                        item = next((item for item in unplaced_items if item.name == item_name and item.player == player and ItemClassification.progression in item.classification), None)
                        if item is None:
                            break
                            # We are out of items to remove anyway
                        logging.debug(f'Removing surplus {item.name}')
                        multiworld.itempool.remove(item)
                        unplaced_items.remove(item)
                if not any_victim:
                    if item_data.get('extra'):
                        for _ in range(item_data['extra']):
                            item = next((item for item in unplaced_items if item.name == item_name and item.player == player), None)
                            if item is None:
                                break
                                # We are out of items to remove anyway
                            extras -= 1
                            logging.debug(f'Removing surplus {item.name}')
                            multiworld.itempool.remove(item)
                            unplaced_items.remove(item)
                filler_to_make_for_player = {player_id: count for player_id, count in filler_to_make_for_player.items() if count > 0}
                if filler_to_make_for_player.values():
                    filler_keys += highest_placed_count
                    available_spots = spot_filled - highest_placed_count
                    extra_to_remove = min(available_spots, extras)
                    item_count = highest_placed_count + extra_to_remove
                    extras -= extra_to_remove

                    queue: Iterator = iter([]) # for type checking reason
                    player_id = None
                    for _ in range(item_count):
                        if player_id is None:
                            queue = iter([player_id for player_id in filler_to_make_for_player.keys()])
                            player_id = next(queue)

                        filler_to_make_for_player[player_id] -= 1
                        if filler_to_make_for_player[player_id] == 0:
                            filler_to_make_for_player.pop(player_id)
                        player_id = next(queue, None)

                    for player_id, count in {p: c for p, c in filler_to_make_for_player.items() if c > 0}.items():
                        skip = False
                        for _ in range(count):
                            if skip:
                                continue
                            jworld = multiworld.worlds[player_id]
                            filler = try_create_filter(jworld)
                            filler.LINKLINK_is_filler = True
                            if filler is not None:
                                filler_made += 1
                                multiworld.itempool.append(filler)
                                unplaced_items.append(filler)
                                if unplaced_nothing is not None and len(unplaced_nothing) > 0:
                                    multiworld.itempool.remove(unplaced_nothing.pop())
                                filler_to_make_for_player[player_id] -= 1
                                if filler_to_make_for_player[player_id] == 0:
                                    filler_to_make_for_player.pop(player_id)
                            else:
                                # if creating filler fail skip the rest of this players attempt
                                skip = True
                    filler_to_make += sum(filler_to_make_for_player.values())

                for location in [l for l in multiworld.get_filled_locations(player) if l.name.startswith(f"{item_name} ")]:
                    if location.item is not None and location.item.name == world.filler_item_name:
                        if location.parent_region is not None:
                            location.parent_region.locations.remove(location)
        if extras > 0:
            logging.info(f"Failed to fit {extras} extra keys in the item pool, randomly picked items from the generated fillers will be removed to avoid creating too many items")
            filler_items = [i for i in unplaced_items if hasattr(i, "LINKLINK_is_filler") and i.LINKLINK_is_filler]
            for _ in range(extras):
                if filler_to_make > 0:
                    filler_to_make -= 1
                    extras -= 1
                elif filler_items:
                    sacrifice = world.random.choice(filler_items)
                    multiworld.itempool.remove(sacrifice)
                    unplaced_items.remove(sacrifice)
                    filler_items.remove(sacrifice)
                    extras -= 1
                else:
                    break
            if extras > 0:
                logging.warning(f"Failed to remove {extras} extra keys, you might see a message later talking about too many items.")

        personal_precol: int = len([i for i in multiworld.precollected_items.get(player, []) if i.name != world.filler_item_name]) \
                                    if count_precollected_items else 0

        nothing_total = filler_to_make + len(multiworld.get_unfilled_locations(player))
        nothing_to_make = nothing_total - len(unplaced_nothing) + personal_precol - extras

        failed_to_remove = 0
        if nothing_to_make < 0:
            for _ in range(abs(nothing_to_make)):
                if len(unplaced_nothing) > 0:
                    multiworld.itempool.remove(unplaced_nothing.pop())
                else:
                    failed_to_remove += 1
        elif nothing_to_make > 0:
            for _ in range(nothing_to_make):
                filler = world.create_filler()
                unplaced_nothing.append(filler)
                multiworld.itempool.append(filler)
        if failed_to_remove:
            logging.warning(f"{multiworld.player_name[player]} failed to remove {failed_to_remove} items you will see in the logs that there are more items than locations")
        if unplaced_nothing:
            replacements = replace_nothings(world, multiworld, player, len(unplaced_nothing))
            for nothing in unplaced_nothing:
                multiworld.itempool.remove(nothing)
            multiworld.itempool.extend(replacements)
        elapsed_time = time.time() - start_time
        logging.info(f"{multiworld.player_name[player]} took {elapsed_time:.4f} seconds to do the linklink magic")

    if world.options.magic_in_pre_fill.value:
        def pre_fill():
            linklink_magic()
        setattr(world, "pre_fill", pre_fill)
    else:
        linklink_magic(False)

def get_filler_item_name(self: World) -> str:
        multiworld = self.multiworld
        player = self.player
        if hasattr(self, "linklink_filler_names"):
            items = self.linklink_filler_names
        else:
            items = {i.name for i in get_items_for_player(multiworld, player, True) if i.classification == ItemClassification.filler and i.name.lower() != "nothing"}
            self.linklink_filler_names = items
        if items:
            return self.random.choice(list(items))
        else:
            return "Nothing"

def try_create_filter(world: World) -> Item|None:
    player = world.player
    player_name = world.multiworld.player_name[player]
    def recursion(tries: int = 0) -> Item|None:
        if tries > 10:
            world.linklink_custom_filler = False
            return None
        if hasattr(world, "linklink_custom_filler"):
            if not world.linklink_custom_filler:
                return None
        if type(world).get_filler_item_name == World.get_filler_item_name:
            # When this is the case the default implementation just pick a random item from the entire itempool of that world
            # progression items included, lets not do that
            type(world).get_filler_item_name = get_filler_item_name
            type(world).linklink_custom_filler = True
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
                type(world).get_filler_item_name = World.get_filler_item_name #Unpatch on fail
                logging.debug(f"linklink: custom get_filler_item_name for {world.game} didn't work, reverting to default")
            type(world).linklink_custom_filler = False
            return None

    return recursion()

def get_linklink_games(world: World) -> set[str]:
    if hasattr(world, "LINKLINK_games"):
        return world.LINKLINK_games
    games = set()
    for item_data in item_table:
        if 'linklink' not in item_data:
            continue
        for game in item_data['linklink'].keys():
            games.add(game)
    world.LINKLINK_games = games
    return games

def get_victims(world: World, filter: bool = False) -> set[int]:
    victims: set = world.options.victims.value # type: ignore
    multiworld = world.multiworld

    if len(victims) == 0:
        victims = set(range(1, multiworld.players + 1))
    else:
        id_for_names = {multiworld.player_name[i]: i for i in range(1, multiworld.players + 1)}
        victims = set([id_for_names[v] for v in victims])

    if filter:
        games = get_linklink_games(world)
        for victim in set(victims):
            if multiworld.worlds[victim].game not in games:
                victims.remove(victim)

    return victims

# This method is run every time an item is added to the state, can be used to modify the value of an item.
# IMPORTANT! Any changes made in this hook must be cancelled/undone in after_remove_item
def after_collect_item(world: World, state: CollectionState, Changed: bool, item: Item):
    # the following let you add to the Potato Item Value count
    # if item.name == "Cooked Potato":
    #     state.prog_items[item.player][format_state_prog_items_key(ProgItemsCat.VALUE, "Potato")] += 1
    pass

# This method is run every time an item is removed from the state, can be used to modify the value of an item.
# IMPORTANT! Any changes made in this hook must be first done in after_collect_item
def after_remove_item(world: World, state: CollectionState, Changed: bool, item: Item):
    # the following let you undo the addition to the Potato Item Value count
    # if item.name == "Cooked Potato":
    #     state.prog_items[item.player][format_state_prog_items_key(ProgItemsCat.VALUE, "Potato")] -= 1
    pass


# This is called before slot data is set and provides an empty dict ({}), in case you want to modify it before Manual does
def before_fill_slot_data(slot_data: dict, world: World, multiworld: MultiWorld, player: int) -> dict:
    return slot_data

# This is called after slot data is set and provides the slot data at the time, in case you want to check and modify it after Manual is done with it
def after_fill_slot_data(slot_data: dict, world: World, multiworld: MultiWorld, player: int) -> dict:
    return slot_data

# This is called right at the end, in case you want to write stuff to the spoiler log
def before_write_spoiler(world: World, multiworld: MultiWorld, spoiler_handle) -> None:
    pass

# This is called when you want to add information to the hint text
def before_extend_hint_information(hint_data: dict[int, dict[int, str]], world: World, multiworld: MultiWorld, player: int) -> None:
    import re
    from itertools import groupby
    items = [loc.item for loc in multiworld.get_filled_locations() if loc.item is not None and loc.item.player == player]
    items.extend(multiworld.precollected_items.get(player, []))

    groups: dict[str,list] = {}
    keyfunc = lambda i: i.name
    data = sorted(items, key=keyfunc)
    for k, g in groupby(data, keyfunc):
        if k not in groups.keys():
            groups[k] = list(g)      # Store group iterator as a list

    if player not in hint_data:
        hint_data.update({player: {}})

    queues: dict[str,Iterator] = {}
    victims: dict[str,list[Item]] = {}
    next_item: dict[str,Item|None] = {}
    for location in multiworld.get_locations(player):
        if not location.address:
            continue
        elif location.parent_region is not None and location.parent_region.name == 'Free Items':
            continue

        item_name = location.name.split("l$l")[0].strip() # re.split(r'\d+', location.name)[0].strip()

        if next_item.get(item_name, None) is None or item_name not in queues.keys():
            victims[item_name] = groups.get(item_name, [])
            world.random.shuffle(victims[item_name])
            queues[item_name] = iter(v for v in victims[item_name])
            next_item[item_name] = next(queues[item_name], None)

        current_item = next_item[item_name]
        if current_item is not None:
            if current_item.location is not None:
                hint_data[player][location.address] = f"{str(current_item.location)}"
            else:
                hint_data[player][location.address] = f"In {multiworld.player_name[player]}'s start inventory"
            pass
        next_item[item_name] = next(queues[item_name], None)
    pass

def after_extend_hint_information(hint_data: dict[int, dict[int, str]], world: World, multiworld: MultiWorld, player: int) -> None:
    pass
