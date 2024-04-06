"""Logical datasets shared by producer and consumer Dags."""

from airflow.datasets import Dataset

EXAMPLE_ORDERS_DATASET = Dataset("template://airflow/orders/daily")
