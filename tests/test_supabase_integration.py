"""End-to-end integration test for the Supabase pipeline.

This test exercises the full CLI command ``gnafer supabase-pipeline`` with a
mocked Supabase client and mocked trigram matcher, simulating a realistic
multi-page pull → geocode → writeback flow.
"""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.config import settings

runner = CliRunner()


@pytest.fixture
def mock_supabase_client():
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

    update = MagicMock()
    table.update.return_value = update

    client._table_chain = {
        "table": table,
        "select": select,
        "eq": eq,
        "order": order,
        "range": range_op,
        "upsert": upsert,
        "update": update,
    }
    return client


class TestSupabasePipelineCLI:
    @patch("src.supabase_pipeline.managed_supabase_client")
    @patch("src.supabase_pipeline.TrigramAddressMatcher")
    @patch("src.supabase_pipeline.get_connection_pool")
    @patch("src.supabase_pipeline.load_street_types")
    def test_full_pipeline_via_cli(
        self,
        mock_load_street_types,
        mock_get_pool,
        mock_matcher_cls,
        mock_managed_client,
    ):
        """Run the CLI command end-to-end with mocked external services."""
        mock_client = MagicMock()
        mock_managed_client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_managed_client.return_value.__exit__ = MagicMock(return_value=False)

        # Simulate two pages of pending addresses
        call_count = 0
        def fetch_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    data=[
                        {"id": 1, "input_address": "1 George St, Sydney NSW 2000", "status": "pending"},
                        {"id": 2, "input_address": "2 George St, Sydney NSW 2000", "status": "pending"},
                    ]
                )
            return MagicMock(data=[])

        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.side_effect = fetch_side_effect

        # Mock matcher returning results
        mock_matcher = mock_matcher_cls.return_value
        mock_matcher.match_batch.return_value = [
            MagicMock(
                address_detail_pid="PID1",
                address_label="1 GEORGE STREET, SYDNEY NSW 2000",
                similarity_score=1.0,
                latitude=-33.8599,
                longitude=151.2094,
                flat_number=None,
                level_type=None,
                level_number=None,
                number_first="1",
                number_last=None,
                lot_number=None,
                street_name="GEORGE",
                street_type="STREET",
                street_suffix=None,
                suburb_name="SYDNEY",
                state="NSW",
                postcode="2000",
                mb_code="10095873900",
                llm_verified=False,
                match_method="TRIGRAM",
            ),
            MagicMock(
                address_detail_pid="PID2",
                address_label="2 GEORGE STREET, SYDNEY NSW 2000",
                similarity_score=0.95,
                latitude=-33.8600,
                longitude=151.2095,
                flat_number=None,
                level_type=None,
                level_number=None,
                number_first="2",
                number_last=None,
                lot_number=None,
                street_name="GEORGE",
                street_type="STREET",
                street_suffix=None,
                suburb_name="SYDNEY",
                state="NSW",
                postcode="2000",
                mb_code="10095873901",
                llm_verified=False,
                match_method="TRIGRAM",
            ),
        ]

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        with patch.object(settings, "supabase_url", "https://test.supabase.co"), patch.object(settings, "supabase_key", "test-key"):
            result = runner.invoke(app, ["supabase-pipeline", "--limit", "10"])

        assert result.exit_code == 0
        assert "Pipeline complete" in result.output
        assert "'pulled': 2" in result.output
        assert "'geocoded': 2" in result.output
        assert "'written': 2" in result.output

        # Verify writeback used correct table and default_to_null=False
        upsert_calls = mock_client.table.return_value.upsert.call_args_list
        assert len(upsert_calls) == 1  # 2 rows fit in one chunk of 500
        _, kwargs = upsert_calls[0]
        assert kwargs.get("default_to_null") is False

        # Verify status updates
        update_calls = mock_client.table.return_value.update.call_args_list
        assert len(update_calls) == 2  # processing + done

        # Verify pool was closed
        mock_pool.closeall.assert_called_once()

    @patch("src.supabase_pipeline.managed_supabase_client")
    def test_no_pending_addresses(self, mock_managed_client):
        """CLI should handle empty queue gracefully."""
        mock_client = MagicMock()
        mock_managed_client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_managed_client.return_value.__exit__ = MagicMock(return_value=False)

        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=[])

        with patch.object(settings, "supabase_url", "https://test.supabase.co"), patch.object(settings, "supabase_key", "test-key"):
            result = runner.invoke(app, ["supabase-pipeline"])

        assert result.exit_code == 0
        assert "No pending addresses found" not in result.output  # logged, not printed
        assert "Pipeline complete" in result.output
        assert "'pulled': 0" in result.output

    def test_fails_when_not_configured(self):
        """CLI should exit with error when Supabase is not configured."""
        with patch.object(settings, "supabase_url", ""), patch.object(settings, "supabase_key", ""):
            result = runner.invoke(app, ["supabase-pipeline"])

        assert result.exit_code != 0
        assert result.exception is not None
        assert isinstance(result.exception, ValueError)
