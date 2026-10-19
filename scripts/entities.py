"""Build or check EvMigEvelyn/entities/*.create.json from docs/mapping.md §8.

For every column row in §8.1-8.3 it reads the Liquibase `type:` on the line after the cited `name:` line, checks that
the Data Fabric type in the mapping follows DEC-6 (NVARCHAR(n) -> STRING n, NVARCHAR(MAX) -> MULTILINE_TEXT 10,000,
DATETIME2 -> DATETIME_WITH_TZ, autoQC/ticker -> BOOLEAN), then compares the entity files with the mapping.
A field name the tenant refused (REFUSED_BY_TENANT) fails the check too.
Usage: python3 -I scripts/entities.py          (check; exit 1 on any difference)
       python3 -I scripts/entities.py --write  (rewrite the three files)
"""
import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
M = Path("/Users/knarayanam/WorkfusionRepos/NSS/names-screening/names-screening-package/src/main/resources/datastore/migrations")
OUT = REPO / "EvMigEvelyn" / "entities"
SECTIONS = {"8.1": "EvMigTransaction", "8.2": "EvMigAlertAnalytics", "8.3": "EvMigHitAnalytics"}
BOOLEAN_COLUMNS = {"autoQC", "ticker"}  # DEC-6: Evelyn writes Java booleans into these NVARCHAR(5) columns
# Field names the tenant refuses although `uip df entities create` lets them through (its own list is only Id, CreatedBy,
# CreateTime, UpdatedBy, UpdateTime, RecordOwner, Version and C#/VB keywords). Lower case. Add each one a tenant refuses.
REFUSED_BY_TENANT = {"uuid"}  # "Field name for 'Uuid' is a reserved SQL word …" (owner's tenant run, 2026-10-19)


def expected_type(column, sql):
    if column in BOOLEAN_COLUMNS:
        return "BOOLEAN", None
    sql = sql.upper()
    if sql == "DATETIME2":
        return "DATETIME_WITH_TZ", None
    if sql == "NVARCHAR(MAX)":
        return "MULTILINE_TEXT", 10000
    n = re.fullmatch(r"NVARCHAR\((\d+)\)", sql)
    if n:
        return "STRING", int(n.group(1))
    raise ValueError(f"no DEC-6 rule for {column} {sql}")


def mapped_type(cell):
    kind = re.match(r"(STRING|MULTILINE_TEXT|DATETIME_WITH_TZ|BOOLEAN)", cell).group(1)
    length = re.match(r"STRING\((\d+)\)", cell) or re.match(r"MULTILINE_TEXT ([\d,]+)", cell)
    return kind, int(length.group(1).replace(",", "")) if length else None


def entities_from_mapping():
    text = (REPO / "docs" / "mapping.md").read_text(encoding="utf-8")
    result, errors = {}, []
    for section, entity in SECTIONS.items():
        body = text.split(f"### {section} ", 1)[1].split("\n### ", 1)[0]
        table = re.search(r"Table name: `M:([^:`]+):\d+` “tableName: (\w+)”", body)
        fields = []
        for row in body.splitlines():
            cite = re.match(r"\| `(\w+)` \| `M:([^:`]+):(\d+)` “name: \w+” \|", row)
            if not cite:
                continue
            column, file, line = cite.group(1), cite.group(2), int(cite.group(3))
            cells = [c.strip() for c in row.strip("|").split("|")]
            i = next(k for k, c in enumerate(cells) if k > 1 and re.fullmatch(r"`[A-Z][A-Za-z0-9]*`", c))
            name, df_cell, sql = cells[i].strip("`"), cells[i + 1], cells[2].split(",")[0].strip()
            if name.lower() in REFUSED_BY_TENANT:
                errors.append(f"{entity}.{name}: Data Fabric refuses this field name (REFUSED_BY_TENANT)")
            yaml_sql = (M / file).read_text(encoding="utf-8").split("\n")[line].split("type:")[1].strip()
            if yaml_sql.upper() != sql.upper():
                errors.append(f"{entity}.{name}: mapping says {sql}, {file}:{line + 1} says {yaml_sql}")
            kind, length = mapped_type(df_cell)
            if (kind, length) != expected_type(column, yaml_sql):
                errors.append(f"{entity}.{name}: mapping says {kind} {length}, DEC-6 gives {expected_type(column, yaml_sql)}")
            field = {"name": name, "type": kind}
            if length:
                field["lengthLimit"] = length
            if "required" in df_cell:
                field["isRequired"] = True
            if "unique" in df_cell:
                field["isUnique"] = True
            default = re.search(r'default "([^"]*)"', df_cell)
            if default:
                field["defaultValue"] = default.group(1)
            field["description"] = f"Evelyn column {column} ({yaml_sql}), {file}"
            fields.append(field)
        result[entity] = {
            "displayName": entity,
            "description": f"Port of Evelyn table {table.group(2)}, final state of its Liquibase changesets "
                           f"(docs/mapping.md §{section}).",
            "fields": fields,
        }
    return result, errors


def main():
    entities, errors = entities_from_mapping()
    for entity, body in entities.items():
        path = OUT / f"{entity}.create.json"
        rendered = json.dumps(body, indent=2, ensure_ascii=False) + "\n"
        if "--write" in sys.argv:
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif not path.exists() or path.read_text(encoding="utf-8") != rendered:
            errors.append(f"{path.relative_to(REPO)} differs from mapping §8 (run with --write to rebuild)")
        print(f"{entity}: {len(body['fields'])} fields")
    for error in errors:
        print("FAIL", error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
