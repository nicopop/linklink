import json
import re
from os import path
from pathlib import Path
from typing import cast, Any
from functools import cache

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

def repl_func(match: re.Match):
    groups = match.groups()
    prop_key = groups[0]
    indent_level = int((len(prop_key) - len(prop_key.lstrip(' ')))/4) + 1
    result: str = " ".join(groups[1].split())
    parts = result.split('",')
    current_length = len(prop_key) + 1 # for the [
    result_parts: list[str] = []
    indent = "    "
    for i, part in enumerate(parts):
        if current_length + len(part) + 1 > 120:
            part = f'",\n{indent * indent_level}{part.lstrip(" ")}'
            current_length = len(part) - 3

        else:
            if i > 0:
                part = '",' + part
            current_length += len(part)
        result_parts.append(part)
    return f"{prop_key}[{''.join(result_parts)}]"

def write_data_file(fname: str, data: dict):
    fpath = path.dirname(__file__)
    fpath = path.join(fpath, fname)
    # regex based on answer in https://www.reddit.com/r/learnpython/comments/ymukyr/removing_new_line_inside_square_brackets_in_json/
    json_str = json.dumps(data, indent=4)
    json_str = re.sub(r"(.*?)\[([^\[\]]+)]", repl_func, json_str)

    with open(file=fpath, mode="w", encoding="utf-8") as f:
        f.write(json_str)

if __name__ == '__main__':
    files = [f.name for f in Path(path.dirname(__file__)).iterdir() if f.is_file()\
        and f.name.startswith("items") and "schema" not in f.name]
    print(files)
    # First get the key groups from schema:
    schema = load_data_file('items.schema.json')
    schema_linklink = schema.get('definitions', {}).get('linklink', {}).get("properties", None)
    if schema_linklink is None:
        raise ValueError("items.schema.json doesn't contain a known definition of the linklink data")
    schema_linklink = cast(dict[str, dict[str, str]], schema_linklink)

    known_groups: dict[str, set[str]] = {}
    key_to_group: dict[str, str] = {}

    for key, value in schema_linklink.items():
        if value.get("group", None):
            group = value["group"]
            if group not in known_groups.keys():
                known_groups[group] = set()
            known_groups[group].add(key)
            key_to_group[key] = group

    @cache
    def get_group_offset(key: str) -> int:
        if key in key_to_group.keys():
            group= key_to_group[key]
            return list(known_groups.keys()).index(group)
        return len(known_groups.keys())

    @cache
    def strip_articles(title: str) -> str:
        title = title.replace("_", " ")
        lower = title.lower()
        if lower.startswith("manual "):
            title = title[7:]
            lower = lower[7:]
        if lower.startswith("the legend of zelda - "):
            title = title[22:]
        elif lower.startswith("the "):
            title = title[4:]
        elif lower.startswith("a "):
            title = title[2:]
        elif lower.startswith("an "):
            title = title[3:]
        return title

    # Second: sort all the items's linklink properties by grouping them together first
    for filename in files:
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
                        (get_group_offset(item[0]), strip_articles(item[0]))))
                # Clean up any empty categories
                if "category" in item and not item["category"]:
                    del item["category"]

            # Third and finally write the change to the file
            write_data_file(filename, itemsjson)
        else:
            raise ValueError(f"Failed to load data from items.schema.json or {filename}")
