import logging
from unittest.mock import MagicMock

import pytest
from notion.collection import CollectionRowBlock

from enex2notion.cli import cli
from enex2notion.enex_types import EvernoteNote
from enex2notion.enex_uploader import clear_page_children, remove_note_page
from enex2notion.utils_exceptions import NoteUploadFailException


@pytest.fixture()
def mock_api(mocker):
    return {
        "get_import_root": mocker.patch("enex2notion.cli_notion.get_import_root"),
        "get_notion_client": mocker.patch("enex2notion.cli_notion.get_notion_client"),
        "get_notebook_page": mocker.patch("enex2notion.cli_upload.get_notebook_page"),
        "create_note_page": mocker.patch("enex2notion.cli_upload.create_note_page"),
        "upload_note_blocks": mocker.patch("enex2notion.cli_upload.upload_note_blocks"),
        "remove_note_page": mocker.patch("enex2notion.cli_upload.remove_note_page"),
        "clear_page_children": mocker.patch(
            "enex2notion.cli_upload.clear_page_children"
        ),
        "parse_note": mocker.patch("enex2notion.cli_upload.parse_note"),
    }


@pytest.fixture()
def fake_note_factory(mocker):
    mock_count = mocker.patch("enex2notion.cli_upload.count_notes")
    mock_iter = mocker.patch("enex2notion.cli_upload.iter_notes")
    mock_iter.return_value = [mocker.MagicMock(note_hash="fake_hash", is_webclip=False)]
    mock_count.side_effect = lambda x: len(mock_iter.return_value)

    return mock_iter


def test_page_created_once_across_retries(mock_api, fake_note_factory, mocker):
    """Block upload fails twice then succeeds; page should be created exactly once."""
    mock_api["upload_note_blocks"].side_effect = [Exception, Exception, None]

    cli(["--token", "fake_token", "--mode", "PAGE", "fake.enex"])

    assert mock_api["create_note_page"].call_count == 1
    assert mock_api["upload_note_blocks"].call_count == 3


def test_page_creation_retried_on_failure(mock_api, fake_note_factory, mocker):
    """Page creation fails once then succeeds; should be called twice."""
    mock_api["create_note_page"].side_effect = [
        Exception("transient"),
        mocker.MagicMock(),
    ]

    cli(["--token", "fake_token", "--mode", "PAGE", "fake.enex"])

    assert mock_api["create_note_page"].call_count == 2
    assert mock_api["upload_note_blocks"].call_count == 1


def test_children_cleared_before_retry(mock_api, fake_note_factory, mocker):
    """Block upload fails once then succeeds; children should be cleared before second attempt."""
    mock_api["upload_note_blocks"].side_effect = [Exception, None]

    cli(["--token", "fake_token", "--mode", "PAGE", "fake.enex"])

    assert mock_api["clear_page_children"].call_count == 1
    assert mock_api["upload_note_blocks"].call_count == 2


def test_keep_failed_leaves_one_page(mock_api, fake_note_factory, mocker, caplog):
    """Retries exhausted with --keep-failed: one page kept with [UNFINISHED UPLOAD] title."""
    page = mocker.MagicMock()
    mock_api["create_note_page"].return_value = page
    mock_api["upload_note_blocks"].side_effect = [Exception] * 5

    with pytest.raises(NoteUploadFailException):
        cli(["--token", "fake_token", "--mode", "PAGE", "--keep-failed", "fake.enex"])

    mock_api["remove_note_page"].assert_called_once_with(mocker.ANY, True)
    assert mock_api["create_note_page"].call_count == 1
    assert "[UNFINISHED UPLOAD]" in page.title_plaintext


def test_no_keep_failed_removes_page(mock_api, fake_note_factory, mocker):
    """Retries exhausted without --keep-failed: page is removed."""
    mock_api["upload_note_blocks"].side_effect = [Exception] * 5

    with pytest.raises(NoteUploadFailException):
        cli(["--token", "fake_token", "--mode", "PAGE", "fake.enex"])

    mock_api["remove_note_page"].assert_called_once_with(mocker.ANY, False)
    assert mock_api["create_note_page"].call_count == 1


