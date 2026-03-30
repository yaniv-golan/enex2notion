import logging

from notion.block import CollectionViewPageBlock, PageBlock
from notion.collection import CollectionRowBlock
from notion.operations import build_operation
from tqdm import tqdm

from enex2notion.enex_types import EvernoteNote
from enex2notion.enex_uploader_block import upload_block
from enex2notion.utils_exceptions import NoteUploadFailException

logger = logging.getLogger(__name__)

PROGRESS_BAR_WIDTH = 80


def upload_note(root, note: EvernoteNote, note_blocks, keep_failed):
    """Compatibility wrapper — creates page, uploads blocks, cleans up on failure."""
    try:
        new_page = create_note_page(root, note)
        try:
            upload_note_blocks(new_page, note, note_blocks)
        except Exception:
            remove_note_page(new_page, keep_failed)
            raise
    except Exception as e:
        raise NoteUploadFailException from e


def create_note_page(root, note: EvernoteNote):
    tmp_name = f"{note.title} [UNFINISHED UPLOAD]"

    logger.debug(f"Creating new page for note '{note.title}'")

    return (
        root.collection.add_row(
            title=tmp_name,
            url=note.url,
            tags=note.tags,
            created=note.created,
        )
        if isinstance(root, CollectionViewPageBlock)
        else root.children.add_new(PageBlock, title_plaintext=tmp_name)
    )


def upload_note_blocks(page, note: EvernoteNote, note_blocks):
    progress_iter = tqdm(
        iterable=note_blocks, unit="block", leave=False, ncols=PROGRESS_BAR_WIDTH
    )

    for block in progress_iter:
        upload_block(page, block)

    # Set proper name after everything is uploaded
    page.title_plaintext = note.title

    _update_edit_time(page, note.updated)


def remove_note_page(page, keep_failed):
    if keep_failed:
        return

    if isinstance(page, CollectionRowBlock):
        page.remove()
    else:
        page.remove(permanently=True)


def clear_page_children(page, note: EvernoteNote):
    page.title_plaintext = f"{note.title} [UNFINISHED UPLOAD]"

    for child in list(page.children):
        child.remove(permanently=True)


def _update_edit_time(page, date):
    page._client.submit_transaction(  # noqa: WPS437
        build_operation(
            id=page.id,
            path="last_edited_time",
            args=int(date.timestamp() * 1000),
            table=page._table,  # noqa: WPS437
        ),
        update_last_edited=False,
    )
