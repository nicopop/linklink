from typing import Any, cast
from pydantic import BaseModel, ValidationError

class Dict_item(BaseModel):
    count: int = 0
    extra: int = 0
    name: str
    category: list[str] = []
    linklink: dict[str, list[str]] | None = None

ITEM_TABLE = []
MAX_PLAYERS = 40
FREE_ITEMS = 12
extra_item_files = ['items_pkmn.json', 'items_kh.json']
FILLER_NAME = ""

# called after the game.json file has been loaded
def after_load_game_file(game_table: dict) -> dict:
    global FILLER_NAME
    FILLER_NAME = game_table.get("filler_item_name", "Nothing")
    return game_table

# called after the items.json file has been loaded, before any item loading or processing has occurred
# if you need access to the items after processing to add ids, etc., you should use the hooks in World.py
def after_load_item_file(item_table: list) -> list:
    # Store a reference to this

    for i, extra_file in enumerate(extra_item_files):
        from ..Data import convert_to_list
        from ..Helpers import load_data_file

        new_table = convert_to_list(load_data_file(extra_file), "data")
        for item in list(new_table):
            item_o = Dict_item.model_validate(item)
            for existing_item in item_table:
                ex_item_o = Dict_item.model_validate(existing_item)
                if item_o.name.strip().lower() == ex_item_o.name.strip().lower():
                    if item_o.linklink is None or ex_item_o.linklink is None:
                        raise Exception(f"Cannot fuse not linklink item to linklink item with name {item_o.name}")
                    ex_item_o.linklink.update(item_o.linklink)
                    ex_item_o.category = list(set(item_o.category + ex_item_o.category))

                    existing_item["category"] = ex_item_o.category
                    existing_item["linklink"] = ex_item_o.linklink
                    existing_item["count"] = max(item_o.count, ex_item_o.count)
                    existing_item["extra"] = max(item_o.extra, ex_item_o.extra)
                    new_table.remove(item)
                    break
        new_table[0]["id"] = (i + 1) * 1000  # Plenty of room for expansion
        item_table.extend(new_table)

    for item in item_table:
        if 'count' not in item:
            item['count'] = 1
        if 'extra' not in item:
            item['extra'] = 0
    ITEM_TABLE.extend(item_table)
    return item_table

# NOTE: Progressive items are not currently supported in Manual. Once they are,
#       this hook will provide the ability to meaningfully change those.
def after_load_progressive_item_file(progressive_item_table: list) -> list:
    return progressive_item_table

# called after the locations.json file has been loaded, before any location loading or processing has occurred
# if you need access to the locations after processing to add ids, etc., you should use the hooks in World.py
def after_load_location_file(location_table: list) -> list:
    for item in ITEM_TABLE:
        if 'linklink' in item:
            count = item['count']
            digit = len(str(count + 1))
            players_digits = len(str(MAX_PLAYERS))

            for i in range(1, count + 1):
                for j in range(1, MAX_PLAYERS + 1):
                    location_table.append({
                        "name": f"{item['name']} {str(i).zfill(digit)} Player {str(j).zfill(players_digits)}",
                        "region": f"{item['name']} {str(i).zfill(digit)}",
                        "category": [item['name']],
                        "requires": "",
                        "linklink": item['name']
                    })
    digit = len(str(FREE_ITEMS + 1))
    for i in range(1, FREE_ITEMS + 1):
        location_table.append({
            "name": f"Free Item {str(i).zfill(digit)}",
            "region": "Free Items",
            "category": ["Free Items"],
            "requires": "",
        })
    return location_table


# called after the locations.json file has been loaded, before any location loading or processing has occurred
# if you need access to the locations after processing to add ids, etc., you should use the hooks in World.py
def after_load_region_file(region_table: dict) -> dict:
    for item in ITEM_TABLE:
        if 'linklink' in item:
            digit = len(str(item['count'] + 1))
            for i in range(1, item['count'] + 1):
                name = f"{item['name']} {str(i).zfill(digit)}"
                if name not in region_table:
                    region_table[name] = {
                        "name": name,
                        "requires": f"|{item['name']}:{i}|",
                    }
    return region_table

# called after the categories.json file has been loaded
def after_load_category_file(category_table: dict) -> dict:
    return category_table

# called after the categories.json file has been loaded
def after_load_option_file(option_table: dict) -> dict:
    # option_table["core"] is the dictionary of modification of existing options
    # option_table["user"] is the dictionary of custom options
    return option_table

# called after the meta.json file has been loaded and just before the properties of the apworld are defined. You can use this hook to change what is displayed on the webhost
# for more info check https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20api.md#webworld-class
def after_load_meta_file(meta_table: dict) -> dict:
    return meta_table

# called when an external tool (eg Universal Tracker) ask for slot data to be read
# use this if you want to restore more data
# return True if you want to trigger a regeneration if you changed anything
def hook_interpret_slot_data(world, player: int, slot_data: dict[str, Any]) -> dict | bool:
    return slot_data
