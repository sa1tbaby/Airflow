# Quick runbook

## Health checks

- Webserver: `GET /health` on port 8080.
- Scheduler health server: `GET /health` on port 8974 inside the container or pod.
- Compose: `docker compose ... ps` and `docker compose ... logs --tail 200 SERVICE`.
- Airflow: inspect import errors in the UI or run `airflow dags list-import-errors` inside the
  container or pod.
- Kubernetes: inspect the Helm release, Jobs and pods, scheduler heartbeat, and StatsD/Prometheus
  metrics.

## Upgrading Airflow

1. Read the release notes and provider compatibility information.
2. Update `.python-version`, `requirements*.in`, Docker/Compose, CI, and Helm values.
3. Regenerate `requirements*.txt` and verify that the dependency diff is expected.
4. Build the image and run the full test suite.
5. Test `airflow db migrate` against a copy of the metadata DB and in staging.
6. Run an integration DAG, verify backup and rollback procedures, and then proceed with the
   production rollout.

Never downgrade the metadata DB without a documented recovery plan.

## Rotating secrets

- Update the relevant value in the ignored root `.env`, run `task init`, apply the regenerated
  Kubernetes Secret when applicable, and restart or roll out the affected services.
- Webserver secret key: update it consistently across all webserver replicas; active UI sessions
  will become invalid.
- Fernet key: prepend the new key to the old key, run `airflow rotate-fernet-key`, verify the
  result, and then remove the old key. Use `NEW_KEY,OLD_KEY` without spaces while both keys are
  active; the environment renderer validates every key in the list.
- DB/broker credentials: enable the new credentials on the server first, update the Secret and
  pods, verify the change, and then revoke the old credentials.

Do not replace a value with `GENERATE_ME` unless an intentional rotation is planned. The renderer
generates markers once and preserves every explicit value on later runs.

## Backup and recovery

Back up the metadata DB using the managed database service. Restore DAGs and code from Git and the
image, and restore task logs from remote log storage. Test the complete recovery process regularly.

## Local cleanup

A normal `down` preserves the PostgreSQL volume. Running Compose with `--volumes` permanently
deletes the local metadata DB and should only be done deliberately.
