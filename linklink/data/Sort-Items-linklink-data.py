import json
import re
from os import path
from typing import cast, Any

def repl_func(match: re.Match):
    result = " ".join(match.group().split())
    parts = result.split('",')
    current_length = 0
    result_parts: list[str] = []
    indent = "                   "
    for i, part in enumerate(parts):
        if i > 0:
            if current_length > 100 and i < len(parts) - 1:
                current_length = len(part) + 2
                part = f'",\n{indent}' + part

            else:
                current_length += len(part) + 2
                part = '",' + part
        else:
            current_length = len(part) + 1
        result_parts.append(part)
    return "".join(result_parts)

def load_data_file(fname: str) -> dict[str, Any]:
    fpath = path.dirname(__file__)
    fpath = path.join(fpath, fname)
    try:
        with open(fpath, 'r', encoding="utf-8-sig") as f:
            filedata = json.load(f)
    except Exception:
        import yaml
        filedata = yaml.safe_load(open(fpath, 'r', encoding="utf-8-sig"))

    return filedata

def write_data_file(fname: str, data: dict):
    fpath = path.dirname(__file__)
    fpath = path.join(fpath, fname)
    # regex based on answer in https://www.reddit.com/r/learnpython/comments/ymukyr/removing_new_line_inside_square_brackets_in_json/
    json_str = json.dumps(data, indent=4)
    json_str = re.sub(r"(?<=\[)[^\[\]]+(?=])", repl_func, json_str)

    with open(file=fpath, mode="w", encoding="utf-8") as f:
        f.write(json_str)

if __name__ == '__main__':
    # First get the key groups from schema:
    schema = load_data_file('items.schema.json')
    schema_linklink = schema.get('definitions', {}).get('linklink', {}).get("properties", None)
    if schema_linklink is None:
        raise ValueError("items.schema.json doesn't contain a known definition of the linklink data")
    schema_linklink = cast(dict[str, dict[str, str]], schema_linklink)

    known_groups: dict[str, set[str]] = {}
    known_keys: set[str] = set()
    for key, value in schema_linklink.items():
        if value.get("group", None):
            group = value["group"]
            if group not in known_groups.keys():
                known_groups[group] = set()
            known_groups[group].add(key)
            known_keys.add(key)
    def get_group_offset(key: str) -> int:
        if key in known_keys:
            for group, values in known_groups.items():
                if key in values:
                    return list(known_groups.keys()).index(group)
        return len(known_groups.keys())

    # Second: sort all the items's linklink properties by grouping them together first
    for filename in ['items.json', 'items_pkmn.json', 'items_kh.json']:
        itemsjson: dict[str, Any] = load_data_file(filename)
        if isinstance(itemsjson, list):
            itemsjson = {"$schema": "items.schema.json","data": itemsjson}

        if itemsjson.get("data"):
            for item in itemsjson.get("data", []):
                item = cast(dict[str, dict[str, list[str]]], item)
                if not item.get("linklink"):
                    continue
                else:
                    item["linklink"] = dict(sorted(item["linklink"].items(), key=lambda item: \
                        (get_group_offset(item[0]), item[0])))
                # Clean up any empty categories
                if "category" in item and not item["category"]:
                    del item["category"]

            # Third and finally write the change to the file
            write_data_file(filename, itemsjson)
        else:
            raise ValueError(f"Failed to load data from items.schema.json or {filename}")
