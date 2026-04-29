-- =============================================================
--  Cycle Detection Example
--  These views form a circular dependency: v_a -> v_b -> v_c -> v_a
-- =============================================================

CREATE VIEW v_a AS SELECT id FROM v_b WHERE active = TRUE;
CREATE VIEW v_b AS SELECT id FROM v_c JOIN extra ON v_c.id = extra.ref;
CREATE VIEW v_c AS SELECT id FROM v_a WHERE flag = 0;
CREATE TABLE extra (id SERIAL PRIMARY KEY, ref INTEGER);
