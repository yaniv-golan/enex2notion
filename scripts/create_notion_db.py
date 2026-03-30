#!/usr/bin/env python3
"""Create a Notion database with the correct schema for enex2notion DB mode.

Requires a Notion integration token (not token_v2).
Create one at https://www.notion.so/my-integrations

The integration must be connected to the parent page before running this script.

Usage:
    python scripts/create_notion_db.py \
        --token <NOTION_API_TOKEN> \
        --parent-page-id <PAGE_ID> \
        --title "My Notebook"

The --title should match your ENEX filename stem (e.g., "My Notebook" for
"My Notebook.enex") so that enex2notion finds the database automatically.
"""

import argparse
import json
import sys

import requests

NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"


def create_database(token, parent_page_id, title):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }

    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": {
            "Title": {"title": {}},
            "Evernote Tags": {"multi_select": {"options": []}},
            "Evernote Web Clip URL": {"url": {}},
            "Evernote Created": {"date": {}},
            "Evernote Updated": {"date": {}},
            "Evernote Author": {"rich_text": {}},
            "Evernote Imported": {"created_time": {}},
            "Last Modified": {"last_edited_time": {}},
        },
    }

    response = requests.post(
        f"{NOTION_API_BASE}/databases", headers=headers, json=body
    )

    if response.status_code != 200:
        print(f"Error creating database: {response.status_code}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    db = response.json()
    db_id = db["id"]
    print(f"Database '{title}' created successfully!")
    print(f"Database ID: {db_id}")
    print(f"URL: {db['url']}")

    _add_formula_columns(headers, db_id)

    return db_id


def _add_formula_columns(headers, db_id):
    formulas = {
        "Real Created": {
            "formula": {
                "expression": (
                    'if(empty(prop("Evernote Created")),'
                    ' prop("Evernote Imported"),'
                    ' prop("Evernote Created"))'
                )
            }
        },
        "Real Updated": {
            "formula": {
                "expression": (
                    'if(empty(prop("Evernote Updated")),'
                    " prop(\"Last Modified\"),"
                    " if(dateBetween(prop(\"Last Modified\"),"
                    ' prop("Evernote Imported"), "seconds") > 120,'
                    " prop(\"Last Modified\"),"
                    ' prop("Evernote Updated")))'
                )
            }
        },
    }

    for name, config in formulas.items():
        body = {"properties": {name: config}}
        response = requests.patch(
            f"{NOTION_API_BASE}/databases/{db_id}", headers=headers, json=body
        )

        if response.status_code != 200:
            print(
                f"Warning: failed to add '{name}' formula: {response.status_code}",
                file=sys.stderr,
            )
            print(response.text, file=sys.stderr)
        else:
            print(f"Added formula column: {name}")


def main():
    parser = argparse.ArgumentParser(
        description="Create a Notion database for enex2notion DB mode import"
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Notion integration token (from notion.so/my-integrations)",
    )
    parser.add_argument(
        "--parent-page-id",
        required=True,
        help="ID of the parent page (UUID, with or without dashes)",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="Database title (should match ENEX filename stem)",
    )

    args = parser.parse_args()
    create_database(args.token, args.parent_page_id, args.title)


if __name__ == "__main__":
    main()
