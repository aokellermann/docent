"""
Tools for string manipulation and file editing.
* State is persistent across command calls and discussions with the user
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>` 
* The `undo_edit` command will revert the last edit made to the file at `path


"insert_line": {
    "description": "Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`.",
    "type": "integer"
},
"path": {
    "description": "Absolute path to file or directory, e.g. `/repo/file.py` or `/repo`.",
    "type": "string"
},

TODO(vincent): never implemented undo_edit, but sonnet seems to never use it anyway
"""


from inspect_ai.util import sandbox as sandbox_env

from inspect_ai.tool._tool import Tool, tool
from inspect_ai.tool._tools._execute import code_viewer

from pathlib import Path

MAX_RESPONSE_LEN: int = 200000

SNIPPET_LINES = 4

TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>"

def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN):
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


def _make_output(
    file_content: str,
    file_descriptor: str,
    total_lines: int,
    init_line: int = 1,
) -> str:
    """Generate output for the CLI based on the content of a file."""
    file_content = maybe_truncate(file_content)
    file_content = "\n".join(
        [
            f"{i + init_line:6}\t{line}"
            for i, line in enumerate(file_content.split("\n"))
        ]
    )
    return (
        f"Here's the result of running `cat -n` on {file_descriptor}:\n"
        + file_content
        + "\n"
        + f"Total lines in file: {total_lines}\n"
    )


@tool(viewer=code_viewer("view", "path", ["view_range"]))
def view(
    timeout: int | None = None, user: str | None = None, sandbox: str | None = None
) -> Tool:
    """View a file or directory.
    """

    async def execute(path: str, view_range: list[int] | None = None) -> str:
        """
        Use this function to view a file or directory. If `path` is a file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep

        Args:
          path (str): The path to the file or directory to view.
          view_range (list[int] | None): The range of lines to view. If None, the full file is shown. Can only be used if `path` is a file.

        Returns:
          The contents of the file or directory.
        """
        if Path(path).is_dir():
            if view_range:
                return "ERROR: The `view_range` parameter is not allowed when `path` points to a directory."
            cmd = ["find", path, "-maxdepth", "2", "-not", "-path", "'*/\\.*'"]
            result = await sandbox_env(sandbox).exec(
                cmd=cmd, timeout=timeout, user=user
            )
            if result.stderr:
                return f"{result.stderr}\n"
            return f"{result.stdout}"
        else:
            cmd = ["cat", path]
            result = await sandbox_env(sandbox).exec(
                cmd=cmd, timeout=timeout, user=user
            )
            if result.stderr:
                return f"{result.stderr}\n"
            file_content = result.stdout
            lines = file_content.split("\n")
            if view_range:
                if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
                    return "ERROR: The `view_range` parameter must be a list of two integers."
                n_lines_file = len(lines)
                init_line, final_line = view_range
                if init_line < 1 or init_line > n_lines_file:
                    return f"ERROR: Invalid `view_range`: {view_range}. Its first element `{init_line}` should be within the range of lines of the file: {[1, n_lines_file]}"
                if final_line > n_lines_file:
                    return f"ERROR: Invalid `view_range`: {view_range}. Its second element `{final_line}` should be smaller than the number of lines in the file: `{n_lines_file}`"
                if final_line != -1 and final_line < init_line:
                    return f"ERROR: Invalid `view_range`: {view_range}. Its second element `{final_line}` should be larger or equal than its first `{init_line}`"
                if final_line == -1:
                    file_content = "\n".join(lines[init_line - 1 :])
                else:
                    file_content = "\n".join(lines[init_line - 1 : final_line])
            return _make_output(
                file_content=file_content,
                file_descriptor=path,
                total_lines=len(lines),
                init_line=1 if view_range is None else view_range[0],
            )

    return execute

@tool(viewer=code_viewer("create", "file_text", ["path"]))
def create(
    timeout: int | None = None, user: str | None = None, sandbox: str | None = None
) -> Tool:
    """Create a file.
    """
    async def execute(path: str, file_text: str) -> str:
        """
        Use this function to create a file with some text. Fails if the file already exists.

        Args:
          path (str): The path to the file to create.
          file_text (str): The text to write to the file.

        Returns:
          A message indicating that the file has been created.
        """
        # check if the path exists in the sandbox first. if yes, return an error
        if not (await sandbox_env(sandbox).exec(cmd=["ls", path], timeout=timeout, user=user)).stderr:
            return f"File {path} already exists."
        await sandbox_env(sandbox).write_file(path, file_text)
        return f"File {path} created successfully."

    return execute


