"""Unit tests for the shared telemetry helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from argoproxy.utils.telemetry import extract_client_ip, record_telemetry


# ---------------------------------------------------------------------------
# extract_client_ip
# ---------------------------------------------------------------------------


class TestExtractClientIp:
    def test_xff_header(self):
        req = MagicMock()
        req.headers.get.return_value = "1.2.3.4, 5.6.7.8"
        assert extract_client_ip(req) == "1.2.3.4"

    def test_client_addr_fallback(self):
        req = MagicMock()
        req.headers.get.return_value = ""
        req.client_addr = ("10.0.0.1", 12345)
        assert extract_client_ip(req) == "10.0.0.1"

    def test_no_ip(self):
        req = MagicMock()
        req.headers.get.return_value = ""
        del req.client_addr
        assert extract_client_ip(req) is None


# ---------------------------------------------------------------------------
# record_telemetry
# ---------------------------------------------------------------------------


class TestRecordTelemetry:
    def _make_request(self, *, has_metrics=True, has_log=True):
        req = MagicMock()
        req.app.metrics = MagicMock() if has_metrics else None
        req.app.request_log = MagicMock() if has_log else None
        req.headers.get.return_value = ""
        del req.client_addr
        return req

    @patch("argoproxy.utils.telemetry.extract_client_ip", return_value="1.2.3.4")
    def test_records_metrics_and_log(self, _mock_ip):
        req = self._make_request()
        record_telemetry(
            req,
            model="gpt-4o",
            source_provider="openai_chat",
            target_provider="openai_chat",
            provider_name="argo-dev",
            is_stream=False,
            status_code=200,
            duration_ms=42.0,
            error_detail=None,
        )
        req.app.metrics.record_request.assert_called_once()
        req.app.request_log.add.assert_called_once()

    def test_no_metrics_no_crash(self):
        req = self._make_request(has_metrics=False)
        record_telemetry(
            req,
            model="gpt-4o",
            source_provider="openai_chat",
            target_provider="openai_chat",
            provider_name="argo-dev",
            is_stream=False,
            status_code=200,
            duration_ms=42.0,
            error_detail=None,
        )
        req.app.request_log.add.assert_called_once()

    def test_no_request_log_no_crash(self):
        req = self._make_request(has_log=False)
        record_telemetry(
            req,
            model="gpt-4o",
            source_provider="openai_chat",
            target_provider="openai_chat",
            provider_name="argo-dev",
            is_stream=False,
            status_code=200,
            duration_ms=42.0,
            error_detail=None,
        )
        req.app.metrics.record_request.assert_called_once()

    def test_stream_decrements_active_streams(self):
        req = self._make_request()
        req.app.metrics.active_streams = 1
        record_telemetry(
            req,
            model="gpt-4o",
            source_provider="openai_chat",
            target_provider="openai_chat",
            provider_name="argo-dev",
            is_stream=True,
            status_code=200,
            duration_ms=42.0,
            error_detail=None,
        )
        assert req.app.metrics.active_streams == 0

    def test_stream_skips_decrement_when_disabled(self):
        req = self._make_request()
        req.app.metrics.active_streams = 0
        record_telemetry(
            req,
            model="gpt-4o",
            source_provider="openai_chat",
            target_provider="openai_chat",
            provider_name="argo-dev",
            is_stream=True,
            status_code=200,
            duration_ms=42.0,
            error_detail=None,
            decrement_active_streams=False,
        )
        assert req.app.metrics.active_streams == 0
