# Object classes from AP core, to represent an entire MultiWorld and this individual World that's part of it
import logging
from worlds.AutoWorld import World
from BaseClasses import MultiWorld, CollectionState, Item, ItemClassification, Location
from typing import TYPE_CHECKING, Iterator

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
from ..Helpers import is_option_enabled, get_option_value

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

# The item pool before starting items are processed, in case you want to see the raw item pool at that stage
def before_create_items_starting(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    return item_pool

# The item pool after starting items are processed but before filler is added, in case you want to see the raw item pool at that stage
def before_create_items_filler(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    # To get the total of non-filler items without counting later.
    world.linklink_keys = len(item_pool)
    return item_pool

    # Some other useful hook options:

    ## Place an item at a specific location
    # location = next(l for l in multiworld.get_unfilled_locations(player=player) if l.name == "Location Name")
    # item_to_place = next(i for i in item_pool if i.name == "Item Name")
    # location.place_locked_item(item_to_place)
    # item_pool.remove(item_to_place)

# The complete item pool prior to being set for generation is provided here, in case you want to make changes to it
def after_create_items(item_pool: list[Item], world: World, multiworld: MultiWorld, player: int) -> list:
    fillers = len(item_pool) - int(world.linklink_keys)
    locations: dict[str, Location] = {n:l for n, l in world.location_name_to_location.items() if not (l.get('victory') or [world.filler_item_name] != l.get("place_item", []) or l.get("place_item_category")) }
    todo = len(locations) - fillers
    if todo > 0:
        for _ in range(todo):
            item_pool.append(world.create_filler())
    return item_pool



def replace_nothings(world: World, multiworld: MultiWorld, player: int, unplaced_nothing: list[Item]| None = None):
    # Remove "Nothing" items and replace them with filler items from other players
    if unplaced_nothing is not None:
        item_pool = unplaced_nothing
    else:
        item_pool = [i for i in multiworld.itempool if i.player == player and i.name == world.filler_item_name]
    item_count = len(item_pool)

    filler_blacklist: list[str] = [] # ["SMZ3", "Links Awakening DX"]  # These games don't have filler items or don't implement them correctly
    victims = list(get_victims(world))
    victims = [v for v in victims if v != player and multiworld.worlds[v].game not in filler_blacklist \
                and "linklink" not in multiworld.worlds[v].game.lower()]  # Only include players with filler items

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
            multiworld.itempool.append(filler)
            if unplaced_nothing is not None and len(unplaced_nothing) > 0:
                multiworld.itempool.remove(unplaced_nothing.pop())
            item_count -= 1
        else:
            victims.remove(other_player)
            if not victims:
                break
            world.random.shuffle(victims)
            queue = iter(v for v in victims)
        other_player = next(queue, None)

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
    start_time = time.time()
    victims = get_victims(world)

    unplaced_items = [i for i in multiworld.itempool if i.location is None]
    unplaced_nothing = [i for i in unplaced_items if i.name == world.filler_item_name and i.player == player]

    filler_to_make: int = 0

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

    logging.info(f"{multiworld.player_name[player]} is casting some linklink black magic with {', '.join([multiworld.player_name[p] for p in victims]) if len(world.options.victims.value) > 0 else 'everyone'}") # type: ignore
    for item_data in item_table:
        if 'linklink' in item_data:
            # logging.debug(repr(linklink))
            linklink: dict[str, list[str]] = item_data['linklink']
            item_count: int = item_data['count']
            item_name: str = item_data['name']
            filler_to_make_for_player: dict[int, int] = {}
            item_cache: dict[int, list[Item]] = {}
            digit = len(str(item_count + 1))
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

                    location = multiworld.get_location(f"{item_name} {str(i).zfill(digit)} Player {str(n).zfill(players_digits)}", player)
                    if location is None:
                        continue

                    if hasattr(jworld, "item_name_groups") and "$item_name_groups" not in linklink[game]:
                        for name in list(linklink[game]):
                            if name in jworld.item_name_groups.keys():
                                linklink[game].remove(name)
                                linklink[game].extend([i for i in jworld.item_name_groups[name]])
                        linklink[game].append("$item_name_groups")

                    if item_cache.get(j, None) is None:
                        shuffle = "$Shuffle" in linklink[game]
                        options = [item for item in unplaced_items if item.name in linklink[game] and item.player == j]
                        options.sort(key=lambda x: linklink[game].index(x.name))
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
                        filler_to_make_for_player[j] += 1
                        n += 1
                        any_placed = True

                if not any_placed:
                    item = next(item for item in unplaced_items if item.name == item_name and item.player == player)
                    logging.debug(f'Removing surplus {item.name}')
                    multiworld.itempool.remove(item)
                    unplaced_items.remove(item)

            if filler_to_make_for_player.values():
                item_count = max(filler_to_make_for_player.values())

                for p, c in dict(filler_to_make_for_player).items():
                    if c == 0:
                        filler_to_make_for_player.pop(p)

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
                        if filler is not None:
                            multiworld.itempool.append(filler)
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

    # personal_precol = [i for i in multiworld.precollected_items.get(player, []) if i.name != world.filler_item_name]

    nothing_total = filler_to_make + len(multiworld.get_unfilled_locations(player))
    nothing_to_make = nothing_total - len(unplaced_nothing) # + len(personal_precol)

    if nothing_to_make < 0:
        for _ in range(abs(nothing_to_make)):
            if len(unplaced_nothing) > 0:
                multiworld.itempool.remove(unplaced_nothing.pop())
    elif nothing_to_make > 0:
        for _ in range(nothing_to_make):
            filler = world.create_filler()
            unplaced_nothing.append(filler)
            multiworld.itempool.append(filler)

    if unplaced_nothing:
        replace_nothings(world, multiworld, player, unplaced_nothing)
    elapsed_time = time.time() - start_time
    logging.info(f"{multiworld.player_name[player]} took {elapsed_time:.4f} seconds to do the linklink magic")

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


def get_victims(world: World) -> set[int]:
    victims: set = world.options.victims.value # type: ignore
    multiworld = world.multiworld

    if len(victims) == 0:
        victims = set(range(1, multiworld.players + 1))
    else:
        id_for_names = {multiworld.player_name[i]: i for i in range(1, multiworld.players + 1)}
        victims = set([id_for_names[v] for v in victims])
    return victims



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

    ### Example way to use this hook:
    # if player not in hint_data:
    #     hint_data.update({player: {}})
    # for location in multiworld.get_locations(player):
    #     if not location.address:
    #         continue
    #
    #     use this section to calculate the hint string
    #
    #     hint_data[player][location.address] = hint_string

    pass

def after_extend_hint_information(hint_data: dict[int, dict[int, str]], world: World, multiworld: MultiWorld, player: int) -> None:
    pass