@tool(viewer=code_viewer("str_replace", "new_str", ["old_str", "path"]))
def str_replace(
    timeout: int | None = None, user: str | None = None, sandbox: str | None = None
) -> Tool:
    """Replace a string in a file.
    """
    async def execute(path: str, old_str: str, new_str: str) -> str:
        """
        Use this function to replace a string in a file.

        Notes for using the `str_replace` command:
        * The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!
        * If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique
        * The `new_str` parameter should contain the edited lines that should replace the `old_str`"

        Args:
          path (str): The path to the file to replace the string in.
          old_str (str): The string to replace.
          new_str (str): The string to replace the old_str with.

        Returns:
          A message indicating that the string has been replaced.
        """

        content = await sandbox_env(sandbox).read_file(path)

        if not old_str.strip():
            if content.strip():
                return f"ERROR: No replacement was performed, old_str is empty which is only allowed when the file is empty. The file {path} is not empty."
            else:
                # replace the whole file with new_str
                new_content = new_str
                await sandbox_env(sandbox).write_file(path, new_content)
                # Prepare the success message
                success_msg = f"The file {path} has been edited. "
                success_msg += _make_output(
                    file_content=new_content,
                    file_descriptor=path,
                    total_lines=len(new_content.split("\n")),
                )
                success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

                return success_msg

        occurrences = content.count(old_str)

        if occurrences == 0:
            return f"ERROR: No replacement was performed, old_str \n ```\n{old_str}\n```\n did not appear verbatim in {path}."
        elif occurrences > 1:
            file_content_lines = content.split("\n")
            lines = [
                idx + 1
                for idx, line in enumerate(file_content_lines)
                if old_str in line
            ]
            return f"ERROR: No replacement was performed. Multiple occurrences of old_str \n ```\n{old_str}\n```\n in lines {lines}. Please ensure it is unique"

        new_content = content.replace(old_str, new_str)
        await sandbox_env(sandbox).write_file(path, new_content)

        # Create a snippet of the edited section
        replacement_line = content.split(old_str)[0].count("\n")
        start_line = max(0, replacement_line - SNIPPET_LINES)
        end_line = replacement_line + SNIPPET_LINES + new_str.count("\n")
        snippet = "\n".join(new_content.split("\n")[start_line : end_line + 1])

        # Prepare the success message
        success_msg = f"The file {path} has been edited. "
        success_msg += _make_output(
            file_content=snippet,
            file_descriptor=path,
            total_lines=len(new_content.split("\n")),
            init_line=start_line + 1,
        )
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return success_msg

    return execute


@tool(viewer=code_viewer("insert", "new_str", ["insert_line", "path"]))
def insert(
    timeout: int | None = None, user: str | None = None, sandbox: str | None = None
) -> Tool:
    """Insert a string into a file.
    """
    async def execute(path: str, insert_line: int, new_str: str) -> str:
        """Inserts new_str AFTER the specified line in the file content.

        Args:
          path (str): The path to the file to insert the string into.
          insert_line (int): The line to insert the string after.
          new_str (str): The string to insert.

        Returns:
          A message indicating that the string has been inserted.
        """
        file_text = await sandbox_env(sandbox).read_file(path)
        file_text_lines = file_text.split("\n")
        n_lines_file = len(file_text_lines)

        if insert_line < 0 or insert_line > n_lines_file:
            return f"ERROR: Invalid `insert_line` parameter: {insert_line}. It should be within the range of lines of the file: {[0, n_lines_file]}"

        new_str_lines = new_str.split("\n")
        new_file_text_lines = (
            file_text_lines[:insert_line]
            + new_str_lines
            + file_text_lines[insert_line:]
        )
        snippet_lines = (
            file_text_lines[max(0, insert_line - SNIPPET_LINES) : insert_line]
            + new_str_lines
            + file_text_lines[insert_line : insert_line + SNIPPET_LINES]
        )

        new_file_text = "\n".join(new_file_text_lines)
        snippet = "\n".join(snippet_lines)

        await sandbox_env(sandbox).write_file(path, new_file_text)

        success_msg = f"The file {path} has been edited. "
        success_msg += _make_output(
            file_content=snippet,
            file_descriptor=path,
            total_lines=len(new_file_text_lines),
            init_line=max(1, insert_line - SNIPPET_LINES + 1),
        )
        success_msg += "Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."

        return success_msg
    return execute
