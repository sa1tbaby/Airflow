-- Example idempotent, interval-aware query for a time-scheduled Dag.
-- Replace the source and destination names with objects from your warehouse.
SELECT
    event_id,
    event_timestamp,
    payload
FROM source_schema.events
WHERE event_timestamp >= TIMESTAMP '{{ data_interval_start | ts }}'
  AND event_timestamp < TIMESTAMP '{{ data_interval_end | ts }}';

