from typing import Any, cast
from . import MAX_PLAYERS, FREE_ITEMS
import logging
# region load extra files
class metadata_class():
    extra_files: list[str]
    ids_reserved: int

    def __init__(self, json: dict[str, Any], offset_size: int = 1000):
        self.extra_files = json.get("extra_files", [])
        self.ids_reserved = json.get("offset", offset_size)

class Item_Validation():
    count: int = 0
    extra: int = 0
    name: str
    category: list[str] = []
    linklink: dict[str, list[str]] | None = None

    def __init__(self, json: dict[str, Any]):
        self.count = json.get("count", 0)
        self.extra = json.get("extra", 0)
        name = json.get("name")
        if name is None:
            raise ValueError("LinkLink Item should have a 'name'")
        self.name = name
        self.category = json.get("category", [])
        self.linklink = json.get("linklink")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "count": self.count, "extra": self.extra, "category": self.category, "linklink": self.linklink}

def recursively_find_files_to_load(data_table: list[dict[str, Any]]|dict[str, Any], offset: int = 0, offset_size: int = 1000, adjust_ids: bool = True) -> tuple[int, int]:
    from ..Helpers import load_data_file
    errors: list[str] = []
    if isinstance(data_table, dict): # things like region files
        current_offset, last_offset_size = 0, 0
        if data_table:
            FileMetaData = data_table.pop("FileMetaData", "")
            if FileMetaData:
                metadata = metadata_class(FileMetaData, 0)
            else:
                return 0, 0
        else:
            return 0, 0
        for extra_file in metadata.extra_files:
            new_dict_table: dict[str, Any] = load_data_file(extra_file)
            new_dict_table.pop("$schema", "")
            recursively_find_files_to_load(new_dict_table)
            shared_keys = list(data_table.keys() & new_dict_table.keys())
            nl = "\n"
            if shared_keys:
                errors.append(f'file {extra_file} contains {len(shared_keys)} key{"s" if len(shared_keys) > 1 else ""} that are shared with existing tables' +
                              f"{nl} Here's the list of those duplicate: [{', '.join(shared_keys)}]")

            else:
                data_table |= new_dict_table

    else: # lists of dicts like locations.json
        if data_table:
            if data_table[0].get("name", "") == "FileMetaData":
                metadata = metadata_class(data_table.pop(0), offset_size)
            elif data_table[0].get("FileMetaData"):
                metadata = metadata_class(data_table[0]["FileMetaData"], offset_size)
            else:
                return offset, offset_size
        else:
            return offset, offset_size

        from ..Data import convert_to_list
        if not adjust_ids:
            metadata.ids_reserved = 0
            offset = 0
        last_offset_size = metadata.ids_reserved
        current_offset = offset
        for extra_file in metadata.extra_files:
            known_names: set[str] = {o["name"] for o in data_table}
            id_offset = current_offset + last_offset_size

            new_table: list[dict[str, Any]] = convert_to_list(load_data_file(extra_file), "data")
            current_offset, last_size = recursively_find_files_to_load(new_table, id_offset, last_offset_size, adjust_ids=adjust_ids)

            # ? maybe find a way to alias the keys so you can have "Fire Magic" in items.json ->
            # ? and "Plasma" in metroid and both work together?
            # ? might be possible by making it add an "or" requirement for each "alias" declared
            # ? that or somehow combine the keys (category maybe)
            category_name = "linklink " + extra_file.lower().removeprefix("items_").removesuffix(".json")
            linklink_errors: list[str] = []
            for item in list(new_table):
                item_o = Item_Validation(item)
                if item_o.linklink is not None:
                    if 'category' not in item:
                        item["category"] = [category_name]
                    elif category_name not in item['category']:
                        item["category"].append(category_name)
                    for existing_item in data_table:
                        ex_item_o = Item_Validation(existing_item)
                        if item_o.name.strip().lower() == ex_item_o.name.strip().lower():
                            if item_o.linklink is None or ex_item_o.linklink is None:
                                linklink_errors.append(item_o.name)
                                continue
                            ex_item_o.linklink.update(item_o.linklink)
                            ex_item_o.category = list(set(item_o.category + ex_item_o.category))

                            existing_item["category"] = ex_item_o.category
                            existing_item["linklink"] = ex_item_o.linklink
                            existing_item["count"] = max(item_o.count, ex_item_o.count)
                            existing_item["extra"] = max(item_o.extra, ex_item_o.extra)
                            new_table.remove(item)
                            break

            new_names: set[str]= {o["name"] for o in new_table}
            shared_keys = list(new_names & known_names)

            if shared_keys:
                nl = "\n"
                errors.append(f'file {extra_file} contains {len(shared_keys)} key{"s" if len(shared_keys) > 1 else ""} that are shared with existing tables' +
                              f"{nl} Here's the list of those duplicate: [{', '.join(shared_keys)}]")

            else:
                if adjust_ids:
                    for manual_dict in list(new_table):
                        if manual_dict.get("id"):
                            manual_dict["id"] += id_offset
                    new_table[0]["id"] = id_offset

                if current_offset != id_offset: # some file got recursively found
                    last_offset_size = last_size
                elif last_offset_size != metadata.ids_reserved: # restore previous offset
                    last_offset_size = metadata.ids_reserved
                data_table.extend(new_table)

    if errors:
        if len(errors) == 1:
            raise Exception("Found an error in the file data: \n - " + errors[0])
        else:
            raise Exception("Found errors in the files data:" + "\n - ".join(errors))
    return current_offset, last_offset_size
