#!/usr/bin/env python3
# scripts/push.py

import http.client
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List

logging.basicConfig(
    level=logging.INFO, stream=sys.stdout, format="%(asctime)s - %(levelname)s - %(message)s"
)

PARAMETER_EXTRACTOR_SYSTEM_PROMPT = """
You are a helpful assistant tasked with extracting structured information based on specific criteria provided. Follow the guidelines below to ensure consistency and accuracy.
### Task
Always call the `extract_parameters` function with the correct parameters. Ensure that the information extraction is contextual and aligns with the provided criteria.
### Memory
Here is the chat history between the human and assistant, provided within <histories> tags:
<histories>

</histories>
### Instructions:
Some additional information is provided below. Always adhere to these instructions as closely as possible:
<instruction>
{instructions}
</instruction>
Steps:
1. Review the chat history provided within the <histories> tags.
2. Extract the relevant information based on the criteria given, output multiple values if there is multiple relevant information that match the criteria in the given text. 
3. Generate a well-formatted output using the defined functions and arguments.
4. Use the `extract_parameter` function to create structured outputs with appropriate parameters.
5. Do not include any XML tags in your output.
### Example
To illustrate, if the task involves extracting a user's name and their request, your function call might look like this: Ensure your output follows a similar structure to examples.
### Final Output
Produce well-formatted function calls in json without XML tags, as shown in the example.
""".strip()

PARAMETERS_TEMPLATE = """
/no_think

### Structure
Here is the structure of the JSON object, you should always follow the structure.
<structure>
{structure}
</structure>

### Text to be converted to JSON
Inside <text></text> XML tags, there is a text that you should convert to a JSON object.
<text>
{text}
</text>

### Format Examples

**Git Commit title format: `<emoji> <flag>: <english_title>`**
[example 1 start]
🔨 chore: Prettier & Add proxyUrl for all providers
[example 1 end]
[example 2 start]
✨ feat: Support ModelScope Provider
[example 2 end]
[example 3 start]
📝 docs(bot): Auto sync agents & plugin to readme
[example 3 end]
""".strip()

COMMITS_GENERATOR_SYSTEM_PROMPT = """
You are an expert code review assistant specializing in analyzing git diffs and generating concise commit titles and structured change summaries.

Your task is to analyze the git diff provided by the user and produce a commit title and detailed change summary that adhere to open-source best practices. Follow these steps to complete the task:

1. **Analyze the Git Diff:**
   - Carefully review the content of the git diff, ensuring you understand all code changes.
   - Identify the primary modifications, including added, deleted, or modified code blocks.
   - Pay close attention to changes in file names, function names, and variable names.
   - **Specifically identify if the changes span multiple files or a single file.**

2. **Generate a Commit Title:**
   - Write a concise commit title that summarizes the main purpose of the changes.
   - The title should be clear, informative, and no more than 50 characters in length.
   - Begin the title with an appropriate tag (e.g., `blog`, `docs`, `feat`, `fix`, `refactor`, `test`) followed by a brief description of the commit's primary action.

3. **Generate a Change Summary:**
   - Create a structured change summary that lists the key modifications.
   - Use an unordered list format (starting with "-") to organize each point.
   - Each point should be concise and highlight the significant changes.
   - **If changes involve multiple files:**
     - **Summarize the overall intent of the changes.**
     - **List the files affected by the changes.**
   - **If changes involve a single file:**
     - **Simply indicate the single file name.**
   - The change summary should be in Chinese.

Present your final answer in the following format:

```
<title>
[Commit title in English, no more than 50 characters, starting with an appropriate tag]
</title>

<summary>
- [Change point 1]
- [Change point 2]
- [Change point 3]
...
</summary>
```
""".strip()

MESSAGE_TEMPLATE = """
请根据以下 git diff 生成提交信息:

```diff
{diff}
```
""".strip()

OPENAI_CONNECTION_HOST = "192.168.3.90"
OPENAI_CONNECTION_PORT = 30000

@dataclass
class CommitMessage:
    title: str
    summary: List[str] = field(default_factory=list)

    @property
    def summary_text(self) -> str:
        return "\n".join(self.summary)


def get_git_diff() -> str:
    # 定义需要忽略的文件和目录
    ignore_patterns = [
        "yarn.lock",
        "package-lock.json",
        ".docusaurus/*",
        "build/*",
        ".DS_Store",
        "node_modules/*",
        "*.log",
    ]
    ignore_args = " ".join(f":(exclude){pattern}" for pattern in ignore_patterns)

    try:
        staged_diff = subprocess.check_output(
            f"git diff --staged -- . {ignore_args}", shell=True, text=True, encoding="utf8"
        )
        unstaged_diff = subprocess.check_output(
            f"git diff -- . {ignore_args}", shell=True, text=True, encoding="utf8"
        )
        return staged_diff + unstaged_diff
    except subprocess.CalledProcessError as e:
        logging.error(f"获取 git diff 失败: {e}")
        sys.exit(1)


