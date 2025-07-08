# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 14:26
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
from pathlib import Path
from settings import DATA_DIR


chat_types = set()
chat_enum = {}
for message_path in DATA_DIR.rglob("*.json"):
    data = json.loads(message_path.read_text(encoding="utf-8"))
    sender_chat = data.get("from", {})
    chat_enum[sender_chat.get("id", "")] = sender_chat

print(chat_types)
print(json.dumps(chat_enum, indent=2, ensure_ascii=False))
