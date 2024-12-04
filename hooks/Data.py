ITEM_TABLE = []
MAX_PLAYERS = 40
FREE_ITEMS = 0
PKMN = False

# called after the game.json file has been loaded
def after_load_game_file(game_table: dict) -> dict:
    return game_table

# called after the items.json file has been loaded, before any item loading or processing has occurred
# if you need access to the items after processing to add ids, etc., you should use the hooks in World.py
def after_load_item_file(item_table: list) -> list:
    # Store a reference to this
    if PKMN:
        from ..Data import load_data_file
        item_table.extend(load_data_file('items_pkmn.json'))

    for item in item_table:
        if 'count' not in item:
            item['count'] = 1
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
            for i in range(1, item['count'] + 1):
                for j in range(1, MAX_PLAYERS + 1):
                    location_table.append({
                        "name": f"{item['name']} {i} Player {j}",
                        "region": f"{item['name']} {i}",
                        "category": [item['name']],
                        "requires": "",
                        "linklink": item['linklink'],
                    })
    for i in range(1, FREE_ITEMS + 1):
        location_table.append({
            "name": f"Free Item {i}",
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
            for i in range(1, item['count'] + 1):
                name = f"{item['name']} {i}"
                if name not in region_table:
                    region_table[name] = {
                        "name": name,
                        "requires": f"|{item['name']}:{i}|",
                    }
    return region_table

# called after the categories.json file has been loaded
def after_load_category_file(category_table: dict) -> dict:
    return category_table

# called after the meta.json file has been loaded and just before the properties of the apworld are defined. You can use this hook to change what is displayed on the webhost
# for more info check https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20api.md#webworld-class
def after_load_meta_file(meta_table: dict) -> dict:
    return meta_table

# called when an external tool (eg Univeral Tracker) ask for slot data to be read
# use this if you want to restore more data
# return True if you want to trigger a regeneration if you changed anything
def hook_interpret_slot_data(world, player: int, slot_data: dict[str, any]) -> bool:
    return False
