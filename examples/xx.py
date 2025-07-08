monospace_tpl = """
👉 {language}
`{content}`
"""


def main(messages: list[dict]) -> dict:
    segments = []
    for message in messages:
        if message.get("type", "") == "quote":
            if content := message.get("content", ""):
                if not content.startswith("> "):
                    segments.append(f"> {content.strip()}\n")
                else:
                    segments.append(f"{content.strip()}\n")
        elif message.get("type", "") == "translation":
            if content := message.get("content", ""):
                language_code = message.get("language_code", "")
                segments.append(monospace_tpl.format(lanuage=language_code, content=content))
    return {
        "type": "fulltext_translation",
        "answer": "".join(segments),
    }