def test_page_created_once_db_mode(mock_api, fake_note_factory, mocker):
    """DB mode: block upload fails twice then succeeds; page created exactly once."""
    mocker.patch("enex2notion.cli_upload.get_notebook_page")
    mock_api["get_notebook_database"] = mocker.patch(
        "enex2notion.cli_upload.get_notebook_database"
    )
    mock_api["upload_note_blocks"].side_effect = [Exception, Exception, None]

    cli(["--token", "fake_token", "--mode", "DB", "fake.enex"])

    assert mock_api["create_note_page"].call_count == 1
    assert mock_api["upload_note_blocks"].call_count == 3


def test_keep_failed_db_mode(mock_api, fake_note_factory, mocker):
    """DB mode: retries exhausted with --keep-failed; remove_note_page called with True."""
    mocker.patch("enex2notion.cli_upload.get_notebook_page")
    mock_api["get_notebook_database"] = mocker.patch(
        "enex2notion.cli_upload.get_notebook_database"
    )
    mock_api["upload_note_blocks"].side_effect = [Exception] * 5

    with pytest.raises(NoteUploadFailException):
        cli(["--token", "fake_token", "--mode", "DB", "--keep-failed", "fake.enex"])

    mock_api["remove_note_page"].assert_called_once_with(mocker.ANY, True)
    assert mock_api["create_note_page"].call_count == 1


def test_keep_failed_resets_title_after_rename(mock_api, fake_note_factory, mocker):
    """If last attempt renamed page before failing, --keep-failed still resets to UNFINISHED."""
    page = mocker.MagicMock()
    page.title_plaintext = "Already Renamed"
    mock_api["create_note_page"].return_value = page
    mock_api["upload_note_blocks"].side_effect = [Exception] * 5

    with pytest.raises(NoteUploadFailException):
        cli(["--token", "fake_token", "--mode", "PAGE", "--keep-failed", "fake.enex"])

    assert "[UNFINISHED UPLOAD]" in page.title_plaintext


def test_cleanup_failure_does_not_mask_upload_error(
    mock_api, fake_note_factory, mocker, caplog
):
    """If remove_note_page fails, the original NoteUploadFailException still propagates."""
    mock_api["upload_note_blocks"].side_effect = [Exception] * 5
    mock_api["remove_note_page"].side_effect = Exception("cleanup failed")

    with caplog.at_level(logging.WARNING, logger="enex2notion"):
        with pytest.raises(NoteUploadFailException):
            cli(["--token", "fake_token", "--mode", "PAGE", "fake.enex"])

    assert "Failed to clean up page" in caplog.text


# --- State-based unit tests for extracted helpers ---


def _make_fake_note(title="test"):
    return EvernoteNote(
        title=title,
        created=None,
        updated=None,
        content="",
        tags=[],
        author="",
        url="",
        is_webclip=False,
        resources=[],
    )


def test_remove_note_page_keep_failed_does_nothing():
    page = MagicMock()
    remove_note_page(page, keep_failed=True)
    page.remove.assert_not_called()


def test_remove_note_page_normal_page():
    page = MagicMock(spec=[])
    page.remove = MagicMock()
    remove_note_page(page, keep_failed=False)
    page.remove.assert_called_once_with(permanently=True)


def test_remove_note_page_collection_row():
    page = MagicMock(spec=CollectionRowBlock)
    remove_note_page(page, keep_failed=False)
    page.remove.assert_called_once_with()


def test_clear_page_children_resets_title_and_removes_children():
    child1 = MagicMock()
    child2 = MagicMock()
    page = MagicMock()
    page.children = [child1, child2]
    note = _make_fake_note("My Note")

    clear_page_children(page, note)

    assert page.title_plaintext == "My Note [UNFINISHED UPLOAD]"
    child1.remove.assert_called_once_with(permanently=True)
    child2.remove.assert_called_once_with(permanently=True)


def test_clear_page_children_empty_page():
    page = MagicMock()
    page.children = []
    note = _make_fake_note("Empty")

    clear_page_children(page, note)

    assert page.title_plaintext == "Empty [UNFINISHED UPLOAD]"
