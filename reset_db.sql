-- reset_db.sql
-- Clears all simulation data for a fresh run.
-- Run this between experiments to avoid stale data contaminating results.
--
-- Usage (from project root):
--   psql -U postgres -d postgres -f reset_db.sql
--
-- Or paste into pgAdmin query tool.

TRUNCATE TABLE sensor_data       RESTART IDENTITY CASCADE;
TRUNCATE TABLE events            RESTART IDENTITY CASCADE;
TRUNCATE TABLE ai_events         RESTART IDENTITY CASCADE;
TRUNCATE TABLE ai_model_metadata RESTART IDENTITY CASCADE;

-- Verify
SELECT 'sensor_data'       AS "table", COUNT(*) AS rows FROM sensor_data
UNION ALL
SELECT 'events',                        COUNT(*) FROM events
UNION ALL
SELECT 'ai_events',                     COUNT(*) FROM ai_events
UNION ALL
SELECT 'ai_model_metadata',             COUNT(*) FROM ai_model_metadata;
