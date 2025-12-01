import json
import re
from os import path
from typing import cast

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

def load_data_file(fname: str) -> dict:
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
    schema = load_data_file('items.schema.json')
    for filename in ['items.json', 'items_pkmn.json', 'items_kh.json']:
        itemsjson = load_data_file(filename)
        if isinstance(itemsjson, list):
            itemsjson = {"$schema": "items.schema.json","data": itemsjson}

        if schema and itemsjson:
            # First get the keys from schema:
            schema_linklink = schema.get('definitions', {}).get('linklink', {}).get("properties", None)
            if schema_linklink is None:
                raise ValueError("items.schema.json doesn't contain a known definition of the linklink data")
            schema_linklink = cast(dict[str, dict[str, str | bool]], schema_linklink)

            known_loz_keys: list[str] = []
            for key, value in schema_linklink.items():
                if value.get("loz", False):
                    known_loz_keys.append(key)

            # Second: sort all the item's linklink properties by placing the zelda ones first
            for item in itemsjson.get("data", []):
                item = cast(dict[str, dict[str, list[str]]], item)
                if not item.get("linklink"):
                    continue
                else:
                    item["linklink"] = dict(sorted(item["linklink"].items(), key=lambda item: (0 if item[0] in known_loz_keys else 1, item[0])))

            # Third and finally write the change to the file
            write_data_file(filename, itemsjson)
        else:
            raise ValueError(f"Failed to load data from items.schema.json or {filename}")
