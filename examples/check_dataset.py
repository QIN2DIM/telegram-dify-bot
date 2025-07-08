# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 14:26
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
from pathlib import Path

dataset_dir = Path(__file__).parent.joinpath("data")

chat_types = set()
chat_enum = {}
for message_path in dataset_dir.rglob("*.json"):
    data = json.loads(message_path.read_text(encoding="utf-8"))
    chat = data["chat"]
    chat_enum[chat["id"]] = chat

print(chat_types)
print(json.dumps(chat_enum, indent=2, ensure_ascii=False))
