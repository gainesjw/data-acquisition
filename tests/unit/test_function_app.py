from unittest.mock import Mock, patch

import pytest

import function_app


def test_timer_metadata_has_monitoring_and_bounded_retries():
    metadata = function_app.app.get_functions()[0].get_dict_repr()
    timer = metadata["bindings"][0]
    assert timer["schedule"] == "0 0 */4 * * *"
    assert timer["runOnStartup"] is False
    assert timer["useMonitor"] is True
    retry = function_app.run_dummy_collector.build().get_settings_dict("retry_policy")
    assert retry["max_retry_count"] == "3"
    assert retry["strategy"] == "fixed_delay"
    assert retry["delay_interval"] == "00:00:10"


@patch("function_app.store_dummy_data")
def test_timer_logs_late_and_success(mock_collect, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        function_app.run_dummy_collector.build().get_user_function()(Mock(past_due=True))
    mock_collect.assert_called_once_with()
    assert "Timer past due" in caplog.text
    assert "collection completed" in caplog.text


@patch("function_app.store_dummy_data", side_effect=RuntimeError("failed"))
def test_timer_propagates_failure_for_host_retry(mock_collect, caplog):
    with pytest.raises(RuntimeError, match="failed"):
        function_app.run_dummy_collector.build().get_user_function()(Mock(past_due=False))
    assert "Dummy collection failed" in caplog.text
