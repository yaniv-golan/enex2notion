import logging

from enex2notion.enex_types import EvernoteNote
from enex2notion.notion_blocks.text import NotionTextBlock, TextProp
from enex2notion.notion_blocks.uploadable import NotionUploadableBlock

logger = logging.getLogger(__name__)


def resolve_resources(note_blocks, note: EvernoteNote):
    for i, block in enumerate(note_blocks):
        # Resolve resource hash to actual resource
        if isinstance(block, NotionUploadableBlock) and block.resource is None:
            block.resource = note.resource_by_md5(block.md5_hash)

            if block.resource is None:
                logger.warning(
                    f"Missing resource in '{note.title}'"
                    f" (hash: {block.md5_hash})"
                )
                note_blocks[i] = NotionTextBlock(
                    TextProp(
                        f"[Missing resource: hash {block.md5_hash}"
                        f" — not included in ENEX export]"
                    )
                )
                continue
        if block.children:
            resolve_resources(block.children, note)
