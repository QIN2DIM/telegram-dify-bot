import asyncio
import fnmatch
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Dict

from loguru import logger
from pydantic import BaseModel, Field

# Add a project path to avoid module import issues
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from settings import LOG_DIR
from utils import init_log
from dify.workflow_tool import invoke_commit_message_generation

init_log(
    runtime=LOG_DIR.joinpath("runtime.log"),
    error=LOG_DIR.joinpath("error.log"),
    serialize=LOG_DIR.joinpath("serialize.log"),
)


USER_PROMPT_TEMPLATE = """
Generate a git commit message for the following changes.

## Git Branch Name:
{branch_name}

## Staged Changes (git diff --staged):
```diff
{diff_content}
```

## Your Task:
Provide the commit message as a single JSON object, following the rules and format specified in the system instructions. Do not add any text before or after the JSON object.
"""

# 上下文最大长度（字符数），16k ~= 16384
MAX_CONTEXT_LENGTH = 16384

# 特殊文件处理规则
SPECIAL_FILE_HANDLERS = {
    ".ipynb": "Summarized notebook changes.",
    "package-lock.json": "Updated dependencies.",
    "pnpm-lock.yaml": "Updated dependencies.",
    "yarn.lock": "Updated dependencies.",
    "poetry.lock": "Updated dependencies.",
}


class LLMInput(BaseModel):
    """Model for data passed to the LLM generation module."""

    git_branch_name: str = Field(...)
    diff_content: str = Field(..., description="Formatted and potentially compressed git diff.")
    full_diff_for_reference: str | None = Field(
        default=None, description="The full, uncompressed diff."
    )


class CommitMessage(BaseModel):
    """Structured output for the generated commit message."""

    type: str = Field(..., description="Commit type (e.g., 'feat', 'fix').")
    scope: str | None = Field(default=None, description="Optional scope of the changes.")
    title: str = Field(..., description="Short, imperative-mood title.")
    body: str | None = Field(default=None, description="Detailed explanation of the changes.")
    footer: str | None = Field(default=None, description="Footer for issues or breaking changes.")

    def to_git_message(self) -> str:
        """Formats the object into a git-commit-ready string."""
        header = f"{self.type}"
        if self.scope:
            header += f"({self.scope})"
        header += f": {self.title}"

        message_parts = [header]
        if self.body:
            message_parts.append(f"\n{self.body}")
        if self.footer:
            message_parts.append(f"\n{self.footer}")

        return "\n".join(message_parts)


