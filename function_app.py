"""Azure Functions entry point for the data-acquisition app."""

import logging

import azure.functions as func

from src.common.collection import store_dummy_data


app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 0 */4 * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
@app.retry(strategy="fixed_delay", max_retry_count="3", delay_interval="00:00:10")
def run_dummy_collector(timer: func.TimerRequest) -> None:
    """Run the dummy collector every four hours."""
    if timer.past_due:
        logging.warning("Timer past due")

    logging.info("Starting dummy collection")
    try:
        blob_url = store_dummy_data()
        logging.info("Dummy collection completed: %s", blob_url)
    except Exception:
        logging.exception("Dummy collection failed")
        raise
