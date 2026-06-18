"""Tests for Supabase client wrapper."""

from unittest.mock import MagicMock, patch

import pytest
from postgrest.exceptions import APIError

from src.config import settings
from src.supabase_client import SupabaseGeocodeClient, get_supabase_client


@pytest.fixture
def mock_supabase():
    """Return a mock Supabase client with chainable table operations."""
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table

    select = MagicMock()
    table.select.return_value = select

    eq = MagicMock()
    select.eq.return_value = eq

    order = MagicMock()
    eq.order.return_value = order

    range_op = MagicMock()
    order.range.return_value = range_op

    upsert = MagicMock()
    table.upsert.return_value = upsert

    client._table_chain = {
        "table": table,
        "select": select,
        "eq": eq,
        "order": order,
        "range": range_op,
        "upsert": upsert,
    }
    return client


class TestGetSupabaseClient:
    def test_raises_when_not_configured(self):
        with (
            patch.object(settings, "supabase_url", ""),
            patch.object(settings, "supabase_key", ""),
            patch.object(settings, "supabase_service_role_key", ""),
            pytest.raises(ValueError, match="SUPABASE_URL and SUPABASE_KEY"),
        ):
            get_supabase_client()

    def test_creates_client_with_timeout(self):
        with (
            patch.object(settings, "supabase_url", "https://test.supabase.co"),
            patch.object(settings, "supabase_key", "test-key"),
            patch.object(settings, "supabase_timeout", 42),
            patch("src.supabase_client.create_client") as mock_create,
        ):
            get_supabase_client()
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert kwargs["options"].httpx_client is not None


class TestFetchPending:
    def test_single_page(self, mock_supabase):
        mock_supabase._table_chain["range"].execute.return_value = MagicMock(
            data=[{"id": "1", "input_address": "a1"}],
        )
        client = SupabaseGeocodeClient(mock_supabase)
        rows = client.fetch_pending()

        assert len(rows) == 1
        assert rows[0]["id"] == "1"
        mock_supabase._table_chain["range"].execute.assert_called_once()

    def test_pagination(self, mock_supabase):
        call_count = 0
        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(data=[{"id": str(i)} for i in range(500)])
            return MagicMock(data=[{"id": "500"}])

        mock_supabase._table_chain["range"].execute.side_effect = side_effect
        with patch.object(settings, "supabase_fetch_chunk", 500):
            client = SupabaseGeocodeClient(mock_supabase)
            rows = client.fetch_pending()

        assert len(rows) == 501
        assert mock_supabase._table_chain["range"].execute.call_count == 2

    def test_respects_limit(self, mock_supabase):
        mock_supabase._table_chain["range"].execute.return_value = MagicMock(
            data=[{"id": str(i)} for i in range(100)],
        )
        client = SupabaseGeocodeClient(mock_supabase)
        rows = client.fetch_pending(limit=10)

        assert len(rows) == 10

    def test_empty_result(self, mock_supabase):
        mock_supabase._table_chain["range"].execute.return_value = MagicMock(data=[])
        client = SupabaseGeocodeClient(mock_supabase)
        rows = client.fetch_pending()

        assert rows == []


class TestMarkProcessing:
    def test_marks_ids(self, mock_supabase):
        mock_supabase._table_chain["upsert"].execute.return_value = MagicMock()
        client = SupabaseGeocodeClient(mock_supabase)
        client.mark_processing(["id1", "id2"])

        mock_supabase._table_chain["upsert"].execute.assert_called_once()
        payload = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert len(payload) == 2
        assert payload[0]["id"] == "id1"
        assert payload[0]["status"] == settings.supabase_status_processing


class TestWritebackResults:
    def test_chunks_upserts(self, mock_supabase):
        mock_supabase._table_chain["upsert"].execute.return_value = MagicMock()
        with patch.object(settings, "supabase_upsert_chunk", 2):
            client = SupabaseGeocodeClient(mock_supabase)
            records = [{"id": str(i), "status": "completed"} for i in range(5)]
            successful, failed = client.writeback_results(records)

        assert successful == 3
        assert failed == 0
        assert mock_supabase._table_chain["upsert"].execute.call_count == 3

    def test_empty_records(self, mock_supabase):
        client = SupabaseGeocodeClient(mock_supabase)
        successful, failed = client.writeback_results([])
        assert successful == 0
        assert failed == 0
        mock_supabase._table_chain["upsert"].execute.assert_not_called()

    def test_retries_then_succeeds(self, mock_supabase):
        call_count = 0
        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise APIError({"message": "rate limit"})
            return MagicMock()

        mock_supabase._table_chain["upsert"].execute.side_effect = side_effect
        client = SupabaseGeocodeClient(mock_supabase)
        successful, failed = client.writeback_results([{"id": "1"}])

        assert successful == 1
        assert failed == 0
        assert call_count == 3

    def test_permanent_failure_marks_chunk_failed(self, mock_supabase):
        mock_supabase._table_chain["upsert"].execute.side_effect = APIError({"message": "perm"})
        client = SupabaseGeocodeClient(mock_supabase)
        records = [{"id": "1"}, {"id": "2"}]
        successful, failed = client.writeback_results(records)

        assert successful == 0
        assert failed == 1
        assert mock_supabase.table.return_value.upsert.call_count >= 2