# endregion

ITEM_TABLE: list[dict[str, Any]] = []
LOCATION_TABLE: list[dict[str, Any]] = []
# called after the game.json file has been loaded
def after_load_game_file(game_table: dict) -> dict:
    return game_table

# called after the items.json file has been loaded, before any item loading or processing has occurred
# if you need access to the items after processing to add ids, etc., you should use the hooks in World.py
def after_load_item_file(item_table: list[dict[str, Any]]) -> list:
    # add the linklink category to all the existing items of the main items.json file
    # first_ll = True
    for item in item_table:
        if item.get('linklink'):
            # if first_ll:
            #     item["id"] = 1000 # give plenty of space for non-ll locations
            #     first_ll = False
            if 'category' not in item:
                item["category"] = ['linklink main']
            elif 'linklink main' not in item['category']:
                item["category"].append('linklink main')
    more_than_one_file = recursively_find_files_to_load(item_table)[0] != 0

    for item in item_table:
        if item.get("linklink"):
            if more_than_one_file:
                if 'linklink all files' not in item['category']:
                    item["category"].append('linklink all files')
            if not item.get("progression"):
                item["progression"] = True
        if 'count' not in item:
            item["count"] = 1
        if 'extra' not in item:
            item["extra"] = 0
    ITEM_TABLE.extend(item_table)
    return item_table


# called after the locations.json file has been loaded, before any location loading or processing has occurred
# if you need access to the locations after processing to add ids, etc., you should use the hooks in World.py
def after_load_location_file(location_table: list) -> list:
    digit = len(str(FREE_ITEMS + 1))
    for i in range(1, FREE_ITEMS + 1):
        location: dict[str, Any] = {
            "name": f"Free Item {str(i).zfill(digit)}",
            "region": "Free Items",
            "category": ["Free Items"],
            "requires": "",
        }
        location_table.append(location)
    recursively_find_files_to_load(location_table)
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
                        "linklink": item['name'],
                        "scoutable": True,
                        "linklink_player": j,
                        "linklink_level": i
                    })
    LOCATION_TABLE.extend(location_table)
    return location_table

# called after the events.json file has been loaded, before any processing has occurred
# If you need access to the events after processing, you should use the hooks in World.py
def after_load_event_file(event_table: list) -> list:
    recursively_find_files_to_load(event_table, adjust_ids=False)
# region create_event
# this region deals with the "create_event" location property
    class event_override():
        name: str
        data: dict[str, Any]

        def __init__(self, name: str, data = {}) -> None:
            if name.startswith("@"):
                name = f"[Event] {name.removeprefix('@')}"
            self.name = name
            self.data = data
            pass
    name: str
    for location in LOCATION_TABLE:
        loc_name: str = location["name"]
        event_request = location.get("create_event")
        if not event_request:
            continue

        base_event_override: dict[str, str] = {"copy_location": location["name"]}
        for property, value in location.items():
            if property.lower().startswith("event_"):
                # we have schema for ["event_visible", "event_category"] but others (except "name") should work too
                property_name = property.removeprefix("event_")
                if property_name == "name":
                    logging.warning(f'Warning: Location "{loc_name}" tried to override the created event(s)\'s name using the property "event_name",\
                                    \nit should be set directly in "create_event" instead')
                    continue
                base_event_override[property_name] = value

        if isinstance(event_request, str):
            events_to_make = [event_override(event_request, base_event_override)]
        elif isinstance(event_request, list):
            events_to_make = []
            for i in event_request:
                if isinstance(i, str):
                    events_to_make.append(event_override(i, base_event_override))
                elif isinstance(i, dict):
                    name = i.pop("name")
                    events_to_make.append(event_override(name, base_event_override | i))
                else:
                    raise ValueError("uh what...")
        else:
            events_to_make = [event_override(f"@{loc_name}", base_event_override)]

        for event_obj in events_to_make:
            event: dict[str, str] = {"name": event_obj.name, "enabled_with_location": event_obj.data["copy_location"]} | event_obj.data

            event_table.append(event)
# endregion
    for item in ITEM_TABLE:
        if 'linklink' in item:
            item_o = Item_Validation(item)
            digit = len(str(item_o.count + 1))
            players_digits = len(str(MAX_PLAYERS))
            for i in range(1, item_o.count + 1):
                name = f"{item_o.name} {str(i).zfill(digit)}"
                event_table.append({
                    "name": "ll_collected",
                    "category": ["Goal"],
                    "location_name": name + " Event",
                    "copy_location": name + f" Player {str(1).zfill(players_digits)}",
                    "visible": True,
                })
    return event_table

# called after the regions.json file has been loaded, before any location loading or processing has occurred
# if you need access to the locations after processing to add ids, etc., you should use the hooks in World.py
def after_load_region_file(region_table: dict) -> dict:
    for item in ITEM_TABLE:
        if 'linklink' in item:
            count = item['count'] + 1
            digit = len(str(count))
            for i in range(1, count):
                name = f"{item['name']} {str(i).zfill(digit)}"
                if name not in region_table:
                    region: dict[str, str|list|bool] = {
                        "name": name,
                        "requires": f"|{item['name']}:{i}|",
                    }
                    region["starting"] = True if i == 1 else False
                    region["connects_to"] = [f"{item['name']} {str(i + 1).zfill(digit)}"] if i < count - 1 else []

                    region_table[name] = region
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
