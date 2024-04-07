# Airflow configuration overrides

The template keeps configuration in environment variables (`AIRFLOW__SECTION__KEY`) instead of
committing a generated `airflow.cfg`. This directory is mounted into local containers and can hold
deployment-specific files such as a logging configuration.

Do not put credentials here. Use `.env` only for local development and a secrets backend or
Kubernetes Secrets in shared environments.

Add a logging configuration or cluster policy here only after adapting and testing it; keep the
default template free of environment-specific Python code.