def generate_commit_message(diff: str) -> CommitMessage | None:
    system_prompt = PARAMETER_EXTRACTOR_SYSTEM_PROMPT.format(instructions=COMMITS_GENERATOR_SYSTEM_PROMPT)
    few_shot_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",
         "content": '### Structure\nHere is the structure of the JSON object, you should always follow the structure.\n<structure>\n{"type": "object", "properties": {"location": {"type": "string", "description": "The location to get the weather information", "required": true}}, "required": ["location"]}\n</structure>\n\n### Text to be converted to JSON\nInside <text></text> XML tags, there is a text that you should convert to a JSON object.\n<text>\nWhat is the weather today in SF?\n</text>\n'},
        {"role": "assistant", "content": '{"location": "San Francisco"}'},
        {"role": 'user',
         'content': '### Structure\nHere is the structure of the JSON object, you should always follow the structure.\n<structure>\n{"type": "object", "properties": {"food": {"type": "string", "description": "The food to eat", "required": true}}, "required": ["food"]}\n</structure>\n\n### Text to be converted to JSON\nInside <text></text> XML tags, there is a text that you should convert to a JSON object.\n<text>\nI want to eat some apple pie.\n</text>\n'},
        {"role": "assistant", "content": '{"result": "apple pie"}'},
    ]

    parameters_structure = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": '生成commit标题：\n- 撰写一个简洁的英文 commit 标题，概括此次变更的主要目的。\n- 标题应该清晰明了，不超过50个字符。\n- 使用动词开头，简要说明此次提交的主要行为。',
            },
            "summary": {
                "type": "array",
                "items": {"type": "string"},
                "description": '生成变更摘要：\n- 用中文编写一个结构化的变更摘要，列出主要的修改点。\n- 使用无序列表格式（以"-"开头）来组织各个要点。\n- 每个要点应该简洁明了，突出重要的变更内容。\n- 如果有多个文件的变更，可以按文件分组列出变更点。',
            },
        },
        "required": ["title", "summary"],
    }
    parameters_text = diff
    parameters_query = PARAMETERS_TEMPLATE.format(structure=parameters_structure, text=parameters_text)

    active_task = [{"role": "user", "content": parameters_query}]

    messages = few_shot_messages + active_task

    payload = {
        "model": "Qwen/QwQ-32B",
        "messages": messages,
        "temperature": 0,
        "max_tokens": 3000
    }

    conn = http.client.HTTPConnection(host=OPENAI_CONNECTION_HOST, port=OPENAI_CONNECTION_PORT)

    try:
        conn.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps(payload),
            headers={"Authorization": f"Bearer apikey", "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response_data = json.loads(response.read().decode("utf-8"))
        data = json.loads(response_data["choices"][0]["message"]["content"])
        return CommitMessage(**data)
    except Exception as e:
        logging.error(str(e))
    finally:
        conn.close()


def git_commit_and_push(commit_message: CommitMessage):
    title = commit_message.title
    summary_text = commit_message.summary_text

    # 获取当前分支名
    current_branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, encoding="utf8"
    ).strip()

    try:
        if IS_DRY_RUN:
            print("\n=== 预览模式 (--dry-run) ===")
            print("以下操作不会真正执行:\n")
            print("git add .")
            print(f'git commit -m "{title}" -m "{summary_text}"')
            print(f"git push origin {current_branch}\n")  # 使用当前分支
            print("生成的提交信息:")
            print("标题:", title)
            print(f"摘要:\n{summary_text}")
            return

        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", title, "-m", summary_text], check=True)
        # 推送到当前分支而不是 main
        subprocess.run(["git", "push", "origin", current_branch], check=True)

        logging.info("成功提交并推送变更！")
        logging.info(f"提交标题: {title}")
        logging.info(f"变更摘要:\n{summary_text}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git操作失败: {e}")
        raise


def main():
    try:
        diff = get_git_diff()

        if not diff.strip():
            logging.info("没有检测到变更")
            return

        commit_message = generate_commit_message(diff)
        git_commit_and_push(commit_message)
    except Exception as e:
        logging.error(f"执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    IS_DRY_RUN = "--dry-run" in sys.argv
    main()
