import os


def shorten_path(path, keep_parts=2):
    parts = [part for part in path.split(os.sep) if part]
    if len(parts) <= keep_parts:
        return path
    return "..." + os.sep + os.sep.join(parts[-keep_parts:])