class GitCommitGenerator:
    """A class to generate git commit messages."""

    def __init__(self, max_context: int = MAX_CONTEXT_LENGTH):
        """
        Initializes the generator. Automatically finds the git repository root.
        """
        # 关键修改：自动发现 Git 仓库的根目录
        self.repo_path = self._find_git_root()
        self.max_context = max_context

        logger.debug(f"GitCommitGenerator initialized for repository: {self.repo_path}")

    @staticmethod
    def _find_git_root() -> Path:
        """
        Finds the root directory of the git repository using `git rev-parse --show-toplevel`.
        This allows the script to be run from any subdirectory of the repository.
        """
        try:
            # 这是查找仓库根目录的标准、可靠方法
            git_root_str = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.PIPE
            ).strip()
            return Path(git_root_str)
        except subprocess.CalledProcessError:
            # 如果此命令失败，说明当前目录或其父目录都不是 Git 仓库
            logger.error("Fatal: Not a git repository (or any of the parent directories).")
            raise ValueError("This script must be run from within a Git repository.")

    @staticmethod
    def _is_ignored(file_path: str, ignore_patterns: List[str]) -> bool:
        """Check if a file path matches any ignore pattern."""
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    @staticmethod
    def _call_llm_api(llm_input: LLMInput) -> CommitMessage | None:
        """
        调用 Dify Workflow 中的快捷指令，跳过意图识别触发特性分支。
        Args:
            llm_input:

        Returns:

        """
        logger.debug("Invoke commit_message_generation tool.")

        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                invoke_commit_message_generation(
                    user_prompt=USER_PROMPT_TEMPLATE.format(
                        branch_name=llm_input.git_branch_name, diff_content=llm_input.diff_content
                    )
                )
            )
        finally:
            loop.close()

        if not (answer := result.data.outputs.answer):
            return
        if not isinstance(answer, dict):
            return

        return CommitMessage(
            type=answer.get("type", ""),
            scope=answer.get("scope", ""),
            title=answer.get("title", ""),
            body=answer.get("body", ""),
            footer=answer.get("footer", ""),
        )

    def _run_command(self, command: List[str], input_: Optional[str] = None) -> str:
        """
        Runs a command, optionally passing stdin, and returns its stdout.

        Args:
            command: The command to run as a list of strings.
            input_: Optional string to be passed as standard input to the command.

        Returns:
            The stdout of the command as a string.
        """
        try:
            # 所有 git 命令都将在正确的 repo_path 下执行
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf8",
                input=input_,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Command '{' '.join(command)}' failed with error:\n{e.stderr}")
            raise

    def _get_ignore_patterns(self) -> List[str]:
        """Reads .gitignore and .dockerignore and returns a list of patterns."""
        patterns = []
        for ignore_file in [".gitignore", ".dockerignore"]:
            path = self.repo_path / ignore_file
            if path.exists():
                logger.debug(f"Reading ignore patterns from '{path}'")
                with open(path, "r", encoding="utf8") as f:
                    patterns.extend(
                        line.strip() for line in f if line.strip() and not line.startswith("#")
                    )
        return patterns

    def _collect_changes(self) -> str:
        """
        Collects unstaged changes from the working directory by running `git diff`.
        This mirrors the "Changes" view in GitHub Desktop.
        """
        logger.debug("Collecting unstaged changes from the working directory (using 'git diff')...")

        # 关键修改：使用 'git diff' 来扫描工作区，而不是 'git diff --staged'
        diff_output = self._run_command(["git", "diff"])

        if not diff_output:
            logger.warning("No unstaged changes found in the working directory.")
            return ""

        ignore_patterns = self._get_ignore_patterns()

        # Split diff output by file (这个解析逻辑对 'git diff' 同样有效)
        file_diffs = re.split(r'diff --git a/.* b/(.*)', diff_output)

        filtered_diffs = []
        if len(file_diffs) > 1:
            for i in range(1, len(file_diffs), 2):
                file_path = file_diffs[i].strip()
                diff_content = file_diffs[i + 1]

                if self._is_ignored(file_path, ignore_patterns):
                    logger.debug(f"Ignoring file specified in ignore list: {file_path}")
                    continue

                header = f"diff --git a/{file_path} b/{file_path}"
                filtered_diffs.append(header + diff_content)

        if not filtered_diffs:
            logger.warning("All changes were on ignored files. No changes to commit.")
            return ""

        logger.success(
            f"Collected diffs for {len(filtered_diffs)} files from the working directory."
        )
        return "\n".join(filtered_diffs)

    def _compress_context(self, diff_content: str) -> str:
        """Compresses the diff content if it exceeds the max length."""
        if len(diff_content) <= self.max_context:
            return diff_content

        logger.warning(
            f"Diff content ({len(diff_content)} chars) exceeds max context length ({self.max_context}). Compressing..."
        )

        file_diffs = re.split(r'(diff --git .*)', diff_content)
        if file_diffs[0] == '':
            file_diffs = file_diffs[1:]

        compressed_diffs: Dict[str, str] = {}
        total_len = 0

        # First, process special files and small files
        file_summaries: List[Dict] = []
        for i in range(0, len(file_diffs), 2):
            header = file_diffs[i]
            content = file_diffs[i + 1]
            match = re.search(r'b/(.*)', header)
            if not match:
                continue

            file_path = match.group(1).strip()

            file_summaries.append(
                {
                    "path": file_path,
                    "header": header,
                    "content": content,
                    "len": len(header) + len(content),
                    "is_special": any(file_path.endswith(ext) for ext in SPECIAL_FILE_HANDLERS),
                }
            )

        # Sort: special files first, then by length (smallest first)
        file_summaries.sort(key=lambda x: (not x['is_special'], x['len']))

        final_diff_parts = []
        files_summarized = []

        for summary in file_summaries:
            file_path = summary['path']

            # Special file handling (e.g., .ipynb, lock files)
            for ext, message in SPECIAL_FILE_HANDLERS.items():
                if file_path.endswith(ext):
                    summary_line = f"--- Summary for {file_path} ---\n{message}\n"
                    if total_len + len(summary_line) <= self.max_context:
                        final_diff_parts.append(summary_line)
                        total_len += len(summary_line)
                    else:
                        files_summarized.append(
                            f"- {file_path} (special file, not included due to size)"
                        )
                    break
            else:  # Not a special file
                diff_part = summary['header'] + summary['content']
                if total_len + len(diff_part) <= self.max_context:
                    final_diff_parts.append(diff_part)
                    total_len += len(diff_part)
                else:
                    files_summarized.append(f"- {file_path} (content truncated due to size)")

        if files_summarized:
            summary_header = (
                "\n--- The following files had large diffs and were summarized or omitted ---\n"
            )
            final_diff_parts.append(summary_header + "\n".join(files_summarized))

        compressed_output = "".join(final_diff_parts)
        logger.success(
            f"Compressed diff from {len(diff_content)} to {len(compressed_output)} chars."
        )
        return compressed_output

    def _generate_prompt_data(self) -> LLMInput | None:
        """Generates the input data for the LLM."""
        branch_name = self._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        full_diff = self._collect_changes()

        if not full_diff:
            return

        compressed_diff = self._compress_context(full_diff)

        return LLMInput(
            git_branch_name=branch_name,
            diff_content=compressed_diff,
            full_diff_for_reference=full_diff,
        )

    def _apply_commit(self, commit_message: CommitMessage):
        """
        Stages all changes from the working directory and then applies the commit.
        This ensures the committed files match what the LLM analyzed.
        """
        message_str = commit_message.to_git_message()
        logger.debug(f"Applying git commit with message:\n---\n{message_str}\n---")

        try:
            # 关键修改：在提交前，暂存所有工作区的变更 (等同于 GitHub Desktop 的操作)
            logger.debug("Staging all changes from the working directory ('git add .')...")
            self._run_command(["git", "add", "."])

            # 使用 -F - 从标准输入读取多行消息进行提交
            self._run_command(["git", "commit", "-F", "-"], input_=message_str)
            logger.success("Commit applied successfully!")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to apply commit. Git output:\n{e.stdout}\n{e.stderr}")

    def run(self):
        """Main execution flow."""
        try:
            # 1. Generate prompt data (includes collecting and compressing changes)
            if not (llm_input := self._generate_prompt_data()):
                logger.warning("No changes to commit. Exiting.")
                return

            # 2. Call LLM to get a structured commit message
            if not (commit_message_obj := self._call_llm_api(llm_input)):
                logger.error("Failed to generate commit message.")
                return

            # 3. Apply the commit
            self._apply_commit(commit_message_obj)

        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")


def main():
    # 检查是否在 git 仓库中
    if not Path(".git").is_dir():
        logger.error("This script must be run from the root of a Git repository.")
    else:
        generator = GitCommitGenerator()
        generator.run()


if __name__ == "__main__":
    main()
