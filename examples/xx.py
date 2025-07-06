monospace_tpl = """
👉 {language}
`{content}`
"""


def main(translation: list) -> dict:
    segments = [
        monospace_tpl.format(language=t["language"], content=t["content"]) for t in translation
    ]
    return {"final": "".join(segments)}
