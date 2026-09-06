from __future__ import annotations

try:
    from airflow.decorators import dag, task
except ImportError:
    dag = None
    task = None


if dag is not None:
    from src.cli import run_pipeline

    @dag(schedule=None, catchup=False, tags=["colliderlake", "resonance"])
    def resonance_2016():
        @task
        def run_all():
            run_pipeline("run2016h_singlemuon", "all")

        run_all()

    resonance_2016()
