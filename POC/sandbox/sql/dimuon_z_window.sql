SELECT
    count(*) AS pair_count,
    avg(invariant_mass) AS avg_mass,
    min(invariant_mass) AS min_mass,
    max(invariant_mass) AS max_mass
FROM dimuon
WHERE invariant_mass BETWEEN 70 AND 110;

