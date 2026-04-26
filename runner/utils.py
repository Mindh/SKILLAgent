# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_file(path: str) -> str:
    with open(os.path.join(BASE_DIR, path), "r", encoding="utf-8") as f:
        return f.read()


_FILE_CACHE: dict = {}


def cached_file(path: str) -> str:
    if path not in _FILE_CACHE:
        _FILE_CACHE[path] = load_file(path)
    return _FILE_CACHE[path]


def log(message: str):
    print(f"[RUN] {message}")
