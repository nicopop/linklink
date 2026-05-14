from typing import Optional, cast, Any, TYPE_CHECKING
from BaseClasses import MultiWorld, Item, Location

if TYPE_CHECKING:
    from .. import ManualWorld

# Use this if you want to override the default behavior of is_option_enabled
# Return True to enable the category, False to disable it, or None to use the default behavior
def before_is_category_enabled(multiworld: MultiWorld, player: int, category_name: str) -> Optional[bool]:
    return None

# Use this if you want to override the default behavior of is_option_enabled
# Return True to enable the item, False to disable it, or None to use the default behavior
def before_is_item_enabled(multiworld: MultiWorld, player: int, item:  dict[str, Any]) -> Optional[bool]:
    if item.get("linklink"):
        if not item.get("count"):
            return False
        return item["linklink_status"][player]
    return None

# Use this if you want to override the default behavior of is_option_enabled
# Return True to enable the location, False to disable it, or None to use the default behavior
def before_is_location_enabled(multiworld: MultiWorld, player: int, location:  dict[str, Any]) -> Optional[bool]:
    world: "ManualWorld" = multiworld.worlds[player] # type: ignore
    if location.get("linklink"):
        if location["linklink_player"] > len(world.linklink_active_victims_ids):
            world.linklink_helpers_disabled_location += 1 # type: ignore
            return False
        item_name: str = location["linklink"]
        item = world.item_name_to_item[item_name]
        if not "linklink_status" in item.keys():
            item["linklink_status"] = {}
        if not player in item["linklink_status"].keys():
            item["linklink_status"][player] = not get_active_linklink_games(world).isdisjoint(set(item["linklink"].keys()))
        if not item["linklink_status"][player]:
            world.linklink_helpers_disabled_location += 1 # type: ignore
        return item["linklink_status"][player]
    return None

def is_game_enabled(game: str, world: "ManualWorld") -> bool:
    return game in get_active_linklink_games(world)
def get_active_linklink_games(world: "ManualWorld") -> set[str]:
    return world.linklink_active_games
# Use this if you want to override the default behavior of is_option_enabled
# Return True to enable the event, False to disable it, or None to use the default behavior
def before_is_event_enabled(multiworld: MultiWorld, player: int, event:  dict[str, Any]) -> Optional[bool]:
    return None
