def main(messages: list[dict]) -> dict:
    segments = []

    for message in messages:
        if message.get("type", "") == "quote":
            continue
            # if content := message.get("content", ""):
            #     if not content.startswith("> "):
            #         segments.append(f"> {content.strip()}\n")
            #     else:
            #         segments.append(f"{content.strip()}\n")
        elif message.get("type", "") == "translation":
            if content := message.get("content", ""):
                if "\n" not in content:
                    segments.append(f"`{content}`".strip())
                else:
                    segments.append(f"```\n{content}\n```".strip())

    return {"answer": "".join(segments)}
