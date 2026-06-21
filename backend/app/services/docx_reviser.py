from __future__ import annotations


def clear_container_content(container) -> None:
    element = container._element
    for child in list(element):
        if child.tag.endswith("}p") or child.tag.endswith("}tbl"):
            element.remove(child)
